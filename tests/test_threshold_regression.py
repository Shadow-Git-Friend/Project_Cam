"""Pin valgus-threshold behavior against real recordings.

This is a regression lock: if anyone retunes `max_knee_valgus_signed_ratio` in
`configs/exercises/football_academy_u10.yaml` such that clean squats start
firing valgus flags or valgus squats stop firing them, this test fails. The
underlying recordings live in `data/raw/` and were captured 2026-05-11.
"""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_squat_report(recording_filename: str) -> dict:
    from project_cam.assessment.io import load_motion
    from project_cam.assessment.reports import build_report
    from project_cam.assessment.rules import load_rules

    frames = load_motion(REPO_ROOT / "data" / "raw" / recording_filename, default_fps=15.0)
    config = load_rules(REPO_ROOT / "configs" / "exercises" / "football_academy_u10.yaml")
    return build_report(
        frames=frames,
        exercise="squat",
        config=config,
        athlete_id="athlete_001",
        age=10,
        sex="male",
        fps=15.0,
    )


def _valgus_coaching_flags(report: dict) -> list[dict]:
    return [
        f
        for f in report.get("flags", [])
        if f.get("severity") == "coaching" and "valgus" in f.get("code", "")
    ]


class ValgusThresholdRegressionTests(unittest.TestCase):
    """Real-recording A/B that locks the 2026-05-11 threshold tuning."""

    def test_clean_squat_produces_zero_valgus_coaching_flags(self):
        report = _build_squat_report("athlete_001_squat_clean.jsonl")
        flags = _valgus_coaching_flags(report)
        self.assertEqual(
            flags,
            [],
            msg=(
                "Clean recording (max-side signed valgus 0.0121) must not fire any "
                "valgus coaching flag. If this fails, either the threshold was lowered "
                "below 0.012 or the metric/normalization changed."
            ),
        )

    def test_valgus_squat_produces_at_least_one_valgus_coaching_flag(self):
        report = _build_squat_report("athlete_001_squat_valgus.jsonl")
        flags = _valgus_coaching_flags(report)
        self.assertGreaterEqual(
            len(flags),
            1,
            msg=(
                "Valgus recording (max-side signed valgus 0.0304) must fire at least "
                "one valgus coaching flag. If this fails, either the threshold was "
                "raised above 0.030 or the metric stopped producing positive values."
            ),
        )

    def test_valgus_recording_max_side_passport_value_above_threshold(self):
        """Smoke-check that the passport summary captures the valgus magnitude we expect."""
        report = _build_squat_report("athlete_001_squat_valgus.jsonl")
        max_valgus = report["passport_summary"]["knee_valgus_max_signed_ratio"]
        self.assertIsNotNone(max_valgus)
        self.assertGreater(
            max_valgus,
            0.020,
            msg=f"Expected max signed valgus > 0.020, got {max_valgus}",
        )

    def test_clean_recording_max_side_passport_value_below_threshold(self):
        report = _build_squat_report("athlete_001_squat_clean.jsonl")
        max_valgus = report["passport_summary"]["knee_valgus_max_signed_ratio"]
        self.assertIsNotNone(max_valgus)
        self.assertLess(
            max_valgus,
            0.020,
            msg=f"Expected max signed valgus < 0.020 for clean recording, got {max_valgus}",
        )


if __name__ == "__main__":
    unittest.main()
