"""Lock Movement Quality severity escalation rules.

Three invariants this test enforces:

1. `info`-severity flags MUST NEVER escalate Movement Quality to "Needs review".
   `info` is reserved for observation-only signals that are explicitly not
   coaching cues (e.g. `knee_line_deviation`, demoted 2026-05-11 after the
   depth-confound finding).
2. `coaching`-severity flags MUST escalate Movement Quality by default.
3. The per-exercise `movement_quality.review_flag_severities` config controls
   which severities escalate. Adding `warning` there must include warnings.
"""

from __future__ import annotations

import unittest

from project_cam.assessment.reports import build_movement_quality


def _flag(code: str, severity: str) -> dict:
    return {"code": code, "severity": severity, "message": "", "value": 0.5, "threshold": 0.1}


def _ok_compliance() -> dict:
    return {"status": "ok"}


def _ok_demo() -> dict:
    return {"status": "usable"}


class MovementQualitySeverityTests(unittest.TestCase):
    def test_info_only_flags_do_not_escalate(self):
        mq = build_movement_quality(
            flags=[_flag("left_knee_line_deviation", "info"), _flag("right_knee_line_deviation", "info")],
            rep_quality=[{"status": "scored"}],
            compliance=_ok_compliance(),
            demo_verdict=_ok_demo(),
        )
        self.assertEqual(mq["status"], "good")
        self.assertEqual(mq["label"], "Looks good")
        self.assertEqual(mq["review_flag_count"], 0)

    def test_coaching_flag_escalates_by_default(self):
        mq = build_movement_quality(
            flags=[_flag("right_knee_valgus", "coaching")],
            rep_quality=[{"status": "scored"}],
            compliance=_ok_compliance(),
            demo_verdict=_ok_demo(),
        )
        self.assertEqual(mq["status"], "needs_review")
        self.assertEqual(mq["review_flag_count"], 1)

    def test_warning_does_not_escalate_with_default_rules(self):
        """Warnings are not in the default review set; they should not escalate."""
        mq = build_movement_quality(
            flags=[_flag("low_confidence", "warning")],
            rep_quality=[{"status": "scored"}],
            compliance=_ok_compliance(),
            demo_verdict=_ok_demo(),
        )
        self.assertEqual(mq["status"], "good")

    def test_warning_escalates_when_configured(self):
        rules = {"movement_quality": {"review_flag_severities": ["coaching", "warning"]}}
        mq = build_movement_quality(
            flags=[_flag("low_confidence", "warning")],
            rep_quality=[{"status": "scored"}],
            compliance=_ok_compliance(),
            demo_verdict=_ok_demo(),
            rules=rules,
        )
        self.assertEqual(mq["status"], "needs_review")
        self.assertEqual(mq["review_flag_count"], 1)

    def test_info_never_escalates_even_when_configured(self):
        """If someone misconfigures `info` into the review set, it must be discarded."""
        rules = {"movement_quality": {"review_flag_severities": ["info"]}}
        mq = build_movement_quality(
            flags=[_flag("left_knee_line_deviation", "info")],
            rep_quality=[{"status": "scored"}],
            compliance=_ok_compliance(),
            demo_verdict=_ok_demo(),
            rules=rules,
        )
        self.assertEqual(mq["status"], "good")
        self.assertNotIn("info", mq["review_severities"])

    def test_unscored_rep_escalates_independently_of_flags(self):
        mq = build_movement_quality(
            flags=[],
            rep_quality=[{"status": "unscored"}],
            compliance=_ok_compliance(),
            demo_verdict=_ok_demo(),
        )
        self.assertEqual(mq["status"], "needs_review")
        self.assertEqual(mq["unscored_rep_count"], 1)

    def test_calibration_failed_overrides_to_blocked(self):
        mq = build_movement_quality(
            flags=[_flag("right_knee_valgus", "coaching")],
            rep_quality=[{"status": "scored"}],
            compliance=_ok_compliance(),
            demo_verdict={"status": "calibration_failed"},
        )
        self.assertEqual(mq["status"], "blocked")
        self.assertEqual(mq["label"], "Cannot score")


if __name__ == "__main__":
    unittest.main()
