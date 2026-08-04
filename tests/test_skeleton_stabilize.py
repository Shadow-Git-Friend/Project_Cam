"""Tests for the display-only skeletal rigidity layer (BoneLengthBank +
stabilize_display_skeleton). The layer softly clamps rendered bone lengths
into a tolerance band around learned per-athlete lengths so per-joint
smoothing noise cannot make the skeleton look liquid/rubbery. It must be
strictly display-safe: direction-preserving, NaN-tolerant, freshness-gated,
inert until lengths lock, and never fighting the L/R merge-split."""

import numpy as np
import pytest

from project_cam.viz.skeleton_stabilize import (
    BONE_PLAUSIBLE_MM,
    BoneLengthBank,
    LIMB_CHAINS,
    WIDTH_PAIRS,
    default_bones,
    stabilize_display_skeleton,
)


def make_pose():
    """A plausible standing pose (mm). Only the joints the layer touches."""
    j = np.full((17, 3), np.nan, dtype=np.float32)
    j[5] = (-180.0, 0.0, 1450.0)   # L shoulder
    j[6] = (180.0, 0.0, 1450.0)    # R shoulder
    j[7] = (-210.0, 0.0, 1160.0)   # L elbow
    j[8] = (210.0, 0.0, 1160.0)    # R elbow
    j[9] = (-230.0, 0.0, 890.0)    # L wrist
    j[10] = (230.0, 0.0, 890.0)    # R wrist
    j[11] = (-95.0, 0.0, 950.0)    # L hip
    j[12] = (95.0, 0.0, 950.0)     # R hip
    j[13] = (-100.0, 0.0, 530.0)   # L knee
    j[14] = (100.0, 0.0, 530.0)    # R knee
    j[15] = (-105.0, 0.0, 90.0)    # L ankle
    j[16] = (105.0, 0.0, 90.0)     # R ankle
    return j


def locked_bank(pose, n=50):
    bank = BoneLengthBank(min_samples=40, window=120)
    for _ in range(n):
        bank.observe(pose)
    return bank


def bone_len(j, a, b):
    return float(np.linalg.norm(j[b].astype(np.float64) - j[a].astype(np.float64)))


def test_bank_locks_after_min_samples():
    pose = make_pose()
    bank = BoneLengthBank(min_samples=10)
    for _ in range(9):
        bank.observe(pose)
    assert bank.length((11, 13)) is None
    bank.observe(pose)
    assert bank.length((11, 13)) == pytest.approx(bone_len(pose, 11, 13), abs=1e-3)
    assert bank.n_locked() == len(default_bones())


def test_bank_out_of_bounds_outliers_never_enter_the_window():
    """A grossly collapsed tibia is stopped by the plausibility bound before
    it can reach the window at all — the first line of defence."""
    pose = make_pose()
    bank = BoneLengthBank(min_samples=10)
    for i in range(30):
        p = pose.copy()
        if i % 5 == 0:
            p[15] = p[13] + np.float32([0.0, 0.0, -55.0])   # 55 mm "tibia"
        bank.observe(p)
    lo, _ = BONE_PLAUSIBLE_MM[(13, 15)]
    assert lo > 55.0                                        # bound does the work
    assert bank.length((13, 15)) == pytest.approx(bone_len(pose, 13, 15), rel=0.01)


def test_bank_median_rejects_in_bounds_outliers():
    """The median is the SECOND line of defence, and the only one that can
    catch a plausible-looking poisoned length.

    An L/R-merge episode does not produce an absurd 55 mm tibia — it produces
    a shortened but perfectly plausible one, which sails past the bounds. Here
    a third of the frames report a 300 mm tibia (inside the 220-620 mm band):
    the median holds the true 440 mm, whereas a mean would learn 393 mm and
    then soft-clamp every healthy tibia ~47 mm short for the rest of the
    session.
    """
    pose = make_pose()
    true_len = bone_len(pose, 13, 15)                       # ~440 mm
    poisoned = 300.0
    lo, hi = BONE_PLAUSIBLE_MM[(13, 15)]
    assert lo < poisoned < hi                               # bounds cannot help

    bank = BoneLengthBank(min_samples=10)
    for i in range(30):
        p = pose.copy()
        if i % 3 == 0:                                      # 10 of 30 frames
            vec = (p[15] - p[13]).astype(np.float64)
            p[15] = p[13] + (vec / np.linalg.norm(vec) * poisoned).astype(np.float32)
        bank.observe(p)

    got = bank.length((13, 15))
    assert got == pytest.approx(true_len, rel=0.01)
    # Guard the aggregator itself: the arithmetic mean of this window is far
    # outside the tolerance above, so swapping median->mean must fail here.
    mean_len = (20 * true_len + 10 * poisoned) / 30.0
    assert abs(mean_len - true_len) > 0.05 * true_len


def test_bank_plausibility_bounds_reject_absurd_lengths():
    pose = make_pose()
    bank = BoneLengthBank(min_samples=1)
    p = pose.copy()
    p[12] = p[11] + np.float32([60.0, 0.0, 0.0])   # 60 mm "hip width" (merged)
    p[9] = p[7] + np.float32([900.0, 0.0, 0.0])    # 900 mm "forearm" (fling)
    bank.observe(p)
    assert bank.length((11, 12)) is None
    assert bank.length((7, 9)) is None
    lo, hi = BONE_PLAUSIBLE_MM[(11, 12)]
    assert lo > 60.0 and hi < 900.0


def test_bank_gates_on_conf_cams_and_exclusions():
    """Each gate must be probed with a bone that NO OTHER gate also blocks.

    Targeting the conf gate at (13,15) while excluding joint 13 made the
    assertion pass on the exclusion instead, leaving the confidence gate — the
    one the live caller actually relies on, since it passes conf/cams but
    pre-filters rather than passing exclude_joints — completely unverified.
    """
    pose = make_pose()
    conf = np.full(17, 0.9)
    cams = np.full(17, 3)
    bank = BoneLengthBank(min_samples=1)
    conf[9] = 0.1   # low-conf left wrist -> (7,9), untouched by the exclusion
    cams[16] = 1    # single-cam right ankle -> (14,16)
    bank.observe(pose, conf=conf, cams=cams, exclude_joints={13})
    assert bank.length((7, 9)) is None      # confidence gate, on its own
    assert bank.length((14, 16)) is None    # camera-count gate, on its own
    assert bank.length((11, 13)) is None    # exclusion (split-rewrote the knee)
    assert bank.length((13, 15)) is None    # exclusion, other endpoint
    assert bank.length((5, 7)) is not None  # nothing blocks this one
    assert bank.length((11, 12)) is not None


def test_bank_reset_forgets():
    pose = make_pose()
    bank = locked_bank(pose)
    bank.reset()
    assert bank.n_locked() == 0


def test_stabilize_clamps_stretched_bone_direction_preserved():
    pose = make_pose()
    bank = locked_bank(pose)
    true_len = bone_len(pose, 13, 15)
    j = pose.copy()
    # Stretch the left tibia 40% by dragging the ankle down.
    vec = (j[15] - j[13]).astype(np.float64)
    j[15] = j[13] + (vec / np.linalg.norm(vec) * true_len * 1.4).astype(np.float32)
    n = stabilize_display_skeleton(j, bank, tol=0.12, soft=0.45)
    assert n >= 1
    # Soft clamp: hi + 0.45 * (1.40L - hi) with hi = 1.12L.
    expect = true_len * (1.12 + 0.45 * (1.40 - 1.12))
    assert bone_len(j, 13, 15) == pytest.approx(expect, rel=1e-3)
    # Direction preserved: still pointing the same way.
    d0 = (pose[15] - pose[13]) / np.linalg.norm(pose[15] - pose[13])
    d1 = (j[15] - j[13]) / np.linalg.norm(j[15] - j[13])
    assert float(np.dot(d0, d1)) == pytest.approx(1.0, abs=1e-6)


def test_stabilize_within_band_untouched():
    pose = make_pose()
    bank = locked_bank(pose)
    j = pose.copy()
    before = j.copy()
    assert stabilize_display_skeleton(j, bank, tol=0.12) == 0
    np.testing.assert_array_equal(j, before)


def test_stabilize_width_pair_symmetric_about_midpoint():
    pose = make_pose()
    bank = locked_bank(pose)
    true_w = bone_len(pose, 11, 12)
    j = pose.copy()
    mid_before = 0.5 * (j[11] + j[12])
    # Hips breathing apart by 35%.
    j[11][0] -= np.float32(0.175 * true_w)
    j[12][0] += np.float32(0.175 * true_w)
    stabilize_display_skeleton(j, bank, tol=0.12, soft=0.45)
    expect = true_w * (1.12 + 0.45 * (1.35 - 1.12))
    assert bone_len(j, 11, 12) == pytest.approx(expect, rel=1e-3)
    np.testing.assert_allclose(0.5 * (j[11] + j[12]), mid_before, atol=1e-3)


def test_stabilize_width_never_reduced_below_split_min_sep():
    """The width clamp must not squeeze a bilateral pair below the L/R
    split's merge threshold — even if a poisoned/narrow learned width says
    the pair should be closer."""
    pose = make_pose()
    bank = locked_bank(pose)
    j = pose.copy()
    # Real hips ~190 mm; force learned band far below the 100 mm floor by
    # requesting an extreme reduction: fake a wide displayed pair with a
    # normal learned width and a tiny floor... the floor must win.
    j[11][0] -= 200.0
    j[12][0] += 200.0  # displayed width ~590 mm
    stabilize_display_skeleton(j, bank, tol=0.0, soft=0.0, min_pair_sep_mm=500.0)
    # Hard clamp would target 190 mm, but the floor (500) blocks any
    # reduction below it — pair must not be narrower than 500 mm.
    assert bone_len(j, 11, 12) >= 500.0 - 1e-6


def test_stabilize_chain_walks_outward():
    """A corrected knee anchors the ankle: after the femur clamp the tibia is
    measured from the NEW knee position, so the ankle stays consistent."""
    pose = make_pose()
    bank = locked_bank(pose)
    femur = bone_len(pose, 11, 13)
    tibia = bone_len(pose, 13, 15)
    j = pose.copy()
    # Knee dragged 30% down the femur direction; ankle kept at its old spot.
    vec = (j[13] - j[11]).astype(np.float64)
    j[13] = j[11] + (vec / np.linalg.norm(vec) * femur * 1.3).astype(np.float32)
    stabilize_display_skeleton(j, bank, tol=0.10, soft=0.0)
    assert bone_len(j, 11, 13) == pytest.approx(femur * 1.10, rel=1e-3)
    # The tibia, measured from the corrected knee, lands near/inside its own
    # band and must not be flung anywhere absurd.
    got_tibia = bone_len(j, 13, 15)
    assert tibia * 0.85 <= got_tibia <= tibia * 1.10


def test_stabilize_nan_unlocked_and_stale_skipped():
    pose = make_pose()
    bank = locked_bank(pose)
    j = pose.copy()
    j[9] = np.nan  # missing left wrist: (7,9) skipped, no NaN spread
    j[15] = j[13] + (j[15] - j[13]) * 2.0  # stretched tibia still clamps
    n = stabilize_display_skeleton(j, bank, tol=0.12)
    assert n >= 1
    assert not np.isfinite(j[9]).any()
    assert np.isfinite(j[15]).all()

    # Unlocked bank: everything untouched.
    fresh_bank = BoneLengthBank(min_samples=40)
    j2 = pose.copy()
    j2[15] = j2[13] + (j2[15] - j2[13]) * 2.0
    before = j2.copy()
    assert stabilize_display_skeleton(j2, fresh_bank, tol=0.12) == 0
    np.testing.assert_array_equal(j2, before)

    # Stale endpoint (fresh_mask False): bone left alone — never fabricate a
    # "plausible" position for an occluded, EMA-held joint.
    j3 = pose.copy()
    j3[15] = j3[13] + (j3[15] - j3[13]) * 2.0
    fresh = np.ones(17, dtype=bool)
    fresh[15] = False
    before3 = j3.copy()
    assert stabilize_display_skeleton(j3, bank, tol=0.12, fresh_mask=fresh) == 0
    np.testing.assert_array_equal(j3, before3)


def test_stabilize_squeezed_bone_restored_toward_lower_band():
    """The merged-legs failure mode: a bone collapsed far below its learned
    length is pushed back out toward the lower tolerance bound."""
    pose = make_pose()
    bank = locked_bank(pose)
    tibia = bone_len(pose, 13, 15)
    j = pose.copy()
    vec = (j[15] - j[13]).astype(np.float64)
    j[15] = j[13] + (vec / np.linalg.norm(vec) * tibia * 0.3).astype(np.float32)
    stabilize_display_skeleton(j, bank, tol=0.12, soft=0.45)
    expect = tibia * (0.88 - 0.45 * (0.88 - 0.30))
    assert bone_len(j, 13, 15) == pytest.approx(expect, rel=1e-3)
    assert bone_len(j, 13, 15) > tibia * 0.3  # meaningfully restored


def test_soft_clamp_converges_geometrically_without_overshoot():
    pose = make_pose()
    bank = locked_bank(pose)
    learned = bone_len(pose, 13, 15)
    upper = learned * 1.12
    joints = pose.copy()
    direction = (joints[15] - joints[13]).astype(np.float64)
    joints[15] = joints[13] + (
        direction / np.linalg.norm(direction) * learned * 1.8
    ).astype(np.float32)

    overflow = []
    for _ in range(6):
        stabilize_display_skeleton(joints, bank, tol=0.12, soft=0.45)
        overflow.append(max(0.0, bone_len(joints, 13, 15) - upper))

    assert all(b < a for a, b in zip(overflow, overflow[1:]))
    for previous, current in zip(overflow, overflow[1:]):
        assert current == pytest.approx(previous * 0.45, rel=2e-4)
    assert all(value >= 0.0 for value in overflow)


def test_zero_length_bone_is_skipped_without_nan_spread():
    pose = make_pose()
    bank = locked_bank(pose)
    joints = pose.copy()
    joints[9] = joints[7]
    before_elbow = joints[7].copy()

    stabilize_display_skeleton(joints, bank, tol=0.12, soft=0.45)

    np.testing.assert_array_equal(joints[7], before_elbow)
    np.testing.assert_array_equal(joints[9], before_elbow)
    assert np.isfinite(joints[[5, 7, 9]]).all()


def test_hard_clamp_solves_shared_joint_chain_root_outward():
    pose = make_pose()
    bank = locked_bank(pose)
    femur = bone_len(pose, 11, 13)
    tibia = bone_len(pose, 13, 15)
    femur_dir = (pose[13] - pose[11]).astype(np.float64)
    tibia_dir = (pose[15] - pose[13]).astype(np.float64)
    joints = pose.copy()
    joints[13] = joints[11] + (
        femur_dir / np.linalg.norm(femur_dir) * femur * 1.5
    ).astype(np.float32)
    joints[15] = joints[13] + (
        tibia_dir / np.linalg.norm(tibia_dir) * tibia * 1.5
    ).astype(np.float32)

    stabilize_display_skeleton(joints, bank, tol=0.10, soft=0.0)

    assert bone_len(joints, 11, 13) == pytest.approx(femur * 1.10, rel=1e-4)
    assert bone_len(joints, 13, 15) == pytest.approx(tibia * 1.10, rel=1e-4)


def test_clamp_is_equivariant_under_rigid_world_transform():
    pose = make_pose()
    bank = locked_bank(pose)
    theta = np.deg2rad(37.0)
    rotation = np.array(
        [
            [np.cos(theta), -np.sin(theta), 0.0],
            [np.sin(theta), np.cos(theta), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    translation = np.array([700.0, -230.0, 90.0])

    for dtype in (np.float32, np.float64):
        distorted = pose.astype(dtype)
        distorted[15] = distorted[13] + 1.6 * (
            distorted[15] - distorted[13]
        )
        corrected = distorted.copy()
        stabilize_display_skeleton(corrected, bank, tol=0.12, soft=0.45)
        transformed = (
            distorted.astype(np.float64) @ rotation.T + translation
        ).astype(dtype)
        stabilize_display_skeleton(transformed, bank, tol=0.12, soft=0.45)
        expected = (
            corrected.astype(np.float64) @ rotation.T + translation
        ).astype(dtype)

        np.testing.assert_allclose(
            transformed, expected, atol=2e-3, equal_nan=True
        )


def test_collapsed_bone_restore_gain_is_bounded():
    """Restoring a length rescales the measured DIRECTION, and a collapsed
    bone's direction is almost pure noise.

    Unbounded, the gain grows without limit: against a learned 440 mm tibia it
    is 2.0x at a 132 mm measurement but 11x at 20 mm and 106x at 2 mm, so 4 mm
    of transverse triangulation noise would render as 424 mm of jitter — the
    opposite of this module's purpose, in exactly the L/R-merge regime it
    exists to help. The cap keeps a genuinely collapsed joint visibly
    collapsed instead of flinging it around a noisy axis.
    """
    pose = make_pose()
    bank = locked_bank(pose)
    true_len = bone_len(pose, 13, 15)
    direction = (pose[15] - pose[13]).astype(np.float64)
    direction /= np.linalg.norm(direction)

    for collapsed in (60.0, 20.0, 2.0):
        j = pose.copy()
        j[15] = (j[13].astype(np.float64) + direction * collapsed).astype(np.float32)
        stabilize_display_skeleton(j, bank, tol=0.13, soft=0.45)
        got = bone_len(j, 13, 15)
        # 1e-2 mm slack: the buffer is float32, far below any meaningful jitter.
        assert got <= collapsed * 2.5 + 1e-2, (
            f"{collapsed} mm bone rescaled {got / collapsed:.1f}x")
        assert got >= collapsed          # still restores, never shrinks further

    # A merely-squeezed bone is under the cap, so recovery is unaffected.
    j = pose.copy()
    squeezed = true_len * 0.30
    j[15] = (j[13].astype(np.float64) + direction * squeezed).astype(np.float32)
    stabilize_display_skeleton(j, bank, tol=0.12, soft=0.45)
    assert bone_len(j, 13, 15) == pytest.approx(
        true_len * (0.88 - 0.45 * (0.88 - 0.30)), rel=1e-3)
