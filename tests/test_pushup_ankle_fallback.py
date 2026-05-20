"""Tests for the single-camera ankle fallback used in push-up coach mode.

When triangulation drops to one camera for an ankle joint, this helper
projects that camera's undistorted ray onto the floor Z-plane and gates
the result against the per-athlete tibia prior (so a foot-raised ray that
skims past the body and lands far down-arena does NOT get accepted just
because it geometrically intersects the floor). The hip-distance gate
catches the user's exact failure mode: when an athlete actively lifts a
foot, the floor-plane intersection of the ankle ray drifts laterally
beyond what the leg can possibly reach.

The helper is intentionally pure: it consumes already-undistorted obs,
the camera extrinsics, the multi-cam-triangulated knee and hip positions,
and the locked priors. State (per-frame consecutive-fallback counters)
lives in the caller.
"""

import unittest

import numpy as np


def _synthetic_camera_east_low(z_mm: float = 450.0):
    """Build a camera looking at the arena center from the East wall at low Z.

    Returns (R, tvec, K) suitable for project_ray_to_z_plane. World frame
    matches the project: X=arena length (0..6230), Y=arena width (0..3050),
    Z=vertical (0=floor). Camera at (~1600, 50, z_mm) looking toward
    (3115, 1525, 200). Z=450 is the post-remount target.
    """
    cam_pos = np.array([1600.0, 50.0, z_mm], dtype=np.float64)
    look_at = np.array([3115.0, 1525.0, 200.0], dtype=np.float64)
    z_axis = look_at - cam_pos
    z_axis /= np.linalg.norm(z_axis)
    up_w = np.array([0.0, 0.0, 1.0])
    x_axis = np.cross(up_w, z_axis); x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    # World->cam rotation: rows are the camera axes in world frame.
    R = np.stack([x_axis, y_axis, z_axis], axis=0)
    tvec = -R @ cam_pos
    K = np.array([[800.0, 0.0, 640.0], [0.0, 800.0, 360.0], [0.0, 0.0, 1.0]])
    return R, tvec, K


def _world_to_normalized_obs(world_pt: np.ndarray, R: np.ndarray, tvec: np.ndarray):
    """Project a 3D world point into normalized (undistorted) image coords."""
    X_c = R @ np.asarray(world_pt, dtype=np.float64) + tvec
    if X_c[2] <= 0:
        return None
    return float(X_c[0] / X_c[2]), float(X_c[1] / X_c[2])


def _priors(femur_l=420.0, femur_r=420.0, tibia_l=380.0, tibia_r=380.0):
    from project_cam.assessment.live_trainer.leg_priors import LegPriors

    return LegPriors(
        femur_l_mm=femur_l, femur_r_mm=femur_r,
        tibia_l_mm=tibia_l, tibia_r_mm=tibia_r,
        sample_count=4, locked_at_frame=10,
    )


class EvaluateAnkleFallbackTests(unittest.TestCase):
    def test_accepts_plausible_floor_ankle_with_good_anchors(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            evaluate_ankle_fallback,
        )

        R, tvec, _K = _synthetic_camera_east_low()
        priors = _priors()
        # Hip somewhere central; knee 420 mm down-arena from hip; true ankle
        # 380 mm further at Z=0 (floor contact).
        hip = np.array([2000.0, 1525.0, 200.0])
        knee = np.array([2420.0, 1525.0, 200.0])
        true_ankle = np.array([2800.0, 1525.0, 0.0])
        obs = _world_to_normalized_obs(true_ankle, R, tvec)
        self.assertIsNotNone(obs)

        result = evaluate_ankle_fallback(
            ankle_idx=15,
            obs_norm=obs,
            R=R, tvec=tvec, target_z_mm=0.0,
            knee_pt=knee, hip_pt=hip,
            priors=priors,
        )

        self.assertIsNotNone(result)
        # Should land within ~10 mm of the true ankle (no projection error
        # in a noise-free synthetic, only numerical precision).
        self.assertLess(float(np.linalg.norm(result - true_ankle)), 10.0)

    def test_rejects_ray_parallel_to_floor(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            evaluate_ankle_fallback,
        )

        # Construct a contrived R that projects the obs into a near-floor-parallel
        # world ray: third world axis (R^T column 2) has tiny Z component.
        R = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1e-9],  # near-parallel third row
        ])
        tvec = np.array([0.0, 0.0, 0.0])
        result = evaluate_ankle_fallback(
            ankle_idx=15,
            obs_norm=(0.0, 0.0),
            R=R, tvec=tvec, target_z_mm=0.0,
            knee_pt=np.array([100.0, 100.0, 100.0]),
            hip_pt=np.array([200.0, 100.0, 100.0]),
            priors=_priors(),
        )
        self.assertIsNone(result)

    def test_rejects_when_proposed_tibia_too_long(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            evaluate_ankle_fallback,
        )

        R, tvec, _K = _synthetic_camera_east_low()
        priors = _priors()
        # Drop a fake "ankle" that lands much further than tibia prior + 15%.
        hip = np.array([2000.0, 1525.0, 200.0])
        knee = np.array([2420.0, 1525.0, 200.0])
        # True ankle that, projected to floor, would land 900 mm from knee.
        bad_ankle = np.array([3320.0, 1525.0, 0.0])
        obs = _world_to_normalized_obs(bad_ankle, R, tvec)

        result = evaluate_ankle_fallback(
            ankle_idx=15,
            obs_norm=obs,
            R=R, tvec=tvec, target_z_mm=0.0,
            knee_pt=knee, hip_pt=hip,
            priors=priors,
        )
        self.assertIsNone(result)

    def test_rejects_lateral_drift_when_foot_is_raised(self):
        """User's reported failure mode: when the athlete raises one foot,
        the ray to Z=0 skims past the body and intersects the floor far
        down-arena. The hip-distance gate must catch this and return None."""
        from project_cam.assessment.live_trainer.leg_priors import (
            evaluate_ankle_fallback,
        )

        R, tvec, _K = _synthetic_camera_east_low()
        priors = _priors()  # femur 420 + tibia 380 = 800 mm leg
        # Hip + knee at one location; pretend the ray landed 2 m further
        # because the athlete's foot was up in the air at the time, and the
        # projection to Z=0 skimmed past the body.
        hip = np.array([2000.0, 1525.0, 200.0])
        knee = np.array([2420.0, 1525.0, 200.0])
        far_drift_floor_point = np.array([4500.0, 1525.0, 0.0])  # ~2.5 m from hip
        obs = _world_to_normalized_obs(far_drift_floor_point, R, tvec)

        result = evaluate_ankle_fallback(
            ankle_idx=15,
            obs_norm=obs,
            R=R, tvec=tvec, target_z_mm=0.0,
            knee_pt=knee, hip_pt=hip,
            priors=priors,
        )
        self.assertIsNone(result)

    def test_rejects_when_knee_anchor_missing(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            evaluate_ankle_fallback,
        )

        R, tvec, _K = _synthetic_camera_east_low()
        result = evaluate_ankle_fallback(
            ankle_idx=15,
            obs_norm=(0.1, 0.1),
            R=R, tvec=tvec, target_z_mm=0.0,
            knee_pt=None,  # no multi-cam knee -> cannot validate tibia
            hip_pt=np.array([2000.0, 1525.0, 200.0]),
            priors=_priors(),
        )
        self.assertIsNone(result)

    def test_rejects_when_hip_anchor_missing(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            evaluate_ankle_fallback,
        )

        R, tvec, _K = _synthetic_camera_east_low()
        result = evaluate_ankle_fallback(
            ankle_idx=15,
            obs_norm=(0.1, 0.1),
            R=R, tvec=tvec, target_z_mm=0.0,
            knee_pt=np.array([2420.0, 1525.0, 200.0]),
            hip_pt=None,  # no multi-cam hip -> cannot validate lateral drift
            priors=_priors(),
        )
        self.assertIsNone(result)

    def test_right_side_indexing_uses_right_priors(self):
        """Ankle index 16 must validate against femur_r/tibia_r priors."""
        from project_cam.assessment.live_trainer.leg_priors import (
            evaluate_ankle_fallback,
        )

        R, tvec, _K = _synthetic_camera_east_low()
        # Asymmetric priors: left tibia tight at 380; right tibia 600.
        priors = _priors(tibia_l=380.0, tibia_r=600.0)
        hip = np.array([2000.0, 1525.0, 200.0])
        knee = np.array([2420.0, 1525.0, 200.0])
        # Ankle at 580 mm from knee — within right tibia gate, outside left.
        true_ankle = np.array([3000.0, 1525.0, 0.0])
        obs = _world_to_normalized_obs(true_ankle, R, tvec)

        right_result = evaluate_ankle_fallback(
            ankle_idx=16, obs_norm=obs, R=R, tvec=tvec, target_z_mm=0.0,
            knee_pt=knee, hip_pt=hip, priors=priors,
        )
        left_result = evaluate_ankle_fallback(
            ankle_idx=15, obs_norm=obs, R=R, tvec=tvec, target_z_mm=0.0,
            knee_pt=knee, hip_pt=hip, priors=priors,
        )

        self.assertIsNotNone(right_result)
        self.assertIsNone(left_result)


if __name__ == "__main__":
    unittest.main()
