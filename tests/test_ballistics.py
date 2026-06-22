"""Tests for the launcher aim solver."""

import math

import numpy as np
import pytest

from project_cam.geometry import (
    forward_right_vectors_from_yaw,
    solve_angles_ballistic,
    world_to_launcher_xy_delta,
)

G = 9.81


def test_forward_right_vectors_zero_yaw():
    fwd, right = forward_right_vectors_from_yaw(0.0)
    assert np.allclose(fwd, [1.0, 0.0, 0.0])
    assert np.allclose(right, [0.0, -1.0, 0.0])


def test_world_to_launcher_delta_decomposes_offset():
    launcher = np.array([600.0, 1560.0, 500.0])
    target = np.array([3000.0, 1560.0, 500.0])  # straight ahead at yaw 0
    x_lat, y_fwd, dz = world_to_launcher_xy_delta(target, launcher, 0.0)
    assert pytest.approx(x_lat, abs=1e-9) == 0.0
    assert pytest.approx(y_fwd, abs=1e-9) == 2.4  # mm -> m
    assert pytest.approx(dz, abs=1e-9) == 0.0


def test_solve_angles_yaw_matches_geometry():
    # Target offset to the right and ahead -> non-zero yaw.
    pitch, yaw = solve_angles_ballistic(x_lat_m=1.0, y_fwd_m=2.0, dz_m=0.0, v_ms=12.0)
    assert yaw == pytest.approx(math.degrees(math.atan2(1.0, 2.0)), abs=1e-9)
    assert 0.0 < pitch < 45.0


def test_solved_pitch_actually_hits_target():
    # Round-trip: fire at the solved pitch and confirm the projectile lands at the
    # target's height after covering the target's horizontal distance.
    x_lat, y_fwd, dz, v = 0.6, 3.0, 0.4, 14.0
    pitch_deg, yaw_deg = solve_angles_ballistic(x_lat, y_fwd, dz, v)
    d = math.hypot(x_lat, y_fwd)
    theta = math.radians(pitch_deg)
    t_flight = d / (v * math.cos(theta))
    height = v * math.sin(theta) * t_flight - 0.5 * G * t_flight ** 2
    assert height == pytest.approx(dz, abs=1e-6)
    assert yaw_deg == pytest.approx(math.degrees(math.atan2(x_lat, y_fwd)), abs=1e-9)


def test_out_of_range_returns_none():
    # 30 m away at a modest muzzle speed is unreachable.
    assert solve_angles_ballistic(0.0, 30.0, 0.0, v_ms=8.0) is None


def test_target_behind_returns_none():
    assert solve_angles_ballistic(0.0, 0.1, 0.0, v_ms=12.0) is None
