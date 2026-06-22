"""Shared math helpers — pre-defense Tier 0 consolidation (2026-04-20).

Geometry-neutral helpers extracted from the 8-way duplication audit. Bodies are
byte-identical to their previous in-place definitions; only parameter casing was
normalized for `undistort_points`.

Pending consolidation (Tier 1, requires regression fixture):
- triangulate_multi (5 diverged copies)
- world_to_launcher_xy_delta (5 copies, geometry-critical)
- solve_angles_ballistic (5 copies, safety-adjacent)
- SerialReader (blm_follow.py + live_aim_test.py)
"""

import cv2
import numpy as np


def undistort_points(pt, k, d):
    pts = np.array([[pt]], dtype=np.float64)
    und = cv2.undistortPoints(pts, k, d)
    return und[0, 0]


def transform_world_point_y(world_pt, y_max, enabled=True):
    if world_pt is None or not enabled:
        return world_pt
    out = np.array(world_pt, copy=True)
    out[..., 1] = y_max - out[..., 1]
    return out


def ema_update(prev, new, alpha):
    if new is None:
        return prev
    if prev is None:
        return np.array(new, dtype=np.float32)
    return (1.0 - alpha) * prev + alpha * np.array(new, dtype=np.float32)
