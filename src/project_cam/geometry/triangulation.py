"""Multi-view triangulation for the arena tracker.

The live system observes a target (a ball or a body joint) in several calibrated
cameras and reconstructs its 3D world position. Two conventions matter and must
not be mixed:

- Observations are **normalized, undistorted** image coordinates -- the output of
  ``cv2.undistortPoints`` with ``P=None`` -- i.e. ``(X_c/Z_c, Y_c/Z_c)``.
- The matching projection matrix is the **bare extrinsic** ``P = [R | t]`` (no
  intrinsic ``K``), because the normalization already removed ``K``.

Pairing normalized observations with a pixel-space ``K @ [R | t]`` (or vice
versa) silently corrupts the DLT scale and produces garbage depth, so the helpers
here keep the two spaces explicit.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


def triangulate_multi(
    observations: Dict[str, Tuple[float, float]],
    proj_mats: Dict[str, np.ndarray],
) -> Optional[np.ndarray]:
    """Linear (DLT) triangulation of one world point from >= 2 views.

    Parameters
    ----------
    observations : dict
        ``{camera_id: (x, y)}`` normalized undistorted image coordinates.
    proj_mats : dict
        ``{camera_id: P}`` where ``P`` is the 3x4 extrinsic projection ``[R | t]``.

    Returns
    -------
    np.ndarray of shape (3,) in world units (mm), or ``None`` if the system is
    rank-deficient (fewer than two usable rows or a degenerate configuration).

    Each view contributes two rows of the homogeneous system ``A x = 0``:
    ``x * P[2] - P[0]`` and ``y * P[2] - P[1]``. The solution is the right
    singular vector of ``A`` with the smallest singular value, dehomogenized.
    """
    if len(observations) < 2:
        return None
    rows = []
    for cam, (x, y) in observations.items():
        p = proj_mats[cam]
        rows.append(x * p[2] - p[0])
        rows.append(y * p[2] - p[1])
    a = np.asarray(rows, dtype=np.float64)
    if a.shape[0] < 4:
        return None
    _, _, vt = np.linalg.svd(a)
    x = vt[-1]
    if abs(x[3]) < 1e-9:
        return None
    return x[:3] / x[3]


def project_world_to_pixel(
    point_w: np.ndarray,
    R: np.ndarray,
    tvec: np.ndarray,
    K: np.ndarray,
    D: np.ndarray,
) -> np.ndarray:
    """Project a 3D world point to distorted pixel coordinates in one camera."""
    rvec, _ = cv2.Rodrigues(np.asarray(R, dtype=np.float64))
    pt = np.asarray(point_w, dtype=np.float64).reshape(1, 1, 3)
    uv, _ = cv2.projectPoints(pt, rvec, np.asarray(tvec, dtype=np.float64), K, D)
    return uv.reshape(2)


def robust_triangulate_ball(
    obs_norm: Dict[str, Tuple[float, float]],
    obs_px: Dict[str, np.ndarray],
    proj_mats: Dict[str, np.ndarray],
    extr: Dict[str, dict],
    intr: Dict[str, dict],
    min_cams: int = 2,
    max_reproj_px: float = 15.0,
) -> Tuple[Optional[np.ndarray], List[str], Optional[float]]:
    """Triangulate while rejecting cameras whose reprojection error is too large.

    A single mislabelled detection (a cone, a marker, a body part flagged as the
    ball) can drag a least-squares fit far off the true position. This routine
    triangulates from all cameras, measures each camera's reprojection error in
    pixels, and iteratively drops the worst offender until either every remaining
    camera is within ``max_reproj_px`` or only ``min_cams`` are left.

    Parameters
    ----------
    obs_norm : dict
        ``{camera_id: (x, y)}`` normalized undistorted observations (for the DLT).
    obs_px : dict
        ``{camera_id: (u, v)}`` raw pixel observations (for the error check).
    proj_mats, extr, intr : dict
        Bare extrinsic projections, full extrinsics (``R``, ``tvec``), and
        intrinsics (``K``, ``D``) keyed by camera id.

    Returns
    -------
    (point_mm, inlier_cams, mean_reproj_px)
        ``point_mm`` is ``None`` if no inlier set of at least ``min_cams`` agrees.
    """
    if len(obs_norm) < min_cams:
        return None, [], None
    active = dict(obs_norm)
    while len(active) >= min_cams:
        X = triangulate_multi(active, proj_mats)
        if X is None:
            return None, [], None
        if max_reproj_px <= 0:
            return X, sorted(active.keys()), 0.0
        reproj = {}
        for cam in list(active.keys()):
            uv = project_world_to_pixel(
                X, extr[cam]["R"], extr[cam]["tvec"], intr[cam]["K"], intr[cam]["D"]
            )
            reproj[cam] = float(np.linalg.norm(uv - obs_px[cam]))
        worst_cam = max(reproj, key=reproj.get)
        if reproj[worst_cam] <= max_reproj_px:
            return X, sorted(active.keys()), float(np.mean(list(reproj.values())))
        if len(active) == min_cams:
            return None, [], reproj[worst_cam]
        del active[worst_cam]
    return None, [], None


def project_ray_to_z_plane(
    obs_norm: Tuple[float, float],
    R: np.ndarray,
    tvec: np.ndarray,
    target_z: float,
) -> Optional[np.ndarray]:
    """Intersect a single camera ray with the world plane ``Z = target_z``.

    When only one camera sees the target, multi-view triangulation is impossible.
    If a depth prior is available (e.g. a Kalman-predicted height, or the floor on
    a cold start), the pixel back-projects to a single 3D point where its ray
    crosses that horizontal plane.

    Parameters
    ----------
    obs_norm : (u, v)
        Normalized undistorted image coordinates (``cv2.undistortPoints`` output).
    R, tvec : np.ndarray
        World->camera rotation (3x3) and translation (3,) in mm.
    target_z : float
        World Z of the plane to intersect, in mm.

    Returns
    -------
    np.ndarray of shape (3,) in world mm, or ``None`` if the ray is parallel to
    the plane or points away from it.

    A pixel ray in the camera frame at depth ``s`` is ``X_c = s * [u, v, 1]``; the
    world point is ``X_w = R^T (X_c - t)``. Setting ``X_w[2] = target_z`` and
    solving for ``s`` gives the unique intersection. The third row of ``R^T`` is
    the third column of ``R``.
    """
    u, v = float(obs_norm[0]), float(obs_norm[1])
    t = np.asarray(tvec, dtype=np.float64).reshape(3)
    r2 = np.asarray(R, dtype=np.float64)[:, 2]
    A = r2[0] * u + r2[1] * v + r2[2]
    if abs(A) < 1e-6:
        return None
    B = r2[0] * t[0] + r2[1] * t[1] + r2[2] * t[2]
    s = (target_z + B) / A
    if s <= 0:
        return None
    X_c = np.array([u * s, v * s, s], dtype=np.float64)
    return np.asarray(R, dtype=np.float64).T @ (X_c - t)
