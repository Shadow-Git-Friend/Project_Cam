"""Per-athlete leg-bone length priors learned during push-up acquisition.

YOLO-Pose mis-detects floor-level legs when the body is in a horizontal
plank: the elevated four-camera rig has limited line-of-sight to the legs,
so multi-view triangulation can either drop joints (only one camera saw
them) or land them on floor clutter (two cameras confidently mis-detect
the same wrong thing). The torso-relative bone-length gate in
``coach_overlay.validate_leg_chain`` is wide enough to let some of those
clutter latches through.

This module learns *per-athlete* femur and tibia lengths during the same
4-frame acquisition window the rep counter already uses, then uses a tight
+/- 15% gate to drop any post-triangulation leg joint whose parent-bone
length is anatomically impossible. The 3D validator operates on the freshly
triangulated joints (``joints_3d_now``) BEFORE the EMA blends them into
``joints_state``, so corrupted points cannot poison the smoother or any
downstream consumer (UDP target stream, coach overlay, 3D arena).

The module is intentionally CV2-free so it can be unit-tested in
isolation; the live tracker is responsible for feeding it the 3D points it
already computed from ``triangulate_multi``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


# Tight per-athlete tolerance. Floor clutter typically yields bone lengths
# well outside +/- 15% of the prior (often 2-5x). Tightening below 15%
# starts to drop legitimate frames where the athlete bends a knee slightly.
_PRIOR_TOL_PCT = 0.15

# Required cameras per leg joint for a frame to count toward calibration.
# Frames where any leg joint was triangulated from fewer than this many
# cameras are silently skipped (the joint's 3D position is too noisy to
# anchor a per-athlete length on).
_MIN_CAMS_PER_LEG_JOINT = 2

# COCO-17 indices for the leg chain.
_HIP_L, _HIP_R = 11, 12
_KNEE_L, _KNEE_R = 13, 14
_ANKLE_L, _ANKLE_R = 15, 16
_LEG_INDICES = (_HIP_L, _HIP_R, _KNEE_L, _KNEE_R, _ANKLE_L, _ANKLE_R)


@dataclass(frozen=True)
class LegPriors:
    """Locked per-athlete leg-bone lengths in millimetres."""

    femur_l_mm: float
    femur_r_mm: float
    tibia_l_mm: float
    tibia_r_mm: float
    sample_count: int
    locked_at_frame: int

    def for_side(self, joint_idx: int) -> tuple[float, float]:
        """Return (femur_mm, tibia_mm) for the side the joint belongs to."""
        if joint_idx in (_HIP_L, _KNEE_L, _ANKLE_L):
            return self.femur_l_mm, self.tibia_l_mm
        return self.femur_r_mm, self.tibia_r_mm


class LegPriorAccumulator:
    """Accumulate per-frame leg-segment lengths until a stable prior locks.

    Usage:
        acc = LegPriorAccumulator(min_frames=4, std_tol_mm=10.0)
        for each acquired push-up frame:
            acc.observe(joints_3d_now, joints_cam_state)
        priors = acc.try_lock()  # returns None until stable
        if athlete leaves -> acc.reset()
    """

    def __init__(self, min_frames: int = 4, std_tol_mm: float = 10.0):
        self.min_frames = max(1, int(min_frames))
        self.std_tol_mm = float(max(0.0, std_tol_mm))
        self._samples: list[dict[str, float]] = []
        self._frame_idx_at_lock = -1

    def reset(self) -> None:
        self._samples.clear()
        self._frame_idx_at_lock = -1

    def observe(
        self,
        joints_3d_world: dict[int, np.ndarray] | dict,
        joints_cam: Iterable[int],
        frame_idx: int = 0,
    ) -> None:
        """Add this frame to the accumulator if it satisfies all gates.

        Gates: every leg joint is present with finite 3D coords AND has
        at least ``_MIN_CAMS_PER_LEG_JOINT`` contributing cameras. Failing
        frames are silently skipped (the accumulator state is unchanged).
        """
        cams = list(joints_cam)
        if not _legs_ready(joints_3d_world, cams):
            return
        try:
            femur_l = _segment_len(joints_3d_world[_HIP_L], joints_3d_world[_KNEE_L])
            femur_r = _segment_len(joints_3d_world[_HIP_R], joints_3d_world[_KNEE_R])
            tibia_l = _segment_len(joints_3d_world[_KNEE_L], joints_3d_world[_ANKLE_L])
            tibia_r = _segment_len(joints_3d_world[_KNEE_R], joints_3d_world[_ANKLE_R])
        except (KeyError, TypeError):
            return
        if not all(np.isfinite([femur_l, femur_r, tibia_l, tibia_r])):
            return
        self._samples.append({
            "femur_l": femur_l, "femur_r": femur_r,
            "tibia_l": tibia_l, "tibia_r": tibia_r,
            "frame_idx": float(frame_idx),
        })

    def try_lock(self) -> LegPriors | None:
        """Return locked priors when enough stable frames are accumulated."""
        if len(self._samples) < self.min_frames:
            return None
        recent = self._samples[-max(self.min_frames, len(self._samples)):]
        keys = ("femur_l", "femur_r", "tibia_l", "tibia_r")
        means: dict[str, float] = {}
        for key in keys:
            arr = np.asarray([s[key] for s in recent], dtype=float)
            if float(np.std(arr)) > self.std_tol_mm:
                # One segment is too jittery to anchor a prior on; the
                # athlete is still settling or a leg joint is mis-tracked.
                return None
            means[key] = float(np.mean(arr))
        return LegPriors(
            femur_l_mm=means["femur_l"],
            femur_r_mm=means["femur_r"],
            tibia_l_mm=means["tibia_l"],
            tibia_r_mm=means["tibia_r"],
            sample_count=len(recent),
            locked_at_frame=int(recent[-1]["frame_idx"]),
        )


class LegChainValidator3D:
    """Drop freshly triangulated leg joints whose bone length is impossible.

    Operates on ``joints_3d_now`` -- the dict of per-frame triangulated
    points returned from ``triangulate_multi`` -- BEFORE the EMA blends
    them into ``joints_state``. A confidently-wrong triangulation that
    sneaks past the camera-count gate (two cameras both lock onto floor
    clutter) is rejected here rather than corrupting the smoother.

    Validation is parent-first: a child joint (knee, ankle) is only
    validated if its parent (hip, knee) is present and finite. A missing
    parent does NOT cause the child to be dropped -- it just cannot be
    judged this frame.
    """

    @staticmethod
    def filter_drops(
        joints_3d_now: dict[int, np.ndarray] | dict,
        priors: LegPriors,
        tol_pct: float = _PRIOR_TOL_PCT,
    ) -> set[int]:
        drops: set[int] = set()
        if not joints_3d_now:
            return drops
        for hip_i, knee_i, ankle_i, femur_prior, tibia_prior in (
            (_HIP_L, _KNEE_L, _ANKLE_L, priors.femur_l_mm, priors.tibia_l_mm),
            (_HIP_R, _KNEE_R, _ANKLE_R, priors.femur_r_mm, priors.tibia_r_mm),
        ):
            hip_pt = _finite_point(joints_3d_now.get(hip_i))
            knee_pt = _finite_point(joints_3d_now.get(knee_i))
            ankle_pt = _finite_point(joints_3d_now.get(ankle_i))
            if knee_pt is not None and hip_pt is not None:
                bone = _segment_len(hip_pt, knee_pt)
                if not _within_tolerance(bone, femur_prior, tol_pct):
                    drops.add(knee_i)
            if ankle_pt is not None and knee_pt is not None:
                bone = _segment_len(knee_pt, ankle_pt)
                if not _within_tolerance(bone, tibia_prior, tol_pct):
                    drops.add(ankle_i)
        return drops


def evaluate_ankle_fallback(
    ankle_idx: int,
    obs_norm: tuple[float, float] | None,
    R: np.ndarray,
    tvec: np.ndarray,
    target_z_mm: float,
    knee_pt: np.ndarray | None,
    hip_pt: np.ndarray | None,
    priors: "LegPriors",
    tol_pct: float = _PRIOR_TOL_PCT,
) -> np.ndarray | None:
    """Propose a 3D ankle position from a single camera ray + priors.

    Used when ``triangulate_multi`` cannot resolve an ankle because only
    one camera saw it (typical during push-ups when the torso occludes
    one or both ankles from elevated views). The undistorted normalized
    obs is projected onto the world plane ``Z = target_z_mm`` and gated
    against two anatomical sanity checks:

    1. Tibia gate. ``|proposed - knee|`` must be within +/- tol_pct of
       the learned tibia prior. Catches the "ray skims through floor
       clutter" case.
    2. Hip-distance gate. ``||proposed_xy - hip_xy||`` must not exceed
       (femur + tibia) * (1 + tol_pct). This is the gate that catches
       the user-reported raised-leg failure mode: when an actively
       raised foot's ray to Z=0 lands far down-arena, this filter
       refuses to accept it.

    Both ``knee_pt`` and ``hip_pt`` MUST be finite (multi-cam triangulated)
    -- without one or both anchors there is no way to validate the
    fallback, so the function returns ``None`` rather than guessing.

    Returns the 3D world point on accept, ``None`` on reject.
    """
    if obs_norm is None or priors is None:
        return None
    knee = _finite_point(knee_pt)
    hip = _finite_point(hip_pt)
    if knee is None or hip is None:
        return None
    femur_prior, tibia_prior = priors.for_side(ankle_idx)

    # Import locally to avoid a circular import path at module load time;
    # project_ray_to_z_plane lives in the live tracker, not here.
    proposed = _ray_to_z_plane(obs_norm, R, tvec, float(target_z_mm))
    if proposed is None:
        return None

    # Tibia gate.
    if not _within_tolerance(float(np.linalg.norm(proposed - knee)),
                             tibia_prior, tol_pct):
        return None

    # Hip-distance gate (in XY of the floor plane).
    max_leg_xy = (femur_prior + tibia_prior) * (1.0 + tol_pct)
    xy_dist = float(np.linalg.norm(proposed[:2] - hip[:2]))
    if xy_dist > max_leg_xy:
        return None

    return proposed


def _ray_to_z_plane(obs_norm, R, tvec, target_z):
    """Vendored copy of the live tracker's ``project_ray_to_z_plane``.

    Duplicating the geometry here keeps the module CV2-free and avoids
    an import cycle with ``Parallel_working/scripts/live_4cam_arena_view_parallel.py``.
    Geometry: pixel ray in cam frame X_c = s*[u,v,1]; X_w = R^T(X_c - t);
    solve X_w[2] = target_z for s. Returns None when the ray is parallel
    to the plane or points behind the lens.
    """
    u, v = float(obs_norm[0]), float(obs_norm[1])
    t = np.asarray(tvec, dtype=np.float64).reshape(3)
    R = np.asarray(R, dtype=np.float64)
    r2 = R[:, 2]
    A = r2[0] * u + r2[1] * v + r2[2]
    if abs(A) < 1e-6:
        return None
    B = r2[0] * t[0] + r2[1] * t[1] + r2[2] * t[2]
    s = (target_z + B) / A
    if s <= 0:
        return None
    X_c = np.array([u * s, v * s, s], dtype=np.float64)
    X_w = R.T @ (X_c - t)
    return X_w


def _legs_ready(joints: dict, cams: list[int]) -> bool:
    if joints is None:
        return False
    if len(cams) < max(_LEG_INDICES) + 1:
        return False
    for idx in _LEG_INDICES:
        if idx not in joints:
            return False
        try:
            cam_count = int(cams[idx])
        except (TypeError, ValueError):
            return False
        if cam_count < _MIN_CAMS_PER_LEG_JOINT:
            return False
        if _finite_point(joints[idx]) is None:
            return False
    return True


def _finite_point(value) -> np.ndarray | None:
    if value is None:
        return None
    try:
        arr = np.asarray(value, dtype=float).reshape(-1)[:3]
    except (TypeError, ValueError):
        return None
    if arr.shape[0] < 3 or not np.isfinite(arr).all():
        return None
    return arr


def _segment_len(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def _within_tolerance(measured: float, prior: float, tol_pct: float) -> bool:
    if not np.isfinite(measured) or not np.isfinite(prior) or prior <= 0.0:
        return False
    lo = prior * (1.0 - tol_pct)
    hi = prior * (1.0 + tol_pct)
    return lo <= measured <= hi
