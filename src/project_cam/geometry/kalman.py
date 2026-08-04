"""Constant-velocity 3D Kalman filter for predictive targeting.

The launcher must aim where the target *will be* when the ball arrives, not where
it is now. After multi-view triangulation produces a 3D position each frame, this
filter smooths the track and extrapolates a short horizon ahead (200-400 ms in the
lab system) so the aim leads a moving athlete.

The filter operates purely on post-triangulation 3D points, so it is independent
of the camera stack and trivially unit-testable on synthetic trajectories.
"""

from __future__ import annotations

import numpy as np


class JointKalmanFilter:
    """Per-target 3D Kalman filter with a constant-velocity motion model.

    State vector ``[x, y, z, vx, vy, vz]`` (positions in mm, velocities in mm/s);
    measurement vector ``[x, y, z]``. Process noise uses the piecewise-constant
    white-noise-acceleration model, so a single ``process_noise`` standard
    deviation controls how aggressively the filter trusts new measurements over
    its motion prediction.
    """

    def __init__(self, process_noise=50.0, measurement_noise=80.0, dt=1.0 / 15.0):
        self.dt = dt
        self._initialized = False
        self.x = np.zeros(6, dtype=np.float64)
        self.P = np.eye(6, dtype=np.float64) * 1e4
        self.H = np.zeros((3, 6), dtype=np.float64)
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.H[2, 2] = 1.0
        self.R = np.eye(3, dtype=np.float64) * measurement_noise ** 2
        self._q_std = process_noise
        self.Q = self._build_Q(dt, process_noise)

    def _build_F(self, dt):
        """State transition for the constant-velocity model."""
        F = np.eye(6, dtype=np.float64)
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt
        return F

    def _build_Q(self, dt, q_std):
        """Piecewise-constant white-noise-acceleration process covariance."""
        q = q_std ** 2
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt3 * dt
        Q = np.zeros((6, 6), dtype=np.float64)
        for i in range(3):
            Q[i, i] = dt4 / 4 * q
            Q[i, i + 3] = dt3 / 2 * q
            Q[i + 3, i] = dt3 / 2 * q
            Q[i + 3, i + 3] = dt2 * q
        return Q

    def predict_step(self, dt=None):
        """Advance the state estimate forward by ``dt`` seconds."""
        if dt is None:
            dt = self.dt
        F = self._build_F(dt)
        Q = self._build_Q(dt, self._q_std)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update_step(self, z, measurement_noise_scale=1.0):
        """Fuse a measurement ``z = [x, y, z]`` (mm).

        The first measurement seeds the state (position only, zero velocity).
        ``measurement_noise_scale`` lets the caller temporarily distrust a noisy
        observation (e.g. a far-camera, low-confidence detection) without
        rebuilding the filter.
        """
        z = np.asarray(z, dtype=np.float64)
        if not self._initialized:
            self.x[:3] = z
            self.x[3:] = 0.0
            self.P = np.eye(6, dtype=np.float64) * 1e4
            self._initialized = True
            return
        y = z - self.H @ self.x
        scale = max(1e-6, float(measurement_noise_scale))
        R = self.R * (scale ** 2)
        S = self.H @ self.P @ self.H.T + R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(6) - K @ self.H) @ self.P

    def get_position(self):
        """Current filtered position ``[x, y, z]`` (mm)."""
        return self.x[:3].copy()

    def get_velocity(self):
        """Current estimated velocity ``[vx, vy, vz]`` (mm/s)."""
        return self.x[3:].copy()

    def predict_ahead(self, t_ahead_sec):
        """Position ``t_ahead_sec`` into the future, leaving the state untouched.

        This is the targeting lead: it answers "where will the joint be when the
        ball gets there" without committing the filter to that prediction.
        """
        if not self._initialized:
            return self.x[:3].copy()
        F = self._build_F(t_ahead_sec)
        x_pred = F @ self.x
        return x_pred[:3].copy()

    def prediction_uncertainty(self, t_ahead_sec):
        """Positional 1-sigma uncertainty (mm) of the lead prediction.

        The launcher can refuse to fire when this exceeds a threshold, trading a
        missed shot for a safe one when the track is poorly conditioned.
        """
        F = self._build_F(t_ahead_sec)
        Q = self._build_Q(t_ahead_sec, self._q_std)
        P_pred = F @ self.P @ F.T + Q
        return float(np.sqrt(P_pred[0, 0] + P_pred[1, 1] + P_pred[2, 2]))

    @property
    def initialized(self):
        return self._initialized
