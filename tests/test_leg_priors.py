"""Tests for per-athlete leg-bone priors learned during push-up acquisition.

The accumulator only consumes frames where every leg joint (hips, knees,
ankles) was triangulated from at least two cameras and is finite. It locks
priors when N consecutive accepted frames agree within a tight std-dev
bound. The 3D validator then drops per-frame triangulated leg joints whose
parent-bone length is outside +/- 15% of the locked prior, so corrupted
triangulations cannot poison the EMA-blended joints_state downstream.
"""
import unittest

import numpy as np


def _push_up_legs(femur_l=420.0, femur_r=420.0, tibia_l=380.0, tibia_r=380.0,
                  hip_y_offset=180.0):
    """COCO-17 push-up legs in 3D world (mm). Body lies along +X with feet
    pointing toward +X. Hips at X=600, knees X=600+femur, ankles X further."""
    joints = {}
    # Hips
    joints[11] = np.array([600.0, -hip_y_offset, 200.0])  # left hip
    joints[12] = np.array([600.0, +hip_y_offset, 200.0])  # right hip
    # Knees: along +X from hips
    joints[13] = np.array([600.0 + femur_l, -hip_y_offset, 150.0])
    joints[14] = np.array([600.0 + femur_r, +hip_y_offset, 150.0])
    # Ankles: along +X from knees
    joints[15] = np.array([600.0 + femur_l + tibia_l, -hip_y_offset, 80.0])
    joints[16] = np.array([600.0 + femur_r + tibia_r, +hip_y_offset, 80.0])
    return joints


def _good_cams():
    """joints_cam list (17 ints) with all leg joints multi-cam tracked."""
    cams = [0] * 17
    for idx in (11, 12, 13, 14, 15, 16):
        cams[idx] = 3
    return cams


class LegPriorAccumulatorTests(unittest.TestCase):
    def test_locks_after_min_frames_with_low_std(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegPriorAccumulator,
        )

        acc = LegPriorAccumulator(min_frames=4, std_tol_mm=10.0)
        # Slight jitter (< 1 mm) — well within tolerance.
        for i in range(4):
            jitter = 0.5 * (i - 1.5)
            acc.observe(
                _push_up_legs(420.0 + jitter, 420.0 - jitter, 380.0, 380.0),
                _good_cams(),
            )
        priors = acc.try_lock()
        self.assertIsNotNone(priors)
        # Synthetic geometry has a 50 mm Z-offset between hip and knee, so
        # the Euclidean femur length is ~423 mm, not exactly 420. Same shape
        # for tibia. Generous delta keeps the test about behaviour (locks at
        # the mean) rather than about exact synthetic distances.
        self.assertAlmostEqual(priors.femur_l_mm, 420.0, delta=5.0)
        self.assertAlmostEqual(priors.femur_r_mm, 420.0, delta=5.0)
        self.assertAlmostEqual(priors.tibia_l_mm, 380.0, delta=10.0)
        self.assertAlmostEqual(priors.tibia_r_mm, 380.0, delta=10.0)
        self.assertGreaterEqual(priors.sample_count, 4)

    def test_does_not_lock_before_min_frames(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegPriorAccumulator,
        )

        acc = LegPriorAccumulator(min_frames=4)
        for _ in range(3):
            acc.observe(_push_up_legs(), _good_cams())
        self.assertIsNone(acc.try_lock())

    def test_rejects_high_std(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegPriorAccumulator,
        )

        acc = LegPriorAccumulator(min_frames=4, std_tol_mm=10.0)
        # Wide tibia jitter (~ +/- 30 mm) -> std too high to lock.
        for i in range(8):
            wide = 30.0 if i % 2 == 0 else -30.0
            acc.observe(
                _push_up_legs(tibia_l=380.0 + wide, tibia_r=380.0 - wide),
                _good_cams(),
            )
        self.assertIsNone(acc.try_lock())

    def test_ignores_frames_where_a_leg_joint_has_single_cam(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegPriorAccumulator,
        )

        acc = LegPriorAccumulator(min_frames=4)
        for _ in range(8):
            cams = _good_cams()
            cams[15] = 1  # left ankle only multi-cam-1 -> frame rejected
            acc.observe(_push_up_legs(), cams)
        # No frames accepted -> no lock.
        self.assertIsNone(acc.try_lock())

    def test_ignores_frames_with_nan_leg_point(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegPriorAccumulator,
        )

        acc = LegPriorAccumulator(min_frames=4)
        for _ in range(8):
            joints = _push_up_legs()
            joints[15] = np.array([np.nan, np.nan, np.nan])  # invalid 3D
            acc.observe(joints, _good_cams())
        self.assertIsNone(acc.try_lock())

    def test_reset_clears_state(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegPriorAccumulator,
        )

        acc = LegPriorAccumulator(min_frames=4)
        for _ in range(4):
            acc.observe(_push_up_legs(), _good_cams())
        self.assertIsNotNone(acc.try_lock())
        acc.reset()
        # After reset, must accumulate again from scratch.
        for _ in range(3):
            acc.observe(_push_up_legs(), _good_cams())
        self.assertIsNone(acc.try_lock())


class LegChainValidator3DTests(unittest.TestCase):
    def _priors(self):
        from project_cam.assessment.live_trainer.leg_priors import LegPriors

        return LegPriors(
            femur_l_mm=420.0, femur_r_mm=420.0,
            tibia_l_mm=380.0, tibia_r_mm=380.0,
            sample_count=4, locked_at_frame=10,
        )

    def test_keeps_legs_within_tolerance(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegChainValidator3D,
        )

        joints = _push_up_legs()  # exactly matches priors
        drops = LegChainValidator3D.filter_drops(joints, self._priors())
        self.assertEqual(drops, set())

    def test_drops_ankle_with_implausibly_long_tibia(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegChainValidator3D,
        )

        joints = _push_up_legs()
        # Left ankle pushed out by 600 mm -> tibia ~ 980 mm, way outside +/-15%.
        joints[15] = joints[15] + np.array([600.0, 0.0, 0.0])
        drops = LegChainValidator3D.filter_drops(joints, self._priors())
        self.assertIn(15, drops)
        self.assertNotIn(16, drops)

    def test_drops_knee_with_implausibly_short_femur(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegChainValidator3D,
        )

        joints = _push_up_legs()
        # Right knee pulled back so femur shrinks to ~120 mm.
        joints[14] = joints[12] + np.array([120.0, 0.0, -50.0])
        drops = LegChainValidator3D.filter_drops(joints, self._priors())
        self.assertIn(14, drops)

    def test_drops_missing_parent_does_not_cause_false_drop(self):
        """If the parent (hip/knee) is missing, the dependent joint cannot
        be validated -- it must NOT be dropped purely from absence."""
        from project_cam.assessment.live_trainer.leg_priors import (
            LegChainValidator3D,
        )

        joints = _push_up_legs()
        joints.pop(11)  # left hip absent
        drops = LegChainValidator3D.filter_drops(joints, self._priors())
        # Left knee (13) cannot be validated -> not dropped.
        self.assertNotIn(13, drops)
        # Right side is fully present -> no drops.
        self.assertNotIn(14, drops)
        self.assertNotIn(16, drops)

    def test_filter_drops_handles_empty_input(self):
        from project_cam.assessment.live_trainer.leg_priors import (
            LegChainValidator3D,
        )

        drops = LegChainValidator3D.filter_drops({}, self._priors())
        self.assertEqual(drops, set())


if __name__ == "__main__":
    unittest.main()
