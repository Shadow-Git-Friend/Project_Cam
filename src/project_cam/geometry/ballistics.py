"""Launcher aim solver: 3D target -> pitch and yaw.

Once a target's 3D world position is known (and optionally led ahead by the
Kalman predictor), the launcher must be pointed at it. This module converts a
world-frame target into the launcher's local lateral/forward/up frame and solves
the projectile equations for the firing pitch and yaw.

Distances are in mm at the world boundary and converted to metres for the
ballistic solve; angles are returned in degrees.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np


def forward_right_vectors_from_yaw(yaw_deg: float) -> Tuple[np.ndarray, np.ndarray]:
    """Unit forward and right vectors (in the world XY plane) for a launcher yaw."""
    yaw = math.radians(yaw_deg)
    fwd = np.array([math.cos(yaw), math.sin(yaw), 0.0], dtype=np.float64)
    right = np.array([fwd[1], -fwd[0], 0.0], dtype=np.float64)
    return fwd, right


def world_to_launcher_xy_delta(
    target_xyz_mm: np.ndarray,
    launcher_xyz_mm: np.ndarray,
    launcher_yaw_deg: float,
) -> Tuple[float, float, float]:
    """Express a world target relative to the launcher, in metres.

    Returns ``(x_lateral_m, y_forward_m, dz_m)`` where forward/right are defined by
    the launcher's yaw and ``dz`` is the vertical offset.
    """
    d = np.asarray(target_xyz_mm, dtype=np.float64) - np.asarray(launcher_xyz_mm, dtype=np.float64)
    fwd, right = forward_right_vectors_from_yaw(launcher_yaw_deg)
    x_lat_mm = float(np.dot(d[:2], right[:2]))
    y_fwd_mm = float(np.dot(d[:2], fwd[:2]))
    dz_mm = float(d[2])
    return x_lat_mm / 1000.0, y_fwd_mm / 1000.0, dz_mm / 1000.0


def solve_angles_ballistic(
    x_lat_m: float,
    y_fwd_m: float,
    dz_m: float,
    v_ms: float,
    g: float = 9.81,
) -> Optional[Tuple[float, float]]:
    """Solve firing ``(pitch_deg, yaw_deg)`` for a fixed muzzle speed.

    Parameters
    ----------
    x_lat_m, y_fwd_m, dz_m : float
        Target offset in the launcher frame (lateral, forward, up), metres.
    v_ms : float
        Muzzle speed in m/s.
    g : float
        Gravity, m/s^2.

    Returns
    -------
    ``(pitch_deg, yaw_deg)`` for the low (flat) trajectory solution, or ``None``
    when the target is behind/too close (``y_fwd_m <= 0.15``) or out of range
    (negative discriminant -- the projectile cannot reach it at ``v_ms``).

    The yaw is a planar heading; the pitch uses the standard projectile range
    equation, choosing the lower of the two valid elevation angles.
    """
    if y_fwd_m <= 0.15:
        return None
    d = math.sqrt(x_lat_m * x_lat_m + y_fwd_m * y_fwd_m)
    if d <= 1e-6:
        return None
    h_deg = math.degrees(math.atan2(x_lat_m, y_fwd_m))
    disc = v_ms ** 4 - g * (g * d ** 2 + 2.0 * dz_m * v_ms ** 2)
    if disc < 0.0:
        return None
    v_rad = math.atan((v_ms ** 2 - math.sqrt(disc)) / (g * d))
    return math.degrees(v_rad), h_deg
