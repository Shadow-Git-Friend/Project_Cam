"""Unit tests for the safety-gate predicates used by BLM runtimes.

Pinning these is important because the gates are the layer that prevents the
launcher from firing at noisy / occluded / stale targets. A regression here
could lead to a bad shot in the garage.
"""

from __future__ import annotations

import unittest

from project_cam.closed_loop.safety_gates import evaluate_joint_gate


class SafetyGateTests(unittest.TestCase):
    def test_clean_sample_passes(self):
        sample = {"x_mm": 0, "y_mm": 0, "z_mm": 0, "conf": 0.9, "cams": 3, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.55,
            min_cameras=2,
            max_staleness_s=1.0,
            now=1_000.05,
        )
        self.assertTrue(result.ok)
        self.assertIsNone(result.reason)
        self.assertAlmostEqual(result.detail["age_s"], 0.05, places=3)

    def test_missing_sample_rejected_with_missing_reason(self):
        result = evaluate_joint_gate(
            None,
            min_confidence=0.55,
            min_cameras=2,
            max_staleness_s=1.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "missing")

    def test_missing_timestamp_rejected_with_missing_reason(self):
        sample = {"conf": 0.9, "cams": 3}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.55,
            min_cameras=2,
            max_staleness_s=1.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "missing")

    def test_stale_sample_rejected(self):
        sample = {"conf": 0.9, "cams": 3, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.55,
            min_cameras=2,
            max_staleness_s=0.5,
            now=1_002.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "stale")
        self.assertGreater(result.detail["age_s"], 0.5)

    def test_low_camera_count_rejected(self):
        sample = {"conf": 0.9, "cams": 1, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.0,  # disable conf check to isolate camera gate
            min_cameras=2,
            max_staleness_s=1.0,
            now=1_000.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "low_camera_count")
        self.assertEqual(result.detail["cams"], 1)

    def test_low_confidence_rejected(self):
        sample = {"conf": 0.30, "cams": 3, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.55,
            min_cameras=2,
            max_staleness_s=1.0,
            now=1_000.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "low_confidence")
        self.assertAlmostEqual(result.detail["conf"], 0.30, places=3)

    def test_zero_min_confidence_disables_confidence_check(self):
        sample = {"conf": 0.0, "cams": 3, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.0,
            min_cameras=2,
            max_staleness_s=1.0,
            now=1_000.0,
        )
        self.assertTrue(result.ok)

    def test_zero_min_cameras_disables_camera_check(self):
        sample = {"conf": 0.8, "cams": 0, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.5,
            min_cameras=0,
            max_staleness_s=1.0,
            now=1_000.0,
        )
        self.assertTrue(result.ok)

    def test_zero_max_staleness_disables_staleness_check(self):
        sample = {"conf": 0.8, "cams": 3, "ts": 1.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.5,
            min_cameras=2,
            max_staleness_s=0.0,
            now=999_999.0,
        )
        self.assertTrue(result.ok)

    def test_check_order_missing_before_stale(self):
        """If multiple gates would fail, the most diagnostic one surfaces first."""
        # No `ts`: missing wins over what would otherwise be low_confidence.
        sample = {"conf": 0.1, "cams": 0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.55,
            min_cameras=2,
            max_staleness_s=1.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "missing")

    def test_check_order_stale_before_cameras(self):
        sample = {"conf": 0.9, "cams": 0, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.5,
            min_cameras=2,
            max_staleness_s=0.5,
            now=1_002.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "stale")

    def test_check_order_cameras_before_confidence(self):
        sample = {"conf": 0.1, "cams": 1, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.55,
            min_cameras=2,
            max_staleness_s=1.0,
            now=1_000.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "low_camera_count")

    def test_string_conf_coerced_or_treated_as_zero(self):
        """Defensive: garbage conf field must not crash, just block."""
        sample = {"conf": "not-a-number", "cams": 3, "ts": 1_000.0}
        result = evaluate_joint_gate(
            sample,
            min_confidence=0.5,
            min_cameras=2,
            max_staleness_s=1.0,
            now=1_000.0,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "low_confidence")


if __name__ == "__main__":
    unittest.main()
