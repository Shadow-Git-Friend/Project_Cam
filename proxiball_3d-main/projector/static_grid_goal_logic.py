from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


SOUTH_WALL_X_MM = 6230.0
SOUTH_WALL_U_MAX_MM = 3050.0
SOUTH_WALL_V_MAX_MM = 2950.0
ZONE_LABELS = ("A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3")


@dataclass(frozen=True)
class WallRect:
    label: str
    u_min: float
    u_max: float
    v_min: float
    v_max: float

    def contains(self, u_mm: float, v_mm: float, pad_mm: float = 0.0) -> bool:
        return (
            self.u_min - pad_mm <= u_mm <= self.u_max + pad_mm
            and self.v_min - pad_mm <= v_mm <= self.v_max + pad_mm
        )

    @property
    def center(self) -> tuple[float, float]:
        return (0.5 * (self.u_min + self.u_max), 0.5 * (self.v_min + self.v_max))


@dataclass(frozen=True)
class GoalEvent:
    zone_label: str
    u_mm: float
    v_mm: float
    t_sec: float
    speed_mm_s: float
    peak_speed_mm_s: float
    track_id: int | str = 0


@dataclass(frozen=True)
class ConsensusZone:
    zone_label: str
    u_mm: float
    v_mm: float
    voting_cams: tuple[str, ...]
    zone_votes: dict[str, tuple[str, ...]]
    per_cam_zones: dict[str, str | None]


@dataclass(frozen=True)
class WallBounds:
    u_min: float
    u_max: float
    v_min: float
    v_max: float


def target_grid_rectangles(
    u_max: float = SOUTH_WALL_U_MAX_MM,
    v_max: float = SOUTH_WALL_V_MAX_MM,
    cols: int = 3,
    rows: int = 3,
    *,
    u_min: float = 0.0,
    v_min: float = 0.0,
) -> list[WallRect]:
    """Return the static 3x3 grid from projector_sim.TargetGridDrill.

    Wall coordinates:
      U: east-to-west across the south wall, in millimetres.
      V: floor-to-ceiling, in millimetres.
    """

    u_span = float(u_max) - float(u_min)
    v_span = float(v_max) - float(v_min)
    u0, u1 = u_min + u_span * 0.08, u_min + u_span * 0.92
    v0, v1 = v_min + v_span * 0.06, v_min + v_span * 0.82
    cell_u, cell_v = (u1 - u0) / cols, (v1 - v0) / rows
    pad_u, pad_v = cell_u * 0.05, cell_v * 0.05

    rects: list[WallRect] = []
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            rects.append(
                WallRect(
                    label=ZONE_LABELS[idx],
                    u_min=u0 + c * cell_u + pad_u,
                    u_max=u0 + (c + 1) * cell_u - pad_u,
                    v_min=v0 + r * cell_v + pad_v,
                    v_max=v0 + (r + 1) * cell_v - pad_v,
                )
            )
    return rects


def wall_bounds_from_homography_data(data: dict) -> WallBounds | None:
    pts = data.get("calibration_points") or []
    wall_pts = [p.get("wall_mm") for p in pts if p.get("wall_mm")]
    if not wall_pts:
        return None
    us = [float(p[0]) for p in wall_pts]
    vs = [float(p[1]) for p in wall_pts]
    return WallBounds(min(us), max(us), min(vs), max(vs))


def wall_bounds_from_homography(path: str | Path) -> WallBounds | None:
    p = Path(path)
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    return wall_bounds_from_homography_data(data)


def find_rect_for_uv(
    rects: Iterable[WallRect],
    u_mm: float,
    v_mm: float,
    pad_mm: float = 0.0,
    active_labels: set[str] | None = None,
) -> WallRect | None:
    for rect in rects:
        if active_labels is not None and rect.label not in active_labels:
            continue
        if rect.contains(u_mm, v_mm, pad_mm=pad_mm):
            return rect
    return None


def consensus_zone_from_wall_uv(
    rects: Iterable[WallRect],
    per_cam_wall_uv: dict[str, tuple[float, float]],
    min_cams: int = 2,
    pad_mm: float = 0.0,
) -> ConsensusZone | None:
    rect_list = list(rects)
    zone_uv_sum: dict[str, list[float]] = {}
    zone_votes, per_cam_zones = zone_votes_from_wall_uv(
        rect_list, per_cam_wall_uv, pad_mm=pad_mm
    )
    for cam, label in per_cam_zones.items():
        if label is None:
            continue
        u_mm, v_mm = per_cam_wall_uv[cam]
        uv_sum = zone_uv_sum.setdefault(label, [0.0, 0.0])
        uv_sum[0] += float(u_mm)
        uv_sum[1] += float(v_mm)

    best_label: str | None = None
    best_voters: tuple[str, ...] = ()
    for label, voters in zone_votes.items():
        if len(voters) > len(best_voters):
            best_label = label
            best_voters = voters

    if best_label is None or len(best_voters) < int(min_cams):
        return None

    n = len(best_voters)
    return ConsensusZone(
        zone_label=best_label,
        u_mm=zone_uv_sum[best_label][0] / n,
        v_mm=zone_uv_sum[best_label][1] / n,
        voting_cams=tuple(sorted(best_voters)),
        zone_votes=zone_votes,
        per_cam_zones=dict(sorted(per_cam_zones.items())),
    )


def zone_votes_from_wall_uv(
    rects: Iterable[WallRect],
    per_cam_wall_uv: dict[str, tuple[float, float]],
    pad_mm: float = 0.0,
) -> tuple[dict[str, tuple[str, ...]], dict[str, str | None]]:
    rect_list = list(rects)
    zone_votes: dict[str, list[str]] = {}
    per_cam_zones: dict[str, str | None] = {}

    for cam, (u_mm, v_mm) in per_cam_wall_uv.items():
        rect = find_rect_for_uv(rect_list, u_mm, v_mm, pad_mm=pad_mm)
        label = rect.label if rect is not None else None
        per_cam_zones[cam] = label
        if label is None:
            continue
        zone_votes.setdefault(label, []).append(cam)

    return (
        {
            label: tuple(sorted(voters))
            for label, voters in sorted(zone_votes.items())
        },
        dict(sorted(per_cam_zones.items())),
    )


def temporal_consensus_zone(
    votes: Iterable[tuple[float, str, str, float, float]],
    now: float,
    window_s: float,
    min_cams: int = 2,
) -> ConsensusZone | None:
    latest: dict[tuple[str, str], tuple[float, float, float]] = {}
    cutoff = float(now) - max(0.0, float(window_s))
    for t_sec, cam, zone_label, u_mm, v_mm in votes:
        t = float(t_sec)
        if t < cutoff:
            continue
        key = (str(zone_label), str(cam))
        prev = latest.get(key)
        if prev is None or t >= prev[0]:
            latest[key] = (t, float(u_mm), float(v_mm))

    by_zone: dict[str, dict[str, tuple[float, float, float]]] = {}
    for (zone_label, cam), item in latest.items():
        by_zone.setdefault(zone_label, {})[cam] = item

    best_label: str | None = None
    best_votes: dict[str, tuple[float, float, float]] = {}
    for zone_label, cam_votes in sorted(by_zone.items()):
        if len(cam_votes) > len(best_votes):
            best_label = zone_label
            best_votes = cam_votes

    if best_label is None or len(best_votes) < int(min_cams):
        return None

    cams = tuple(sorted(best_votes))
    u_avg = sum(best_votes[cam][1] for cam in cams) / len(cams)
    v_avg = sum(best_votes[cam][2] for cam in cams) / len(cams)
    return ConsensusZone(
        zone_label=best_label,
        u_mm=u_avg,
        v_mm=v_avg,
        voting_cams=cams,
        zone_votes={
            label: tuple(sorted(cam_votes))
            for label, cam_votes in sorted(by_zone.items())
        },
        per_cam_zones={
            cam: zone_label
            for (zone_label, cam) in sorted(latest)
        },
    )


def intersect_ray_with_world_x(
    normalized_uv: tuple[float, float] | np.ndarray,
    R: np.ndarray,
    tvec: np.ndarray,
    x_mm: float = SOUTH_WALL_X_MM,
    depth_sign: float | None = 1.0,
) -> np.ndarray | None:
    """Intersect a camera ray with the world plane X = x_mm.

    R and tvec are the calibrated world-to-camera extrinsics. The pixel ray is
    expressed as camera-frame normalized coordinates [u, v, 1].
    Some calibration bundles use negative camera-space Z for visible points;
    depth_sign selects that convention instead of assuming positive depth.
    """

    u, v = float(normalized_uv[0]), float(normalized_uv[1])
    ray_cam = np.array([u, v, 1.0], dtype=np.float64)
    R = np.asarray(R, dtype=np.float64).reshape(3, 3)
    t = np.asarray(tvec, dtype=np.float64).reshape(3)

    r0 = R[:, 0]
    denom = float(np.dot(r0, ray_cam))
    if abs(denom) < 1e-9:
        return None

    offset = float(np.dot(r0, t))
    depth = (float(x_mm) + offset) / denom
    if depth_sign is None:
        if abs(depth) <= 1e-9:
            return None
    elif depth * (1.0 if depth_sign >= 0.0 else -1.0) <= 0.0:
        return None

    point_cam = depth * ray_cam
    point_world = R.T @ (point_cam - t)
    return point_world


def load_intrinsics(path: str | Path) -> dict[str, np.ndarray]:
    with Path(path).open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    k = np.array(data["camera_matrix"], dtype=np.float64)
    d = np.array(data["distortion_coefficients"], dtype=np.float64)
    if d.ndim == 2:
        d = d.reshape(-1)
    return {"K": k, "D": d}


def load_extrinsics(path: str | Path, cam_role: str) -> dict[str, np.ndarray]:
    import cv2

    with Path(path).open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if cam_role not in data:
        raise KeyError(f"{cam_role!r} not found in {path}")
    cam = data[cam_role]
    rvec = np.array(cam["rvec"], dtype=np.float64).reshape(3, 1)
    tvec = np.array(cam["tvec"], dtype=np.float64).reshape(3, 1) * 1000.0
    R, _ = cv2.Rodrigues(rvec)
    return {"R": R, "tvec": tvec}


class SouthWallMapper:
    def __init__(
        self,
        K: np.ndarray,
        D: np.ndarray,
        R: np.ndarray,
        tvec: np.ndarray,
        wall_x_mm: float = SOUTH_WALL_X_MM,
    ):
        self.K = np.asarray(K, dtype=np.float64)
        self.D = np.asarray(D, dtype=np.float64).reshape(-1)
        self.R = np.asarray(R, dtype=np.float64).reshape(3, 3)
        self.tvec = np.asarray(tvec, dtype=np.float64).reshape(3, 1)
        self.wall_x_mm = float(wall_x_mm)
        ref = np.array(
            [
                self.wall_x_mm,
                0.5 * SOUTH_WALL_U_MAX_MM,
                0.5 * SOUTH_WALL_V_MAX_MM,
            ],
            dtype=np.float64,
        )
        ref_cam = self.R @ ref + self.tvec.reshape(3)
        self._depth_sign = -1.0 if float(ref_cam[2]) < 0.0 else 1.0

    @classmethod
    def from_files(
        cls,
        intrinsics_path: str | Path,
        extrinsics_path: str | Path,
        cam_role: str = "camNorth",
        wall_x_mm: float = SOUTH_WALL_X_MM,
    ) -> "SouthWallMapper":
        intr = load_intrinsics(intrinsics_path)
        extr = load_extrinsics(extrinsics_path, cam_role)
        return cls(intr["K"], intr["D"], extr["R"], extr["tvec"], wall_x_mm=wall_x_mm)

    def pixel_to_wall(self, pixel_xy: tuple[float, float]) -> tuple[float, float, np.ndarray] | None:
        import cv2

        pts = np.array([[[float(pixel_xy[0]), float(pixel_xy[1])]]], dtype=np.float64)
        und = cv2.undistortPoints(pts, self.K, self.D).reshape(2)
        point = intersect_ray_with_world_x(
            und,
            self.R,
            self.tvec,
            x_mm=self.wall_x_mm,
            depth_sign=self._depth_sign,
        )
        if point is None or not np.isfinite(point).all():
            return None
        return float(point[1]), float(point[2]), point

    def wall_to_pixel(self, u_mm: float, v_mm: float) -> tuple[int, int]:
        import cv2

        point = np.array([[[self.wall_x_mm, float(u_mm), float(v_mm)]]], dtype=np.float64)
        rvec, _ = cv2.Rodrigues(self.R)
        uv, _ = cv2.projectPoints(point, rvec, self.tvec, self.K, self.D)
        x, y = uv.reshape(2)
        return int(round(float(x))), int(round(float(y)))


class StaticGridGoalLogic:
    def __init__(
        self,
        rects: Iterable[WallRect] | None = None,
        min_flight_speed_mm_s: float = 1500.0,
        decel_ratio: float = 0.40,
        cooldown_s: float = 0.8,
        hit_pad_mm: float = 80.0,
        speed_smoothing: float = 0.0,
        active_labels: Iterable[str] | None = None,
    ):
        self.rects = list(rects) if rects is not None else target_grid_rectangles()
        self.min_flight_speed_mm_s = float(min_flight_speed_mm_s)
        self.decel_ratio = float(decel_ratio)
        self.cooldown_s = float(cooldown_s)
        self.hit_pad_mm = float(hit_pad_mm)
        self.speed_smoothing = float(np.clip(speed_smoothing, 0.0, 0.95))
        self.active_labels = set(active_labels) if active_labels else None
        self._last_point: dict[int | str, tuple[float, float, float]] = {}
        self._speed: dict[int | str, float] = {}
        self._peak_speed: dict[int | str, float] = {}
        self._last_goal_t = -math.inf

    def reset_track(self, track_id: int | str = 0) -> None:
        self._last_point.pop(track_id, None)
        self._speed.pop(track_id, None)
        self._peak_speed.pop(track_id, None)

    def update(
        self,
        t_sec: float,
        u_mm: float,
        v_mm: float,
        track_id: int | str = 0,
    ) -> GoalEvent | None:
        t = float(t_sec)
        u = float(u_mm)
        v = float(v_mm)

        prev = self._last_point.get(track_id)
        self._last_point[track_id] = (t, u, v)
        if prev is None:
            self._speed[track_id] = 0.0
            self._peak_speed[track_id] = 0.0
            return None

        t_prev, u_prev, v_prev = prev
        dt = t - t_prev
        if dt <= 1e-6:
            return None

        raw_speed = math.hypot(u - u_prev, v - v_prev) / dt
        prev_speed = self._speed.get(track_id, raw_speed)
        speed = (
            self.speed_smoothing * prev_speed
            + (1.0 - self.speed_smoothing) * raw_speed
        )
        peak = max(self._peak_speed.get(track_id, 0.0), speed)
        self._speed[track_id] = speed
        self._peak_speed[track_id] = peak

        rect = find_rect_for_uv(
            self.rects,
            u,
            v,
            pad_mm=self.hit_pad_mm,
            active_labels=self.active_labels,
        )
        if rect is None:
            return None

        if t - self._last_goal_t < self.cooldown_s:
            return None

        had_flight = peak >= self.min_flight_speed_mm_s
        slowed = speed <= self.decel_ratio * peak
        if not (had_flight and slowed):
            return None

        self._last_goal_t = t
        event = GoalEvent(
            zone_label=rect.label,
            u_mm=u,
            v_mm=v,
            t_sec=t,
            speed_mm_s=speed,
            peak_speed_mm_s=peak,
            track_id=track_id,
        )
        self._peak_speed[track_id] = speed
        return event
