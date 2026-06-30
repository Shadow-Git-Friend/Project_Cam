"""Live-arena helpers for supine leg-raise skeleton stabilization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import MutableMapping

import numpy as np

from .limb_identity import LegPose, LimbIdentityTracker

_LEFT_LEG = (11, 13, 15)
_RIGHT_LEG = (12, 14, 16)
_LOWER_BODY = _LEFT_LEG + _RIGHT_LEG
_DEPENDENT_ANKLES = {13: 15, 14: 16}


@dataclass(frozen=True)
class LegIdentityLockResult:
    swapped: bool
    status: str
    keep_cost: float | None
    swap_cost: float | None


def apply_leg_identity_lock(
    joints_3d_now: MutableMapping[int, np.ndarray],
    joint_conf_state,
    joint_cam_state,
    tracker: LimbIdentityTracker,
) -> LegIdentityLockResult:
    """Apply temporal left/right leg identity lock to live 3D joints.

    ``LimbIdentityTracker`` decides whether the current lower-body labels are
    swapped relative to the previous frame. When they are, this function rewrites
    the live joint dict plus confidence/camera metadata before the viewer's EMA
    consumes the points.
    """
    result = tracker.resolve(
        _pose_from_joints(joints_3d_now, _LEFT_LEG),
        _pose_from_joints(joints_3d_now, _RIGHT_LEG),
    )
    if result.swapped:
        for left_idx, right_idx in zip(_LEFT_LEG, _RIGHT_LEG):
            _swap_joint(joints_3d_now, left_idx, right_idx)
            joint_conf_state[left_idx], joint_conf_state[right_idx] = (
                joint_conf_state[right_idx],
                joint_conf_state[left_idx],
            )
            joint_cam_state[left_idx], joint_cam_state[right_idx] = (
                joint_cam_state[right_idx],
                joint_cam_state[left_idx],
            )
    return LegIdentityLockResult(
        swapped=bool(result.swapped),
        status=result.status,
        keep_cost=result.keep_cost,
        swap_cost=result.swap_cost,
    )


def apply_leg_segment_drops(
    joints_3d_now: MutableMapping[int, np.ndarray],
    joint_conf_state,
    joint_cam_state,
    drops: set[int],
) -> set[int]:
    """Drop invalid leg joints and metadata before the live EMA consumes them."""
    expanded = set(int(j) for j in drops)
    for joint_idx, ankle_idx in _DEPENDENT_ANKLES.items():
        if joint_idx in expanded:
            expanded.add(ankle_idx)
    for joint_idx in expanded:
        joints_3d_now.pop(joint_idx, None)
        joint_conf_state[joint_idx] = 0.0
        joint_cam_state[joint_idx] = 0
    return expanded


def lower_body_snapshot(joints: MutableMapping[int, np.ndarray]) -> dict[str, list[float] | None]:
    """JSON-ready snapshot of lower-body 3D points for diagnostics."""
    return {str(idx): _point_list(joints.get(idx)) for idx in _LOWER_BODY}


def lower_body_pose2d_snapshot(per_cam_pose: dict) -> dict[str, dict[str, dict] | None]:
    """JSON-ready lower-body 2D keypoints/scores by camera."""
    out: dict[str, dict[str, dict] | None] = {}
    for cam, pose in per_cam_pose.items():
        if pose is None:
            out[str(cam)] = None
            continue
        try:
            kpts, scores = pose
        except (TypeError, ValueError):
            out[str(cam)] = None
            continue
        cam_out = {}
        for idx in _LOWER_BODY:
            cam_out[str(idx)] = {
                "xy": _point2_list(kpts, idx),
                "score": _score_value(scores, idx),
            }
        out[str(cam)] = cam_out
    return out


def segment_lengths_snapshot(joints: MutableMapping[int, np.ndarray]) -> dict[str, float | None]:
    """JSON-ready lower-body segment lengths in millimetres."""
    return {
        "left_femur_mm": _segment_len(joints.get(11), joints.get(13)),
        "left_tibia_mm": _segment_len(joints.get(13), joints.get(15)),
        "right_femur_mm": _segment_len(joints.get(12), joints.get(14)),
        "right_tibia_mm": _segment_len(joints.get(14), joints.get(16)),
    }


def _pose_from_joints(joints: MutableMapping[int, np.ndarray], indices) -> LegPose:
    hip_idx, knee_idx, ankle_idx = indices
    return LegPose.of(
        hip=joints.get(hip_idx),
        knee=joints.get(knee_idx),
        ankle=joints.get(ankle_idx),
    )


def _swap_joint(joints: MutableMapping[int, np.ndarray], left_idx: int, right_idx: int) -> None:
    left = joints.get(left_idx)
    right = joints.get(right_idx)
    if right is None:
        joints.pop(left_idx, None)
    else:
        joints[left_idx] = np.asarray(right, dtype=float)
    if left is None:
        joints.pop(right_idx, None)
    else:
        joints[right_idx] = np.asarray(left, dtype=float)


def _point_list(value) -> list[float] | None:
    if value is None:
        return None
    try:
        arr = np.asarray(value, dtype=float).reshape(-1)[:3]
    except (TypeError, ValueError):
        return None
    if arr.shape[0] < 3 or not np.isfinite(arr).all():
        return None
    return [float(arr[0]), float(arr[1]), float(arr[2])]


def _point2_list(kpts, idx: int) -> list[float] | None:
    try:
        arr = np.asarray(kpts, dtype=float)
        xy = arr[idx, :2]
    except (IndexError, TypeError, ValueError):
        return None
    if xy.shape[0] < 2 or not np.isfinite(xy).all():
        return None
    return [float(xy[0]), float(xy[1])]


def _score_value(scores, idx: int) -> float | None:
    try:
        value = float(np.asarray(scores, dtype=float)[idx])
    except (IndexError, TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _segment_len(a, b) -> float | None:
    pa = _point_list(a)
    pb = _point_list(b)
    if pa is None or pb is None:
        return None
    return float(np.linalg.norm(np.asarray(pa, dtype=float) - np.asarray(pb, dtype=float)))
