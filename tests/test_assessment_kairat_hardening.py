import json
import math
import tempfile
import unittest
from pathlib import Path


class KairatHardeningTests(unittest.TestCase):
    def test_demo_config_exposes_squat_and_push_up(self):
        from project_cam.assessment.rules import load_rules

        config = load_rules("configs/exercises/football_academy_u10.yaml")

        self.assertEqual(
            set(config["exercises"].keys()),
            {"squat", "push_up"},
        )
        self.assertIn("deferred_exercises", config)
        self.assertNotIn("push_up", config["deferred_exercises"])
        self.assertIn("single_leg_squat", config["deferred_exercises"])
        self.assertIn("plank", config["deferred_exercises"])

    def test_pelvis_z_travel_detects_squat_rep_and_records_rep_quality(self):
        from project_cam.assessment.reports import build_report
        from project_cam.assessment.rules import load_rules

        frames = _five_good_squats(cams=3)

        report = build_report(
            frames=frames,
            exercise="squat",
            config=load_rules("configs/exercises/football_academy_u10.yaml"),
            athlete_id="athlete_001",
            age=10,
            sex="male",
            fps=15.0,
        )

        self.assertEqual(len(report["reps"]), 5)
        self.assertEqual(report["reps"][0]["segmentation_method"], "pelvis_z_plus_knee_hysteresis")
        self.assertGreaterEqual(report["reps"][0]["pelvis_travel_mm"], 150.0)
        self.assertEqual(report["rejected_reps"], [])
        self.assertEqual(report["rep_quality"][0]["status"], "scored")
        self.assertEqual(report["demo_verdict"]["status"], "usable")

    def test_noisy_knee_angle_without_pelvis_travel_is_rejected(self):
        from project_cam.assessment.reports import build_report
        from project_cam.assessment.rules import load_rules

        frames = [_squat_frame(knee_angle=angle, hip_z=1000 + (idx % 2), cams=3) for idx, angle in enumerate([165, 120, 88, 95, 130, 165])]

        report = build_report(
            frames=frames,
            exercise="squat",
            config=load_rules("configs/exercises/football_academy_u10.yaml"),
            athlete_id="athlete_001",
            age=10,
            sex="male",
            fps=15.0,
        )

        self.assertEqual(report["reps"], [])
        self.assertTrue(any(item["reason_code"] == "low_rom" for item in report["rejected_reps"]))
        self.assertEqual(report["demo_verdict"]["status"], "re_record")

    def test_low_joint_camera_confidence_blocks_knee_metric_scoring(self):
        from project_cam.assessment.reports import build_report
        from project_cam.assessment.rules import load_rules

        frames = _five_good_squats(cams=2)

        report = build_report(
            frames=frames,
            exercise="squat",
            config=load_rules("configs/exercises/football_academy_u10.yaml"),
            athlete_id="athlete_001",
            age=10,
            sex="male",
            fps=15.0,
        )

        knee_conf = report["metric_confidence"]["angles_deg"]["left_knee"]
        self.assertEqual(knee_conf["status"], "blocked")
        self.assertIn("left_knee", knee_conf["required_joints"])
        self.assertTrue(any(item["status"] == "unscored" for item in report["rep_quality"]))

    def test_legacy_json_marks_metric_confidence_limited(self):
        from project_cam.assessment.reports import build_report
        from project_cam.assessment.rules import load_rules

        frames = [
            {"joints": _squat_joints(165, 1000)},
            {"joints": _squat_joints(90, 805)},
            {"joints": _squat_joints(165, 1000)},
        ]

        report = build_report(
            frames=frames,
            exercise="squat",
            config=load_rules("configs/exercises/football_academy_u10.yaml"),
            athlete_id="legacy_001",
            age=10,
            sex="male",
            fps=10.0,
        )

        self.assertEqual(report["metric_confidence"]["angles_deg"]["left_knee"]["source"], "legacy_estimated")
        self.assertEqual(report["metric_confidence"]["angles_deg"]["left_knee"]["status"], "limited")

    def test_calibration_warning_sets_calibration_failed_verdict(self):
        from project_cam.assessment.reports import build_report
        from project_cam.assessment.rules import load_rules

        report = build_report(
            frames=_five_good_squats(cams=3),
            exercise="squat",
            config=load_rules("configs/exercises/football_academy_u10.yaml"),
            athlete_id="athlete_001",
            age=10,
            sex="male",
            fps=15.0,
            calibration={"status": "warning", "warnings": ["shoulder_width_mm jitter 21.0mm exceeds 15.0mm."]},
        )

        self.assertEqual(report["calibration_gate"]["status"], "failed")
        self.assertEqual(report["demo_verdict"]["status"], "calibration_failed")

    def test_html_report_contains_verdict_and_rep_table(self):
        from project_cam.assessment.render import render_html_report
        from project_cam.assessment.reports import build_report
        from project_cam.assessment.rules import load_rules

        report = build_report(
            frames=_five_good_squats(cams=3),
            exercise="squat",
            config=load_rules("configs/exercises/football_academy_u10.yaml"),
            athlete_id="athlete_001",
            age=10,
            sex="male",
            fps=15.0,
        )

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "report.html"
            render_html_report(report, out)
            html = out.read_text(encoding="utf-8")

        self.assertIn("Demo Verdict", html)
        self.assertIn("Rep Quality Table", html)
        self.assertIn("Pelvis Travel", html)
        # New wording: signed valgus when above threshold, otherwise undirected.
        self.assertTrue(
            "Right knee drifts inward (valgus)" in html
            or "Right knee tracks off the hip-ankle line" in html,
            "expected the new valgus or hip-ankle-line message in HTML",
        )

    def test_real_garage_data_angles_are_bounded_and_low_confidence_is_explicit(self):
        from project_cam.assessment.offline_assess import run_assessment

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "garage_report.json"
            report = run_assessment(
                input_path="garage_lab_combined/output/motion_capture_data_garage.json",
                output_path=out,
                exercise="squat",
                athlete_id="garage_test",
                age=10,
                sex="male",
                fps=15.0,
            )

        for summary in report["metrics"]["angles_deg"].values():
            if summary is None:
                continue
            self.assertGreaterEqual(summary["min"], 0.0)
            self.assertLessEqual(summary["max"], 180.0)
        self.assertIn(report["metric_confidence"]["angles_deg"]["left_knee"]["status"], {"limited", "blocked", "trusted"})


def _squat_frame(knee_angle, hip_z, cams):
    joints = _squat_joints(knee_angle, hip_z)
    return {
        "joints": joints,
        "joint_conf": [0.95 if point is not None else 0.0 for point in joints],
        "joint_cams": [cams if point is not None else 0 for point in joints],
    }


def _five_good_squats(cams):
    pattern = [
        (165, 1000),
        (132, 930),
        (102, 850),
        (88, 805),
        (105, 850),
        (135, 930),
        (165, 1000),
    ]
    frames = []
    for _ in range(5):
        frames.extend(_squat_frame(knee_angle=angle, hip_z=hip_z, cams=cams) for angle, hip_z in pattern)
    return frames


def _squat_joints(knee_angle_deg, hip_z):
    joints = [None] * 17
    theta = math.radians(knee_angle_deg)

    def side(x):
        hip = [x, 0, hip_z]
        knee = [x, 0, hip_z - 450]
        ankle = [x + 450 * math.sin(theta), 0, hip_z - 450 + 450 * math.cos(theta)]
        shoulder = [x, 0, hip_z + 550]
        elbow = [x + 80, 0, hip_z + 250]
        wrist = [x + 120, 0, hip_z + 50]
        return shoulder, elbow, wrist, hip, knee, ankle

    for idx, point in zip([5, 7, 9, 11, 13, 15], side(-180)):
        joints[idx] = point
    for idx, point in zip([6, 8, 10, 12, 14, 16], side(180)):
        joints[idx] = point
    joints[0] = [0, 0, hip_z + 700]
    return joints


if __name__ == "__main__":
    unittest.main()
