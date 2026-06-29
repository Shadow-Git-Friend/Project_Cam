"""Supine (lying) leg-raise tracking as a post-processor over COCO-17 joints.

The generic 3D skeleton makes a lying leg raise hard to read: which leg is up,
and how far. This mode is an exercise-specific layer ON TOP of the existing
triangulated joints -- it does not retrain the pose model and does not change the
behaviour of the squat or push-up paths. It:

- computes a per-leg elevation angle (leg vector vs the horizontal floor plane),
- locks left/right identity over time (``limb_identity``),
- guards each frame's geometry with a segment-length prior (``limb_constraints``),
- counts reps and reports, per leg, the angle, confidence, contributing camera
  count, identity-lock status, and whether a joint was directly triangulated.

Single-camera joint *recovery* is OFF unless explicitly enabled in the config:
joints have no floor-plane prior (unlike the ball), so we never silently
fabricate a 3D leg position.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import List, Optional

import numpy as np

from ..joints import JOINT_NAME_TO_INDEX, JOINT_NAMES
from .limb_constraints import (
    LegSegmentPrior,
    _pt,
    accept_by_segment_prior,
    calibrate_segment_lengths,
)
from .limb_identity import IdentityResult, LegPose, LimbIdentityTracker


@dataclass
class LegRaiseConfig:
    side: str = "alternating"            # "left" | "right" | "alternating"
    min_angle_deg: float = 60.0
    target_angle_deg: float = 90.0
    conf_min: float = 0.25
    max_reproj_px: float = 70.0
    left_right_lock: bool = True
    segment_length_prior: bool = True
    segment_tolerance: float = 0.25
    calibration_frames: int = 15         # short straight-leg hold at session start
    allow_constrained_inference: bool = False


@dataclass
class LegState:
    angle_deg: Optional[float]
    confidence: float
    camera_count: float                  # mean contributing cams across the 3 joints
    reps: int
    inferred_joints: List[str] = field(default_factory=list)
    rejected_by_prior: bool = False


@dataclass
class LegRaiseFrameState:
    frame_index: Optional[int]
    phase: str                           # "calibrating" | "tracking"
    identity_status: str
    swapped: bool
    left: LegState
    right: LegState

    def to_dict(self) -> dict:
        return asdict(self)


def leg_elevation_angle(hip, knee=None, ankle=None) -> Optional[float]:
    """Elevation of the leg above the horizontal plane, in degrees [0, 90].

    Uses the hip->ankle vector when available (whole-leg elevation), else the
    hip->knee vector (thigh elevation). Lying flat ~ 0 deg; raised vertical ~ 90.
    The angle is ``atan2(dz, horizontal)`` so it is independent of which floor
    direction the body points along.
    """
    h = _pt(hip)
    distal = _pt(ankle) if ankle is not None else None
    if distal is None:
        distal = _pt(knee) if knee is not None else None
    if h is None or distal is None:
        return None
    delta = distal - h
    horizontal = float(math.hypot(float(delta[0]), float(delta[1])))
    vertical = float(delta[2])
    if horizontal < 1e-9 and abs(vertical) < 1e-9:
        return None
    return float(math.degrees(math.atan2(abs(vertical), horizontal)))


def infer_joint_from_segment(
    proximal,
    prev_distal,
    segment_mm: float,
    *,
    enabled: bool,
) -> Optional[np.ndarray]:
    """Constrained estimate of a missing distal joint along the prior direction.

    Returns None unless ``enabled``. When enabled and the previous distal joint
    and proximal joint are known, it places the joint at ``segment_mm`` from the
    proximal joint along the last-known direction. This is the only sanctioned
    single-view fallback for leg joints, and it is opt-in by design.
    """
    if not enabled:
        return None
    p = _pt(proximal)
    prev = _pt(prev_distal)
    if p is None or prev is None or segment_mm <= 0:
        return None
    direction = prev - p
    n = float(np.linalg.norm(direction))
    if n < 1e-9:
        return None
    return p + (direction / n) * segment_mm


class _RepCounter:
    """down -> up (>= target) -> down (< min) counts one rep, with hysteresis."""

    def __init__(self, min_angle: float, target_angle: float):
        self.min_angle = min_angle
        self.target_angle = target_angle
        self.count = 0
        self._up = False

    def update(self, angle: Optional[float]) -> int:
        if angle is None:
            return self.count
        if not self._up and angle >= self.target_angle:
            self._up = True
        elif self._up and angle <= self.min_angle:
            self._up = False
            self.count += 1
        return self.count


class LegRaiseTracker:
    """Stateful per-session leg-raise tracker. ``process(frame)`` per frame."""

    def __init__(self, config: Optional[LegRaiseConfig] = None):
        self.config = config or LegRaiseConfig()
        self._identity = (
            LimbIdentityTracker() if self.config.left_right_lock else None
        )
        self._calib_left: List[tuple] = []
        self._calib_right: List[tuple] = []
        self._prior_left: Optional[LegSegmentPrior] = None
        self._prior_right: Optional[LegSegmentPrior] = None
        self._rep_left = _RepCounter(self.config.min_angle_deg,
                                     self.config.target_angle_deg)
        self._rep_right = _RepCounter(self.config.min_angle_deg,
                                      self.config.target_angle_deg)
        self._prev_ankle = {"left": None, "right": None}
        self._frames = 0

    # -- joint extraction -------------------------------------------------- #
    def _joint(self, frame: dict, name: str):
        joints = frame.get("joints", [])
        conf = frame.get("joint_conf", [1.0] * len(JOINT_NAMES))
        idx = JOINT_NAME_TO_INDEX[name]
        if idx >= len(joints):
            return None
        c = conf[idx] if idx < len(conf) else 1.0
        if c is not None and float(c) < self.config.conf_min:
            return None
        return _pt(joints[idx])

    def _leg_conf(self, frame: dict, side: str) -> float:
        conf = frame.get("joint_conf", [1.0] * len(JOINT_NAMES))
        vals = []
        for j in (f"{side}_hip", f"{side}_knee", f"{side}_ankle"):
            idx = JOINT_NAME_TO_INDEX[j]
            if idx < len(conf) and conf[idx] is not None:
                vals.append(float(conf[idx]))
        return float(min(vals)) if vals else 0.0

    def _leg_cams(self, frame: dict, side: str) -> float:
        cams = frame.get("joint_cams", [0] * len(JOINT_NAMES))
        vals = []
        for j in (f"{side}_hip", f"{side}_knee", f"{side}_ankle"):
            idx = JOINT_NAME_TO_INDEX[j]
            if idx < len(cams):
                vals.append(int(cams[idx] or 0))
        return float(np.mean(vals)) if vals else 0.0

    def _build_leg(self, frame: dict, side: str) -> LegPose:
        return LegPose(
            hip=self._joint(frame, f"{side}_hip"),
            knee=self._joint(frame, f"{side}_knee"),
            ankle=self._joint(frame, f"{side}_ankle"),
        )

    # -- main step --------------------------------------------------------- #
    def process(self, frame: dict) -> LegRaiseFrameState:
        self._frames += 1
        left = self._build_leg(frame, "left")
        right = self._build_leg(frame, "right")

        phase = "calibrating" if self._frames <= self.config.calibration_frames \
            else "tracking"

        if phase == "calibrating":
            if left.hip is not None and left.knee is not None and left.ankle is not None:
                self._calib_left.append((left.hip, left.knee, left.ankle))
            if right.hip is not None and right.knee is not None and right.ankle is not None:
                self._calib_right.append((right.hip, right.knee, right.ankle))
        elif self.config.segment_length_prior and self._prior_left is None \
                and self._prior_right is None:
            self._prior_left = calibrate_segment_lengths(
                self._calib_left, tolerance=self.config.segment_tolerance)
            self._prior_right = calibrate_segment_lengths(
                self._calib_right, tolerance=self.config.segment_tolerance)
            if self._identity is not None:
                self._identity.prior_left = self._prior_left
                self._identity.prior_right = self._prior_right

        if self._identity is not None and phase == "tracking":
            ident: IdentityResult = self._identity.resolve(left, right)
            left, right = ident.left, ident.right
            status, swapped = ident.status, ident.swapped
        else:
            status, swapped = "cold_start", False

        left_state = self._leg_state(frame, "left", left, self._prior_left, self._rep_left)
        right_state = self._leg_state(frame, "right", right, self._prior_right, self._rep_right)

        return LegRaiseFrameState(
            frame_index=frame.get("frame_index"),
            phase=phase,
            identity_status=status,
            swapped=swapped,
            left=left_state,
            right=right_state,
        )

    def _leg_state(self, frame, side, leg: LegPose, prior, rep: _RepCounter) -> LegState:
        inferred: List[str] = []
        ankle = leg.ankle
        if ankle is None and leg.knee is not None and prior is not None and prior.reliable:
            ankle = infer_joint_from_segment(
                leg.knee, self._prev_ankle[side], prior.shin_mm,
                enabled=self.config.allow_constrained_inference)
            if ankle is not None:
                inferred.append(f"{side}_ankle")

        rejected = False
        if prior is not None and not accept_by_segment_prior(
                prior, leg.hip, leg.knee, ankle):
            rejected = True
            angle = None
        else:
            angle = leg_elevation_angle(leg.hip, leg.knee, ankle)

        if ankle is not None:
            self._prev_ankle[side] = ankle

        reps = rep.update(angle if not rejected else None)
        return LegState(
            angle_deg=angle,
            confidence=self._leg_conf(frame, side),
            camera_count=self._leg_cams(frame, side),
            reps=reps,
            inferred_joints=inferred,
            rejected_by_prior=rejected,
        )

    def summary(self) -> dict:
        return {
            "frames": self._frames,
            "left_reps": self._rep_left.count,
            "right_reps": self._rep_right.count,
            "left_right_swaps": self._identity.swap_count if self._identity else 0,
            "prior_left": asdict(self._prior_left) if self._prior_left else None,
            "prior_right": asdict(self._prior_right) if self._prior_right else None,
            "config": asdict(self.config),
        }
