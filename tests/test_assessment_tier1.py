import json
import math
import tempfile
import unittest
from pathlib import Path


class AssessmentTier1Tests(unittest.TestCase):
    def test_mirwald_maturity_offset_for_boys_and_girls(self):
        from project_cam.assessment.maturity import calculate_maturity_offset

        boy = calculate_maturity_offset(
            sex="male",
            age_years=10.0,
            standing_height_cm=140.0,
            sitting_height_cm=72.0,
            body_mass_kg=34.0,
        )
        girl = calculate_maturity_offset(
            sex="female",
            age_years=10.0,
            standing_height_cm=140.0,
            sitting_height_cm=72.0,
            body_mass_kg=34.0,
        )

        self.assertAlmostEqual(boy["maturity_offset_years"], -3.2889, places=3)
        self.assertAlmostEqual(girl["maturity_offset_years"], -1.7889, places=3)
        self.assertEqual(boy["maturity_status"], "pre_phv")
        self.assertAlmostEqual(boy["age_at_phv_years"], 13.2889, places=3)

    def test_compliance_flags_shallow_squat_protocol(self):
        from project_cam.assessment.reports import build_report
        from project_cam.assessment.rules import load_rules

        frames = [{"joints": _squat_joints(angle)} for angle in [172, 168, 165, 160, 158, 162, 166, 170]]
        report = build_report(
            frames=frames,
            exercise="squat",
            config=load_rules("configs/exercises/football_academy_u10.yaml"),
            athlete_id="athlete_001",
            age=10,
            sex="male",
            fps=15.0,
            session_id="bad_squat",
        )

        self.assertEqual(report["compliance"]["status"], "insufficient")
        self.assertIn("Re-record", report["compliance"]["suggestion"])

    def test_squat_segmentation_rejects_angle_only_fake_rep(self):
        from project_cam.assessment.segmentation import detect_reps_with_rejections

        angles = [170, 166, 145, 118, 99, 94, 90, 96, 101, 113, 128, 143, 158, 170]
        metrics = [
            {
                "frame_index": idx,
                "angles_deg": {"left_knee": angle, "right_knee": angle + (1 if idx % 2 else 0)},
                "quality": {"valid_joint_ratio": 0.9},
            }
            for idx, angle in enumerate(angles)
        ]
        rules = {
            "segmentation": {
                "enter_angle_deg": 105,
                "exit_angle_deg": 135,
                "min_consecutive_frames": 2,
                "min_rep_duration_s": 0.5,
                "max_rep_duration_s": 3.0,
                "max_missing_frame_ratio": 0.3,
                "ema_alpha": 0.55,
            }
        }

        result = detect_reps_with_rejections(metrics, "squat", rules, fps=15.0)

        self.assertEqual(result["reps"], [])
        self.assertTrue(any(item["reason_code"] == "missing_joints" for item in result["rejected_reps"]))

    def test_calibration_check_reports_stable_and_unstable_tpose(self):
        from project_cam.assessment.cal_check import run_calibration_check

        stable = [{"joints": _tpose_joints(shoulder_jitter=0.0, wrist_jitter=0.0)} for _ in range(12)]
        unstable = [{"joints": _tpose_joints(shoulder_jitter=float(i * 8), wrist_jitter=0.0)} for i in range(12)]

        with tempfile.TemporaryDirectory() as td:
            stable_in = Path(td) / "stable.json"
            stable_out = Path(td) / "stable_report.json"
            unstable_in = Path(td) / "unstable.json"
            unstable_out = Path(td) / "unstable_report.json"
            stable_in.write_text(json.dumps(stable), encoding="utf-8")
            unstable_in.write_text(json.dumps(unstable), encoding="utf-8")

            stable_report = run_calibration_check(stable_in, stable_out, fps=15.0)
            unstable_report = run_calibration_check(unstable_in, unstable_out, fps=15.0)

        self.assertEqual(stable_report["status"], "ok")
        self.assertEqual(unstable_report["status"], "warning")
        self.assertGreater(unstable_report["measurements"]["shoulder_width_mm"]["std"], 15.0)

    def test_html_report_renderer_contains_coach_visible_sections(self):
        from project_cam.assessment.offline_assess import run_assessment
        from project_cam.assessment.render import render_html_report

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            input_path = td_path / "squat.json"
            json_path = td_path / "report.json"
            html_path = td_path / "report.html"
            input_path.write_text(json.dumps([{"joints": _squat_joints(a)} for a in [170, 140, 100, 90, 120, 155, 170]]), encoding="utf-8")
            report = run_assessment(
                input_path=input_path,
                output_path=json_path,
                exercise="squat",
                athlete_id="athlete_001",
                age=10,
                sex="male",
                fps=15.0,
                standing_height_cm=140.0,
                sitting_height_cm=72.0,
                body_mass_kg=34.0,
            )

            render_html_report(report, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("Chart.js", html)
        self.assertIn("athlete_001", html)
        self.assertIn("Coaching screen only", html)
        self.assertIn("Maturity Offset", html)
        self.assertIn("Angle Over Time", html)
        self.assertIn("Left / Right Symmetry", html)


def _squat_joints(knee_angle_deg):
    joints = [None] * 17
    theta = math.radians(knee_angle_deg)

    def side(x):
        hip = [x, 0, 1000]
        knee = [x, 0, 550]
        ankle = [x + 450 * math.sin(theta), 0, 550 + 450 * math.cos(theta)]
        shoulder = [x, 0, 1550]
        elbow = [x + 80, 0, 1250]
        wrist = [x + 120, 0, 1050]
        return shoulder, elbow, wrist, hip, knee, ankle

    left = side(-180)
    right = side(180)
    for idx, point in zip([5, 7, 9, 11, 13, 15], left):
        joints[idx] = point
    for idx, point in zip([6, 8, 10, 12, 14, 16], right):
        joints[idx] = point
    joints[0] = [0, 0, 1700]
    return joints


def _tpose_joints(shoulder_jitter, wrist_jitter):
    joints = [None] * 17
    joints[5] = [-200 - shoulder_jitter, 0, 1500]
    joints[6] = [200 + shoulder_jitter, 0, 1500]
    joints[7] = [-450, 0, 1500]
    joints[8] = [450, 0, 1500]
    joints[9] = [-700 - wrist_jitter, 0, 1500]
    joints[10] = [700 + wrist_jitter, 0, 1500]
    joints[11] = [-120, 0, 950]
    joints[12] = [120, 0, 950]
    joints[13] = [-120, 0, 520]
    joints[14] = [120, 0, 520]
    joints[15] = [-120, 0, 80]
    joints[16] = [120, 0, 80]
    return joints


if __name__ == "__main__":
    unittest.main()
