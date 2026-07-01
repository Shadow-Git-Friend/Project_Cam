"""COCO-17 to SMPL joint mapping for Project_Cam avatar fitting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np

SMPL_JOINT_NAMES = [
    "pelvis",
    "left_hip",
    "right_hip",
    "spine1",
    "left_knee",
    "right_knee",
    "spine2",
    "left_ankle",
    "right_ankle",
    "spine3",
    "left_foot",
    "right_foot",
    "neck",
    "left_collar",
    "right_collar",
    "head",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hand",
    "right_hand",
]

_SMPL_NAME_TO_INDEX = {name: idx for idx, name in enumerate(SMPL_JOINT_NAMES)}

COCO_TO_SMPL = {
    0: _SMPL_NAME_TO_INDEX["head"],
    5: _SMPL_NAME_TO_INDEX["left_shoulder"],
    6: _SMPL_NAME_TO_INDEX["right_shoulder"],
    7: _SMPL_NAME_TO_INDEX["left_elbow"],
    8: _SMPL_NAME_TO_INDEX["right_elbow"],
    9: _SMPL_NAME_TO_INDEX["left_wrist"],
    10: _SMPL_NAME_TO_INDEX["right_wrist"],
    11: _SMPL_NAME_TO_INDEX["left_hip"],
    12: _SMPL_NAME_TO_INDEX["right_hip"],
    13: _SMPL_NAME_TO_INDEX["left_knee"],
    14: _SMPL_NAME_TO_INDEX["right_knee"],
    15: _SMPL_NAME_TO_INDEX["left_ankle"],
    16: _SMPL_NAME_TO_INDEX["right_ankle"],
}


@dataclass(frozen=True)
class SmplJointTargets:
    """SMPL joint targets derived from one COCO-17 3D frame."""

    smpl_indices: np.ndarray
    points_mm: np.ndarray
    weights: np.ndarray
    names: list[str]


def extract_smpl_targets(
    coco_joints_mm,
    confidences: Optional[Iterable[float]] = None,
    *,
    min_confidence: float = 0.25,
    include_head: bool = False,
) -> SmplJointTargets:
    """Extract reliable SMPL joint targets from a COCO-17 3D frame."""

    joints = _as_coco_array(coco_joints_mm)
    conf = _as_confidences(confidences)
    indices: list[int] = []
    points: list[np.ndarray] = []
    weights: list[float] = []
    names: list[str] = []

    for coco_idx, smpl_idx in sorted(COCO_TO_SMPL.items(), key=lambda item: item[1]):
        if coco_idx == 0 and not include_head:
            continue
        point = joints[coco_idx]
        if not np.isfinite(point).all():
            continue
        weight = float(conf[coco_idx])
        if weight < float(min_confidence):
            continue
        indices.append(int(smpl_idx))
        points.append(point.astype(np.float64, copy=False))
        weights.append(weight)
        names.append(SMPL_JOINT_NAMES[smpl_idx])

    return SmplJointTargets(
        smpl_indices=np.asarray(indices, dtype=np.int64),
        points_mm=np.asarray(points, dtype=np.float64).reshape(-1, 3),
        weights=np.asarray(weights, dtype=np.float64),
        names=names,
    )


def _as_coco_array(coco_joints_mm) -> np.ndarray:
    arr = np.asarray(coco_joints_mm, dtype=np.float64)
    if arr.shape == (17, 3):
        return arr
    out = np.full((17, 3), np.nan, dtype=np.float64)
    flat = arr.reshape(-1, 3) if arr.size else np.empty((0, 3), dtype=np.float64)
    n = min(len(out), len(flat))
    out[:n] = flat[:n]
    return out


def _as_confidences(confidences) -> np.ndarray:
    if confidences is None:
        return np.ones((17,), dtype=np.float64)
    out = np.zeros((17,), dtype=np.float64)
    arr = np.asarray(list(confidences), dtype=np.float64).reshape(-1)
    n = min(len(out), len(arr))
    out[:n] = arr[:n]
    out[~np.isfinite(out)] = 0.0
    return out
