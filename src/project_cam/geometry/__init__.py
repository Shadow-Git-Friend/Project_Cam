"""Standalone multi-view geometry, prediction, and ballistics.

This package contains the hardware-free core algorithms behind the project name:

- ``triangulation`` -- multi-view SVD/DLT triangulation with robust per-camera
  reprojection rejection, plus single-camera ray/plane intersection.
- ``kalman`` -- constant-velocity 3D Kalman filter for predictive targeting.
- ``ballistics`` -- launcher aim solver (pitch/yaw) from a 3D target.

Every function operates on plain NumPy arrays and calibration matrices, so the
modules can be reviewed and unit-tested without cameras, model weights, or the
live inference stack.
"""

from .ballistics import (
    forward_right_vectors_from_yaw,
    solve_angles_ballistic,
    world_to_launcher_xy_delta,
)
from .kalman import JointKalmanFilter
from .triangulation import (
    project_ray_to_z_plane,
    project_world_to_pixel,
    robust_triangulate_ball,
    triangulate_multi,
)

__all__ = [
    "triangulate_multi",
    "robust_triangulate_ball",
    "project_ray_to_z_plane",
    "project_world_to_pixel",
    "JointKalmanFilter",
    "forward_right_vectors_from_yaw",
    "world_to_launcher_xy_delta",
    "solve_angles_ballistic",
]
