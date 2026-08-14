"""Comparability evidence for training sessions.

A drill session number is only comparable to another if it was produced by the
same protocol, the same applied workload, and a known calibration with a known
camera set. None of that was recorded, so a 2-camera degraded run and a clean
6-camera run were indistinguishable in the log — and the rule "degraded numbers
must not enter a baseline" could not be applied at all.

These tests pin the raw-facts contract: the listener separates viewer liveness
from tracking, keeps the per-joint quality the viewer already sends, and the
session record carries the protocol + the parameters actually used.
"""

import importlib.util
import json
import re
import subprocess
import time
from pathlib import Path

import pytest

from project_cam.training.drills import (
    DRILL_REGISTRY,
    FINGERPRINT_EXCLUDED,
    PROTOCOL_CATALOG,
    applied_parameters,
    build_session_record,
    protocol_parameters_fingerprint,
    validate_workload,
)

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "Parallel_working/run_training_drill.sh"
BOARD = ROOT / "garage_lab_combined/scripts/training_drill.py"


def load_board():
    """Import the drill board without cv2 side effects at call time."""
    spec = importlib.util.spec_from_file_location("training_drill_board", BOARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------- workload validation ---------------------------

def test_zero_workload_is_rejected_not_silently_replaced():
    """`args.rounds or 4` turned 0 into 4: the session ran a workload nobody
    asked for while the record implied otherwise."""
    with pytest.raises(ValueError, match="between 2 and 8"):
        validate_workload("balance", 0)


@pytest.mark.parametrize("drill_id,bad", [
    ("balance", 9), ("shuttle", 7), ("line_hops", 6),
    ("gk_save", 4), ("gk_updown", 121.0),
])
def test_out_of_range_workload_is_rejected(drill_id, bad):
    with pytest.raises(ValueError):
        validate_workload(drill_id, bad)


def test_every_catalog_default_is_inside_its_own_range():
    """A range that excluded the shipped default would break every existing
    template the moment validation switched on."""
    defaults = {"balance": 4, "shuttle": 3, "line_hops": 3,
                "gk_save": 10, "gk_updown": 30.0}
    for drill_id, default in defaults.items():
        assert validate_workload(drill_id, default) is not None


def test_catalog_covers_exactly_the_shipped_drills():
    assert set(PROTOCOL_CATALOG) == set(DRILL_REGISTRY)


# --------------------------- applied parameters ----------------------------

def test_applied_parameters_read_back_from_the_built_drill():
    """Read off the object, not the request: constructors clamp (max(1, ...)),
    and the record must describe the session that actually ran."""
    drill = DRILL_REGISTRY["balance"](holds=3, hold_s=20.0)
    params = applied_parameters(drill)
    assert params == {"holds": 3, "hold_s": 20.0}

    clamped = DRILL_REGISTRY["balance"](holds=0)
    assert applied_parameters(clamped)["holds"] == 1  # not the requested 0


def test_protocol_defining_fixed_parameters_are_recorded():
    """hold_s / work_s are not settable through the wrapper allowlist but they
    DEFINE the exercise, so they must be in the record (and the fingerprint):
    a 20 s hold and a 30 s hold are not the same drill."""
    assert "hold_s" in applied_parameters(DRILL_REGISTRY["balance"]())
    assert "work_s" in applied_parameters(DRILL_REGISTRY["line_hops"]())


# ------------------------------- fingerprint -------------------------------

def test_fingerprint_is_canonical_across_int_float_and_key_order():
    a = protocol_parameters_fingerprint("balance.v1", {"holds": 4, "hold_s": 20.0})
    b = protocol_parameters_fingerprint("balance.v1", {"hold_s": 20, "holds": 4.0})
    assert a == b, "4 and 4.0 must not split a baseline in two"


def test_fingerprint_separates_different_workloads():
    """Same protocol, different volume -> different baseline. protocol_id alone
    cannot express this, which is why the fingerprint exists."""
    four = protocol_parameters_fingerprint("balance.v1", {"holds": 4, "hold_s": 20.0})
    eight = protocol_parameters_fingerprint("balance.v1", {"holds": 8, "hold_s": 20.0})
    assert four != eight


def test_seed_is_excluded_from_the_fingerprint():
    """A different random cue order is the same protocol; splitting baselines on
    it would make every gk_save session its own epoch."""
    assert "seed" in FINGERPRINT_EXCLUDED
    drill = DRILL_REGISTRY["gk_save"](rounds=10, seed=7)
    assert "seed" not in applied_parameters(drill)


def test_pinned_seed_is_recorded_for_audit():
    """One Random drives both the corner and the cue delay, so a pinned seed
    makes the sequence learnable — reaction times would improve without the
    athlete getting faster. Must be visible in the evidence."""
    board = load_board()
    pinned = DRILL_REGISTRY["gk_save"](rounds=10, seed=7)
    assert board.session_evidence_context(pinned, None)["seed_pinned"] is True
    free = DRILL_REGISTRY["gk_save"](rounds=10)
    assert "seed_pinned" not in board.session_evidence_context(free, None)



def test_a_ball_packet_does_not_pretend_a_person_was_tracked():
    """A ball is not a body, and it gets its own clock.

    The served drill needs the delivery even when the keeper drops out of
    tracking for a frame, so a ball must not depend on joints. Equally it must
    never advance the TRACKING clock: an armed drill state reading a ball-only
    packet as a fresh observation of the athlete would be the same defect the
    heartbeat rule exists to prevent.
    """
    board = load_board()
    listener = make_listener(board)
    now = time.time()
    ball = {"x_mm": 1000.0, "y_mm": 1500.0, "z_mm": 1200.0,
            "vx_mm_s": 9000.0, "vy_mm_s": 0.0, "vz_mm_s": 0.0,
            "mode": "AIRBORNE", "cams": 3, "coasting": False}
    listener._observe_packet({"ball": ball}, {}, {}, {}, now=now)

    assert listener.last_ball_ts == now
    assert listener.last_ts == 0.0, "the tracking clock must stay untouched"
    assert listener.get(max_age=0.6)[0] is None
    assert listener.get_ball(max_age=1.0) == ball


def test_a_stale_ball_sample_is_withheld_rather_than_interpolated():
    """A served drill measures SEGMENTS between consecutive ball packets. A stale
    sample would stretch one across metres of unobserved flight, so the listener
    withholds it and the drill treats the stretch as unobserved."""
    board = load_board()
    listener = make_listener(board)
    listener._observe_packet(
        {"ball": {"x_mm": 1.0, "y_mm": 2.0, "z_mm": 3.0}}, {}, {}, {},
        now=time.time() - 5.0)
    assert listener.get_ball(max_age=0.25) is None
    assert listener.get_ball(max_age=10.0) is not None


def test_only_a_drill_that_declares_it_receives_the_ball():
    """The eight pose-only machines keep a two-argument `update`, so they cannot
    start depending on a stream they were never designed around."""
    board = load_board()
    ball = {"x_mm": 1000.0, "y_mm": 1500.0, "z_mm": 1200.0,
            "vx_mm_s": 9000.0, "vy_mm_s": 0.0, "vz_mm_s": 0.0,
            "mode": "AIRBORNE", "cams": 3, "coasting": False}

    assert DRILL_REGISTRY["gk_save_served"].wants_ball is True
    for kind, cls in DRILL_REGISTRY.items():
        if kind == "gk_save_served":
            continue
        assert getattr(cls, "wants_ball", False) is False, kind

    # Behaviour, not a source string: a mutation sweep showed the grep version of
    # this contract survived making the dispatch unconditional, which would hand a
    # third argument to eight `update`s that take two.
    pose_only = DRILL_REGISTRY["balance"](holds=2)
    pose_only.start(0.0)
    board.drill_tick(pose_only, 0.1, None, ball)      # must not raise

    served = DRILL_REGISTRY["gk_save_served"](serves=3, goal_x_mm=6230.0)
    seen = {}
    served.update = lambda now, joints=None, b=None: seen.setdefault("ball", b)
    board.drill_tick(served, 0.1, None, ball)
    assert seen["ball"] is ball, "a served drill must actually receive the ball"


# ------------------------- listener liveness vs tracking -------------------

def make_listener(board):
    """A listener with no socket thread; we drive _observe_packet directly."""
    listener = board.UDPJointListener.__new__(board.UDPJointListener)
    import threading
    listener.lock = threading.Lock()
    listener.joints = None
    listener.joint_conf = {}
    listener.joint_cams = {}
    listener.last_ts = 0.0
    listener.last_packet_ts = 0.0
    listener.capture = None
    listener._packets = 0
    listener._packets_with_joints = 0
    listener._cams_seen = []
    listener._role_open_packets = {}
    listener.ball = None
    listener.last_ball_ts = 0.0
    listener._packets_with_ball = 0
    return listener


CAPTURE = {
    "context_schema": "project_cam.capture_context.v1",
    "configured_camera_roles": ["cam0", "cam1", "cam2"],
    "opened_camera_roles": ["cam0", "cam1"],
    "calibration_fingerprint": "sha256:abc",
}


def test_heartbeat_marks_the_viewer_alive_without_faking_tracking():
    """The whole point of the heartbeat: distinguish "nobody tracked" from
    "viewer died". It must NOT advance the tracking clock, or an armed drill
    state would read an empty packet as a fresh observation."""
    board = load_board()
    listener = make_listener(board)
    # Real clock: get()/viewer_alive() compare against time.time().
    now = time.time()
    listener._observe_packet({"capture": CAPTURE}, {}, {}, {}, now=now)

    assert listener.last_packet_ts == now
    assert listener.last_ts == 0.0            # tracking clock untouched
    assert listener.viewer_alive(max_age=2.0) is True
    joints, _age = listener.get(max_age=0.6)
    assert joints is None                     # drill sees absence of tracking


def test_joint_packet_advances_both_clocks_and_keeps_quality():
    board = load_board()
    listener = make_listener(board)
    now = time.time()
    listener._observe_packet(
        {"capture": CAPTURE},
        {"left_hip": (1.0, 2.0, 3.0)}, {"left_hip": 0.9}, {"left_hip": 4},
        now=now)

    assert listener.last_ts == listener.last_packet_ts == now
    assert listener.joint_cams == {"left_hip": 4}      # not discarded
    assert listener.joint_conf == {"left_hip": 0.9}
    joints, _ = listener.get(max_age=1e9)
    assert joints == {"left_hip": (1.0, 2.0, 3.0)}


def test_valid_frame_ratio_counts_heartbeats_as_invalid_frames():
    board = load_board()
    listener = make_listener(board)
    for i in range(3):
        listener._observe_packet({"capture": CAPTURE}, {}, {}, {}, now=1.0 + i)
    listener._observe_packet(
        {"capture": CAPTURE}, {"left_hip": (0.0, 0.0, 0.0)}, {}, {"left_hip": 6},
        now=10.0)

    quality = listener.capture_quality()
    assert quality["packets_observed"] == 4
    assert quality["pose_valid_frame_ratio"] == pytest.approx(0.25)
    assert quality["median_reported_joint_cameras"] == 6.0


def test_camera_open_ratio_is_by_role_and_never_a_bare_count():
    """A bare camera_count cannot say WHICH role was missing, and role names are
    stable where /dev/videoN is not."""
    board = load_board()
    listener = make_listener(board)
    listener._observe_packet({"capture": CAPTURE}, {}, {}, {}, now=1.0)

    ratios = listener.capture_quality()["camera_open_ratio_by_role"]
    assert ratios == {"cam0": 1.0, "cam1": 1.0, "cam2": 0.0}


def test_quality_is_none_without_a_capture_context():
    """Old viewers send no context; the session stays visible but carries no
    comparability claim rather than an invented one."""
    board = load_board()
    listener = make_listener(board)
    listener._observe_packet({}, {"left_hip": (0.0, 0.0, 0.0)}, {}, {}, now=1.0)
    assert listener.capture_quality() is None


def test_quality_carries_no_verdict_fields():
    """quality_class / baseline_eligible are computed by the versioned policy,
    not frozen into the record — otherwise a threshold change cannot be
    re-applied to history."""
    board = load_board()
    listener = make_listener(board)
    listener._observe_packet({"capture": CAPTURE}, {}, {}, {}, now=1.0)
    quality = listener.capture_quality()
    assert "quality_class" not in quality
    assert "baseline_eligible" not in quality


# ------------------------------ record shape -------------------------------

def test_evidence_context_and_athlete_id_are_optional_v1_additions():
    """The desktop reader looks fields up by key but rejects an unknown schema
    string, so these must be additive within v1."""
    drill = DRILL_REGISTRY["balance"](holds=4)
    plain = build_session_record(drill, "Ann", "t0", "t1")
    assert plain["schema"] == "project_cam.training.v1"
    assert "evidence_context" not in plain and "athlete_id" not in plain

    rich = build_session_record(drill, "Ann", "t0", "t1",
                               athlete_id="uuid-1",
                               evidence_context={"protocol_id": "balance.v1"})
    assert rich["schema"] == "project_cam.training.v1"
    assert rich["athlete_id"] == "uuid-1"
    assert rich["evidence_context"]["protocol_id"] == "balance.v1"
    json.dumps(rich)  # must stay JSON-safe


def test_record_evidence_context_matches_the_real_drill():
    board = load_board()
    drill = DRILL_REGISTRY["gk_updown"](duration_s=45.0)
    context = board.session_evidence_context(drill, None)
    assert context["protocol_id"] == "gk_updown.v1"
    assert context["applied_parameters"] == {"duration_s": 45.0}
    assert context["protocol_parameters_fingerprint"].startswith("sha256:")


# --------------------- wrapper launch allowlist (exit 2) -------------------

def test_wrapper_rejects_a_launcher_flag_with_exit_2_before_starting_anything():
    """The drill wrapper's allowlist is real code (`*) exit 2`) that no test
    exercised. It is the boundary that keeps a drill launch view-only, so a
    program cannot smuggle --shoot-enabled through as a parameter.

    Asserts the exact code 2, not merely non-zero: an unrelated failure exiting
    1 would otherwise pass this test.
    """
    result = subprocess.run(
        ["bash", str(WRAPPER), "balance", "--shoot-enabled"],
        text=True, capture_output=True, cwd=ROOT, timeout=60,
    )
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "unknown argument" in result.stderr
    combined = result.stdout + result.stderr
    assert "cameras active" not in combined   # viewer never reached
    assert "Traceback" not in combined


def test_wrapper_rejects_an_unknown_argument_with_exit_2():
    result = subprocess.run(
        ["bash", str(WRAPPER), "balance", "--totally-unknown", "7"],
        text=True, capture_output=True, cwd=ROOT, timeout=60,
    )
    assert result.returncode == 2, (result.returncode, result.stderr)
    assert "unknown argument" in result.stderr


# ------------------- heartbeat must never reach fire control ----------------

LIVE = ROOT / "Parallel_working/scripts/live_4cam_arena_view_parallel.py"


def test_capture_context_is_opt_in():
    """Default OFF is a safety property, not a preference.

    `store_runtime_safety_packet` treats any packet without a valid `safety`
    block as cause to `invalidate_runtime_aim` and clear the joint buffers
    (fail-closed by design). An unconditional heartbeat would therefore fight
    fire control continuously. Flipping this default is a safety change.
    """
    source = LIVE.read_text(encoding="utf-8")
    assert '"--udp-capture-context", action="store_true"' in source
    assert "default=True" not in source.split("--udp-capture-context")[1][:400]


def test_default_send_gate_reduces_to_joints_only_with_every_extra_off():
    """With every opt-in flag off the guard must reduce to the original
    `if joints_payload:` — the UDP payload path is protected geometry.

    Rewritten 2026-08-07, when `--udp-ball` added a second opt-in disjunct. The
    property is NOT "the guard reads exactly this string": it is that every extra
    term is falsy unless its own `store_true` flag was passed, so the launcher's
    packet stream is byte-identical by default. A test pinned to the literal line
    would have to be rewritten for each new consumer channel and would say
    nothing about the guarantee.
    """
    source = LIVE.read_text(encoding="utf-8")
    match = re.search(r"\n\s*if (joints_payload[^\n]*):\n\s*pkt = \{", source)
    assert match, "the send guard moved — re-read the UDP block"
    terms = [term.strip() for term in match.group(1).split(" or ")]
    assert terms[0] == "joints_payload", terms
    # Each additional term is gated by an opt-in flag, so it is falsy by default.
    extras = {
        "capture_context is not None": "--udp-capture-context",
        "ball_payload": "--udp-ball",
    }
    assert set(terms[1:]) <= set(extras), (
        f"undeclared disjunct in the send guard: {set(terms[1:]) - set(extras)}")
    for term in terms[1:]:
        flag = extras[term]
        assert f'"{flag}", action="store_true"' in source, flag
        assert "default=True" not in source.split(flag)[1][:400], flag
    # And each block attaches its key only when it actually has one.
    assert 'if capture_context is not None:\n                        pkt["capture"]' in source
    assert 'if ball_payload is not None:\n                        pkt["ball"]' in source


def test_the_ball_channel_is_opt_in_and_never_reaches_the_launcher():
    """Same fail-closed reasoning as the capture-context heartbeat.

    A packet without a `safety` block disarms the runtime by design, so any extra
    packet this channel causes must never appear on a launcher-facing profile. The
    served drill is the only consumer, and it is view-only.
    """
    source = LIVE.read_text(encoding="utf-8")
    assert '"--udp-ball", action="store_true"' in source
    assert "default=True" not in source.split("--udp-ball")[1][:400]
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert "--udp-ball" in wrapper, "the served drill needs the ball channel"
    for script in sorted((ROOT / "Parallel_working").glob("run_live*blm*.sh")):
        assert "--udp-ball" not in script.read_text(encoding="utf-8"), script


def test_the_ball_velocity_is_mirrored_as_a_displacement_not_as_a_point():
    """The Y mirror is `y -> Y_max - y`, so a POSITION gets the offset and a
    VELOCITY only gets its sign flipped. Passing a velocity through
    `transform_world_point_y` would add Y_max to it — a silent axis error of
    exactly the kind geometry.md forbids, and one that would place every serve on
    the wrong side of the goal.
    """
    source = LIVE.read_text(encoding="utf-8")
    block = source[source.index("ball_payload = None"):]
    block = block[:block.index("# With capture context on")]
    assert "transform_world_point_y(" in block, "the position must be mirrored"
    assert '"vy_mm_s": -vy if udp_world_y_mirror else vy' in block
    # The velocity must NOT be routed through the point transform.
    assert "transform_world_point_y(vel" not in block
    assert "transform_world_point_y(ball_kf" not in block


def test_only_the_view_only_drill_wrapper_enables_the_heartbeat():
    """Any BLM/launcher-facing profile must stay on the silent default."""
    assert "--udp-capture-context" in WRAPPER.read_text(encoding="utf-8")
    for script in sorted((ROOT / "Parallel_working").glob("run_live*blm*.sh")):
        assert "--udp-capture-context" not in script.read_text(encoding="utf-8"), script
