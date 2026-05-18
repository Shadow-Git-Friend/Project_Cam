import math
import unittest


def _metrics(joints):
    from project_cam.assessment.kinematics import frame_kinematics

    conf = [0.95 if p is not None else 0.0 for p in joints]
    cams = [3 if p is not None else 0 for p in joints]
    return frame_kinematics({"joints": joints, "joint_conf": conf, "joint_cams": cams})


def _squat_joints(knee_angle_deg, hip_z):
    """COCO-17 body in a squat pose; hip-knee-ankle angle == knee_angle_deg."""
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


def _pushup_joints(elbow_angle_deg, hip_drop_mm=0.0):
    """COCO-17 body in a push-up pose; shoulder-elbow-wrist angle == elbow_angle_deg.

    hip_drop_mm lowers the pelvis below the shoulder-ankle line, bending the
    shoulder-hip-ankle (trunk_to_leg) angle away from 180 degrees.
    """
    joints = [None] * 17
    t = math.radians(elbow_angle_deg)

    def side(y):
        shoulder = [0.0, y, 500.0]
        elbow = [0.0, y, 300.0]
        wrist = [200.0 * math.sin(t), y, 300.0 + 200.0 * math.cos(t)]
        hip = [600.0, y, 500.0 - hip_drop_mm]
        ankle = [1300.0, y, 500.0]
        return shoulder, elbow, wrist, hip, ankle

    for idx, point in zip([5, 7, 9, 11, 15], side(-180.0)):
        joints[idx] = point
    for idx, point in zip([6, 8, 10, 12, 16], side(180.0)):
        joints[idx] = point
    joints[0] = [0.0, 0.0, 560.0]
    return joints


def _make(exercise):
    from project_cam.assessment.live_trainer.rep_state import make_counter
    from project_cam.assessment.rules import exercise_rules, load_rules

    config = load_rules("configs/exercises/football_academy_u10.yaml")
    return make_counter(exercise, exercise_rules(config, exercise))


_SQUAT_REP = [(165, 1000), (132, 930), (102, 850), (88, 805), (105, 850), (135, 930), (165, 1000)]
_SHALLOW_SQUAT_REP = [(165, 1000), (150, 990), (140, 980), (135, 975), (140, 980), (150, 990), (165, 1000)]
_PUSHUP_REP = [165, 120, 95, 80, 95, 120, 165]
_SHALLOW_PUSHUP_REP = [165, 150, 138, 132, 138, 150, 165]


class RepCounterSquatTests(unittest.TestCase):
    def test_counts_five_clean_squats(self):
        counter = _make("squat")
        for _ in range(5):
            for knee, hip_z in _SQUAT_REP:
                counter.update(_metrics(_squat_joints(knee, hip_z)))
        self.assertEqual(counter.state.rep_count, 5)
        self.assertEqual(counter.state.incomplete_count, 0)
        self.assertEqual(counter.state.status, "UP")

    def test_shallow_squats_flagged_incomplete_not_counted(self):
        counter = _make("squat")
        for _ in range(5):
            for knee, hip_z in _SHALLOW_SQUAT_REP:
                counter.update(_metrics(_squat_joints(knee, hip_z)))
        self.assertEqual(counter.state.rep_count, 0)
        self.assertGreaterEqual(counter.state.incomplete_count, 1)
        self.assertIn("shallow", counter.state.cue.lower())


class RepCounterPushUpTests(unittest.TestCase):
    def test_counts_five_clean_push_ups(self):
        counter = _make("push_up")
        for _ in range(5):
            for elbow in _PUSHUP_REP:
                counter.update(_metrics(_pushup_joints(elbow)))
        self.assertEqual(counter.state.rep_count, 5)
        self.assertEqual(counter.state.incomplete_count, 0)

    def test_shallow_push_ups_flagged_incomplete(self):
        counter = _make("push_up")
        for _ in range(5):
            for elbow in _SHALLOW_PUSHUP_REP:
                counter.update(_metrics(_pushup_joints(elbow)))
        self.assertEqual(counter.state.rep_count, 0)
        self.assertGreaterEqual(counter.state.incomplete_count, 1)

    def test_trunk_misalignment_triggers_cue(self):
        counter = _make("push_up")
        for elbow in _PUSHUP_REP:
            counter.update(_metrics(_pushup_joints(elbow, hip_drop_mm=200.0)))
        cue = counter.state.cue.lower()
        self.assertTrue("trunk" in cue or "body" in cue)


class RepCounterTrackingTests(unittest.TestCase):
    def test_missing_leg_joints_show_low_tracking_no_false_reps(self):
        counter = _make("squat")
        for _ in range(5):
            for knee, hip_z in _SQUAT_REP:
                joints = _squat_joints(knee, hip_z)
                for idx in (13, 14, 15, 16):
                    joints[idx] = None
                counter.update(_metrics(joints))
        self.assertEqual(counter.state.rep_count, 0)
        self.assertFalse(counter.state.tracking_ok)
        self.assertLess(counter.state.tracking_quality, 0.5)


class DashboardTests(unittest.TestCase):
    def test_render_dashboard_returns_bgr_canvas(self):
        import numpy as np

        from project_cam.assessment.live_trainer.dashboard import render_dashboard
        from project_cam.assessment.live_trainer.rep_state import RepState

        state = RepState(rep_count=3, status="DOWN", phase="BOTTOM",
                         current_angle=92.0, depth_pct=80.0,
                         tracking_quality=0.9, tracking_ok=True, cue="Good form")
        joints = _squat_joints(92.0, 850.0)
        canvas = render_dashboard("squat", state, joints, width=900, height=720)

        self.assertEqual(canvas.shape, (720, 900, 3))
        self.assertEqual(canvas.dtype, np.uint8)

    def test_render_dashboard_handles_missing_joints(self):
        from project_cam.assessment.live_trainer.dashboard import render_dashboard
        from project_cam.assessment.live_trainer.rep_state import RepState

        canvas = render_dashboard("push_up", RepState(), [None] * 17)
        self.assertEqual(canvas.shape[2], 3)


if __name__ == "__main__":
    unittest.main()
