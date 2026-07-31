"""Display-only mannequin avatar built from triangulated COCO-17 joints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Optional

import cv2
import numpy as np

from ..joints import JOINT_NAME_TO_INDEX, JOINT_NAMES

_TORSO_JOINTS = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
_TORSO_MARKERS = (
    ("upper_torso_center", ("left_shoulder", "right_shoulder")),
    ("lower_torso_center", ("left_hip", "right_hip")),
    ("torso_center", _TORSO_JOINTS),
)
_LIMB_SEGMENTS = (
    ("left_upper_arm", "left_shoulder", "left_elbow"),
    ("left_forearm", "left_elbow", "left_wrist"),
    ("right_upper_arm", "right_shoulder", "right_elbow"),
    ("right_forearm", "right_elbow", "right_wrist"),
    ("left_thigh", "left_hip", "left_knee"),
    ("left_shin", "left_knee", "left_ankle"),
    ("right_thigh", "right_hip", "right_knee"),
    ("right_shin", "right_knee", "right_ankle"),
)
_BODY_SEGMENTS = tuple((a, b) for _, a, b in _LIMB_SEGMENTS) + (
    ("left_shoulder", "right_shoulder"),
    ("left_hip", "right_hip"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
)


@dataclass(frozen=True)
class AvatarRenderConfig:
    """Visual tuning for the live mannequin avatar."""

    segment_marker_count: int = 2
    body_alpha: float = 0.85
    body_color_bgr: tuple[int, int, int] = (230, 230, 224)
    body_edge_bgr: tuple[int, int, int] = (160, 160, 154)
    marker_color_bgr: tuple[int, int, int] = (210, 85, 35)
    marker_outline_bgr: tuple[int, int, int] = (245, 245, 245)
    torso_alpha: float = 0.9
    limb_thickness_px: int = 14
    torso_thickness_px: int = 18
    marker_radius_px: int = 4
    shadow_color_bgr: tuple[int, int, int] = (22, 18, 16)
    shadow_thickness_px: int = 8


@dataclass(frozen=True)
class AvatarMarker:
    """One joint or virtual body marker in millimetres."""

    name: str
    xyz_mm: list[float]
    kind: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_virtual_markers(
    joints_3d,
    config: Optional[AvatarRenderConfig] = None,
) -> list[AvatarMarker]:
    """Build deterministic joint and virtual markers from COCO-17 joints."""

    cfg = config or AvatarRenderConfig()
    joints = _as_joint_array(joints_3d)
    markers: list[AvatarMarker] = []

    for name in JOINT_NAMES:
        point = _joint(joints, name)
        if point is not None:
            markers.append(AvatarMarker(
                name=f"joint_{name}",
                xyz_mm=_list3(point),
                kind="joint",
            ))

    for marker_name, names in _TORSO_MARKERS:
        pts = [_joint(joints, name) for name in names]
        if all(point is not None for point in pts):
            center = np.mean(np.asarray(pts, dtype=np.float64), axis=0)
            markers.append(AvatarMarker(
                name=marker_name,
                xyz_mm=_list3(center),
                kind="virtual",
            ))

    count = max(0, int(cfg.segment_marker_count))
    for segment_name, start_name, end_name in _LIMB_SEGMENTS:
        start = _joint(joints, start_name)
        end = _joint(joints, end_name)
        if start is None or end is None:
            continue
        for idx in range(1, count + 1):
            t = idx / float(count + 1)
            point = (1.0 - t) * start + t * end
            markers.append(AvatarMarker(
                name=f"{segment_name}_{idx:02d}",
                xyz_mm=_list3(point),
                kind="virtual",
            ))

    return sorted(markers, key=lambda marker: marker.name)


def draw_avatar_body_cv2(
    img: np.ndarray,
    joints_3d,
    project_fn: Callable,
    config: Optional[AvatarRenderConfig] = None,
    *,
    draw_body: bool = True,
    draw_markers: bool = True,
) -> np.ndarray:
    """Draw a mannequin-style avatar onto an existing BGR image."""

    cfg = config or AvatarRenderConfig()
    joints = _as_joint_array(joints_3d)
    if draw_body:
        _draw_shadow(img, joints, project_fn, cfg)
        overlay = img.copy()
        _draw_body(overlay, joints, project_fn, cfg)
        alpha = float(np.clip(cfg.body_alpha, 0.0, 1.0))
        cv2.addWeighted(overlay, alpha, img, 1.0 - alpha, 0.0, img)
    if draw_markers:
        _draw_markers(img, build_virtual_markers(joints, cfg), project_fn, cfg)
    return img


def _draw_body(img, joints, project_fn, cfg: AvatarRenderConfig) -> None:
    torso = [_joint(joints, name) for name in _TORSO_JOINTS]
    if all(point is not None for point in torso):
        torso_pts = np.asarray(torso, dtype=np.float64)
        screen, ok = project_fn(torso_pts)
        if np.all(ok):
            poly = np.asarray(screen, dtype=np.int32)
            cv2.fillConvexPoly(img, poly, cfg.body_color_bgr, cv2.LINE_AA)
            cv2.polylines(img, [poly], True, cfg.body_edge_bgr, 2, cv2.LINE_AA)

    for start_name, end_name in _BODY_SEGMENTS:
        start = _joint(joints, start_name)
        end = _joint(joints, end_name)
        if start is None or end is None:
            continue
        _draw_capsule(img, project_fn, start, end, cfg.limb_thickness_px,
                      cfg.body_color_bgr, cfg.body_edge_bgr)

    shoulder_center = _mean_joints(joints, ("left_shoulder", "right_shoulder"))
    nose = _joint(joints, "nose")
    if nose is not None:
        radius = _head_radius_px(joints, project_fn, cfg)
        screen, ok = project_fn(nose.reshape(1, 3))
        if ok[0]:
            p = _pt2(screen[0])
            cv2.circle(img, p, radius + 2, cfg.body_edge_bgr, -1, cv2.LINE_AA)
            cv2.circle(img, p, radius, cfg.body_color_bgr, -1, cv2.LINE_AA)
    elif shoulder_center is not None:
        head = shoulder_center + np.array([0.0, 0.0, 260.0], dtype=np.float64)
        screen, ok = project_fn(head.reshape(1, 3))
        if ok[0]:
            p = _pt2(screen[0])
            cv2.circle(img, p, max(10, cfg.limb_thickness_px), cfg.body_color_bgr,
                       -1, cv2.LINE_AA)


def _draw_shadow(img, joints, project_fn, cfg: AvatarRenderConfig) -> None:
    for start_name, end_name in _BODY_SEGMENTS:
        start = _joint(joints, start_name)
        end = _joint(joints, end_name)
        if start is None or end is None:
            continue
        p1 = start.copy()
        p2 = end.copy()
        p1[2] = 0.0
        p2[2] = 0.0
        screen, ok = project_fn(np.vstack([p1, p2]))
        if ok[0] and ok[1]:
            cv2.line(img, _pt2(screen[0]), _pt2(screen[1]), cfg.shadow_color_bgr,
                     max(1, int(cfg.shadow_thickness_px)), cv2.LINE_AA)


def _draw_capsule(img, project_fn, start, end, thickness, fill, edge) -> None:
    screen, ok = project_fn(np.vstack([start, end]))
    if not (ok[0] and ok[1]):
        return
    p1 = _pt2(screen[0])
    p2 = _pt2(screen[1])
    outer = max(1, int(thickness) + 3)
    inner = max(1, int(thickness))
    cv2.line(img, p1, p2, edge, outer, cv2.LINE_AA)
    cv2.circle(img, p1, outer // 2, edge, -1, cv2.LINE_AA)
    cv2.circle(img, p2, outer // 2, edge, -1, cv2.LINE_AA)
    cv2.line(img, p1, p2, fill, inner, cv2.LINE_AA)
    cv2.circle(img, p1, inner // 2, fill, -1, cv2.LINE_AA)
    cv2.circle(img, p2, inner // 2, fill, -1, cv2.LINE_AA)


def _draw_markers(
    img: np.ndarray,
    markers: list[AvatarMarker],
    project_fn: Callable,
    cfg: AvatarRenderConfig,
) -> None:
    if not markers:
        return
    points = np.asarray([marker.xyz_mm for marker in markers], dtype=np.float64)
    screen, ok = project_fn(points)
    for idx, good in enumerate(ok):
        if not good:
            continue
        p = _pt2(screen[idx])
        radius = max(1, int(cfg.marker_radius_px))
        cv2.circle(img, p, radius + 2, cfg.marker_outline_bgr, -1, cv2.LINE_AA)
        cv2.circle(img, p, radius, cfg.marker_color_bgr, -1, cv2.LINE_AA)


def _head_radius_px(joints, project_fn, cfg: AvatarRenderConfig) -> int:
    left = _joint(joints, "left_ear")
    if left is None:
        left = _joint(joints, "left_shoulder")
    right = _joint(joints, "right_ear")
    if right is None:
        right = _joint(joints, "right_shoulder")
    if left is None or right is None:
        return max(10, int(cfg.limb_thickness_px))
    screen, ok = project_fn(np.vstack([left, right]))
    if not (ok[0] and ok[1]):
        return max(10, int(cfg.limb_thickness_px))
    dist = float(np.linalg.norm(screen[0] - screen[1]))
    return int(np.clip(dist * 0.32, 10.0, 28.0))


def _mean_joints(joints, names) -> Optional[np.ndarray]:
    pts = [_joint(joints, name) for name in names]
    if not all(point is not None for point in pts):
        return None
    return np.mean(np.asarray(pts, dtype=np.float64), axis=0)


def _as_joint_array(joints_3d) -> np.ndarray:
    arr = np.asarray(joints_3d, dtype=np.float64)
    if arr.shape != (len(JOINT_NAMES), 3):
        out = np.full((len(JOINT_NAMES), 3), np.nan, dtype=np.float64)
        flat = arr.reshape(-1, 3) if arr.size else np.empty((0, 3), dtype=np.float64)
        n = min(len(out), len(flat))
        out[:n] = flat[:n]
        return out
    return arr


def _joint(joints: np.ndarray, name: str) -> Optional[np.ndarray]:
    idx = JOINT_NAME_TO_INDEX[name]
    point = joints[idx]
    if point.shape[0] < 3 or not np.isfinite(point).all():
        return None
    return point.astype(np.float64, copy=False)


def _list3(point: np.ndarray) -> list[float]:
    return [float(point[0]), float(point[1]), float(point[2])]


def _pt2(point) -> tuple[int, int]:
    return int(round(float(point[0]))), int(round(float(point[1])))
