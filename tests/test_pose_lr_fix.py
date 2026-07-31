"""Tests for per-camera left/right keypoint relabeling (fix_lr_swaps_for_cam).

The 'both legs rise' artifact: a camera facing the person mirrors YOLO's
left/right labels; triangulating mixed labels collapses both 3D limbs onto
their average. The fix relabels each camera's L/R pairs against the previous
3D state before triangulation.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def load_live_module():
    path = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")
    spec = importlib.util.spec_from_file_location("live_4cam_arena_view_parallel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_cam():
    """Identity-rotation camera at the origin looking down +Z, no distortion."""
    R = np.eye(3)
    tvec = np.zeros(3)
    K = np.array([[800.0, 0.0, 320.0], [0.0, 800.0, 180.0], [0.0, 0.0, 1.0]])
    D = np.zeros(5)
    return R, tvec, K, D


def make_state_and_kpts(live, ankle_l=(-300.0, 0.0, 3000.0), ankle_r=(300.0, 0.0, 3000.0)):
    """3D state with distinct L/R ankles and the matching (correct) 2D kpts."""
    R, tvec, K, D = make_cam()
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    joints_state[15] = ankle_l  # left ankle
    joints_state[16] = ankle_r  # right ankle
    kpts = np.zeros((17, 2), dtype=np.float64)
    kpts[15] = live.project_world_to_pixel(joints_state[15], R, tvec, K, D)
    kpts[16] = live.project_world_to_pixel(joints_state[16], R, tvec, K, D)
    scores = np.zeros(17, dtype=np.float64)
    scores[15] = 0.9
    scores[16] = 0.8
    return joints_state, kpts, scores, (R, tvec, K, D)


def test_mirrored_labels_get_swapped_back():
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(live)
    correct = kpts.copy()
    # Simulate the camera mirroring left/right (labels swapped).
    kpts[[15, 16]] = kpts[[16, 15]]
    scores[15], scores[16] = scores[16], scores[15]
    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 1
    assert kpts[15] == pytest.approx(correct[15])
    assert kpts[16] == pytest.approx(correct[16])
    assert scores[15] == pytest.approx(0.9)  # confidence follows the point


def test_correct_labels_left_alone():
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(live)
    before = kpts.copy()
    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 0
    assert kpts == pytest.approx(before)


def test_no_3d_state_means_no_swap():
    live = load_live_module()
    _, kpts, scores, cam = make_state_and_kpts(live)
    empty_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts[[15, 16]] = kpts[[16, 15]]
    assert live.fix_lr_swaps_for_cam(kpts, scores, empty_state, *cam) == 0


def test_low_confidence_pairs_skipped():
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(live)
    kpts[[15, 16]] = kpts[[16, 15]]
    scores[15] = 0.05  # below min_conf
    assert live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam, min_conf=0.2) == 0


def test_ambiguous_geometry_not_dithered():
    # L and R nearly coincident in this view: cross is not CLEARLY better,
    # so the margin must prevent a swap.
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(
        live, ankle_l=(-5.0, 0.0, 3000.0), ankle_r=(5.0, 0.0, 3000.0))
    kpts[15, 0] += 1.0  # tiny noise
    assert live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam) == 0


def test_ratio_margin_refuses_a_weak_crossed_advantage():
    """The 0.75 RATIO gate, isolated from the absolute-advantage floor.

    The test above happens to make the crossed matching 4.3x WORSE than
    direct, so no gate is exercised at all and `margin` could be set to 10.0
    (i.e. disabled) with the suite still green. Here the crossed matching is
    genuinely better in absolute terms — 196.3 px vs 230.4 px, a 34.1 px
    advantage, comfortably over min_advantage_px — but the ratio is only 0.85.
    Both detections have merely drifted toward the midpoint, which is noise on
    a well-separated pair, not a mirror. Only the ratio gate can refuse this.
    """
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(
        live, ankle_l=(-400.0, 0.0, 3000.0), ankle_r=(400.0, 0.0, 3000.0))
    R, tvec, K, D = cam
    pl = np.asarray(live.project_world_to_pixel(
        joints_state[15], R, tvec, K, D), dtype=np.float64)
    pr = np.asarray(live.project_world_to_pixel(
        joints_state[16], R, tvec, K, D), dtype=np.float64)
    mid = 0.5 * (pl + pr)
    sep = pr - pl
    # Each detection pulled to just past the midpoint, biased a hair toward
    # the opposite side.
    kpts[15] = mid + 0.04 * sep
    kpts[16] = mid - 0.04 * sep

    direct = (np.linalg.norm(kpts[15] - pl) + np.linalg.norm(kpts[16] - pr))
    cross = (np.linalg.norm(kpts[15] - pr) + np.linalg.norm(kpts[16] - pl))
    assert cross < direct                              # crossed IS better...
    assert (direct - cross) > 6.0                      # ...by more than the floor
    assert cross / direct == pytest.approx(0.852, abs=0.01)   # ...but not clearly

    before = kpts[[15, 16]].copy()
    assert live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam) == 0
    assert kpts[[15, 16]] == pytest.approx(before)


def put(live, cam, joints_state, kpts, scores, jid, world, conf=0.9, mirror_of=None):
    """Set a joint's 3D state and its (optionally mislabeled) 2D detection."""
    R, tvec, K, D = cam
    joints_state[jid] = world
    src = world if mirror_of is None else mirror_of
    kpts[jid] = live.project_world_to_pixel(np.asarray(src, float), R, tvec, K, D)
    scores[jid] = conf


def test_single_leg_stance_collapsed_ankles_rescued_by_leg_chain():
    """Regression for the merged-legs single-leg-stance artifact.

    Once the 3D ankle state has collapsed (left==right), the ankle pair alone
    is forever ambiguous — reprojecting two coincident 3D points gives
    direct==cross, so the old per-pair fix could NEVER unswap the ankles and
    the legs stayed merged. The healthy hips/knees in the same chain must
    carry the decision and unswap the ankles too.
    """
    live = load_live_module()
    cam = make_cam()
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts = np.zeros((17, 2), dtype=np.float64)
    scores = np.zeros(17, dtype=np.float64)
    # Healthy hips + knees, camera mirrored ALL leg labels (2D of the other side).
    hips = {11: (-150.0, 0.0, 3000.0), 12: (150.0, 0.0, 3000.0)}
    knees = {13: (-140.0, 250.0, 3000.0), 14: (200.0, 230.0, 3000.0)}
    for l, r in ((11, 12), (13, 14)):
        src = hips if l == 11 else knees
        put(live, cam, joints_state, kpts, scores, l, src[l], mirror_of=src[r])
        put(live, cam, joints_state, kpts, scores, r, src[r], mirror_of=src[l])
    # Collapsed ankle STATE (both at the same point) but the camera sees the
    # true ankles apart — with mirrored labels.
    true_l, true_r = (-30.0, 500.0, 3000.0), (60.0, 460.0, 3000.0)
    put(live, cam, joints_state, kpts, scores, 15, (0.0, 490.0, 3000.0), mirror_of=true_r)
    put(live, cam, joints_state, kpts, scores, 16, (4.0, 488.0, 3000.0), mirror_of=true_l)

    R, tvec, K, D = cam
    want_l = live.project_world_to_pixel(np.asarray(true_l), R, tvec, K, D)
    want_r = live.project_world_to_pixel(np.asarray(true_r), R, tvec, K, D)
    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 3                                   # hips + knees + ankles measured
    assert kpts[15] == pytest.approx(np.asarray(want_l))
    assert kpts[16] == pytest.approx(np.asarray(want_r))


def test_unmeasured_face_follows_whole_body_mirror():
    """A chain with no 3D evidence follows the whole-body verdict: a mirrored
    camera mirrors everything, so the eyes get unswapped by the legs' vote."""
    live = load_live_module()
    cam = make_cam()
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts = np.zeros((17, 2), dtype=np.float64)
    scores = np.zeros(17, dtype=np.float64)
    legs = {11: (-150.0, 0.0, 3000.0), 12: (150.0, 0.0, 3000.0),
            13: (-140.0, 250.0, 3000.0), 14: (200.0, 230.0, 3000.0),
            15: (-120.0, 500.0, 3000.0), 16: (170.0, 480.0, 3000.0)}
    for l, r in ((11, 12), (13, 14), (15, 16)):
        put(live, cam, joints_state, kpts, scores, l, legs[l], mirror_of=legs[r])
        put(live, cam, joints_state, kpts, scores, r, legs[r], mirror_of=legs[l])
    # Eyes: detections but NO 3D state (state stays NaN) — mirrored too.
    eye_l_px, eye_r_px = np.array([300.0, 60.0]), np.array([340.0, 62.0])
    kpts[1], kpts[2] = eye_r_px, eye_l_px
    scores[1] = scores[2] = 0.8

    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 3                                   # three measured leg pairs
    assert kpts[1] == pytest.approx(eye_l_px)       # face followed the body
    assert kpts[2] == pytest.approx(eye_r_px)


def test_chain_with_own_ambiguous_evidence_stays_put():
    """A chain that HAS measured pairs keeps its own (conservative) verdict
    even when another chain clearly mirrors — no cross-chain dithering."""
    live = load_live_module()
    cam = make_cam()
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts = np.zeros((17, 2), dtype=np.float64)
    scores = np.zeros(17, dtype=np.float64)
    arms = {5: (-200.0, -300.0, 3000.0), 6: (200.0, -300.0, 3000.0),
            7: (-230.0, -100.0, 3000.0), 8: (230.0, -100.0, 3000.0)}
    for l, r in ((5, 6), (7, 8)):
        put(live, cam, joints_state, kpts, scores, l, arms[l], mirror_of=arms[r])
        put(live, cam, joints_state, kpts, scores, r, arms[r], mirror_of=arms[l])
    # Ankles: coincident state AND coincident detections -> truly ambiguous.
    put(live, cam, joints_state, kpts, scores, 15, (0.0, 500.0, 3000.0))
    put(live, cam, joints_state, kpts, scores, 16, (4.0, 498.0, 3000.0))
    before = kpts[[15, 16]].copy()

    live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert kpts[[15, 16]] == pytest.approx(before)  # legs kept their own verdict


def test_tiny_cost_ratio_fluke_needs_absolute_advantage():
    """Near-coincident pairs can clear the 0.75 RATIO on a few px of keypoint
    noise (e.g. direct 8 px vs cross 5 px). Without an absolute advantage
    floor that fluke would mirror the pair — and, worse, drive its chain."""
    live = load_live_module()
    cam = make_cam()
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts = np.zeros((17, 2), dtype=np.float64)
    scores = np.zeros(17, dtype=np.float64)
    # Eyes ~12 px apart in this view; detections shifted so the crossed
    # matching wins by ratio (cost ~3 px vs ~9 px) but only ~6 px absolute.
    put(live, cam, joints_state, kpts, scores, 1, (-22.0, -600.0, 3000.0))
    put(live, cam, joints_state, kpts, scores, 2, (22.0, -600.0, 3000.0))
    R, tvec, K, D = cam
    pl = np.asarray(live.project_world_to_pixel(
        np.asarray((-22.0, -600.0, 3000.0)), R, tvec, K, D), dtype=np.float64)
    pr = np.asarray(live.project_world_to_pixel(
        np.asarray((22.0, -600.0, 3000.0)), R, tvec, K, D), dtype=np.float64)
    # Noisy detections collapsed near the midpoint, each biased a hair toward
    # the OPPOSITE side: cross beats direct by ratio (~0.67) but only by a
    # few px absolute — pure keypoint noise, not a mirror.
    mid = 0.5 * (pl + pr)
    sep = pr - pl
    kpts[1] = mid + 0.1 * sep
    kpts[2] = mid - 0.1 * sep
    before = kpts[[1, 2]].copy()
    # Deliberately NOT passing min_advantage_px: the live caller overrides only
    # min_conf, so the signature default is what actually protects production.
    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 0
    assert kpts[[1, 2]] == pytest.approx(before)


def test_face_noise_cannot_mirror_unmeasured_limbs():
    """Whole-body verdicts must come from well-separated pairs: two mirrored
    face pairs (eyes/ears a few px apart) must NOT flip high-confidence limb
    detections whose 3D state is momentarily unavailable."""
    live = load_live_module()
    cam = make_cam()
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts = np.zeros((17, 2), dtype=np.float64)
    scores = np.zeros(17, dtype=np.float64)
    # Face pairs: state present, tiny reprojected separation (~8 px), labels
    # genuinely mirrored — a real but WEAK whole-body signal.
    face = {1: (-15.0, -600.0, 3000.0), 2: (15.0, -600.0, 3000.0),
            3: (-16.0, -630.0, 3000.0), 4: (16.0, -630.0, 3000.0)}
    for l, r in ((1, 2), (3, 4)):
        put(live, cam, joints_state, kpts, scores, l, face[l], mirror_of=face[r])
        put(live, cam, joints_state, kpts, scores, r, face[r], mirror_of=face[l])
    # Legs: NO 3D state (stale reset) but healthy, well-separated detections.
    ankle_l_px, ankle_r_px = np.array([240.0, 320.0]), np.array([400.0, 322.0])
    kpts[15], kpts[16] = ankle_l_px, ankle_r_px
    scores[15] = scores[16] = 0.9

    # Signature default again — production never passes this threshold.
    live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert kpts[15] == pytest.approx(ankle_l_px)   # limbs untouched
    assert kpts[16] == pytest.approx(ankle_r_px)


def test_one_separated_pair_is_not_a_whole_body_mirror():
    """The whole-body verdict needs a QUORUM of at least two well-separated
    pairs before it may flip chains that carry no evidence of their own.

    One mirrored pair is an ordinary limb confusion; concluding from it that
    the entire camera is mirrored, and rewriting every unmeasured chain to
    match, turns a local error into a whole-body one. The face here has
    detections but no 3D state, so it follows the whole-body verdict and is
    the visible witness for the quorum.
    """
    live = load_live_module()
    cam = make_cam()
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts = np.zeros((17, 2), dtype=np.float64)
    scores = np.zeros(17, dtype=np.float64)
    # Exactly ONE well-separated, genuinely mirrored pair (the hips).
    hips = {11: (-300.0, 0.0, 3000.0), 12: (300.0, 0.0, 3000.0)}
    put(live, cam, joints_state, kpts, scores, 11, hips[11], mirror_of=hips[12])
    put(live, cam, joints_state, kpts, scores, 12, hips[12], mirror_of=hips[11])
    # Face: detections, no 3D state -> defers to the whole-body verdict.
    eye_l_px, eye_r_px = np.array([300.0, 60.0]), np.array([340.0, 62.0])
    kpts[1], kpts[2] = eye_l_px, eye_r_px
    scores[1] = scores[2] = 0.8

    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 1                                  # the hips fixed themselves
    assert kpts[1] == pytest.approx(eye_l_px)      # face NOT dragged along
    assert kpts[2] == pytest.approx(eye_r_px)


def arms_state(live, cam, mirrored_pairs):
    """Outstretched-arm chain; only `mirrored_pairs` get swapped 2D labels."""
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts = np.zeros((17, 2), dtype=np.float64)
    scores = np.zeros(17, dtype=np.float64)
    arms = {5: (-200.0, -300.0, 3000.0), 6: (200.0, -300.0, 3000.0),
            7: (-350.0, -100.0, 3000.0), 8: (350.0, -100.0, 3000.0),
            9: (-680.0, 100.0, 3000.0), 10: (680.0, 100.0, 3000.0)}
    for l, r in ((5, 6), (7, 8), (9, 10)):
        flip = (l, r) in mirrored_pairs
        put(live, cam, joints_state, kpts, scores, l, arms[l],
            mirror_of=arms[r] if flip else None)
        put(live, cam, joints_state, kpts, scores, r, arms[r],
            mirror_of=arms[l] if flip else None)
    R, tvec, K, D = cam
    want = {j: live.project_world_to_pixel(np.asarray(p), R, tvec, K, D)
            for j, p in arms.items()}
    return joints_state, kpts, scores, want


def test_mirrored_distal_pair_not_outvoted_by_siblings():
    """A distal-only L/R confusion must be corrected on its OWN evidence.

    Summing the arm chain let one mirrored wrist pair be outvoted by the
    correctly-labelled shoulders and elbows, so the mislabeled wrists
    triangulated onto the opposite arm (~1.36 m) and reached joints_state —
    which is the UDP aim target and the firing-line snapshot input.
    """
    live = load_live_module()
    cam = make_cam()
    joints_state, kpts, scores, want = arms_state(live, cam, {(9, 10)})

    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 1                                        # only the wrist pair
    for j in (5, 6, 7, 8, 9, 10):
        assert kpts[j] == pytest.approx(np.asarray(want[j]))


def test_conclusive_sibling_not_dragged_by_mirrored_majority():
    """A summed chain vote also fails the other way: with elbows and wrists
    mirrored, the majority verdict swapped ALL three arm pairs and thereby
    broke the shoulders, whose own labels were clean."""
    live = load_live_module()
    cam = make_cam()
    joints_state, kpts, scores, want = arms_state(live, cam, {(7, 8), (9, 10)})

    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 2                                        # elbows + wrists only
    for j in (5, 6, 7, 8, 9, 10):
        assert kpts[j] == pytest.approx(np.asarray(want[j]))
