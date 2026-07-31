"""Hardware-free contracts for the production UDP launcher fire boundary."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from project_cam.closed_loop.fire_control import ArmedShotContext, arm_shot_context
from project_cam.closed_loop.firing_line import FIRING_LINE_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "garage_lab_combined/scripts/launcher_runtime_from_udp.py"
NOW = 1_800_000_000.0


def _load_runtime():
    scripts_dir = str(RUNTIME_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    name = "_launcher_runtime_fire_control_contract"
    spec = importlib.util.spec_from_file_location(name, RUNTIME_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_desktop_session_defaults_are_opt_in_and_path_safe(monkeypatch, tmp_path):
    module = _load_runtime()
    monkeypatch.delenv("PROJECT_CAM_SESSION_ID", raising=False)
    monkeypatch.delenv("PROJECT_CAM_SESSION_DIR", raising=False)
    monkeypatch.delenv("PROJECT_CAM_EVENT_LOG_OUTPUT", raising=False)
    assert module.desktop_session_defaults() == ("", "")

    session_dir = tmp_path / "session"
    monkeypatch.setenv("PROJECT_CAM_SESSION_ID", "desktop-1")
    monkeypatch.setenv("PROJECT_CAM_SESSION_DIR", str(session_dir))
    assert module.desktop_session_defaults() == (
        "desktop-1",
        str(session_dir / "events.jsonl"),
    )

    monkeypatch.setenv(
        "PROJECT_CAM_EVENT_LOG_OUTPUT", str(tmp_path / "explicit.jsonl")
    )
    assert module.desktop_session_defaults() == (
        "desktop-1",
        str(tmp_path / "explicit.jsonl"),
    )


def _joint(x: float, y: float, z: float = 1000.0) -> dict:
    return {
        "x_mm": x,
        "y_mm": y,
        "z_mm": z,
        "conf": 0.9,
        "cams": 3,
        "last_seen_frame": 100,
    }


def _person(track_id: int, *, primary: bool, joints: dict | None = None) -> dict:
    return {
        "track_id": track_id,
        "primary": primary,
        "track_last_seen_frame": 100,
        "joints": joints or {"nose": _joint(4000.0, 0.0)},
    }


def _snapshot(
    *,
    primary_track_id: int = 1,
    primary_epoch: int = 4,
    frame: int = 100,
    timestamp: float = NOW,
) -> dict:
    return {
        "schema": FIRING_LINE_SCHEMA,
        "snapshot_ts": timestamp,
        "frame": frame,
        "geometry_id": "world_mm",
        "y_mirrored": False,
        "mode": "multi_person",
        "primary_track_id": primary_track_id,
        "primary_epoch": primary_epoch,
        "observed_person_count": 1,
        "ambiguous_detections": False,
        "unassigned_candidate_count": 0,
        "people": [_person(primary_track_id, primary=True)],
    }


def _blocked_snapshot() -> dict:
    snapshot = _snapshot()
    snapshot["people"].append(
        _person(
            2,
            primary=False,
            joints={
                "nose": _joint(2000.0, 0.0, 800.0),
                "left_eye": _joint(2000.0, -20.0, 800.0),
                "right_eye": _joint(2000.0, 20.0, 800.0),
            },
        )
    )
    snapshot["observed_person_count"] = 2
    return snapshot


def _context(snapshot: dict | None = None) -> ArmedShotContext:
    context, decision = arm_shot_context(
        snapshot or _snapshot(),
        target_xyz_mm=(4000.0, 0.0, 1000.0),
        pitch_deg=0.0,
        yaw_deg=0.0,
        speed_mps=10.0,
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        extension_mm=0.0,
        now=NOW,
    )
    assert decision.ok and context is not None
    return context


def _armed_state(module, context: ArmedShotContext | None = None):
    state = module.RuntimeFireState()
    state.aim_generation = 7
    state.armed_generation = 7
    state.armed_context = context or _context()
    return state


def test_static_shoot_mode_is_rejected_before_serial_open(monkeypatch):
    module = _load_runtime()
    serial_calls = []

    def forbidden_serial(*args, **kwargs):
        serial_calls.append((args, kwargs))
        raise AssertionError("serial must not open")

    monkeypatch.setattr(module, "serial", SimpleNamespace(Serial=forbidden_serial))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(RUNTIME_PATH),
            "--serial-port", "FAKE",
            "--launcher-yaw-deg", "0",
            "--static-target-x-mm", "1000",
            "--static-target-y-mm", "2000",
            "--static-target-z-mm", "1000",
            "--shoot-enabled",
            "--disable-zone-check",
            "--correction-mode", "none",
        ],
    )

    with pytest.raises(RuntimeError, match=r"(?i)static.*shoot|shoot.*static"):
        module.main()
    assert serial_calls == []


def test_static_aim_only_and_positive_serial_write_timeout_are_valid():
    module = _load_runtime()

    module.validate_runtime_configuration(
        static_mode=True, shoot_enabled=False, serial_write_timeout_sec=0.5
    )
    with pytest.raises(RuntimeError, match="write timeout"):
        module.validate_runtime_configuration(
            static_mode=False, shoot_enabled=False, serial_write_timeout_sec=0.0
        )


def test_safety_packet_missing_or_malformed_clears_and_rejects_in_shoot_mode():
    module = _load_runtime()
    state = module.RuntimeFireState()
    buffers = {"nose": deque([object()])}

    assert module.store_runtime_safety_packet(
        state, {"safety": _snapshot()}, buffers, shoot_enabled=True
    ) is True
    assert state.latest_safety == _snapshot()

    assert module.store_runtime_safety_packet(
        state, {"joints": {}}, buffers, shoot_enabled=True
    ) is False
    assert state.latest_safety is None
    assert list(buffers["nose"]) == []

    buffers["nose"].append(object())
    assert module.store_runtime_safety_packet(
        state, {"safety": "bad"}, buffers, shoot_enabled=True
    ) is False
    assert state.latest_safety is None
    assert list(buffers["nose"]) == []


def test_aim_only_keeps_legacy_joint_packets_without_fabricating_safety():
    module = _load_runtime()
    state = module.RuntimeFireState()
    marker = object()
    buffers = {"nose": deque([marker])}

    assert module.store_runtime_safety_packet(
        state, {"joints": {"nose": {}}}, buffers, shoot_enabled=False
    ) is True
    assert state.latest_safety is None
    assert list(buffers["nose"]) == [marker]


def test_primary_context_change_invalidates_aim_and_clears_target_buffers():
    module = _load_runtime()
    state = _armed_state(module)
    state.latest_safety = _snapshot()
    state.latest_safety_order = (100, NOW)
    state.latest_primary_key = (1, 4, False)
    buffers = {"nose": deque([object()])}

    changed = _snapshot(primary_track_id=2, primary_epoch=5, frame=101, timestamp=NOW + 0.1)
    assert module.store_runtime_safety_packet(
        state, {"safety": changed}, buffers, shoot_enabled=True
    ) is True

    assert state.latest_safety == changed
    assert state.armed_context is None
    assert state.armed_generation is None
    assert state.aim_generation == 8
    assert list(buffers["nose"]) == []


def test_regressive_snapshot_never_replaces_newer_safety():
    module = _load_runtime()
    state = module.RuntimeFireState()
    buffers = {"nose": deque()}
    newest = _snapshot(frame=102, timestamp=NOW + 0.2)
    older = _snapshot(frame=101, timestamp=NOW + 0.1)

    assert module.store_runtime_safety_packet(
        state, {"safety": newest}, buffers, shoot_enabled=True
    ) is True
    assert module.store_runtime_safety_packet(
        state, {"safety": older}, buffers, shoot_enabled=True
    ) is False
    assert state.latest_safety == newest


def test_set_command_quantization_matches_context_and_commit_is_generation_bound():
    module = _load_runtime()
    command, command_v, command_h = module.build_runtime_set_command(
        pitch_deg=1.2349, yaw_deg=-2.3451, wheel_left=800, wheel_right=801
    )
    assert command == "set 1.23 -2.35 800 801"
    assert command_v == 1.23
    assert command_h == -2.35

    context = ArmedShotContext(
        target_xyz_mm=(4000.0, 0.0, 1000.0),
        pitch_deg=command_v,
        yaw_deg=command_h,
        speed_mps=10.0,
        primary_track_id=1,
        primary_epoch=4,
        y_mirrored=False,
        aim_timestamp=NOW,
    )
    state = module.RuntimeFireState()
    commands = []
    module.commit_runtime_aim(
        state, context=context, command=command, send_command=commands.append
    )

    assert commands == [command]
    assert state.armed_context is context
    assert state.armed_generation == state.aim_generation == 1


@pytest.mark.parametrize(
    ("shoot_enabled", "latest", "context_mode", "reason", "commands"),
    [
        (False, _snapshot(), "missing", "shoot_disabled", []),
        (True, _snapshot(), "missing", "aim_context_missing", ["stop"]),
        (True, None, "valid", "clearance_missing", ["stop"]),
        (True, _snapshot(timestamp=NOW - 1.0), "valid", "clearance_stale", ["stop"]),
        (True, _blocked_snapshot(), "valid", "firing_line_blocked", ["stop"]),
        (
            True,
            _snapshot(primary_track_id=2, primary_epoch=5),
            "valid",
            "primary_changed",
            ["stop"],
        ),
    ],
)
def test_runtime_request_fails_closed_for_every_unsafe_manual_or_auto_state(
    shoot_enabled, latest, context_mode, reason, commands
):
    module = _load_runtime()
    state = module.RuntimeFireState()
    if context_mode == "valid":
        state = _armed_state(module)
    sent = []

    outcome = module.request_runtime_shoot(
        state,
        sent.append,
        shoot_enabled=shoot_enabled,
        latest_snapshot=latest,
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        source="test",
        extension_mm=0.0,
        now=NOW,
    )

    assert sent == commands
    assert outcome["reason"] == reason
    assert outcome["serial_shoot_sent"] is False
    assert state.armed_context is None
    assert state.armed_generation is None
    json.dumps(outcome)


def test_clear_context_sends_exactly_one_shoot_and_consumes_authorization():
    module = _load_runtime()
    state = _armed_state(module)
    sent = []

    outcome = module.request_runtime_shoot(
        state,
        sent.append,
        shoot_enabled=True,
        latest_snapshot=_snapshot(),
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        source="auto",
        extension_mm=0.0,
        now=NOW,
    )

    assert sent == ["shoot"]
    assert outcome["serial_shoot_sent"] is True
    assert state.armed_context is None
    assert state.aim_generation == 8

    second = module.request_runtime_shoot(
        state,
        sent.append,
        shoot_enabled=True,
        latest_snapshot=_snapshot(),
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        source="auto",
        extension_mm=0.0,
        now=NOW,
    )
    assert sent == ["shoot", "stop"]
    assert second["reason"] == "aim_context_missing"


def test_final_sender_rechecks_generation_after_clearance_evaluation(monkeypatch):
    module = _load_runtime()
    state = _armed_state(module)
    serial_commands = []

    def delayed_request(send_command, **kwargs):
        module.invalidate_runtime_aim(state)
        outcome = {
            "serial_shoot_sent": False,
            "reason": "shoot_command_failed",
            "message": "serial shoot command failed",
        }
        try:
            send_command("shoot")
        except RuntimeError:
            send_command("stop")
        return outcome

    monkeypatch.setattr(module, "request_shoot", delayed_request)
    outcome = module.request_runtime_shoot(
        state,
        serial_commands.append,
        shoot_enabled=True,
        latest_snapshot=_snapshot(),
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        source="race-test",
        now=NOW,
    )

    assert serial_commands == ["stop"]
    assert outcome["serial_shoot_sent"] is False


def test_fire_outcome_audit_is_json_safe_and_truthful():
    module = _load_runtime()

    class FakeEventLogger:
        def __init__(self):
            self.events = []

        def emit(self, event_type, payload):
            self.events.append((event_type, payload))

    records = []
    logger = FakeEventLogger()
    blocked = {
        "source": "manual",
        "reason": "primary_changed",
        "message": "primary changed",
        "serial_shoot_sent": False,
        "decision": {"ok": False},
    }
    module.audit_runtime_fire_outcome(
        blocked,
        joint_name="nose",
        log_decision=lambda **kwargs: records.append(kwargs),
        event_logger=logger,
    )
    successful = dict(blocked, reason=None, message=None, serial_shoot_sent=True)
    module.audit_runtime_fire_outcome(
        successful,
        joint_name="nose",
        log_decision=lambda **kwargs: records.append(kwargs),
        event_logger=logger,
    )

    assert records[0]["decision"] == "FIRE_BLOCKED"
    assert records[0]["extra"]["fire_outcome"] == blocked
    assert records[1]["decision"] == "FIRE_SENT"
    assert [event for event, _ in logger.events] == [
        "safety_gate_blocked",
        "ball_launched",
    ]
    json.dumps(records)
    json.dumps(logger.events)


def test_runtime_source_has_one_interlock_and_no_direct_literal_shoot_bypass():
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    direct = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "send_cmd"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "shoot"
    ]
    assert direct == []
    assert "arm_shot_context(" in source
    assert "request_runtime_shoot(" in source
    assert source.count("request_and_audit_fire(") >= 3  # definition + manual + auto


def test_runtime_refreshes_udp_safety_during_rpm_wait_and_before_auto_fire():
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    rpm_region = source[source.index("if args.shoot_enabled:", source.index("# 2) Wait telemetry")):
                        source.index("hold_sec =", source.index("# 2) Wait telemetry"))]
    auto_fire_region = source[source.index("# 3) Shoot or aim-only"):
                              source.index("# 4) Return to zero")]

    assert "ingest_targets_once()" in rpm_region
    assert "request_and_audit_fire(" in auto_fire_region
