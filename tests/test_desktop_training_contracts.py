"""Contracts wiring the TRAINING view (Tauri app) to the drill runner stack.

These are file-content contracts (like the desktop-control-center tests): they
pin the drill IDs, launch wrapper, safety posture, and Rust command wiring so
a rename in one layer cannot silently break another.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from project_cam.training import DRILL_REGISTRY, build_session_record

ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "Parallel_working/run_training_drill.sh"
RUNNER = ROOT / "garage_lab_combined/scripts/training_drill.py"
DRILLS_TS = ROOT / "project-cam-desktop/src/drills.ts"
TRAINING_VIEW = ROOT / "project-cam-desktop/src/views/TrainingView.tsx"
APP_TSX = ROOT / "project-cam-desktop/src/App.tsx"
SIDEBAR_TSX = ROOT / "project-cam-desktop/src/components/Sidebar.tsx"
MAIN_RS = ROOT / "project-cam-desktop/src-tauri/src/main.rs"


def load_runner():
    spec = importlib.util.spec_from_file_location("training_drill_board", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrapper_exists_is_executable_and_view_only():
    assert WRAPPER.is_file()
    assert os.access(WRAPPER, os.X_OK), "wrapper must be executable"
    text = WRAPPER.read_text()
    # launches the viewer with the UDP broadcast + the drill board
    assert "run_live_usb6_mirrored_skeleton.sh" in text
    assert "training_drill.py" in text
    assert "reaction_arena.py" not in text
    assert "--udp-target-port 5005" in text
    assert "--udp-target-cams-min 2" in text
    # hard safety posture: the training stack must never reach the launcher
    for forbidden in ("--shoot-enabled", "live_aim_test", "blm_follow",
                      "/dev/ttyUSB", "launcher_runtime"):
        assert forbidden not in text, f"wrapper must not reference {forbidden}"


def test_wrapper_accepts_fullscreen_as_a_boolean_allowlisted_flag():
    """Parse --fullscreen, then fail on a following sentinel before the viewer.

    If fullscreen were absent from the allowlist the error would name it. If it
    incorrectly consumed a value, it would swallow the sentinel. Reaching the
    sentinel proves the flag is a valueless boolean without opening hardware.
    """
    result = subprocess.run(
        [
            "bash", str(WRAPPER), "reaction_zones",
            "--fullscreen", "--after-fullscreen",
        ],
        text=True,
        capture_output=True,
        cwd=ROOT,
        timeout=60,
    )
    assert result.returncode == 2
    assert "unknown argument: --after-fullscreen" in result.stderr
    assert "starting live viewer" not in result.stdout + result.stderr
    allowlist = WRAPPER.read_text(encoding="utf-8")
    assert re.search(
        r"--fullscreen\)\s+DRILL_ARGS\+=\(--fullscreen\);\s+shift\s+;;",
        allowlist,
    )


def test_runner_is_view_only_and_logs_to_training_dir():
    text = RUNNER.read_text()
    assert "import serial" not in text
    assert "/dev/tty" not in text
    assert "training_logs" in text
    assert "sessions_index.jsonl" in text


def test_training_runner_inherits_the_desktop_session_id():
    text = RUNNER.read_text(encoding="utf-8")
    assert 'os.environ.get("PROJECT_CAM_SESSION_ID"' in text
    assert "session_id=desktop_session_id" in text


def test_runner_help_lists_every_drill():
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        text=True, capture_output=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    for drill_id in DRILL_REGISTRY:
        assert drill_id in result.stdout


def test_reaction_zones_runner_uses_cli_geometry_and_writes_v1_context():
    runner = load_runner()
    args = SimpleNamespace(
        drill="reaction_zones",
        rounds=None,
        duration=None,
        arena_y_mm=3050.0,
        wall_margin_mm=500.0,
        seed=None,
    )
    drill = runner.build_drill(args)
    assert drill.kind == "reaction_zones"
    assert drill.rounds == 10
    assert drill.arena_y_mm == 3050.0
    assert drill.wall_margin_mm == 500.0

    context = runner.session_evidence_context(drill, None)
    assert context["protocol_id"] == "reaction_zones.v1"
    assert context["applied_parameters"]["rounds"] == 10
    assert context["applied_parameters"]["arena_y_mm"] == 3050.0
    assert context["applied_parameters"]["wall_margin_mm"] == 500.0
    assert context["protocol_parameters_fingerprint"].startswith("sha256:")
    assert "seed_pinned" not in context

    record = build_session_record(
        drill,
        "Арлен",
        "2026-07-30T10:00:00",
        "2026-07-30T10:02:00",
        session_id="reaction-session-typed-reader",
        evidence_context=context,
    )
    assert record["schema"] == "project_cam.training.v1"
    assert record["drill"] == "reaction_zones"
    assert record["evidence_context"] == context


@pytest.mark.parametrize(
    "state", ("set_wait", "armed", "active", "result", "done")
)
def test_reaction_zones_board_renders_every_state_headlessly(state, monkeypatch):
    runner = load_runner()
    drill = DRILL_REGISTRY["reaction_zones"](
        arena_y_mm=3050.0,
        rounds=1,
        wall_margin_mm=500.0,
        arm_hold_s=0.1,
        cue_delay_min_s=0.2,
        cue_delay_max_s=0.2,
        seed=3,
    )
    drill.state = state
    drill.arm_zone = 1
    drill.target = 0
    drill.go_time = 1.0
    drill.t_state = 1.0
    drill.cue_at = 2.0
    if state == "result":
        drill.last_result = ("hit", 0.31)
    if state == "done":
        drill.round_idx = 1
        drill.hits = 1
        drill.results = [{
            "round": 1,
            "zone": "LEFT",
            "target_center_mm": 508.3,
            "result": "hit",
            "reaction_s": 0.31,
        }]

    drawn = []
    monkeypatch.setattr(
        runner, "text",
        lambda _img, value, *_args, **_kwargs: drawn.append(str(value)),
    )
    monkeypatch.setattr(
        runner, "text_c",
        lambda _img, value, *_args, **_kwargs: drawn.append(str(value)),
    )
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    args = SimpleNamespace(arena_y_mm=3050.0)
    runner.DRAWERS["reaction_zones"](
        image, drill, 2.1, person_for_board(1525.0), args, 1280, 720
    )
    assert drawn, f"{state} rendered no athlete-facing text"
    assert not any("score" in value.lower() for value in drawn)


def person_for_board(y_mm):
    return {
        "left_hip": (3000.0, y_mm - 100.0, 1000.0),
        "right_hip": (3000.0, y_mm + 100.0, 1000.0),
    }


def test_reaction_zones_event_lines_distinguish_hit_miss_and_void():
    runner = load_runner()
    drill = DRILL_REGISTRY["reaction_zones"](arena_y_mm=3050.0)
    hit = runner.event_line(drill, {
        "event": "round", "round": 1, "zone": "LEFT",
        "result": "hit", "reaction_s": 0.31,
    })
    miss = runner.event_line(drill, {
        "event": "round", "round": 2, "zone": "RIGHT",
        "result": "miss", "reaction_s": None,
    })
    void = runner.event_line(drill, {
        "event": "round_void", "round": 3, "zone": "CENTER",
        "reason": "tracking_lost",
    })
    assert "LEFT" in hit and "HIT" in hit and "0.31" in hit
    assert "RIGHT" in miss and "MISS" in miss
    assert "CENTER" in void and "VOID" in void and "tracking" in void.lower()


def test_ui_catalog_ids_match_python_registry():
    text = DRILLS_TS.read_text()
    ts_ids = set(re.findall(r'^\s*id:\s*"([a-z_]+)"', text, re.MULTILINE))
    assert ts_ids == set(DRILL_REGISTRY), (
        f"drills.ts ids {ts_ids} != DRILL_REGISTRY {set(DRILL_REGISTRY)}")


def test_resolver_owns_the_wrapper_path_and_emits_only_forwarded_flags():
    """The wrapper path moved from the UI into the Rust resolver, so the check
    moves with it: whatever the resolver can emit must be a flag the wrapper's
    own `case` allowlist forwards, or the launch dies with exit 2."""
    profiles = (ROOT / "project-cam-desktop/src-tauri/src/launch_profiles.rs").read_text()
    assert "Parallel_working/run_training_drill.sh" in profiles
    view = TRAINING_VIEW.read_text()
    assert "run_training_drill.sh" not in view, "the UI must not name the script"

    wrapper = WRAPPER.read_text()
    arm = profiles[profiles.index("impl TrainingDrillRequest {"):]
    arm = arm[:arm.index("\n}")]
    for flag in set(re.findall(r'"(--[a-z-]+)"', arm)):
        assert flag in wrapper, f"wrapper does not forward {flag}"
    for flag in (
        "--athlete", "--face-id", "--flip", "--rounds", "--duration",
        "--fullscreen",
    ):
        assert flag in wrapper


def test_training_view_is_wired_into_the_app():
    assert "TRAINING" in SIDEBAR_TSX.read_text()
    app = APP_TSX.read_text()
    assert "TrainingView" in app
    assert 'view === "TRAINING"' in app


def test_training_history_uses_the_single_bounded_evidence_reader():
    """TRAINING must not carry its own evidence reader.

    It used to invoke a `training_sessions` command that read the whole session
    index with `read_to_string` (no byte cap) and handed raw JSONL lines to the
    UI to parse — a second, unbounded and untyped path to data the typed loader
    already covers via `read_jsonl_tail`. One reader means one byte cap and one
    rejection accounting.
    """
    text = MAIN_RS.read_text()
    handler = text[text.index("generate_handler!"):]
    assert "training_sessions," not in handler
    assert "fn training_sessions" not in text
    assert "fn load_session_evidence" in text

    view = (ROOT / "project-cam-desktop/src/views/TrainingView.tsx").read_text()
    assert 'invoke<string[]>("training_sessions"' not in view
    assert '"load_session_evidence"' in view
