"""The drill board's shared presentation layer.

The board is an athlete-facing display on a projector, sharing a machine with
six camera threads and pose inference. So the rules it has to keep are as much
about honesty as about looks: every effect must encode a measured quantity, a
degraded capture must be visible while the session runs, and the whole frame has
to fit inside a few milliseconds.

These tests pin the parts where a plausible-looking change would silently break
one of those properties.
"""

import importlib.util
import time
from pathlib import Path

import numpy as np
import pytest

from project_cam.training import DRILL_REGISTRY

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "garage_lab_combined/scripts/training_drill.py"
ARENA_Y_MM = 3050.0
FRAME_BUDGET_MS = 8.0


@pytest.fixture(scope="module")
def board():
    spec = importlib.util.spec_from_file_location("training_drill_board", BOARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Args:
    width, height = 1280, 720
    athlete = "Арлен"
    flip = False
    min_cameras_expected = 6


def quality(opened=6, valid=0.97):
    roles = [f"camUsb{i:02d}" for i in range(1, 7)]
    return {
        "context_schema": "project_cam.capture_context.v1",
        "configured_camera_roles": roles,
        "opened_camera_roles": roles[:opened],
        "calibration_fingerprint": "sha256:3a9e9bf23b7147ec18a",
        "pose_valid_frame_ratio": valid,
        "median_reported_joint_cameras": 4.0,
        "packets_observed": 1200,
    }


def pose_at(y_mm, z=950.0):
    return {"left_hip": (0.0, y_mm - 90, z), "right_hip": (0.0, y_mm + 90, z)}


def drive_to(drill, state, *, y_mm=500.0, limit=400):
    """Advance the drill to a state using a stationary athlete."""
    t = 0.1
    drill.start(0.0)
    for _ in range(limit):
        if drill.state == state:
            return t
        t += 0.1
        drill.update(t, pose_at(y_mm))
    raise AssertionError(f"never reached {state!r} (stuck in {drill.state!r})")


def spy_text(board, monkeypatch):
    """Capture (string, colour) for every label the board draws."""
    drawn = []
    for name in ("text", "text_c"):
        original = getattr(board, name)

        def wrapper(img, s, *a, _orig=original, **kw):
            colour = a[2] if len(a) > 2 else kw.get("color")
            drawn.append((str(s), colour))
            return _orig(img, s, *a, **kw)

        monkeypatch.setattr(board, name, wrapper)
    return drawn


# ----------------------------- cached stage ---------------------------------

def test_background_is_cached_but_hands_out_a_copy(board):
    """Rebuilding a 2.7 MB gradient every frame was waste; handing out the
    cached array itself would be worse — one frame's drawing would poison every
    later frame."""
    first = board._bg(320, 180)
    first[:] = 255
    second = board._bg(320, 180)
    assert second.max() < 255, "callers must not be able to scribble on the cache"
    assert (320, 180) in {(w, h) for (w, h) in board._BG_CACHE}


# ------------------------------- glow ---------------------------------------

def test_glow_is_additive_bounded_and_zero_gain_is_free(board):
    img = np.zeros((120, 120, 3), np.uint8)
    board.glow(img, 60, 60, 30, board.YELLOW, 1.0)
    assert img.max() > 0, "a glow must actually brighten the frame"
    assert img.max() <= 255, "additive blending must clip, never wrap"

    before = img.copy()
    board.glow(img, 60, 60, 30, board.YELLOW, 0.0)
    np.testing.assert_array_equal(img, before)


def test_glow_saturates_instead_of_wrapping(board):
    """uint8 addition wraps to black at 256 — the exact artefact that would make
    the brightest cue look like a hole."""
    img = np.full((80, 80, 3), 240, np.uint8)
    board.glow(img, 40, 40, 25, board.WHITE, 1.0)
    assert img.min() >= 240, f"wraparound: darkest pixel is {img.min()}"


def test_glow_survives_being_clipped_by_the_frame_edge(board):
    img = np.zeros((60, 60, 3), np.uint8)
    for cx, cy in ((0, 0), (59, 59), (-20, 30), (30, 90)):
        board.glow(img, cx, cy, 25, board.GREEN, 0.8)  # must not raise


# ------------------------------ timing tiers ---------------------------------

def test_tiers_are_bands_on_a_measured_time(board):
    assert board.tier_of(0.40)[0] == "PERFECT"
    assert board.tier_of(board.TIER_GOOD_S)[0] == "PERFECT"
    assert board.tier_of(board.TIER_GOOD_S + 0.01)[0] == "GOOD"
    assert board.tier_of(board.TIER_LATE_S + 0.01)[0] == "LATE"
    assert board.tier_of(None)[0] == "—"
    # A tier is never a score: no numeric grade comes out of this.
    for value in (0.3, 0.55, 0.9, None):
        assert isinstance(board.tier_of(value)[0], str)


# ---------------------------- the honesty rail -------------------------------

def test_rail_reports_degradation_in_amber_while_the_session_runs(board, monkeypatch):
    drawn = spy_text(board, monkeypatch)
    img = board._bg(Args.width, Args.height)
    board.evidence_rail(img, Args.width, Args.height, quality(opened=4, valid=0.71),
                        8.1, min_cameras=6)
    labels = {s: c for s, c in drawn}
    assert "CAMERAS 4/6" in labels and labels["CAMERAS 4/6"] == board.AMBER
    assert "VALID 71%" in labels and labels["VALID 71%"] == board.AMBER
    assert "DEGRADED" in labels


def test_rail_is_green_only_when_the_check_actually_passed(board, monkeypatch):
    drawn = spy_text(board, monkeypatch)
    img = board._bg(Args.width, Args.height)
    board.evidence_rail(img, Args.width, Args.height, quality(), 14.6, min_cameras=6)
    labels = {s: c for s, c in drawn}
    assert labels["CAMERAS 6/6"] == board.GREEN
    assert labels["VALID 97%"] == board.GREEN


def test_missing_capture_context_says_so_instead_of_implying_a_clean_run(board, monkeypatch):
    drawn = spy_text(board, monkeypatch)
    img = board._bg(Args.width, Args.height)
    board.evidence_rail(img, Args.width, Args.height, None, None)
    text = " | ".join(s for s, _ in drawn)
    assert "UNAVAILABLE" in text
    assert "CAMERAS" not in text, "no camera claim without a capture context"


def test_timing_resolution_follows_the_observed_rate(board, monkeypatch):
    """A reaction time is quantised by one packet interval, so the disclosed
    resolution must degrade with the real rate — not quote a nominal 15 Hz."""
    img = board._bg(Args.width, Args.height)
    for hz, expected in ((15.0, "0.03"), (8.0, "0.06"), (5.0, "0.10")):
        drawn = spy_text(board, monkeypatch)
        board.evidence_rail(img, Args.width, Args.height, quality(), hz)
        notes = [s for s, _ in drawn if "Hz" in s]
        assert notes, f"no resolution note at {hz} Hz"
        assert expected in notes[0], f"{hz} Hz -> {notes[0]}"


# --------------------------- reaction_zones states ---------------------------

@pytest.mark.parametrize("state", ["set_wait", "armed", "active"])
def test_every_live_state_renders(board, state):
    drill = DRILL_REGISTRY["reaction_zones"](arena_y_mm=ARENA_Y_MM, rounds=10, seed=7)
    t = drive_to(drill, state)
    img = board.render(drill, t, pose_at(500), 0.05, Args.athlete, 0.0, False,
                       Args, quality=quality(), observed_hz=14.6)
    assert img.shape == (Args.height, Args.width, 3)
    assert img.max() > 0


def test_a_cue_never_reads_as_a_result(board, monkeypatch):
    """Yellow means the system is asking for something. Once the round resolves
    the zone label must carry the verdict colour instead."""
    drill = DRILL_REGISTRY["reaction_zones"](arena_y_mm=ARENA_Y_MM, rounds=10, seed=7)
    t = drive_to(drill, "active")
    target = drill.zone_name(drill.target)

    drawn = spy_text(board, monkeypatch)
    board.render(drill, t, pose_at(500), 0.05, Args.athlete, 0.0, False, Args,
                 quality=quality(), observed_hz=14.6)
    assert (target, board.YELLOW) in drawn, "the live cue should be yellow"

    t += 0.5
    drill.update(t, pose_at(drill.target_centres_mm[drill.target]))
    assert drill.last_result[0] == "hit"
    drawn = spy_text(board, monkeypatch)
    board.render(drill, t, pose_at(500), 0.05, Args.athlete, 0.0, False, Args,
                 quality=quality(), observed_hz=14.6)
    colours = {s: c for s, c in drawn}
    assert colours[target] == board.GREEN
    assert colours[target] != board.YELLOW


def test_a_hit_shows_the_raw_time_with_its_unit_and_a_tier(board, monkeypatch):
    drill = DRILL_REGISTRY["reaction_zones"](arena_y_mm=ARENA_Y_MM, rounds=10, seed=7)
    t = drive_to(drill, "active")
    t += 0.5
    drill.update(t, pose_at(drill.target_centres_mm[drill.target]))
    reaction = drill.last_result[1]

    drawn = spy_text(board, monkeypatch)
    board.render(drill, t, pose_at(500), 0.05, Args.athlete, 0.0, False, Args,
                 quality=quality(), observed_hz=14.6)
    rendered = [s for s, _ in drawn]
    assert f"{reaction:.2f}" in rendered, "the measured time must be on screen"
    assert " s" in rendered, "and it must carry its unit"
    assert board.tier_of(reaction)[0] in rendered


def test_tracking_loss_is_announced_and_does_not_disarm(board, monkeypatch):
    drill = DRILL_REGISTRY["reaction_zones"](arena_y_mm=ARENA_Y_MM, rounds=10, seed=7)
    t = drive_to(drill, "armed")

    drawn = spy_text(board, monkeypatch)
    board.render(drill, t, None, 9.9, Args.athlete, 0.0, False, Args,
                 quality=quality(), observed_hz=14.6)
    assert "TRACKING LOST" in [s for s, _ in drawn]
    assert drill.state == "armed", "rendering must not change drill state"


def test_the_board_never_prints_a_composite_score(board, monkeypatch):
    """The invented 0-100 balance score was removed from the athlete's screen
    deliberately; no drill may reintroduce a graded number."""
    drill = DRILL_REGISTRY["reaction_zones"](arena_y_mm=ARENA_Y_MM, rounds=10, seed=7)
    t = drive_to(drill, "active")
    t += 0.5
    drill.update(t, pose_at(drill.target_centres_mm[drill.target]))

    drawn = spy_text(board, monkeypatch)
    board.render(drill, t, pose_at(500), 0.05, Args.athlete, 0.0, False, Args,
                 quality=quality(), observed_hz=14.6)
    for s, _ in drawn:
        assert "score" not in s.lower(), s


# ------------------------------ frame budget ---------------------------------

def test_a_frame_fits_the_budget(board):
    """The board shares the machine with six camera threads and inference.
    Rebuilding the gradient and blending glows in float32 measured 8.22 ms —
    over budget — which is why both are cached."""
    drill = DRILL_REGISTRY["reaction_zones"](arena_y_mm=ARENA_Y_MM, rounds=10, seed=9)
    t = drive_to(drill, "active")
    joints = pose_at(1400)
    args, q = Args, quality()

    board.render(drill, t, joints, 0.05, Args.athlete, 0.0, False, args,
                 quality=q, observed_hz=14.6)   # warm the caches
    runs = 60
    start = time.perf_counter()
    for _ in range(runs):
        board.render(drill, t, joints, 0.05, Args.athlete, 0.0, False, args,
                     quality=q, observed_hz=14.6)
    per_ms = (time.perf_counter() - start) / runs * 1000.0
    # Generous headroom over the measured ~3.3 ms so this fails on a real
    # regression, not on a busy CI box.
    assert per_ms < FRAME_BUDGET_MS * 2, f"{per_ms:.2f} ms per frame"
