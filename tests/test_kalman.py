"""Tests for the constant-velocity predictive Kalman filter."""

import numpy as np

from project_cam.geometry import JointKalmanFilter


def _run_constant_velocity(x0, v, n=80, dt=1.0 / 30.0, process_noise=50.0, meas_noise=5.0):
    kf = JointKalmanFilter(process_noise=process_noise, measurement_noise=meas_noise, dt=dt)
    for i in range(n):
        z = x0 + v * (i * dt)
        if not kf.initialized:
            kf.update_step(z)
        else:
            kf.predict_step()
            kf.update_step(z)
    return kf


def test_estimates_constant_velocity():
    x0 = np.array([100.0, 200.0, 300.0])
    v = np.array([200.0, -100.0, 50.0])  # mm/s
    kf = _run_constant_velocity(x0, v)
    assert np.allclose(kf.get_velocity(), v, atol=3.0)


def test_predict_ahead_leads_the_target():
    x0 = np.array([0.0, 0.0, 1000.0])
    v = np.array([300.0, 150.0, 0.0])  # mm/s
    dt = 1.0 / 30.0
    kf = _run_constant_velocity(x0, v, dt=dt)
    pos_now = kf.get_position()
    horizon = 0.3  # 300 ms lead, the lab targeting horizon
    pred = kf.predict_ahead(horizon)
    assert np.allclose(pred, pos_now + v * horizon, atol=2.0)


def test_predict_ahead_does_not_mutate_state():
    kf = _run_constant_velocity(np.zeros(3), np.array([100.0, 0.0, 0.0]))
    before = kf.get_position()
    kf.predict_ahead(0.5)
    assert np.allclose(kf.get_position(), before)


def test_uninitialized_predict_is_safe():
    kf = JointKalmanFilter()
    assert not kf.initialized
    assert np.allclose(kf.predict_ahead(0.4), np.zeros(3))


def test_uncertainty_grows_with_horizon():
    kf = _run_constant_velocity(np.zeros(3), np.array([50.0, 0.0, 0.0]))
    near = kf.prediction_uncertainty(0.1)
    far = kf.prediction_uncertainty(1.0)
    assert far > near
