"""Tests for display-only pose latency compensation in the live viewer."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def load_live_module():
    path = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")
    spec = importlib.util.spec_from_file_location("live_4cam_arena_view_parallel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_tracking_kf(live, velocity_mm_s=(500.0, 0.0, 0.0), dt=1.0 / 15.0, steps=30):
    """KF fed a constant-velocity target long enough to converge."""
    kf = live.JointKalmanFilter(process_noise=500.0, measurement_noise=10.0, dt=dt)
    vel = np.asarray(velocity_mm_s)
    pos = np.array([1000.0, 2000.0, 900.0])
    for i in range(steps):
        if i > 0:
            kf.predict_step()
        kf.update_step(pos + vel * dt * i)
    return kf, pos + vel * dt * (steps - 1), vel


def test_compensation_leads_along_velocity():
    live = load_live_module()
    kf, last_pos, vel = make_tracking_kf(live)
    comp_s = 0.130
    state_pt = last_pos.astype(np.float32)
    out = live.latency_compensated_point(kf, state_pt, comp_s, max_uncertainty_mm=500.0)
    expected = last_pos + vel * comp_s
    assert out == pytest.approx(expected, abs=15.0)  # within KF convergence noise
    # And it must lead the state, not trail it.
    assert out[0] > state_pt[0]


def test_uninitialized_or_disabled_returns_state():
    live = load_live_module()
    kf = live.JointKalmanFilter()
    state_pt = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert live.latency_compensated_point(kf, state_pt, 0.13, 500.0) is state_pt
    assert live.latency_compensated_point(None, state_pt, 0.13, 500.0) is state_pt
    kf.update_step([1.0, 2.0, 3.0])
    assert live.latency_compensated_point(kf, state_pt, 0.0, 500.0) is state_pt


def test_high_uncertainty_falls_back_to_state():
    live = load_live_module()
    kf, last_pos, _ = make_tracking_kf(live, steps=2)  # barely initialized -> big P
    state_pt = last_pos.astype(np.float32)
    out = live.latency_compensated_point(kf, state_pt, 0.4, max_uncertainty_mm=1.0)
    assert out is state_pt


def test_measured_dt_predict_step_matches_elapsed_time():
    """predict_step(dt) must propagate position by v*dt — the property the
    --kalman-measured-dt flag relies on when the loop runs slower than --fps."""
    live = load_live_module()
    kf, last_pos, vel = make_tracking_kf(live)
    v_est = kf.get_velocity()
    p0 = kf.get_position()
    kf.predict_step(0.2)
    assert kf.get_position() == pytest.approx(p0 + v_est * 0.2, rel=1e-9)
