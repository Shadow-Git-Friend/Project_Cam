"""Fire-control boundary and launcher-script contract tests.

These tests never construct a real UDP socket or serial connection.  The
shared helpers receive a command callback, and listener packet storage is
exercised on unstarted instances.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import threading
import time
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import project_cam.closed_loop.fire_control as fire_control_module
from project_cam.closed_loop.fire_control import (
    ArmedShotContext,
    arm_shot_context,
    request_shoot,
)
from project_cam.closed_loop.firing_line import FIRING_LINE_SCHEMA

NOW = 1_800_000_000.0
ROOT = Path(__file__).resolve().parents[1]
LIVE_AIM_PATH = ROOT / "garage_lab_combined/scripts/live_aim_test.py"
FOLLOW_PATH = ROOT / "garage_lab_combined/scripts/blm_follow.py"


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
        "joints": joints or {"nose": _joint(4000.0, 0.0, 1000.0)},
    }


def _snapshot(*, primary_track_id: int = 1, primary_epoch: int = 4) -> dict:
    primary = _person(primary_track_id, primary=True)
    return {
        "schema": FIRING_LINE_SCHEMA,
        "snapshot_ts": NOW,
        "frame": 100,
        "geometry_id": "world_mm",
        "y_mirrored": False,
        "mode": "multi_person",
        "primary_track_id": primary_track_id,
        "primary_epoch": primary_epoch,
        "observed_person_count": 1,
        "ambiguous_detections": False,
        "unassigned_candidate_count": 0,
        "people": [primary],
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


def _arm(snapshot: dict | None, *, now: float = NOW):
    return arm_shot_context(
        snapshot,
        target_xyz_mm=(4000.0, 0.0, 1000.0),
        pitch_deg=0.0,
        yaw_deg=0.0,
        speed_mps=10.0,
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        extension_mm=0.0,
        now=now,
    )


def _request(commands: list[str], snapshot, context, **overrides):
    kwargs = {
        "shoot_enabled": True,
        "latest_snapshot": snapshot,
        "armed_context": context,
        "launcher_xyz_mm": (0.0, 0.0, 1000.0),
        "launcher_yaw_deg": 0.0,
        "source": "test",
        "extension_mm": 0.0,
        "now": NOW,
    }
    kwargs.update(overrides)
    return request_shoot(commands.append, **kwargs)


def test_arm_captures_only_a_clear_actual_aim_in_an_immutable_context():
    context, decision = _arm(_snapshot())

    assert decision.ok is True
    assert isinstance(context, ArmedShotContext)
    assert context.target_xyz_mm == (4000.0, 0.0, 1000.0)
    assert context.primary_track_id == 1
    assert context.primary_epoch == 4
    assert context.y_mirrored is False
    assert context.aim_timestamp == NOW
    with pytest.raises(FrozenInstanceError):
        context.pitch_deg = 10.0
    json.dumps(context.to_dict())


@pytest.mark.parametrize(
    ("snapshot", "now", "reason"),
    [
        (None, NOW, "clearance_missing"),
        (_snapshot(), NOW + 1.0, "clearance_stale"),
        (_blocked_snapshot(), NOW, "firing_line_blocked"),
    ],
)
def test_arm_fails_closed_without_returning_a_context(snapshot, now, reason):
    context, decision = _arm(snapshot, now=now)

    assert context is None
    assert decision.ok is False
    assert decision.reason == reason


def test_request_shoot_rechecks_and_sends_exactly_one_shoot_when_clear():
    snapshot = _snapshot()
    context, _ = _arm(snapshot)
    commands: list[str] = []

    outcome = _request(commands, snapshot, context)

    assert commands == ["shoot"]
    assert outcome["serial_shoot_sent"] is True
    assert outcome["reason"] is None
    json.dumps(outcome)


@pytest.mark.parametrize(
    ("latest_snapshot", "context_mode", "overrides", "reason"),
    [
        (None, "valid", {}, "clearance_missing"),
        (_snapshot(), "missing", {}, "aim_context_missing"),
        (_blocked_snapshot(), "valid", {}, "firing_line_blocked"),
        (_snapshot(primary_track_id=2, primary_epoch=5), "valid", {}, "primary_changed"),
        (_snapshot(), "valid", {"shoot_enabled": False}, "shoot_disabled"),
    ],
)
def test_blocked_requests_never_shoot_and_stop_any_possibly_armed_launcher(
    latest_snapshot, context_mode, overrides, reason
):
    context, _ = _arm(_snapshot())
    if context_mode == "missing":
        context = None
    commands: list[str] = []

    outcome = _request(commands, latest_snapshot, context, **overrides)

    assert "shoot" not in commands
    assert commands == ["stop"]
    assert outcome["serial_shoot_sent"] is False
    assert outcome["reason"] == reason
    assert outcome["source"] == "test"
    json.dumps(outcome)


def test_stop_is_best_effort_and_a_failure_cannot_turn_a_block_into_a_shot():
    context, _ = _arm(_snapshot())
    commands: list[str] = []

    def failing_send(command: str) -> None:
        commands.append(command)
        raise OSError("serial unavailable")

    outcome = request_shoot(
        failing_send,
        shoot_enabled=True,
        latest_snapshot=None,
        armed_context=context,
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        source="test",
        now=NOW,
    )

    assert commands == ["stop"]
    assert outcome["serial_shoot_sent"] is False
    assert outcome["stop_command_sent"] is False
    assert "OSError" in outcome["stop_error"]
    json.dumps(outcome)


def _load_script(path: Path):
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    name = f"_fire_control_contract_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unstarted_listener(module):
    listener = module.UDPJointListener.__new__(module.UDPJointListener)
    listener.lock = threading.Lock()
    listener.joints = {}
    listener.latest_safety = None
    listener.last_packet_ts = 0.0
    listener.packet_count = 0
    return listener


def _armed_follow_handler(module, monkeypatch):
    """Build an actual follow handler whose first shot stays in flight."""
    snapshot = _snapshot()
    snapshot["snapshot_ts"] = time.time()
    armed_context, decision = arm_shot_context(
        snapshot,
        target_xyz_mm=(4000.0, 0.0, 1000.0),
        pitch_deg=0.0,
        yaw_deg=0.0,
        speed_mps=10.0,
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        extension_mm=0.0,
        now=snapshot["snapshot_ts"],
    )
    assert decision.ok and armed_context is not None

    class CoordinatedSerial:
        def __init__(self):
            self.commands: list[str] = []
            self.first_shoot_written = threading.Event()
            self.reload_written = threading.Event()
            self.second_command_written = threading.Event()
            self._lock = threading.Lock()

        def write(self, payload: bytes) -> None:
            command = payload.decode().strip()
            with self._lock:
                self.commands.append(command)
                if command == "shoot":
                    self.first_shoot_written.set()
                if command == "reload":
                    self.reload_written.set()
                if len(self.commands) >= 2:
                    self.second_command_written.set()

    class GatedReader:
        def __init__(self):
            self.finish_actions = threading.Event()

        @property
        def last_state_msg(self) -> str:
            if self.finish_actions.is_set():
                return "SHOT FIRED RELOAD DONE"
            return ""

        @last_state_msg.setter
        def last_state_msg(self, _value: str) -> None:
            pass

    state = {
        "busy": False,
        "armed": True,
        "target": "nose",
        "paused": False,
        "quit": False,
        "aim_generation": 0,
        "last_v": 0.0,
        "last_h": 0.0,
        "armed_context": armed_context,
    }
    fake_serial = CoordinatedSerial()
    fake_reader = GatedReader()
    monkeypatch.setattr(module, "safe_print", lambda _message: None)
    handler = module.CommandHandler(
        state,
        threading.Lock(),
        fake_serial,
        fake_reader,
        True,
        lambda: snapshot,
        (0.0, 0.0, 1000.0),
        0.0,
    )
    return handler, state, fake_serial, fake_reader, armed_context


class _FastForwardClock:
    """Advance handler status deadlines without real sleeping."""

    def __init__(self):
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration


@pytest.mark.parametrize("path", [LIVE_AIM_PATH, FOLLOW_PATH])
def test_listener_atomically_stores_and_returns_the_latest_safety_object(path):
    module = _load_script(path)
    listener = _unstarted_listener(module)
    safety = _snapshot()

    listener._store_packet(
        {"joints": {"nose": {"x_mm": 1, "y_mm": 2, "z_mm": 3}}, "safety": safety},
        received_at=NOW,
    )

    assert listener.get_safety_snapshot() == safety
    assert listener.get_joint("nose")["ts"] == NOW
    listener._store_packet({"joints": {}}, received_at=NOW + 0.1)
    assert listener.get_safety_snapshot() is None


@pytest.mark.parametrize("path", [LIVE_AIM_PATH, FOLLOW_PATH])
def test_scripts_route_arming_and_firing_through_the_shared_boundary(path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    direct_shoot_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "send_serial"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "shoot"
    ]
    assert direct_shoot_calls == []
    assert "arm_shot_context(" in source
    assert "request_shoot(" in source
    assert "armed_context" in source
    assert "get_safety_snapshot" in source


@pytest.mark.parametrize("path", [LIVE_AIM_PATH, FOLLOW_PATH])
def test_script_serial_connections_have_a_bounded_write_timeout(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    serial_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "serial"
        and node.func.attr == "Serial"
    ]

    assert serial_calls
    for call in serial_calls:
        keyword = next(
            (item for item in call.keywords if item.arg == "write_timeout"),
            None,
        )
        assert keyword is not None
        assert isinstance(keyword.value, ast.Constant)
        assert 0.0 < float(keyword.value.value) <= 1.0


def test_follow_reload_clears_context_and_do_shoot_uses_request_helper():
    source = FOLLOW_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    command_handler = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CommandHandler"
    )
    methods = {node.name: ast.get_source_segment(source, node) for node in command_handler.body if isinstance(node, ast.FunctionDef)}

    assert 'self.state["armed_context"] = None' in methods["_do_reload"]
    assert "request_shoot(" in methods["_do_shoot"]
    assert 'send_serial(self.ser, "shoot")' not in methods["_do_shoot"]


def test_follow_final_aim_commit_rejects_a_candidate_after_shoot_marks_busy():
    module = _load_script(FOLLOW_PATH)
    old_context, _ = _arm(_snapshot())
    new_context = ArmedShotContext(
        target_xyz_mm=(4100.0, 0.0, 1000.0),
        pitch_deg=1.2,
        yaw_deg=2.3,
        speed_mps=10.0,
        primary_track_id=1,
        primary_epoch=4,
        y_mirrored=False,
        aim_timestamp=NOW + 0.1,
    )
    state = {
        "busy": False,
        "armed": True,
        "target": "nose",
        "aim_generation": 7,
        "last_v": 0.0,
        "last_h": 0.0,
        "armed_context": old_context,
    }
    state_lock = threading.Lock()

    # Deterministically model _do_shoot winning the state lock after the aim
    # calculation but before its serial-set commit.
    with state_lock:
        state["busy"] = True
        captured_for_shot = state["armed_context"]
    commands: list[str] = []
    committed = module.commit_aim_command(
        state,
        state_lock,
        expected_target="nose",
        expected_generation=7,
        command="set 1.2 2.3 800 800",
        command_v=1.2,
        command_h=2.3,
        armed_context=new_context,
        send_command=commands.append,
    )

    assert captured_for_shot is old_context
    assert committed is False
    assert commands == []
    assert state["armed_context"] is old_context

    state["busy"] = False
    state["aim_generation"] = 8
    assert module.commit_aim_command(
        state,
        state_lock,
        expected_target="nose",
        expected_generation=7,
        command="set 1.2 2.3 800 800",
        command_v=1.2,
        command_h=2.3,
        armed_context=new_context,
        send_command=commands.append,
    ) is False
    state["aim_generation"] = 7
    state["target"] = "right_shoulder"
    assert module.commit_aim_command(
        state,
        state_lock,
        expected_target="nose",
        expected_generation=7,
        command="set 1.2 2.3 800 800",
        command_v=1.2,
        command_h=2.3,
        armed_context=new_context,
        send_command=commands.append,
    ) is False
    state["target"] = "nose"
    state["armed"] = False
    assert module.commit_aim_command(
        state,
        state_lock,
        expected_target="nose",
        expected_generation=7,
        command="set 1.2 2.3 800 800",
        command_v=1.2,
        command_h=2.3,
        armed_context=new_context,
        send_command=commands.append,
    ) is False

    state["armed"] = True
    assert module.commit_aim_command(
        state,
        state_lock,
        expected_target="nose",
        expected_generation=7,
        command="set 1.2 2.3 800 800",
        command_v=1.2,
        command_h=2.3,
        armed_context=new_context,
        send_command=commands.append,
    ) is True
    assert commands == ["set 1.2 2.3 800 800"]
    assert state["last_v"] == 1.2
    assert state["last_h"] == 2.3
    assert state["armed_context"] is new_context


def test_follow_unarmed_shoot_still_routes_enabled_request_and_sends_stop(monkeypatch):
    module = _load_script(FOLLOW_PATH)

    class FakeSerial:
        def __init__(self):
            self.commands: list[str] = []

        def write(self, payload: bytes) -> None:
            self.commands.append(payload.decode().strip())

    class FakeReader:
        last_state_msg = ""

    state = {
        "busy": False,
        "armed": False,
        "target": "nose",
        "aim_generation": 0,
        "last_v": None,
        "last_h": None,
        "armed_context": None,
    }
    fake_serial = FakeSerial()
    monkeypatch.setattr(module, "safe_print", lambda _message: None)
    handler = module.CommandHandler(
        state,
        threading.Lock(),
        fake_serial,
        FakeReader(),
        True,
        lambda: _snapshot(),
        (0.0, 0.0, 1000.0),
        0.0,
    )

    handler._do_shoot()

    assert fake_serial.commands == ["stop"]
    assert state["armed"] is False
    assert state["armed_context"] is None


def test_follow_busy_duplicate_cannot_shoot_same_armed_context_twice(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, armed_context = _armed_follow_handler(
        module, monkeypatch
    )
    handler.auto_reload = True
    errors: list[BaseException] = []

    def run_shoot() -> None:
        try:
            handler._do_shoot()
        except BaseException as exc:
            errors.append(exc)

    first_shoot = threading.Thread(target=run_shoot)
    first_shoot.start()
    assert fake_serial.first_shoot_written.wait(timeout=2.0)
    assert state["busy"] is True
    assert state["armed_context"] is armed_context

    duplicate_shoot = threading.Thread(target=run_shoot)
    duplicate_shoot.start()
    assert fake_serial.second_command_written.wait(timeout=2.0)
    fake_reader.finish_actions.set()
    first_shoot.join(timeout=3.0)
    duplicate_shoot.join(timeout=3.0)

    assert not first_shoot.is_alive()
    assert not duplicate_shoot.is_alive()
    assert errors == []
    assert fake_serial.commands.count("shoot") == 1
    assert "stop" in fake_serial.commands
    assert "reload" not in fake_serial.commands
    assert state["armed_context"] is None


def test_follow_auto_reload_handoff_rechecks_generation_after_pause(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, _ = _armed_follow_handler(
        module, monkeypatch
    )
    handler.auto_reload = True
    fake_reader.finish_actions.set()
    messages: list[str] = []

    def invalidate_at_auto_reload_handoff(message: str) -> None:
        messages.append(message)
        if message == "  [SHOT COMPLETE] auto-reloading...":
            handler.handle("pause")

    monkeypatch.setattr(module, "safe_print", invalidate_at_auto_reload_handoff)

    handler._do_shoot()

    assert "  [SHOT COMPLETE] auto-reloading..." in messages
    assert fake_serial.commands.count("shoot") == 1
    assert "reload" not in fake_serial.commands
    assert "stop" in fake_serial.commands
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None


def test_follow_reload_is_rejected_with_stop_while_shot_is_busy(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, _ = _armed_follow_handler(
        module, monkeypatch
    )
    errors: list[BaseException] = []

    def run(action) -> None:
        try:
            action()
        except BaseException as exc:
            errors.append(exc)

    shoot_thread = threading.Thread(target=run, args=(handler._do_shoot,))
    shoot_thread.start()
    assert fake_serial.first_shoot_written.wait(timeout=2.0)
    assert state["busy"] is True

    reload_thread = threading.Thread(target=run, args=(handler._do_reload,))
    reload_thread.start()
    assert fake_serial.second_command_written.wait(timeout=2.0)
    fake_reader.finish_actions.set()
    shoot_thread.join(timeout=3.0)
    reload_thread.join(timeout=3.0)

    assert not shoot_thread.is_alive()
    assert not reload_thread.is_alive()
    assert errors == []
    assert "reload" not in fake_serial.commands
    assert "stop" in fake_serial.commands
    assert state["armed_context"] is None


def test_follow_voice_stop_physically_stops_an_active_reload(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, _ = _armed_follow_handler(
        module, monkeypatch
    )
    errors: list[BaseException] = []

    def run_reload() -> None:
        try:
            handler._do_reload()
        except BaseException as exc:
            errors.append(exc)

    reload_thread = threading.Thread(target=run_reload)
    reload_thread.start()
    assert fake_serial.reload_written.wait(timeout=2.0)
    assert state["busy"] is True
    assert state["armed_context"] is None

    handler.handle("stop")

    commands_after_stop = list(fake_serial.commands)
    fake_reader.finish_actions.set()
    reload_thread.join(timeout=3.0)
    assert not reload_thread.is_alive()
    assert errors == []
    assert commands_after_stop == ["reload", "stop"]
    assert state["busy"] is False
    assert state["armed"] is False


@pytest.mark.parametrize("command", ["pause", "right_shoulder", "quit", "__quit__"])
def test_follow_every_operator_invalidation_stops_an_active_reload(
    monkeypatch, command
):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, _ = _armed_follow_handler(
        module, monkeypatch
    )
    errors: list[BaseException] = []

    def run_reload() -> None:
        try:
            handler._do_reload()
        except BaseException as exc:
            errors.append(exc)

    reload_thread = threading.Thread(target=run_reload)
    reload_thread.start()
    assert fake_serial.reload_written.wait(timeout=2.0)

    handler.handle(command)

    commands_after_invalidation = list(fake_serial.commands)
    fake_reader.finish_actions.set()
    reload_thread.join(timeout=3.0)
    assert not reload_thread.is_alive()
    assert errors == []
    assert commands_after_invalidation == ["reload", "stop"]
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None


def test_operator_stop_is_serialized_before_a_fresh_aim_commit():
    module = _load_script(FOLLOW_PATH)
    old_context, _ = _arm(_snapshot())
    new_context = ArmedShotContext(
        target_xyz_mm=(4100.0, 0.0, 1000.0),
        pitch_deg=1.2,
        yaw_deg=2.3,
        speed_mps=10.0,
        primary_track_id=1,
        primary_epoch=4,
        y_mirrored=False,
        aim_timestamp=NOW + 0.1,
    )
    allow_stop = threading.Event()
    stop_started = threading.Event()
    trace: list[str] = []
    errors: list[BaseException] = []

    class CoordinatedLock:
        def __init__(self):
            self._lock = threading.Lock()

        def __enter__(self):
            if threading.current_thread().name == "fresh-aim" and self._lock.locked():
                # With correct serialization, the commit releases the blocked
                # stop only after observing that invalidation still owns state.
                allow_stop.set()
            self._lock.acquire()
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            self._lock.release()

    state_lock = CoordinatedLock()
    state = {
        "busy": False,
        "armed": True,
        "quit": False,
        "target": "nose",
        "aim_generation": 7,
        "last_v": 0.0,
        "last_h": 0.0,
        "armed_context": old_context,
    }

    def blocking_stop(command: str) -> None:
        assert command == "stop"
        stop_started.set()
        assert allow_stop.wait(timeout=2.0)
        trace.append(command)

    def send_fresh_aim(command: str) -> None:
        trace.append(command)
        allow_stop.set()

    def run_invalidation() -> None:
        try:
            module.invalidate_operator_command(
                state,
                state_lock,
                updates={"target": "right_shoulder"},
                shoot_enabled=True,
                send_command=blocking_stop,
            )
        except BaseException as exc:
            errors.append(exc)

    committed: list[bool] = []

    def run_commit() -> None:
        try:
            committed.append(
                module.commit_aim_command(
                    state,
                    state_lock,
                    expected_target="right_shoulder",
                    expected_generation=8,
                    command="set 1.2 2.3 800 800",
                    command_v=1.2,
                    command_h=2.3,
                    armed_context=new_context,
                    send_command=send_fresh_aim,
                )
            )
        except BaseException as exc:
            errors.append(exc)

    invalidation_thread = threading.Thread(target=run_invalidation)
    invalidation_thread.start()
    assert stop_started.wait(timeout=2.0)
    commit_thread = threading.Thread(target=run_commit, name="fresh-aim")
    commit_thread.start()
    invalidation_thread.join(timeout=3.0)
    commit_thread.join(timeout=3.0)

    assert not invalidation_thread.is_alive()
    assert not commit_thread.is_alive()
    assert errors == []
    assert committed == [True]
    assert trace == ["stop", "set 1.2 2.3 800 800"]
    assert state["armed_context"] is new_context


@pytest.mark.parametrize("command", ["quit", "__quit__"])
def test_follow_quit_variants_physically_stop_an_active_shot(monkeypatch, command):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, _ = _armed_follow_handler(
        module, monkeypatch
    )
    errors: list[BaseException] = []

    def run_shoot() -> None:
        try:
            handler._do_shoot()
        except BaseException as exc:
            errors.append(exc)

    shoot_thread = threading.Thread(target=run_shoot)
    shoot_thread.start()
    assert fake_serial.first_shoot_written.wait(timeout=2.0)

    handler.handle(command)

    commands_after_quit = list(fake_serial.commands)
    fake_reader.finish_actions.set()
    shoot_thread.join(timeout=3.0)
    assert not shoot_thread.is_alive()
    assert errors == []
    assert commands_after_quit == ["shoot", "stop"]
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None


@pytest.mark.parametrize("quit_command", ["quit", "__quit__"])
def test_follow_quit_latch_rejects_a_queued_reload(monkeypatch, quit_command):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, _ = _armed_follow_handler(
        module, monkeypatch
    )
    state["armed"] = False
    state["armed_context"] = None
    state["last_v"] = None
    state["last_h"] = None
    fake_reader.finish_actions.set()

    handler.handle(quit_command)
    handler.handle("reload")

    assert state["quit"] is True
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None
    assert "reload" not in fake_serial.commands
    assert fake_serial.commands == ["stop"]


def test_follow_reload_completion_cannot_rearm_after_busy_conflict(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, _ = _armed_follow_handler(
        module, monkeypatch
    )
    errors: list[BaseException] = []

    def run(action) -> None:
        try:
            action()
        except BaseException as exc:
            errors.append(exc)

    reload_thread = threading.Thread(target=run, args=(handler._do_reload,))
    reload_thread.start()
    assert fake_serial.reload_written.wait(timeout=2.0)
    reload_generation = state["aim_generation"]
    assert state["busy"] is True

    conflicting_shoot = threading.Thread(target=run, args=(handler._do_shoot,))
    conflicting_shoot.start()
    assert fake_serial.second_command_written.wait(timeout=2.0)
    conflicting_shoot.join(timeout=2.0)
    assert not conflicting_shoot.is_alive()
    assert state["aim_generation"] > reload_generation

    fake_reader.finish_actions.set()
    reload_thread.join(timeout=3.0)

    assert not reload_thread.is_alive()
    assert errors == []
    assert fake_serial.commands == ["reload", "stop"]
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None


def test_follow_invalidated_reload_claim_cannot_emit_reload_after_stop(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, fake_reader, _ = _armed_follow_handler(
        module, monkeypatch
    )
    reload_claimed = threading.Event()
    allow_reload_send = threading.Event()
    errors: list[BaseException] = []

    def block_after_reload_claim(message: str) -> None:
        if message.startswith("  Reloading:"):
            reload_claimed.set()
            assert allow_reload_send.wait(timeout=2.0)

    monkeypatch.setattr(module, "safe_print", block_after_reload_claim)

    def run(action) -> None:
        try:
            action()
        except BaseException as exc:
            errors.append(exc)

    reload_thread = threading.Thread(target=run, args=(handler._do_reload,))
    reload_thread.start()
    assert reload_claimed.wait(timeout=2.0)
    assert state["busy"] is True
    reload_generation = state["aim_generation"]

    conflicting_shoot = threading.Thread(target=run, args=(handler._do_shoot,))
    conflicting_shoot.start()
    conflicting_shoot.join(timeout=2.0)
    assert not conflicting_shoot.is_alive()
    assert state["aim_generation"] > reload_generation
    assert fake_serial.commands == ["stop"]

    fake_reader.finish_actions.set()
    allow_reload_send.set()
    reload_thread.join(timeout=3.0)

    assert not reload_thread.is_alive()
    assert errors == []
    assert fake_serial.commands
    assert set(fake_serial.commands) == {"stop"}
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None


def test_follow_reload_status_timeout_stops_and_stays_disarmed(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, _, _ = _armed_follow_handler(module, monkeypatch)
    messages: list[str] = []
    monkeypatch.setattr(module, "safe_print", messages.append)
    monkeypatch.setattr(module, "time", _FastForwardClock())
    initial_generation = state["aim_generation"]

    handler._do_reload()

    assert fake_serial.commands == ["reload", "stop"]
    assert state["aim_generation"] >= initial_generation + 2
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None
    assert any("timeout" in message.lower() for message in messages)
    assert not any("RELOAD COMPLETE" in message for message in messages)


def test_follow_shot_status_timeout_stops_without_auto_reload(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, fake_serial, _, _ = _armed_follow_handler(module, monkeypatch)
    handler.auto_reload = True
    messages: list[str] = []
    monkeypatch.setattr(module, "safe_print", messages.append)
    monkeypatch.setattr(module, "time", _FastForwardClock())
    initial_generation = state["aim_generation"]

    handler._do_shoot()

    assert fake_serial.commands.count("shoot") == 1
    assert "stop" in fake_serial.commands
    assert "reload" not in fake_serial.commands
    assert state["aim_generation"] >= initial_generation + 2
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None
    assert any("timeout" in message.lower() for message in messages)
    assert not any("SHOT COMPLETE" in message for message in messages)


def test_follow_preserves_fast_shot_ack_published_during_serial_write(monkeypatch):
    module = _load_script(FOLLOW_PATH)
    handler, state, _, _, _ = _armed_follow_handler(module, monkeypatch)
    messages: list[str] = []

    class AckReader:
        last_state_msg = "stale prior status"

    class AckSerial:
        def __init__(self, reader):
            self.reader = reader
            self.commands: list[str] = []

        def write(self, payload: bytes) -> None:
            command = payload.decode().strip()
            self.commands.append(command)
            if command == "shoot":
                self.reader.last_state_msg = "SHOT FIRED"

    ack_reader = AckReader()
    ack_serial = AckSerial(ack_reader)
    handler.serial_reader = ack_reader
    handler.ser = ack_serial
    monkeypatch.setattr(module, "safe_print", messages.append)
    monkeypatch.setattr(module, "time", _FastForwardClock())

    handler._do_shoot()

    assert ack_serial.commands == ["shoot"]
    assert state["busy"] is False
    assert state["armed"] is False
    assert state["armed_context"] is None
    assert any("SHOT COMPLETE" in message for message in messages)
    assert not any("timeout" in message.lower() for message in messages)


def test_follow_invalidated_during_clearance_cannot_reach_final_shoot_callback(
    monkeypatch,
):
    module = _load_script(FOLLOW_PATH)
    snapshot = _snapshot()
    snapshot["snapshot_ts"] = time.time()
    armed_context, decision = arm_shot_context(
        snapshot,
        target_xyz_mm=(4000.0, 0.0, 1000.0),
        pitch_deg=0.0,
        yaw_deg=0.0,
        speed_mps=10.0,
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        extension_mm=0.0,
        now=snapshot["snapshot_ts"],
    )
    assert decision.ok and armed_context is not None

    class FakeSerial:
        def __init__(self):
            self.commands: list[str] = []

        def write(self, payload: bytes) -> None:
            self.commands.append(payload.decode().strip())

    class FakeReader:
        @property
        def last_state_msg(self) -> str:
            return "SHOT FIRED"

        @last_state_msg.setter
        def last_state_msg(self, _value: str) -> None:
            pass

    state = {
        "busy": False,
        "armed": True,
        "target": "nose",
        "paused": False,
        "quit": False,
        "aim_generation": 0,
        "last_v": 0.0,
        "last_h": 0.0,
        "armed_context": armed_context,
    }
    state_lock = threading.Lock()
    fake_serial = FakeSerial()
    handler = module.CommandHandler(
        state,
        state_lock,
        fake_serial,
        FakeReader(),
        True,
        lambda: snapshot,
        (0.0, 0.0, 1000.0),
        0.0,
    )
    monkeypatch.setattr(module, "safe_print", lambda _message: None)

    evaluation_started = threading.Event()
    allow_evaluation_to_finish = threading.Event()
    original_evaluate = fire_control_module.evaluate_shot_clearance

    def blocking_evaluate(*args, **kwargs):
        evaluation_started.set()
        assert allow_evaluation_to_finish.wait(timeout=2.0)
        return original_evaluate(*args, **kwargs)

    monkeypatch.setattr(
        fire_control_module,
        "evaluate_shot_clearance",
        blocking_evaluate,
    )
    errors: list[BaseException] = []

    def run_shoot() -> None:
        try:
            handler._do_shoot()
        except BaseException as exc:  # surfaced below on the test thread
            errors.append(exc)

    shoot_thread = threading.Thread(target=run_shoot)
    shoot_thread.start()
    assert evaluation_started.wait(timeout=2.0)

    # Voice/editor command invalidates the context while request_shoot is
    # evaluating.  The final callback must notice the generation/context change.
    handler.handle("right_shoulder")
    allow_evaluation_to_finish.set()
    shoot_thread.join(timeout=2.0)

    assert not shoot_thread.is_alive()
    assert errors == []
    assert "shoot" not in fake_serial.commands
    assert "stop" in fake_serial.commands


def test_follow_loop_invalidation_publishes_state_before_stop_and_pending_shoot(
    monkeypatch,
):
    module = _load_script(FOLLOW_PATH)
    snapshot = _snapshot()
    snapshot["snapshot_ts"] = time.time()
    armed_context, decision = arm_shot_context(
        snapshot,
        target_xyz_mm=(4000.0, 0.0, 1000.0),
        pitch_deg=0.0,
        yaw_deg=0.0,
        speed_mps=10.0,
        launcher_xyz_mm=(0.0, 0.0, 1000.0),
        launcher_yaw_deg=0.0,
        extension_mm=0.0,
        now=snapshot["snapshot_ts"],
    )
    assert decision.ok and armed_context is not None

    class FakeSerial:
        def __init__(self):
            self.commands: list[str] = []

        def write(self, payload: bytes) -> None:
            self.commands.append(payload.decode().strip())

    class FakeReader:
        @property
        def last_state_msg(self) -> str:
            return "SHOT FIRED"

        @last_state_msg.setter
        def last_state_msg(self, _value: str) -> None:
            pass

    state = {
        "busy": False,
        "armed": True,
        "target": "nose",
        "paused": False,
        "quit": False,
        "aim_generation": 0,
        "last_v": 0.0,
        "last_h": 0.0,
        "armed_context": armed_context,
    }
    state_lock = threading.Lock()
    fake_serial = FakeSerial()
    handler = module.CommandHandler(
        state,
        state_lock,
        fake_serial,
        FakeReader(),
        True,
        lambda: snapshot,
        (0.0, 0.0, 1000.0),
        0.0,
    )
    monkeypatch.setattr(module, "safe_print", lambda _message: None)

    evaluation_started = threading.Event()
    allow_evaluation_to_finish = threading.Event()
    original_evaluate = fire_control_module.evaluate_shot_clearance

    def blocking_evaluate(*args, **kwargs):
        evaluation_started.set()
        assert allow_evaluation_to_finish.wait(timeout=2.0)
        return original_evaluate(*args, **kwargs)

    monkeypatch.setattr(
        fire_control_module,
        "evaluate_shot_clearance",
        blocking_evaluate,
    )
    errors: list[BaseException] = []

    def run_shoot() -> None:
        try:
            handler._do_shoot()
        except BaseException as exc:
            errors.append(exc)

    shoot_thread = threading.Thread(target=run_shoot)
    shoot_thread.start()
    assert evaluation_started.wait(timeout=2.0)

    invalidate = getattr(module, "invalidate_armed_aim", None)
    if invalidate is None:
        # Baseline behavior from the loop branches: stop first, leaving a gap
        # before their later lock/clear operation.
        module.send_serial(fake_serial, "stop")
    else:
        invalidate(
            state,
            state_lock,
            send_command=lambda command: module.send_serial(fake_serial, command),
        )
    allow_evaluation_to_finish.set()
    shoot_thread.join(timeout=2.0)

    assert not shoot_thread.is_alive()
    assert errors == []
    assert "shoot" not in fake_serial.commands
    assert "stop" in fake_serial.commands
    assert state["armed_context"] is None
    assert state["last_v"] is None
    assert state["last_h"] is None
    assert state["aim_generation"] >= 2


def test_follow_main_uses_atomic_invalidation_for_all_four_block_branches():
    source = FOLLOW_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    main_source = next(
        ast.get_source_segment(source, node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    assert main_source.count("invalidate_armed_aim(") == 4


@pytest.mark.parametrize("path", [LIVE_AIM_PATH, FOLLOW_PATH])
def test_scripts_arm_and_store_the_exact_one_decimal_transmitted_angles(path):
    source = path.read_text(encoding="utf-8")

    assert 'command_v = float(f"{v_deg:.1f}")' in source
    assert 'command_h = float(f"{h_deg:.1f}")' in source
    assert 'f"set {command_v:.1f} {command_h:.1f}' in source
    assert "pitch_deg=command_v" in source
    assert "yaw_deg=command_h" in source


def test_both_successful_and_blocked_fire_outcomes_are_audited():
    live_source = LIVE_AIM_PATH.read_text(encoding="utf-8")
    follow_source = FOLLOW_PATH.read_text(encoding="utf-8")
    follow_tree = ast.parse(follow_source)
    handler = next(
        node
        for node in follow_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CommandHandler"
    )
    do_shoot = next(
        ast.get_source_segment(follow_source, node)
        for node in handler.body
        if isinstance(node, ast.FunctionDef) and node.name == "_do_shoot"
    )

    assert '"fire_outcome": outcome' in live_source
    assert "json.dumps(outcome" in do_shoot
    assert do_shoot.index("json.dumps(outcome") < do_shoot.index(
        'if not outcome["serial_shoot_sent"]'
    )


@pytest.mark.parametrize("path", [LIVE_AIM_PATH, FOLLOW_PATH])
def test_shoot_enabled_aim_is_cleared_and_stopped_when_clearance_blocks(path):
    source = path.read_text(encoding="utf-8")
    arm_index = source.index("arm_shot_context(")
    boundary = "commit_aim_command(" if path == FOLLOW_PATH else "send_serial(ser, cmd_str)"
    set_send_index = source.index(boundary, arm_index)
    guarded_region = source[arm_index:set_send_index]

    assert "if not" in guarded_region
    stop_contract = "invalidate_armed_aim(" if path == FOLLOW_PATH else '"stop"'
    assert stop_contract in guarded_region
    assert "armed_context" in guarded_region
    assert "continue" in guarded_region
