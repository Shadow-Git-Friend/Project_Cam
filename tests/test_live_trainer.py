import math
import json
import socket
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


def _standing_joints(elbow_angle_deg):
    """COCO-17 body standing upright; arms swing through shoulder-elbow-wrist
    angle == elbow_angle_deg. The torso is vertical, so posture_metrics reports
    a ~90 deg incline and the push-up acquisition gate must reject it."""
    joints = [None] * 17
    t = math.radians(elbow_angle_deg)

    def side(y):
        shoulder = [0.0, y, 1400.0]
        elbow = [0.0, y, 1200.0]
        wrist = [200.0 * math.sin(t), y, 1200.0 + 200.0 * math.cos(t)]
        hip = [0.0, y, 950.0]
        knee = [0.0, y, 500.0]
        ankle = [0.0, y, 80.0]
        return shoulder, elbow, wrist, hip, knee, ankle

    for idx, point in zip([5, 7, 9, 11, 13, 15], side(-180.0)):
        joints[idx] = point
    for idx, point in zip([6, 8, 10, 12, 14, 16], side(180.0)):
        joints[idx] = point
    joints[0] = [0.0, 0.0, 1600.0]
    return joints


def _make(exercise):
    from project_cam.assessment.live_trainer.rep_state import make_counter
    from project_cam.assessment.rules import exercise_rules, load_rules

    config = load_rules("configs/exercises/football_academy_u10.yaml")
    return make_counter(exercise, exercise_rules(config, exercise))


# Realistic multi-frame rep traces. The live counter EMA-smooths the signal
# angle, so patterns are long enough for the filter to settle each rep.
# Squat frames are (knee_angle_deg, hip_z_mm); push-up frames are elbow angle.
_SQUAT_REP = list(zip(
    [167, 160, 148, 132, 116, 102, 93, 93, 100, 114, 130, 145, 156, 163, 167],
    [980, 966, 938, 892, 832, 705, 580, 560, 592, 700, 840, 905, 945, 968, 980],
))
_SHALLOW_SQUAT_REP = list(zip(
    [166, 160, 152, 144, 136, 130, 128, 134, 144, 154, 162, 166, 167],
    [980, 974, 965, 953, 940, 930, 925, 935, 953, 970, 980, 980, 980],
))
_PUSHUP_REP = [167, 158, 142, 124, 108, 95, 89, 95, 110, 128, 146, 158, 165, 168, 168]
_SHALLOW_PUSHUP_REP = [166, 158, 148, 140, 134, 130, 128, 132, 140, 150, 160, 166, 167]


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

    def test_trunk_cue_suppressed_when_ankles_weakly_tracked(self):
        """A bent-trunk push-up must not raise the trunk cue when the ankles
        were triangulated from too few cameras -- the angle is unreliable."""
        from project_cam.assessment.kinematics import frame_kinematics

        counter = _make("push_up")
        for elbow in _PUSHUP_REP:
            joints = _pushup_joints(elbow, hip_drop_mm=200.0)  # visibly bent trunk
            conf = [0.95 if p is not None else 0.0 for p in joints]
            cams = [3 if p is not None else 0 for p in joints]
            cams[15] = 1  # left ankle seen by only one camera
            cams[16] = 1  # right ankle seen by only one camera
            metrics = frame_kinematics(
                {"joints": joints, "joint_conf": conf, "joint_cams": cams}
            )
            counter.update(metrics)
        self.assertNotIn("trunk", counter.state.cue.lower())

    def test_pushup_acquires_without_ankle_joints(self):
        """Acquisition must not depend on the ankles: an athlete whose feet
        are out of frame / mistracked must still be counted."""
        counter = _make("push_up")
        for elbow in _PUSHUP_REP:
            joints = _pushup_joints(elbow)
            joints[15] = None  # ankles missing entirely
            joints[16] = None
            counter.update(_metrics(joints))
        self.assertTrue(counter.state.acquired)
        self.assertEqual(counter.state.rep_count, 1)


def _metrics_with_ankle_cams(joints, ankle_cams):
    """Build kinematics for push-up tests with explicit ankle camera counts."""
    from project_cam.assessment.kinematics import frame_kinematics

    conf = [0.95 if p is not None else 0.0 for p in joints]
    cams = [3 if p is not None else 0 for p in joints]
    cams[15] = int(ankle_cams)
    cams[16] = int(ankle_cams)
    return frame_kinematics({"joints": joints, "joint_conf": conf, "joint_cams": cams})


class RepCounterTrunkCueAnkleStreakTests(unittest.TestCase):
    """A single fluky frame of multi-cam ankle tracking must not be enough to
    let the trunk cue fire -- the cue is anchored on the shoulder-hip-ankle
    triangle, so ankle geometry has to be reliable over several frames before
    we trust the resulting trunk angle.
    """

    def test_trunk_cue_blocked_until_ankle_streak_satisfied(self):
        counter = _make("push_up")
        # Acquire the set with ankles weakly tracked. The acquisition gate
        # ignores ankles, so the set still acquires; the trunk streak starts
        # at 0 because every acquisition frame has ankle_cams=1.
        for elbow in _PUSHUP_REP[:4]:
            counter.update(_metrics_with_ankle_cams(
                _pushup_joints(elbow, hip_drop_mm=200.0), ankle_cams=1))
        self.assertTrue(counter.state.acquired)

        # Four good-ankle frames -> streak builds to 4, still below the
        # required threshold of 5. Trunk cue must remain suppressed even
        # though the trunk is visibly bent.
        for elbow in _PUSHUP_REP[4:8]:
            counter.update(_metrics_with_ankle_cams(
                _pushup_joints(elbow, hip_drop_mm=200.0), ankle_cams=3))
        self.assertNotIn("trunk", counter.state.cue.lower())

    def test_trunk_cue_fires_once_ankle_streak_satisfied(self):
        counter = _make("push_up")
        # Acquire with weak ankles so the streak starts at zero.
        for elbow in _PUSHUP_REP[:4]:
            counter.update(_metrics_with_ankle_cams(
                _pushup_joints(elbow, hip_drop_mm=200.0), ankle_cams=1))
        self.assertTrue(counter.state.acquired)

        # Five+ good-ankle frames on a bent-trunk plank -> streak satisfied,
        # trunk cue may now fire.
        for elbow in _PUSHUP_REP[4:]:
            counter.update(_metrics_with_ankle_cams(
                _pushup_joints(elbow, hip_drop_mm=200.0), ankle_cams=3))
        self.assertIn("trunk", counter.state.cue.lower())

    def test_trunk_cue_blocked_when_ankle_cams_flicker(self):
        """A streak that resets on every other frame must never satisfy the
        ankle gate, even across many push-up frames."""
        counter = _make("push_up")
        for elbow in _PUSHUP_REP[:4]:
            counter.update(_metrics_with_ankle_cams(
                _pushup_joints(elbow, hip_drop_mm=200.0), ankle_cams=3))
        self.assertTrue(counter.state.acquired)

        # Repeated bent-trunk frames with ankles flickering between cams=1 and
        # cams=3. The streak never reaches the threshold, so the cue stays off.
        for idx, elbow in enumerate(_PUSHUP_REP[4:] * 3):
            cams = 3 if idx % 2 == 0 else 1
            counter.update(_metrics_with_ankle_cams(
                _pushup_joints(elbow, hip_drop_mm=200.0), ankle_cams=cams))
        self.assertNotIn("trunk", counter.state.cue.lower())


class RepCounterElbowVelocityClampTests(unittest.TestCase):
    """An impossible per-frame elbow-angle jump (occlusion / mislabel near a
    phase transition) must not be allowed to advance or close the rep cycle.
    The clamp rejects the spike and coasts on the prior value; a *sustained*
    jump across multiple consecutive frames is accepted as real fast motion."""

    def test_single_frame_elbow_spike_does_not_open_a_cycle(self):
        counter = _make("push_up")
        # Settle a stable plank, locked-out at the top.
        for _ in range(6):
            counter.update(_metrics(_pushup_joints(170)))
        self.assertTrue(counter.state.acquired)
        self.assertEqual(counter.state.status, "UP")

        # One-frame spike to elbow=30 (delta ~140 deg/frame, anatomically
        # impossible at 15 FPS). Without the clamp the EMA would drop
        # current_angle below the descent gate and flip status to DOWN.
        counter.update(_metrics(_pushup_joints(30)))

        self.assertEqual(counter.state.status, "UP")
        self.assertGreater(counter.state.current_angle, 150.0)

    def test_single_frame_elbow_spike_does_not_close_a_cycle(self):
        counter = _make("push_up")
        # Acquire and descend to the bottom of a push-up.
        for _ in range(6):
            counter.update(_metrics(_pushup_joints(170)))
        for elbow in (158, 140, 122, 105, 92, 88):
            counter.update(_metrics(_pushup_joints(elbow)))
        self.assertEqual(counter.state.status, "DOWN")
        rep_count_before = counter.state.rep_count

        # One-frame spike up to elbow=180 (delta ~92 deg/frame). The clamp
        # must reject the spike so the cycle is not falsely closed.
        counter.update(_metrics(_pushup_joints(180)))

        self.assertEqual(counter.state.status, "DOWN")
        self.assertEqual(counter.state.rep_count, rep_count_before)

    def test_sustained_elbow_change_is_accepted_after_streak(self):
        counter = _make("push_up")
        for _ in range(6):
            counter.update(_metrics(_pushup_joints(170)))
        # Sustained drop to 80 across multiple frames: the clamp coasts the
        # first anomaly frame then accepts the new value once it persists.
        for _ in range(4):
            counter.update(_metrics(_pushup_joints(80)))
        self.assertLess(counter.state.current_angle, 120.0)

    def test_normal_pushups_still_count_with_velocity_clamp(self):
        counter = _make("push_up")
        for _ in range(5):
            for elbow in _PUSHUP_REP:
                counter.update(_metrics(_pushup_joints(elbow)))
        self.assertEqual(counter.state.rep_count, 5)
        self.assertEqual(counter.state.incomplete_count, 0)


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


class UdpDrainTests(unittest.TestCase):
    def test_receive_available_drains_all_queued_packets_and_restores_timeout(self):
        from project_cam.assessment.live_trainer.__main__ import _receive_available

        class FakeSocket:
            def __init__(self):
                self.packets = [b"one", b"two", b"three"]
                self.blocking = True
                self.timeout = 0.2

            def recvfrom(self, _size):
                if self.packets:
                    return self.packets.pop(0), ("127.0.0.1", 5015)
                if self.blocking:
                    raise socket.timeout()
                raise BlockingIOError()

            def setblocking(self, value):
                self.blocking = bool(value)

            def settimeout(self, value):
                self.timeout = value
                self.blocking = value is not None

        sock = FakeSocket()

        packets = _receive_available(sock)

        self.assertEqual(packets, [b"one", b"two", b"three"])
        self.assertEqual(sock.timeout, 0.2)

    def test_process_joint_packets_updates_counter_for_every_drained_packet(self):
        from project_cam.assessment.live_trainer.__main__ import _process_joint_packets

        counter = _make("squat")
        packets = [
            json.dumps({"type": "joints", "joints": _squat_joints(knee, hip_z)}).encode("utf-8")
            for knee, hip_z in _SQUAT_REP
        ]

        last_joints, count = _process_joint_packets(
            packets, counter, fps=15.0, start_count=0, log_fh=None
        )

        self.assertEqual(count, len(_SQUAT_REP))
        self.assertEqual(counter.state.rep_count, 1)
        self.assertIsNotNone(last_joints)


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


class RepCounterPushUpAcquisitionTests(unittest.TestCase):
    def test_standing_arm_motion_is_not_counted_as_pushups(self):
        counter = _make("push_up")
        for _ in range(5):
            for elbow in _PUSHUP_REP:  # full elbow ROM, but the body is vertical
                counter.update(_metrics(_standing_joints(elbow)))
        self.assertEqual(counter.state.rep_count, 0)
        self.assertEqual(counter.state.incomplete_count, 0)
        self.assertFalse(counter.state.acquired)
        self.assertEqual(counter.state.phase, "WAITING")

    def test_horizontal_pushups_are_acquired(self):
        counter = _make("push_up")
        for elbow in _PUSHUP_REP:
            counter.update(_metrics(_pushup_joints(elbow)))
        self.assertTrue(counter.state.acquired)

    def test_single_horizontal_frame_does_not_acquire(self):
        """One horizontal frame amid standing motion must not start a set --
        acquisition needs several consecutive verified plank frames."""
        counter = _make("push_up")
        for elbow in (170, 150, 120):  # standing arm swing
            counter.update(_metrics(_standing_joints(elbow)))
        counter.update(_metrics(_pushup_joints(100)))  # one stray horizontal frame
        for elbow in (120, 150, 170):  # back to standing
            counter.update(_metrics(_standing_joints(elbow)))
        self.assertFalse(counter.state.acquired)
        self.assertEqual(counter.state.rep_count, 0)

    def test_standing_up_mid_pushup_abandons_open_cycle(self):
        counter = _make("push_up")
        for elbow in _PUSHUP_REP[:4]:  # descend into a plank push-up
            counter.update(_metrics(_pushup_joints(elbow)))
        self.assertEqual(counter.state.status, "DOWN")
        # Stand up before completing the rep; feed enough standing frames to
        # exceed the release debounce so the set is abandoned, not counted.
        for elbow in (110, 140, 165, 170, 170, 170, 170, 170, 170):
            counter.update(_metrics(_standing_joints(elbow)))
        self.assertEqual(counter.state.rep_count, 0)
        self.assertEqual(counter.state.incomplete_count, 0)
        self.assertFalse(counter.state.acquired)

    def test_brief_tracking_dropout_keeps_set_acquired(self):
        """A short tracking dropout inside an active set must not drop it:
        the release debounce coasts through a few bad frames."""
        counter = _make("push_up")
        for elbow in _PUSHUP_REP:  # acquire a set
            counter.update(_metrics(_pushup_joints(elbow)))
        self.assertTrue(counter.state.acquired)
        for _ in range(3):  # 3 bad frames (< release debounce)
            joints = _pushup_joints(110)
            for idx in (9, 10, 15, 16):  # drop wrists + ankles -> low tracking
                joints[idx] = None
            counter.update(_metrics(joints))
        self.assertTrue(counter.state.acquired)

    def test_noisy_short_cycle_is_not_counted(self):
        """A 2-frame elbow flicker that opens and closes a cycle must be
        ignored, not counted as a rep -- it is far too short to be real."""
        counter = _make("push_up")
        for _ in range(6):  # settle a plank, locked out at the top
            counter.update(_metrics(_pushup_joints(170)))
        self.assertTrue(counter.state.acquired)
        # Dip deep then snap straight in two frames: clears the ROM and depth
        # gates but is far too short in frame count to be a real push-up.
        counter.update(_metrics(_pushup_joints(90)))
        counter.update(_metrics(_pushup_joints(175)))
        self.assertEqual(counter.state.rep_count, 0)


if __name__ == "__main__":
    unittest.main()
