import json
import math
import tempfile
import unittest
from pathlib import Path


class AssessmentMvpTests(unittest.TestCase):
    def test_3d_angle_and_frame_kinematics_handle_missing_joints(self):
        from project_cam.assessment.kinematics import angle_degrees, frame_kinematics

        self.assertAlmostEqual(
            angle_degrees([0, 0, 1], [0, 0, 0], [1, 0, 0]),
            90.0,
            places=4,
        )
        self.assertIsNone(angle_degrees(None, [0, 0, 0], [1, 0, 0]))

        joints = [None] * 17
        joints[5] = [0, 0, 1500]    # left_shoulder
        joints[11] = [0, 0, 950]    # left_hip
        joints[13] = [0, 0, 500]    # left_knee
        joints[15] = [450, 0, 500]  # left_ankle

        metrics = frame_kinematics({"joints": joints})

        self.assertAlmostEqual(metrics["angles_deg"]["left_knee"], 90.0, places=4)
        self.assertIn("left_trunk_to_leg", metrics["angles_deg"])
        self.assertGreater(metrics["quality"]["valid_joint_ratio"], 0.0)
        self.assertLess(metrics["quality"]["valid_joint_ratio"], 1.0)

    def test_loads_existing_offline_json_and_udp_jsonl(self):
        from project_cam.assessment.io import load_motion
        from project_cam.assessment.joints import JOINT_NAME_TO_INDEX

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            offline_path = td_path / "motion.json"
            joints = [None] * 17
            joints[JOINT_NAME_TO_INDEX["left_knee"]] = [1, 2, 3]
            offline_path.write_text(json.dumps([{"joints": joints}]), encoding="utf-8")

            offline_frames = load_motion(offline_path, default_fps=15)
            self.assertEqual(len(offline_frames), 1)
            self.assertEqual(
                offline_frames[0]["joints"][JOINT_NAME_TO_INDEX["left_knee"]],
                [1.0, 2.0, 3.0],
            )

            udp_path = td_path / "session.jsonl"
            udp_path.write_text(
                json.dumps(
                    {
                        "type": "joints",
                        "frame": 3,
                        "ts": 10.5,
                        "joints": {
                            "left_knee": {
                                "x_mm": 10,
                                "y_mm": 20,
                                "z_mm": 30,
                                "conf": 0.75,
                                "cams": 3,
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            udp_frames = load_motion(udp_path, default_fps=15)
            idx = JOINT_NAME_TO_INDEX["left_knee"]
            self.assertEqual(udp_frames[0]["frame_index"], 3)
            self.assertEqual(udp_frames[0]["joints"][idx], [10.0, 20.0, 30.0])
            self.assertEqual(udp_frames[0]["joint_cams"][idx], 3)
            self.assertAlmostEqual(udp_frames[0]["joint_conf"][idx], 0.75)

    def test_report_generation_for_synthetic_squat(self):
        from project_cam.assessment.offline_assess import run_assessment

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            input_path = td_path / "squat.json"
            output_path = td_path / "report.json"
            input_path.write_text(json.dumps(_synthetic_squat_frames()), encoding="utf-8")

            report = run_assessment(
                input_path=input_path,
                output_path=output_path,
                exercise="squat",
                athlete_id="athlete_001",
                age=10,
                sex="male",
                fps=15.0,
                config_path=Path("configs/exercises/football_academy_u10.yaml"),
            )

            self.assertTrue(output_path.exists())
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], "project_cam.assessment.v1")
            self.assertEqual(saved["exercise"], "squat")
            self.assertEqual(saved["session"]["athlete_id"], "athlete_001")
            self.assertIn("confidence_score", saved["quality"])
            self.assertIn("left_knee", saved["metrics"]["angles_deg"])
            self.assertGreaterEqual(len(saved["reps"]), 1)
            self.assertGreaterEqual(len(report["reference_context"]), 5)
            text = json.dumps(saved).lower()
            self.assertNotIn("ronaldo", text)
            self.assertNotIn("messi", text)

    def test_confidence_decreases_when_joints_are_missing(self):
        from project_cam.assessment.kinematics import frame_kinematics
        from project_cam.assessment.metrics import confidence_score

        full = _synthetic_squat_frames()[0]
        partial = {"joints": [None] * 17}
        partial["joints"][13] = [0, 0, 500]

        full_quality = confidence_score([full], [frame_kinematics(full)])
        partial_quality = confidence_score([partial], [frame_kinematics(partial)])

        self.assertGreater(full_quality["confidence_score"], partial_quality["confidence_score"])

    def test_all_configured_exercises_generate_reports(self):
        from project_cam.assessment.reports import build_report
        from project_cam.assessment.rules import load_rules

        config = load_rules("configs/exercises/football_academy_u10.yaml")
        frames = _synthetic_squat_frames()

        for exercise in config["exercises"]:
            with self.subTest(exercise=exercise):
                report = build_report(
                    frames=frames,
                    exercise=exercise,
                    config=config,
                    athlete_id="athlete_001",
                    age=10,
                    sex="female",
                    fps=15.0,
                    session_id="session_001",
                )
                self.assertEqual(report["exercise"], exercise)
                self.assertIn("flags", report)
                self.assertIn("reference_context", report)


def _synthetic_squat_frames():
    pattern = [
        (170, 1000),
        (150, 945),
        (120, 875),
        (90, 805),
        (85, 800),
        (100, 850),
        (130, 925),
        (160, 990),
        (172, 1000),
    ]
    return [{"joints": _squat_joints(angle, hip_z)} for angle, hip_z in pattern]


def _squat_joints(knee_angle_deg, hip_z=1000):
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

    left = side(-180)
    right = side(180)
    for idx, point in zip([5, 7, 9, 11, 13, 15], left):
        joints[idx] = point
    for idx, point in zip([6, 8, 10, 12, 14, 16], right):
        joints[idx] = point
    joints[0] = [0, 0, hip_z + 700]
    return joints


if __name__ == "__main__":
    unittest.main()
