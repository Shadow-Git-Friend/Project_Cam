"""3D kinematic measurements from COCO-17 Project_Cam joints."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .joints import JOINT_NAME_TO_INDEX, JOINT_NAMES

ANGLE_TRIPLETS = {
    "left_elbow": ("left_shoulder", "left_elbow", "left_wrist"),
    "right_elbow": ("right_shoulder", "right_elbow", "right_wrist"),
    "left_shoulder": ("left_elbow", "left_shoulder", "left_hip"),
    "right_shoulder": ("right_elbow", "right_shoulder", "right_hip"),
    "left_hip": ("left_shoulder", "left_hip", "left_knee"),
    "right_hip": ("right_shoulder", "right_hip", "right_knee"),
    "left_knee": ("left_hip", "left_knee", "left_ankle"),
    "right_knee": ("right_hip", "right_knee", "right_ankle"),
    "left_trunk_to_leg": ("left_shoulder", "left_hip", "left_ankle"),
    "right_trunk_to_leg": ("right_shoulder", "right_hip", "right_ankle"),
}


def angle_degrees(a: Any, b: Any, c: Any) -> float | None:
    """Return angle ABC in degrees, or None when a point is missing/degenerate."""
    pa, pb, pc = _as_point(a), _as_point(b), _as_point(c)
    if pa is None or pb is None or pc is None:
        return None
    v1 = pa - pb
    v2 = pc - pb
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 <= 1e-9 or n2 <= 1e-9:
        return None
    cos_val = float(np.dot(v1, v2) / (n1 * n2))
    cos_val = max(-1.0, min(1.0, cos_val))
    return float(math.degrees(math.acos(cos_val)))


def distance_mm(a: Any, b: Any) -> float | None:
    pa, pb = _as_point(a), _as_point(b)
    if pa is None or pb is None:
        return None
    return float(np.linalg.norm(pa - pb))


def frame_kinematics(frame: dict[str, Any]) -> dict[str, Any]:
    joints = frame.get("joints", [])
    joint_conf = frame.get("joint_conf", [0.0] * len(JOINT_NAMES))
    joint_cams = frame.get("joint_cams", [0] * len(JOINT_NAMES))
    angles = {}
    for name, (ja, jb, jc) in ANGLE_TRIPLETS.items():
        angles[name] = angle_degrees(_joint(joints, ja), _joint(joints, jb), _joint(joints, jc))

    pelvis_center = midpoint(_joint(joints, "left_hip"), _joint(joints, "right_hip"))
    distances = {
        "shoulder_width_mm": distance_mm(_joint(joints, "left_shoulder"), _joint(joints, "right_shoulder")),
        "hip_width_mm": distance_mm(_joint(joints, "left_hip"), _joint(joints, "right_hip")),
        "stance_width_mm": distance_mm(_joint(joints, "left_ankle"), _joint(joints, "right_ankle")),
        "pelvis_center_z_mm": float(pelvis_center[2]) if pelvis_center is not None else None,
    }
    distances["stance_width_by_shoulder"] = _safe_ratio(distances["stance_width_mm"], distances["shoulder_width_mm"])
    distances["stance_width_by_hip"] = _safe_ratio(distances["stance_width_mm"], distances["hip_width_mm"])

    asymmetry = {
        "elbow": _abs_delta(angles["left_elbow"], angles["right_elbow"]),
        "shoulder": _abs_delta(angles["left_shoulder"], angles["right_shoulder"]),
        "hip": _abs_delta(angles["left_hip"], angles["right_hip"]),
        "knee": _abs_delta(angles["left_knee"], angles["right_knee"]),
        "trunk_to_leg": _abs_delta(angles["left_trunk_to_leg"], angles["right_trunk_to_leg"]),
    }

    knee_line = {
        "left": knee_line_deviation_ratio(joints, "left"),
        "right": knee_line_deviation_ratio(joints, "right"),
    }
    knee_valgus = {
        "left": knee_valgus_signed_ratio(joints, "left"),
        "right": knee_valgus_signed_ratio(joints, "right"),
    }

    valid_joint_count = sum(1 for p in joints[: len(JOINT_NAMES)] if _as_point(p) is not None)
    return {
        "frame_index": frame.get("frame_index"),
        "time_s": frame.get("time_s"),
        "angles_deg": angles,
        "distances": distances,
        "asymmetry_deg": asymmetry,
        "knee_line_deviation_ratio": knee_line,
        "knee_valgus_signed_ratio": knee_valgus,
        "centers": {
            "pelvis": pelvis_center.tolist() if pelvis_center is not None else None,
        },
        "posture": posture_metrics(joints),
        "quality": {
            "valid_joint_count": valid_joint_count,
            "valid_joint_ratio": valid_joint_count / float(len(JOINT_NAMES)),
            "joint_conf": [float(v) for v in joint_conf[: len(JOINT_NAMES)]],
            "joint_cams": [int(v) for v in joint_cams[: len(JOINT_NAMES)]],
            "has_camera_counts": any(int(v) > 0 for v in joint_cams[: len(JOINT_NAMES)]),
        },
    }


def posture_metrics(joints: list[Any]) -> dict[str, Any]:
    """Body-orientation measures used to gate live exercise acquisition.

    ``torso_incline_deg`` is the inclination of the shoulder->hip line from
    the horizontal plane, in [0, 90]: ~0 = horizontal (push-up / plank),
    ~90 = vertical (standing / squat). None when the shoulders or hips are
    not both visible.
    """
    shoulder_mid = midpoint(_joint(joints, "left_shoulder"), _joint(joints, "right_shoulder"))
    hip_mid = midpoint(_joint(joints, "left_hip"), _joint(joints, "right_hip"))
    torso_incline_deg = None
    if shoulder_mid is not None and hip_mid is not None:
        delta = hip_mid - shoulder_mid
        horizontal = float(math.hypot(float(delta[0]), float(delta[1])))
        vertical = abs(float(delta[2]))
        if horizontal + vertical > 1e-6:
            torso_incline_deg = float(math.degrees(math.atan2(vertical, horizontal)))
    return {"torso_incline_deg": torso_incline_deg}


def knee_line_deviation_ratio(joints: list[Any], side: str) -> float | None:
    hip = _as_point(_joint(joints, f"{side}_hip"))
    knee = _as_point(_joint(joints, f"{side}_knee"))
    ankle = _as_point(_joint(joints, f"{side}_ankle"))
    if hip is None or knee is None or ankle is None:
        return None
    line = ankle - hip
    line_len = float(np.linalg.norm(line))
    if line_len <= 1e-9:
        return None
    return float(np.linalg.norm(np.cross(knee - hip, line)) / (line_len * line_len))


def knee_valgus_signed_ratio(joints: list[Any], side: str) -> float | None:
    """Signed knee deviation along the lateral body axis, normalized by leg length.

    Positive = knee medial to hip-ankle line (valgus / "drifts inward").
    Negative = knee lateral to hip-ankle line (varus / bowed out).
    Returns None when any required joint is missing or geometry is degenerate.
    """
    hip = _as_point(_joint(joints, f"{side}_hip"))
    knee = _as_point(_joint(joints, f"{side}_knee"))
    ankle = _as_point(_joint(joints, f"{side}_ankle"))
    other_hip_name = "right_hip" if side == "left" else "left_hip"
    other_hip = _as_point(_joint(joints, other_hip_name))
    if hip is None or knee is None or ankle is None or other_hip is None:
        return None
    leg = ankle - hip
    leg_len = float(np.linalg.norm(leg))
    if leg_len <= 1e-9:
        return None
    medial = other_hip - hip
    medial_len = float(np.linalg.norm(medial))
    if medial_len <= 1e-9:
        return None
    leg_unit = leg / leg_len
    medial_unit = medial / medial_len
    medial_perp = medial_unit - np.dot(medial_unit, leg_unit) * leg_unit
    medial_perp_len = float(np.linalg.norm(medial_perp))
    if medial_perp_len <= 1e-9:
        return None
    medial_perp /= medial_perp_len
    return float(np.dot(knee - hip, medial_perp) / leg_len)


def midpoint(a: Any, b: Any) -> np.ndarray | None:
    pa, pb = _as_point(a), _as_point(b)
    if pa is None or pb is None:
        return None
    return 0.5 * (pa + pb)


def _joint(joints: list[Any], name: str) -> Any:
    idx = JOINT_NAME_TO_INDEX[name]
    if idx >= len(joints):
        return None
    return joints[idx]


def _as_point(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    try:
        point = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if point.shape[0] < 3:
        return None
    point = point[:3]
    if not np.isfinite(point).all():
        return None
    return point


def _safe_ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or abs(den) <= 1e-9:
        return None
    return float(num / den)


def _abs_delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return float(abs(left - right))
