"""Contact-aware interpretation for triangulated COCO-17 skeleton frames.

This module turns the project paper takeaways into a lightweight diagnostic
layer over the existing 3D joints. It does not fit SMPL, infer pressure maps,
or mutate pose points. It estimates support/contact state, a coarse center of
mass proxy, and temporal static-raised-limb warnings from already-triangulated
joints.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional

import numpy as np

from ..joints import JOINT_NAME_TO_INDEX, JOINT_NAMES

_SUPPORT_CANDIDATES = (
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)

_TORSO_COM_JOINTS = (
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
)

_DISTAL_JOINTS = (
    "left_wrist",
    "right_wrist",
    "left_ankle",
    "right_ankle",
)


@dataclass(frozen=True)
class ContactInterpretationConfig:
    """Tunable gates for contact-aware skeleton interpretation."""

    support_z_mm: Optional[float] = None
    contact_tolerance_mm: float = 80.0
    penetration_tolerance_mm: float = 50.0
    min_confidence: float = 0.25
    min_cameras: int = 2
    min_support_contacts: int = 2
    max_com_support_distance_mm: float = 450.0
    static_raise_mm: float = 250.0
    static_velocity_mm_s: float = 40.0


@dataclass(frozen=True)
class ContactPoint:
    """One reliable joint interpreted as touching the support plane."""

    name: str
    xyz_mm: list[float]
    distance_to_support_mm: float
    confidence: float
    camera_count: int


@dataclass
class ContactInterpretation:
    """JSON-ready interpretation payload for one frame."""

    frame_index: Optional[int]
    support_z_mm: float
    support_status: str
    contacts: list[ContactPoint] = field(default_factory=list)
    support_center_xy_mm: Optional[list[float]] = None
    support_polygon_xy_mm: list[list[float]] = field(default_factory=list)
    proxy_com_xyz_mm: Optional[list[float]] = None
    com_to_support_xy_mm: Optional[float] = None
    raised_static_joints: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class ContactAwarePoseInterpreter:
    """Stateful wrapper that adds velocity-based diagnostics."""

    def __init__(self, config: Optional[ContactInterpretationConfig] = None):
        self.config = config or ContactInterpretationConfig()
        self._prev_points: dict[str, np.ndarray] = {}
        self._prev_time_s: Optional[float] = None

    def reset(self) -> None:
        self._prev_points.clear()
        self._prev_time_s = None

    def process(self, frame: dict) -> ContactInterpretation:
        result = interpret_contact(frame, self.config)
        current = _reliable_points(frame, self.config, _DISTAL_JOINTS)
        time_s = _frame_time_s(frame)
        dt = None
        if time_s is not None and self._prev_time_s is not None:
            dt = max(0.0, time_s - self._prev_time_s)

        if dt is not None and dt > 1e-9:
            raised_static = []
            for name in _DISTAL_JOINTS:
                point = current.get(name)
                prev = self._prev_points.get(name)
                if point is None or prev is None:
                    continue
                height = float(point[2] - result.support_z_mm)
                if height < self.config.static_raise_mm:
                    continue
                velocity = float(np.linalg.norm(point - prev) / dt)
                if velocity <= self.config.static_velocity_mm_s:
                    raised_static.append(name)
            if raised_static:
                result.raised_static_joints = raised_static
                _add_flag(result.flags, "static_raised_joint")

        self._prev_points = current
        self._prev_time_s = time_s
        return result


def interpret_contact(
    frame: dict,
    config: Optional[ContactInterpretationConfig] = None,
) -> ContactInterpretation:
    """Interpret support/contact state for one triangulated skeleton frame."""

    cfg = config or ContactInterpretationConfig()
    support_points = _reliable_points(frame, cfg, _SUPPORT_CANDIDATES)
    all_points = _reliable_points(frame, cfg, JOINT_NAMES)
    flags: list[str] = []

    support_z = _support_z(cfg, support_points.values(), all_points.values())
    contacts, penetration_names = _contact_points(frame, cfg, support_points, support_z)
    if penetration_names:
        _add_flag(flags, "support_penetration")

    support_status = _support_status(len(contacts), cfg.min_support_contacts)
    if support_status == "unsupported":
        _add_flag(flags, "no_support_contacts")
    elif support_status == "weak_support":
        _add_flag(flags, "weak_support")

    center_xy = _weighted_contact_center(contacts)
    polygon_xy = _convex_hull_xy([point.xyz_mm[:2] for point in contacts])
    proxy_com = _proxy_com(all_points)
    com_distance = _xy_distance(proxy_com, center_xy)
    if (
        com_distance is not None
        and com_distance > cfg.max_com_support_distance_mm
    ):
        _add_flag(flags, "com_far_from_support")
    if proxy_com is None:
        _add_flag(flags, "no_proxy_com")

    return ContactInterpretation(
        frame_index=_frame_index(frame),
        support_z_mm=float(support_z),
        support_status=support_status,
        contacts=contacts,
        support_center_xy_mm=center_xy,
        support_polygon_xy_mm=polygon_xy,
        proxy_com_xyz_mm=proxy_com,
        com_to_support_xy_mm=com_distance,
        flags=flags,
    )


def _contact_points(
    frame: dict,
    cfg: ContactInterpretationConfig,
    points: dict[str, np.ndarray],
    support_z: float,
) -> tuple[list[ContactPoint], list[str]]:
    contacts: list[ContactPoint] = []
    penetration_names: list[str] = []
    for name, point in points.items():
        dist = float(point[2] - support_z)
        if dist < -abs(cfg.penetration_tolerance_mm):
            penetration_names.append(name)
        if abs(dist) > cfg.contact_tolerance_mm:
            continue
        contacts.append(ContactPoint(
            name=name,
            xyz_mm=_list3(point),
            distance_to_support_mm=dist,
            confidence=_joint_conf(frame, name),
            camera_count=_joint_cams(frame, name),
        ))
    return contacts, penetration_names


def _support_z(
    cfg: ContactInterpretationConfig,
    support_points: Iterable[np.ndarray],
    all_points: Iterable[np.ndarray],
) -> float:
    if cfg.support_z_mm is not None:
        return float(cfg.support_z_mm)
    candidates = list(support_points) or list(all_points)
    if not candidates:
        return 0.0
    return float(min(float(point[2]) for point in candidates))


def _support_status(contact_count: int, min_contacts: int) -> str:
    if contact_count <= 0:
        return "unsupported"
    if contact_count < max(1, int(min_contacts)):
        return "weak_support"
    return "supported"


def _weighted_contact_center(contacts: list[ContactPoint]) -> Optional[list[float]]:
    if not contacts:
        return None
    weights = np.asarray([
        max(0.01, point.confidence) * max(1, point.camera_count)
        for point in contacts
    ], dtype=float)
    xy = np.asarray([point.xyz_mm[:2] for point in contacts], dtype=float)
    center = np.average(xy, axis=0, weights=weights)
    return [float(center[0]), float(center[1])]


def _proxy_com(points: dict[str, np.ndarray]) -> Optional[list[float]]:
    torso = [points[name] for name in _TORSO_COM_JOINTS if name in points]
    if len(torso) >= 2:
        return _list3(np.mean(np.asarray(torso, dtype=float), axis=0))
    hips = [points[name] for name in ("left_hip", "right_hip") if name in points]
    if hips:
        return _list3(np.mean(np.asarray(hips, dtype=float), axis=0))
    if points:
        return _list3(np.mean(np.asarray(list(points.values()), dtype=float), axis=0))
    return None


def _xy_distance(
    point_xyz: Optional[list[float]],
    center_xy: Optional[list[float]],
) -> Optional[float]:
    if point_xyz is None or center_xy is None:
        return None
    return float(np.linalg.norm(
        np.asarray(point_xyz[:2], dtype=float) - np.asarray(center_xy, dtype=float)
    ))


def _reliable_points(
    frame: dict,
    cfg: ContactInterpretationConfig,
    names: Iterable[str],
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for name in names:
        point = _joint_point(frame, name)
        if point is None:
            continue
        if _joint_conf(frame, name) < cfg.min_confidence:
            continue
        if _joint_cams(frame, name) < cfg.min_cameras:
            continue
        out[name] = point
    return out


def _joint_point(frame: dict, name: str) -> Optional[np.ndarray]:
    idx = JOINT_NAME_TO_INDEX[name]
    joints = frame.get("joints") or []
    if idx >= len(joints):
        return None
    raw = joints[idx]
    if raw is None:
        return None
    try:
        point = np.asarray(raw, dtype=float).reshape(-1)[:3]
    except (TypeError, ValueError):
        return None
    if point.shape[0] < 3 or not np.isfinite(point).all():
        return None
    return point


def _joint_conf(frame: dict, name: str) -> float:
    idx = JOINT_NAME_TO_INDEX[name]
    conf = frame.get("joint_conf") or []
    if idx >= len(conf) or conf[idx] is None:
        return 1.0
    try:
        value = float(conf[idx])
    except (TypeError, ValueError):
        return 0.0
    return value if np.isfinite(value) else 0.0


def _joint_cams(frame: dict, name: str) -> int:
    idx = JOINT_NAME_TO_INDEX[name]
    cams = frame.get("joint_cams") or []
    if idx >= len(cams) or cams[idx] is None:
        return 0
    try:
        return max(0, int(cams[idx]))
    except (TypeError, ValueError):
        return 0


def _frame_index(frame: dict) -> Optional[int]:
    value = frame.get("frame_index")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _frame_time_s(frame: dict) -> Optional[float]:
    value = frame.get("time_s")
    if value is None:
        return None
    try:
        time_s = float(value)
    except (TypeError, ValueError):
        return None
    return time_s if np.isfinite(time_s) else None


def _convex_hull_xy(points: list[list[float]]) -> list[list[float]]:
    unique = sorted({(float(p[0]), float(p[1])) for p in points})
    if len(unique) <= 2:
        return [[x, y] for x, y in unique]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    return [[float(x), float(y)] for x, y in hull]


def _list3(point: np.ndarray) -> list[float]:
    return [float(point[0]), float(point[1]), float(point[2])]


def _add_flag(flags: list[str], value: str) -> None:
    if value not in flags:
        flags.append(value)
