"""Supine leg-raise post-processor: angles, reps, inference gating, isolation."""

import math

import numpy as np

from project_cam.assessment.joints import JOINT_NAME_TO_INDEX, JOINT_NAMES
from project_cam.assessment.kinematics import frame_kinematics
from project_cam.assessment.live_trainer.leg_raise_mode import (
    LegRaiseConfig,
    LegRaiseTracker,
    infer_joint_from_segment,
    leg_elevation_angle,
)

HIP = np.array([0.0, 0.0, 500.0])
LEG_LEN = 800.0


def leg_at_angle(theta_deg, hip=HIP, length=LEG_LEN):
    """Ankle position for a straight leg raised theta_deg above horizontal."""
    t = math.radians(theta_deg)
    return hip + np.array([0.0, length * math.cos(t), length * math.sin(t)])


def make_frame(idx, *, left=None, right=None, conf=1.0, cams=2):
    """Build a COCO-17 frame. left/right are (hip, knee, ankle) triples."""
    joints = [None] * len(JOINT_NAMES)
    confs = [conf] * len(JOINT_NAMES)
    camlist = [cams] * len(JOINT_NAMES)

    def place(side, triple):
        if triple is None:
            return
        hip, knee, ankle = triple
        for name, pt in ((f"{side}_hip", hip), (f"{side}_knee", knee),
                         (f"{side}_ankle", ankle)):
            joints[JOINT_NAME_TO_INDEX[name]] = None if pt is None else list(pt)

    place("left", left)
    place("right", right)
    return {"frame_index": idx, "joints": joints, "joint_conf": confs,
            "joint_cams": camlist}


# --- elevation angle --------------------------------------------------------
def test_elevation_angle_flat_and_vertical():
    assert leg_elevation_angle(HIP, ankle=leg_at_angle(0)) == 0.0
    assert abs(leg_elevation_angle(HIP, ankle=leg_at_angle(90)) - 90.0) < 1e-6


def test_elevation_angle_partial():
    assert abs(leg_elevation_angle(HIP, ankle=leg_at_angle(60)) - 60.0) < 1e-6
    assert abs(leg_elevation_angle(HIP, ankle=leg_at_angle(45)) - 45.0) < 1e-6


def test_elevation_falls_back_to_knee_when_ankle_missing():
    knee = leg_at_angle(30, length=400.0)
    assert abs(leg_elevation_angle(HIP, knee=knee, ankle=None) - 30.0) < 1e-6


def test_elevation_none_without_points():
    assert leg_elevation_angle(None) is None


# --- constrained inference gating ------------------------------------------
def test_infer_joint_disabled_by_default():
    knee = np.array([0.0, 0.0, 500.0])
    prev_ankle = np.array([0.0, 0.0, 900.0])
    assert infer_joint_from_segment(knee, prev_ankle, 400.0, enabled=False) is None


def test_infer_joint_enabled_respects_segment_length():
    knee = np.array([0.0, 0.0, 500.0])
    prev_ankle = np.array([0.0, 0.0, 900.0])
    out = infer_joint_from_segment(knee, prev_ankle, 400.0, enabled=True)
    assert out is not None
    assert abs(np.linalg.norm(out - knee) - 400.0) < 1e-6


# --- rep counting -----------------------------------------------------------
def test_counts_right_leg_reps():
    cfg = LegRaiseConfig(left_right_lock=False, segment_length_prior=False,
                         calibration_frames=0)
    tracker = LegRaiseTracker(cfg)
    flat_left = (HIP, leg_at_angle(0, length=400), leg_at_angle(0))
    last = None
    for i, theta in enumerate([10, 90, 10, 90, 10]):
        right = (HIP, leg_at_angle(theta / 2, length=400), leg_at_angle(theta))
        last = tracker.process(make_frame(i, left=flat_left, right=right))
    assert last.right.reps == 2
    assert tracker.summary()["right_reps"] == 2


def test_tracking_reports_angle_and_phase():
    cfg = LegRaiseConfig(left_right_lock=False, segment_length_prior=False,
                         calibration_frames=0)
    tracker = LegRaiseTracker(cfg)
    right = (HIP, leg_at_angle(45, length=400), leg_at_angle(90))
    state = tracker.process(make_frame(0, right=right))
    assert state.phase == "tracking"
    assert abs(state.right.angle_deg - 90.0) < 1e-6
    assert state.right.camera_count == 2.0


def test_calibration_phase_first():
    tracker = LegRaiseTracker(LegRaiseConfig(calibration_frames=15))
    full = (HIP, leg_at_angle(0, length=400), leg_at_angle(0))
    state = tracker.process(make_frame(0, left=full, right=full))
    assert state.phase == "calibrating"


# --- single-camera recovery gating -----------------------------------------
def _calibrate_then_drop_ankle(allow_inference):
    cfg = LegRaiseConfig(left_right_lock=False, segment_length_prior=True,
                         calibration_frames=5,
                         allow_constrained_inference=allow_inference)
    tracker = LegRaiseTracker(cfg)
    knee = leg_at_angle(0, length=400)
    ankle = leg_at_angle(0)
    full = (HIP, knee, ankle)
    for i in range(5):
        tracker.process(make_frame(i, left=full, right=full))
    # frame 6: right ankle drops out (single-camera-style loss)
    dropped = (HIP, knee, None)
    return tracker.process(make_frame(5, left=full, right=dropped))


def test_single_cam_recovery_disabled_by_default():
    state = _calibrate_then_drop_ankle(allow_inference=False)
    assert state.right.inferred_joints == []


def test_single_cam_recovery_when_explicitly_enabled():
    state = _calibrate_then_drop_ankle(allow_inference=True)
    assert "right_ankle" in state.right.inferred_joints


# --- isolation from squat/push-up paths ------------------------------------
def test_leg_raise_does_not_alter_squat_pushup_kinematics():
    full_left = (HIP, leg_at_angle(20, length=400), leg_at_angle(40))
    full_right = (HIP, leg_at_angle(25, length=400), leg_at_angle(50))
    frame = make_frame(0, left=full_left, right=full_right)

    before = frame_kinematics(frame)
    LegRaiseTracker(LegRaiseConfig()).process(frame)
    after = frame_kinematics(frame)
    assert before == after  # leg-raise mode mutates no shared kinematics state
