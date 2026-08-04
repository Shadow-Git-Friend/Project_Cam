"""Live arena leg-raise stabilization helpers."""

import numpy as np

from project_cam.assessment.live_trainer.leg_raise_stabilizer import (
    apply_leg_identity_lock,
    apply_leg_segment_drops,
    lower_body_pose2d_snapshot,
    lower_body_snapshot,
    segment_lengths_snapshot,
)
from project_cam.assessment.live_trainer.limb_identity import LimbIdentityTracker


def _pt(x):
    return np.array([float(x), 0.0, 500.0], dtype=float)


def _seeded_tracker():
    tracker = LimbIdentityTracker(swap_margin_mm=50.0)
    joints = {
        11: _pt(-100),
        12: _pt(100),
        13: _pt(-100),
        14: _pt(100),
        15: _pt(-100),
        16: _pt(100),
    }
    conf = np.arange(17, dtype=np.float32) / 100.0
    cams = np.arange(17, dtype=np.int32)
    apply_leg_identity_lock(joints, conf, cams, tracker)
    return tracker


def test_apply_leg_identity_lock_swaps_lower_body_points_and_metadata():
    tracker = _seeded_tracker()
    joints = {
        5: _pt(-300),
        6: _pt(300),
        11: _pt(100),
        12: _pt(-100),
        13: _pt(100),
        14: _pt(-100),
        15: _pt(100),
        16: _pt(-100),
    }
    conf = np.arange(17, dtype=np.float32) / 10.0
    cams = np.arange(17, dtype=np.int32)

    result = apply_leg_identity_lock(joints, conf, cams, tracker)

    assert result.swapped is True
    assert joints[5][0] == -300.0
    assert joints[6][0] == 300.0
    assert joints[11][0] == -100.0
    assert joints[12][0] == 100.0
    assert joints[13][0] == -100.0
    assert joints[14][0] == 100.0
    assert joints[15][0] == -100.0
    assert joints[16][0] == 100.0
    assert conf[11] == np.float32(1.2)
    assert conf[12] == np.float32(1.1)
    assert cams[15] == 16
    assert cams[16] == 15


def test_apply_leg_identity_lock_handles_missing_partner_joint():
    tracker = _seeded_tracker()
    joints = {
        11: _pt(100),
        13: _pt(100),
        14: _pt(-100),
        16: _pt(-100),
    }
    conf = np.arange(17, dtype=np.float32)
    cams = np.arange(17, dtype=np.int32)

    result = apply_leg_identity_lock(joints, conf, cams, tracker)

    assert result.swapped is True
    assert 11 not in joints
    assert joints[12][0] == 100.0
    assert joints[13][0] == -100.0
    assert joints[14][0] == 100.0
    assert 15 in joints
    assert 16 not in joints


def test_apply_leg_segment_drops_clears_metadata_and_dependent_ankle():
    joints = {
        11: _pt(-100),
        12: _pt(100),
        13: _pt(-120),
        14: _pt(120),
        15: _pt(-140),
        16: _pt(140),
    }
    conf = np.ones(17, dtype=np.float32)
    cams = np.full(17, 4, dtype=np.int32)

    dropped = apply_leg_segment_drops(joints, conf, cams, {13})

    assert dropped == {13, 15}
    assert 13 not in joints
    assert 15 not in joints
    assert 14 in joints
    assert 16 in joints
    assert conf[13] == 0.0
    assert conf[15] == 0.0
    assert cams[13] == 0
    assert cams[15] == 0


def test_lower_body_snapshots_are_json_ready():
    joints = {
        11: np.array([1.0, 2.0, 3.0]),
        13: np.array([4.0, 2.0, 3.0]),
        15: np.array([4.0, 6.0, 3.0]),
    }

    snap = lower_body_snapshot(joints)
    lengths = segment_lengths_snapshot(joints)

    assert snap["11"] == [1.0, 2.0, 3.0]
    assert snap["12"] is None
    assert lengths["left_femur_mm"] == 3.0
    assert lengths["left_tibia_mm"] == 4.0
    assert lengths["right_femur_mm"] is None


def test_lower_body_pose2d_snapshot_is_json_ready():
    kpts = np.zeros((17, 2), dtype=np.float32)
    scores = np.zeros(17, dtype=np.float32)
    kpts[11] = [10.5, 20.25]
    scores[11] = 0.75
    kpts[16] = [30.0, 40.0]
    scores[16] = 0.9

    snap = lower_body_pose2d_snapshot({"camA": (kpts, scores), "camB": None})

    assert snap["camA"]["11"] == {"xy": [10.5, 20.25], "score": 0.75}
    assert snap["camA"]["12"] == {"xy": [0.0, 0.0], "score": 0.0}
    assert snap["camA"]["16"] == {"xy": [30.0, 40.0], "score": 0.8999999761581421}
    assert snap["camB"] is None
