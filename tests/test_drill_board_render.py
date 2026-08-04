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
from types import SimpleNamespace

import cv2
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


#: Sizes the board actually runs at: the design baseline, a tiled half-screen
#: pane, and true fullscreen on the rig's 1920x1080 projector/monitor.
BOARD_SIZES = [(1280, 720), (925, 520), (1600, 900), (1920, 1080)]


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


def pose_full(y_mm=1400.0, z=950.0, x=3100.0, y=None, ank_l=None, ank_r=None):
    """A whole stationary athlete — enough joints for every drill's drawer.

    `y` is an alias for `y_mm` so scripted traces can read naturally, and the
    ankle heights are settable because a raised foot IS the balance drill's
    trigger.
    """
    y_mm = y_mm if y is None else y
    ank_l = 95.0 if ank_l is None else ank_l
    ank_r = 95.0 if ank_r is None else ank_r
    return {
        "nose": (x, y_mm, z + 560),
        "left_shoulder": (x, y_mm - 160, z + 380),
        "right_shoulder": (x, y_mm + 160, z + 380),
        "left_elbow": (x, y_mm - 220, z + 300),
        "right_elbow": (x, y_mm + 220, z + 300),
        "left_wrist": (x, y_mm - 260, z + 250),
        "right_wrist": (x, y_mm + 260, z + 250),
        "left_hip": (x, y_mm - 90, z),
        "right_hip": (x, y_mm + 90, z),
        "left_knee": (x, y_mm - 90, 500.0),
        "right_knee": (x, y_mm + 90, 500.0),
        "left_ankle": (x, y_mm - 90, ank_l),
        "right_ankle": (x, y_mm + 90, ank_r),
    }


def board_args(W, H, athlete="Арлен"):
    """Full CLI-shaped args at an arbitrary board size (drawers read geometry
    off args, not just width/height)."""
    return SimpleNamespace(
        width=W, height=H, athlete=athlete, flip=False, min_cameras_expected=6,
        arena_x_mm=6230.0, arena_y_mm=ARENA_Y_MM, wall_margin_mm=500.0,
        shuttle_center_mm=3115.0, shuttle_half_mm=2000.0,
        hold_s=20.0, work_s=20.0,
    )


def make_drill(board, drill_id, sized=None):
    """Build any registry drill through the board's own CLI defaults."""
    return board.build_drill(SimpleNamespace(
        drill=drill_id, rounds=None, duration=None, seed=5, flip=False,
        arena_x_mm=6230.0, arena_y_mm=ARENA_Y_MM, wall_margin_mm=500.0,
        shuttle_center_mm=3115.0, shuttle_half_mm=2000.0,
        hold_s=20.0, work_s=20.0,
    ))


def drive_to_any(drill, *, steps=120):
    """Advance any drill past idle/countdown with a stationary athlete."""
    drill.start(0.0)
    t = 0.1
    for _ in range(steps):
        t += 0.1
        drill.update(t, pose_full())
    return t


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


# --------------------------- resolution independence -------------------------
#
# The board runs at three very different sizes: the 1280x720 design baseline, a
# ~925x520 tiled pane beside the 3D arena, and 1920x1080 fullscreen on the
# projector. Every label scales with H, so any offset that does NOT is a bug
# that only shows at one of them — the top-right clock was pinned at `W - 330`
# and ran 109 px off the right edge at fullscreen.

@pytest.mark.parametrize("size", BOARD_SIZES)
@pytest.mark.parametrize("drill_id", sorted(DRILL_REGISTRY))
def test_the_top_bar_never_overflows_at_any_board_size(board, size, drill_id, monkeypatch):
    """Title, athlete name and progress+clock must all stay inside the frame."""
    W, H = size
    sized = board_args(W, H)
    drill = make_drill(board, drill_id)
    t = drive_to_any(drill)
    drawn = []
    original = board.text

    def spy(img, s, org, scale, color, thick=2, shadow=True):
        drawn.append((s, org, scale, thick))
        return original(img, s, org, scale, color, thick, shadow=shadow)

    monkeypatch.setattr(board, "text", spy)
    # A long clock and the widest workload label are the worst case.
    board.render(drill, t + 3599.0, pose_full(), 0.05, "Александра", 0.0,
                 False, sized, quality=quality(), observed_hz=14.6)
    for s, org, scale, thick in drawn:
        (tw, _), _ = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        assert org[0] >= 0, (drill_id, size, s, org)
        assert org[0] + tw <= W, (
            f"{drill_id} at {W}x{H}: {s!r} ends at {org[0] + tw} > {W}")


@pytest.mark.parametrize("size", BOARD_SIZES)
def test_the_key_hints_and_rail_stay_below_the_drill_stage(board, size):
    """`stage_bottom` is what keeps drawers off the honesty rail, so it has to
    scale with the chrome it is protecting."""
    W, H = size
    assert board.stage_bottom(H) < H - board.px(H, 44) < H - board.px(H, 34) < H


def test_the_720_baseline_layout_is_byte_identical(board):
    """Scaling the chrome must not move anything at the design size, where the
    whole board was reviewed by eye."""
    assert board.px(720, board.BAR_H) == 64
    assert board.px(720, board.BAR_RULE) == 65
    assert board.px(720, board.BAR_BASELINE) == 42
    assert board.px(720, 22) == 22
    assert board.stage_bottom(720) == 720 - board.STAGE_BOTTOM_RESERVED


def test_athlete_names_are_centred_by_their_rendered_width(board):
    """cv2 measures Cyrillic by BYTES, so a byte-based centre puts «Арлен»
    twice as far left as it belongs — the name must be measured by whichever
    backend draws it."""
    cyrillic = board.name_width("Арлен", 1.0, 2)
    latin = board.name_width("Arlen", 1.0, 2)
    assert cyrillic == pytest.approx(latin, rel=0.45), (cyrillic, latin)
    byte_width = cv2.getTextSize("Арлен".encode("utf-8").decode("latin-1"),
                                 cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0][0]
    assert cyrillic < byte_width * 0.75, (cyrillic, byte_width)


# --------------------------- one layout grammar ------------------------------
#
# Every board reads the same way: a per-attempt rail top-left, the protocol note
# top-right, the hero measurement (or the prompt that replaces it) in the middle,
# and the spatial stage below. These tests pin that structure rather than exact
# pixels, so a board can be restyled but not left with an empty middle or a
# stage that only works at one resolution.

def drive(drill, target, limit=900):
    """Advance any drill to `target` with a per-drill scripted athlete.

    A stationary hips-only pose cannot reach most states: gk_save calibrates off
    the shoulders, balance needs a raised foot, reactive_cut needs the athlete to
    cross the cue line. Each drill therefore gets the motion its own state
    machine is looking for.
    """
    drill.start(0.0)
    t = 0.1
    x = 600.0
    for step in range(limit):
        if drill.state == target:
            return t
        t += 0.1
        if drill.kind == "balance":
            raised = drill.state != "countdown"
            drill.update(t, pose_full(ank_l=420.0 if raised else 95.0))
        elif drill.kind == "reactive_cut":
            if drill.state in ("set_wait", "idle"):
                x = 600.0
            else:
                x += 90.0
            drill.update(t, pose_full(x=x))
        elif drill.kind == "line_hops":
            drill.update(t, pose_full(y=1525.0 + (300.0 if step % 6 < 3 else -300.0)))
        elif drill.kind == "gk_updown":
            drill.update(t, pose_full(z=980.0 if step % 16 < 8 else 330.0))
        else:
            drill.update(t, pose_full())
    raise AssertionError(f"{drill.kind} never reached {target!r} "
                         f"(stuck in {drill.state!r})")


LIVE_STATES = {
    "balance": ["countdown", "hold"],
    "shuttle": ["arm", "countdown"],
    "line_hops": ["countdown", "work"],
    "gk_save": ["set_wait", "armed"],
    "gk_updown": ["countdown", "work"],
    "reaction_zones": ["set_wait", "armed", "active"],
    "cmj": ["countdown", "work"],
    "hop_symmetry": ["countdown", "arm"],
    "reactive_cut": ["set_wait", "approach"],
}


def ink_bands(img, bands=8, threshold=45):
    """Share of drawn (non-background) pixels in each horizontal band.

    The stage background is a dark gradient, so anything brighter than
    `threshold` is content. Comparing the SHAPE of this profile across
    resolutions catches geometry that does not scale — the exact defect that put
    the goal frame in the top half of a 1080-tall board.
    """
    lit = img.max(axis=2) > threshold
    total = max(1, int(lit.sum()))
    step = img.shape[0] / bands
    return [int(lit[int(i * step):int((i + 1) * step)].sum()) / total
            for i in range(bands)]


@pytest.mark.parametrize("drill_id", sorted(DRILL_REGISTRY))
def test_every_board_draws_something_in_the_hero_band(board, drill_id, monkeypatch):
    """The middle of the board is never empty in a live state.

    A drill that shows only its stage leaves the athlete with nothing to read at
    the distance they are standing.
    """
    drill = make_drill(board, drill_id)
    args = board_args(1280, 720)
    for state in LIVE_STATES[drill_id]:
        drill.reset()
        t = drive(drill, state)
        img = board.render(drill, t, pose_full(), 0.05, args.athlete, 0.0, False,
                           args, quality=quality(), observed_hz=14.6)
        # Measured range across all nine boards in these states is 1380-12716
        # lit pixels, so 1200 fails only when the headline itself is gone — not
        # merely when a board is sparse.
        band = img[int(720 * 0.20):int(720 * 0.36)]
        lit = int((band.max(axis=2) > 45).sum())
        assert lit > 1200, f"{drill_id}/{drill.state}: hero band nearly empty ({lit} px)"


@pytest.mark.parametrize("drill_id", sorted(DRILL_REGISTRY))
def test_board_geometry_scales_with_the_frame(board, drill_id):
    """Layout must be resolution-independent, not just overflow-free.

    Compared as the vertical distribution of drawn pixels: absolute pixel
    geometry (a stage pinned to y=130..520) keeps its size while the frame grows,
    so its ink migrates into the upper bands at 1080 and the profiles diverge.
    """
    frames = {}
    for W, H in ((1280, 720), (1920, 1080)):
        drill = make_drill(board, drill_id)
        state = LIVE_STATES[drill_id][-1]
        t = drive(drill, state)
        args = board_args(W, H)
        frames[H] = ink_bands(board.render(
            drill, t, pose_full(), 0.05, args.athlete, 0.0, False, args,
            quality=quality(), observed_hz=14.6))
    drift = sum(abs(a - b) for a, b in zip(frames[720], frames[1080]))
    assert drift < 0.30, (
        f"{drill_id}: ink profile moved by {drift:.2f} between 720 and 1080\n"
        f"  720: {[round(v, 3) for v in frames[720]]}\n"
        f" 1080: {[round(v, 3) for v in frames[1080]]}")


@pytest.mark.parametrize("drill_id", ["reaction_zones", "reactive_cut", "gk_save"])
def test_no_cue_colour_survives_into_a_result(board, drill_id, monkeypatch):
    """Yellow is the ASK. Once a rep has resolved, nothing may still be yellow.

    Checked on the whole frame, not just the labels: reactive_cut kept drawing
    the resolved gate line and its glow in cue yellow, so a completed rep still
    looked like a live instruction.
    """
    drill = make_drill(board, drill_id)
    t = drive(drill, "active")
    args = board_args(1280, 720)
    # Resolve the rep the way each drill does, then render the result state.
    for _ in range(400):
        t += 0.1
        if drill.kind == "reaction_zones":
            drill.update(t, pose_at(drill.target_centres_mm[drill.target]))
        elif drill.kind == "gk_save":
            side, high = drill.target
            y = 400.0 if side == 0 else 2650.0
            z = 1600.0 if high else 300.0
            j = pose_full()
            j["left_wrist"] = j["right_wrist"] = (3115.0, y, z)
            drill.update(t, j)
        else:
            drill.update(t, pose_full())
        if drill.state == "result":
            break
    assert drill.state == "result", f"{drill_id} never resolved a rep"

    img = board.render(drill, t, pose_full(), 0.05, args.athlete, 0.0, False,
                       args, quality=quality(), observed_hz=14.6)
    # Cue yellow is the board's YELLOW (0, 222, 255) specifically — AMBER
    # (59, 169, 240) is a legitimate result colour, so the mask has to separate
    # them by the green channel rather than lumping all warm hues together.
    stage = img[int(720 * 0.18):int(720 * 0.90)].astype(int)
    b, g, r = stage[:, :, 0], stage[:, :, 1], stage[:, :, 2]
    cue_like = int(((r > 200) & (g > 200) & (b < 80)).sum())
    assert cue_like < 250, f"{drill_id}: {cue_like} cue-yellow px left in a result"


def test_layout_offsets_scale_with_the_board(board):
    """`px` is the whole mechanism for resolution independence.

    Returning the raw value keeps the 720 baseline correct — which is why the
    baseline test cannot catch it — so the scaling itself has to be pinned.
    """
    assert board.px(1080, 64) == 96
    assert board.px(1080, 34) == 51
    assert board.px(360, 64) == 32
    assert board.px(520, 44) == 32
    assert board.stage_bottom(1080) == 1080 - 93


def test_every_hop_is_coloured_by_the_limb_that_made_it(board):
    """`history_bars(colors=...)` must key off the ATTEMPT, not the value.

    Two hops of the same distance on different legs are the normal case for a
    symmetric athlete, and looking the colour up by value paints both with the
    first one's limb.
    """
    img = board._bg(400, 200)
    values = [1200.0, 1200.0]
    colors = [board.GREEN, board.AMBER]
    board.history_bars(img, 20, 60, 360, 80, values, 720, colors=colors)
    left_half = img[60:140, 20:200].reshape(-1, 3)
    right_half = img[60:140, 200:380].reshape(-1, 3)
    assert any(tuple(px) == board.GREEN for px in left_half), "first hop not green"
    assert any(tuple(px) == board.AMBER for px in right_half), "second hop not amber"


def test_absolute_gauge_has_no_phantom_reference_line(board):
    """gk_updown's gauge is absolute height with marked DOWN/SET thresholds.

    Drawing the generic mid-gauge reference there put a second rule right next to
    the DOWN line, reading as a threshold that does not exist.
    """
    ref = board._bg(300, 400)
    board.height_column(ref, 100, 50, 180, 350, 720, 0.4, show_mid=True,
                        label="STAND")
    plain = board._bg(300, 400)
    board.height_column(plain, 100, 50, 180, 350, 720, 0.4, show_mid=False,
                        fill_from="bottom")
    mid_row_ref = ref[200, 88:192]
    mid_row_plain = plain[200, 88:192]
    steel = board.STEEL
    assert any(tuple(px) == steel for px in mid_row_ref), "show_mid must draw it"
    assert not any(tuple(px) == steel for px in mid_row_plain), \
        "absolute gauge must not draw a mid reference"


def test_category_bars_are_readable_without_colour(board):
    """A bar's CATEGORY must not be carried by hue alone.

    hop_symmetry colours each hop by limb, GREEN for left and AMBER for right —
    a pair that deuteranopia makes hard to separate, on a board an athlete reads
    from three metres. The limb is therefore also stamped on the bar as L / R.

    Differential, not absolute: the stage background carries its own grid, so
    counting lit pixels in the tag row passes even with no tags drawn.
    """
    def ink(tags):
        img = board._bg(400, 260)
        board.history_bars(img, 20, 60, 360, 80, [1200.0, 1150.0], 720,
                           colors=[board.GREEN, board.AMBER], tags=tags)
        row = img[145:185]
        return int((row.max(axis=2) > 45).sum())

    without = ink(None)
    with_tags = ink(["L", "R"])
    assert with_tags - without > 60, (
        f"tags added only {with_tags - without} px of ink below the bars")


def test_the_limb_tag_reaches_the_hop_symmetry_board(board, monkeypatch):
    """The helper supports tags; this pins that the DRILL actually passes them.

    Asserted on the call, not on pixels: a pixel assertion over the board cannot
    distinguish a missing tag from the background behind it.
    """
    calls = []
    real = board.history_bars

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(board, "history_bars", spy)

    drill = make_drill(board, "hop_symmetry")
    drive(drill, "hop")
    # Two completed hops on opposite legs, injected directly: driving six real
    # hops through the state machine is slow and this test is about the label.
    drill.results = [
        {"attempt": 1, "leg": "left", "distance_mm": 1400.0, "stabilise_s": 2.1},
        {"attempt": 2, "leg": "right", "distance_mm": 1150.0, "stabilise_s": 2.4},
    ]
    args = board_args(1280, 720)
    board.render(drill, 30.0, pose_full(), 0.05, args.athlete, 0.0, False,
                 args, quality=quality(), observed_hz=14.6)

    tagged = [c for c in calls if c.get("tags")]
    assert tagged, "hop_symmetry drew its history bars without limb tags"
    assert tagged[0]["tags"] == ["L", "R"], tagged[0]["tags"]
    assert len(tagged[0]["colors"]) == 2, "colour must stay, tags are additive"

    # And the legend must say what the letters mean, not what the colours mean.
    source = BOARD.read_text(encoding="utf-8")
    assert "L left leg, R right leg" in source
    assert "green left, amber right" not in source


# ------------------- failure modes must reach the athlete -------------------
#
# The plausibility guards (see tests/test_drill_plausibility.py) turn three
# previously-silent faults into named outcomes. A guard that the board does not
# render is only half a fix: the score stops being wrong, but the athlete still
# sees nothing where a result used to be.

def _arm_gk_save(drill, limit=60):
    """gk_save needs shoulders AND hips to calibrate its bands, so the
    hips-only `pose_at` helper cannot arm it."""
    t = 0.0
    drill.start(t)
    for _ in range(limit):
        t += 0.1
        drill.update(t, pose_full(y=ARENA_Y_MM / 2.0))
        if drill.state == "armed":
            return t
    raise AssertionError(f"never armed (stuck in {drill.state!r})")


def test_an_anticipated_save_reads_as_neither_a_save_nor_a_miss(board, monkeypatch):
    """The 0.034 s "save" must not be dressed up as a save, or written off as a
    miss the keeper never made."""
    drill = make_drill(board, "gk_save")
    t = _arm_gk_save(drill)
    t = drill.cue_at + 0.001
    drill.update(t, pose_full(y=ARENA_Y_MM / 2.0))
    assert drill.state == "active"
    side, high = drill.target
    wrist_y = 200.0 if side == 0 else ARENA_Y_MM - 200.0
    wrist_z = 1900.0 if high else 200.0
    joints = pose_full(y=ARENA_Y_MM / 2.0)
    joints["right_wrist"] = (3000.0, wrist_y, wrist_z)
    t += 0.034
    drill.update(t, joints)
    assert drill.last_result[0] == "anticipated"

    args = board_args(1280, 720)
    drawn = spy_text(board, monkeypatch)
    board.render(drill, t, joints, 0.05, args.athlete, 0.0, False, args,
                 quality=quality(), observed_hz=14.6)
    strings = [s for s, _ in drawn]
    colours = {s: c for s, c in drawn}
    assert "MISS" not in strings, "an early hand is not a miss"
    assert any("ANTICIPATED" in s for s in strings)
    assert any("TOO EARLY" in s for s in strings)
    # The verdict word must not be in cue-yellow: yellow is the ask, never the
    # outcome (the rule the reaction_zones board already follows).
    verdict = next(s for s in strings if "ANTICIPATED" in s)
    assert colours[verdict] != board.YELLOW


def test_a_voided_gk_round_says_what_to_do_instead_of_showing_a_result(
        board, monkeypatch):
    drill = make_drill(board, "gk_save")
    _arm_gk_save(drill)
    drill._record_void(5.0, "pre_positioned")
    args = board_args(1280, 720)
    drawn = spy_text(board, monkeypatch)
    board.render(drill, 5.1, pose_full(y=ARENA_Y_MM / 2.0), 0.05, args.athlete,
                 0.0, False, args, quality=quality(), observed_hz=14.6)
    strings = [s for s, _ in drawn]
    assert "MISS" not in strings
    assert any("RESET" in s for s in strings)
    assert any("already covered" in s for s in strings)


def test_a_balance_session_with_no_measurable_hold_says_so(board, monkeypatch):
    """An empty panel reads as "nothing happened"; the capture was faulty."""
    drill = make_drill(board, "balance")
    drive_to_any(drill)
    drill.state = "done"
    drill.results = [{
        "hold": 1, "stance": "left", "sway_rms_mm": None,
        "max_excursion_mm": None, "touchdowns": 0, "single_leg_pct": 41.0,
        "score": None, "samples_used": 9, "samples_rejected": 63,
    }]
    args = board_args(1280, 720)
    drawn = spy_text(board, monkeypatch)
    board.render(drill, 40.0, pose_full(), 0.05, args.athlete, 0.0, False, args,
                 quality=quality(), observed_hz=14.6)
    strings = [s for s, _ in drawn]
    assert any("NO MEASURED HOLD" in s for s in strings)
    assert any("63 pelvis sample" in s for s in strings)


def test_a_discarded_jump_is_visible_rather_than_deleted(board, monkeypatch):
    drill = make_drill(board, "cmj")
    drive_to_any(drill)
    drill.state = "done"
    drill.stand_z = 950.0
    drill.results = [
        {"jump": 1, "pelvis_rise_mm": 380.0},
        {"jump": 2, "pelvis_rise_mm": 902.0, "implausible": True},
    ]
    args = board_args(1280, 720)
    drawn = spy_text(board, monkeypatch)
    board.render(drill, 40.0, pose_full(), 0.05, args.athlete, 0.0, False, args,
                 quality=quality(), observed_hz=14.6)
    strings = [s for s, _ in drawn]
    assert any("FAULT" in s for s in strings), strings
    # The impossible number must never be the headline figure.
    assert not any("902" in s for s in strings)
    assert any("380" in s for s in strings)
