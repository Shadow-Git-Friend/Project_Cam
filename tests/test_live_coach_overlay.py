import unittest

import numpy as np


def _body_3d():
    joints = [None] * 17
    joints[5] = [-220.0, 0.0, 1500.0]
    joints[6] = [220.0, 0.0, 1500.0]
    joints[7] = [-300.0, 0.0, 1100.0]
    joints[8] = [300.0, 0.0, 1100.0]
    joints[9] = [-330.0, 0.0, 760.0]
    joints[10] = [330.0, 0.0, 760.0]
    joints[11] = [-180.0, 0.0, 950.0]
    joints[12] = [180.0, 0.0, 950.0]
    joints[13] = [-180.0, 0.0, 520.0]
    joints[14] = [180.0, 0.0, 520.0]
    joints[15] = [-180.0, 0.0, 80.0]
    joints[16] = [180.0, 0.0, 80.0]
    joints[0] = [0.0, 0.0, 1720.0]
    return joints


def _pose_2d(center_x=500.0, center_y=340.0, scale=1.0):
    kpts = np.full((17, 2), np.nan, dtype=np.float32)
    scores = np.zeros((17,), dtype=np.float32)
    points = {
        0: (center_x, center_y - 230 * scale),
        5: (center_x - 95 * scale, center_y - 150 * scale),
        6: (center_x + 95 * scale, center_y - 150 * scale),
        7: (center_x - 130 * scale, center_y - 55 * scale),
        8: (center_x + 130 * scale, center_y - 55 * scale),
        9: (center_x - 150 * scale, center_y + 50 * scale),
        10: (center_x + 150 * scale, center_y + 50 * scale),
        11: (center_x - 70 * scale, center_y + 10 * scale),
        12: (center_x + 70 * scale, center_y + 10 * scale),
        13: (center_x - 72 * scale, center_y + 155 * scale),
        14: (center_x + 72 * scale, center_y + 155 * scale),
        15: (center_x - 75 * scale, center_y + 295 * scale),
        16: (center_x + 75 * scale, center_y + 295 * scale),
    }
    for idx, pt in points.items():
        kpts[idx] = pt
        scores[idx] = 0.94
    return kpts, scores


class CoachCameraSelectionTests(unittest.TestCase):
    def test_squat_prefers_front_camera_from_body_orientation(self):
        from project_cam.assessment.live_trainer.coach_overlay import select_best_camera

        camera_positions = {
            "camFront": np.array([0.0, -3200.0, 1700.0]),
            "camSide": np.array([3200.0, 0.0, 1700.0]),
        }
        per_cam_pose = {
            "camFront": _pose_2d(),
            "camSide": _pose_2d(),
        }

        chosen = select_best_camera("squat", _body_3d(), per_cam_pose, camera_positions)

        self.assertEqual(chosen, "camFront")

    def test_pushup_prefers_side_camera_from_body_orientation(self):
        from project_cam.assessment.live_trainer.coach_overlay import select_best_camera

        camera_positions = {
            "camFront": np.array([0.0, -3200.0, 1700.0]),
            "camSide": np.array([3200.0, 0.0, 1700.0]),
        }
        per_cam_pose = {
            "camFront": _pose_2d(),
            "camSide": _pose_2d(),
        }

        chosen = select_best_camera("push_up", _body_3d(), per_cam_pose, camera_positions)

        self.assertEqual(chosen, "camSide")

    def test_pushup_camera_selection_prefers_visible_legs(self):
        from project_cam.assessment.live_trainer.coach_overlay import select_best_camera

        # Two equally well-aligned side cameras; only legs visibility differs.
        camera_positions = {
            "camA": np.array([3200.0, 0.0, 1700.0]),
            "camB": np.array([-3200.0, 0.0, 1700.0]),
        }
        good_kpts, good_scores = _pose_2d()
        weak_kpts, weak_scores = _pose_2d()
        weak_scores[[13, 14, 15, 16]] = 0.10  # legs barely seen on camB

        chosen = select_best_camera(
            "push_up",
            _body_3d(),
            {"camA": (good_kpts, good_scores), "camB": (weak_kpts, weak_scores)},
            camera_positions,
        )

        self.assertEqual(chosen, "camA")

    def test_camera_selection_keeps_previous_camera_on_small_score_changes(self):
        from project_cam.assessment.live_trainer.coach_overlay import select_best_camera

        camera_positions = {
            "camA": np.array([0.0, -3200.0, 1700.0]),
            "camB": np.array([0.0, -3000.0, 1700.0]),
        }
        pose_a = _pose_2d()
        pose_b = _pose_2d()
        pose_b[1][:] = np.minimum(1.0, pose_b[1] + 0.03)

        chosen = select_best_camera(
            "squat",
            _body_3d(),
            {"camA": pose_a, "camB": pose_b},
            camera_positions,
            previous_camera="camA",
        )

        self.assertEqual(chosen, "camA")


class CoachRoiTests(unittest.TestCase):
    def test_roi_stays_in_frame_and_uses_fixed_size_after_lock(self):
        from project_cam.assessment.live_trainer.coach_overlay import StableRoi

        roi = StableRoi(width=420, height=360, alpha=0.25)
        kpts_a, scores_a = _pose_2d(center_x=450.0, scale=0.8)
        kpts_b, scores_b = _pose_2d(center_x=900.0, scale=1.35)

        first = roi.update((720, 1280, 3), kpts_a, scores_a)
        second = roi.update((720, 1280, 3), kpts_b, scores_b)

        self.assertEqual(first.width, 420)
        self.assertEqual(first.height, 360)
        self.assertEqual(second.width, 420)
        self.assertEqual(second.height, 360)
        self.assertGreaterEqual(second.x1, 0)
        self.assertGreaterEqual(second.y1, 0)
        self.assertLessEqual(second.x2, 1280)
        self.assertLessEqual(second.y2, 720)
        self.assertLess(second.center[0], 900.0)

    def test_roi_center_is_not_dragged_by_one_bad_heel_keypoint(self):
        from project_cam.assessment.live_trainer.coach_overlay import StableRoi

        roi = StableRoi(width=420, height=360, alpha=1.0)
        kpts, scores = _pose_2d(center_x=650.0, center_y=360.0, scale=0.8)
        kpts[16] = [40.0, 40.0]
        scores[16] = 0.99

        locked = roi.update((720, 1280, 3), kpts, scores)

        self.assertGreater(locked.center[0], 520.0)


class CoachOverlayRenderingTests(unittest.TestCase):
    def test_pushup_overlay_prefers_projected_lower_body_keypoints(self):
        from project_cam.assessment.live_trainer.coach_overlay import repair_overlay_keypoints

        raw_kpts, raw_scores = _pose_2d()
        projected_kpts = np.full((17, 2), np.nan, dtype=np.float32)
        projected_scores = np.zeros((17,), dtype=np.float32)
        projected_kpts[13] = [410.0, 420.0]
        projected_kpts[14] = [510.0, 420.0]
        projected_kpts[15] = [390.0, 520.0]
        projected_kpts[16] = [530.0, 520.0]
        projected_scores[[13, 14, 15, 16]] = 0.95
        raw_kpts[15] = [80.0, 80.0]
        raw_kpts[16] = [90.0, 85.0]

        repaired_kpts, repaired_scores = repair_overlay_keypoints(
            "push_up", raw_kpts, raw_scores, projected_kpts, projected_scores
        )

        self.assertTrue(np.allclose(repaired_kpts[15], [390.0, 520.0]))
        self.assertTrue(np.allclose(repaired_kpts[16], [530.0, 520.0]))
        self.assertAlmostEqual(float(repaired_scores[15]), 0.95)
        self.assertTrue(np.allclose(repaired_kpts[7], raw_kpts[7]))

    def test_repair_rejects_projected_joint_with_impossible_limb(self):
        from project_cam.assessment.live_trainer.coach_overlay import repair_overlay_keypoints

        raw_kpts, raw_scores = _pose_2d()
        projected_kpts = np.full((17, 2), np.nan, dtype=np.float32)
        projected_scores = np.zeros((17,), dtype=np.float32)
        # Projected ankle teleported across the image (stale triangulation
        # landing on a background object) -> implausible shin length.
        projected_kpts[15] = [1250.0, 60.0]
        projected_scores[15] = 0.95

        repaired_kpts, _ = repair_overlay_keypoints(
            "push_up", raw_kpts, raw_scores, projected_kpts, projected_scores
        )

        self.assertTrue(np.allclose(repaired_kpts[15], raw_kpts[15]))

    def test_angle_labels_include_squat_knees(self):
        from project_cam.assessment.live_trainer.coach_overlay import collect_angle_labels

        kpts, scores = _pose_2d()
        metrics = {"angles_deg": {"left_knee": 96.0, "right_knee": 101.0}}

        labels = collect_angle_labels("squat", metrics, kpts, scores)
        texts = [label.text for label in labels]

        self.assertIn("L knee 96", texts)
        self.assertIn("R knee 101", texts)

    def test_angle_labels_include_pushup_elbows_and_trunk(self):
        from project_cam.assessment.live_trainer.coach_overlay import collect_angle_labels

        kpts, scores = _pose_2d()
        metrics = {
            "angles_deg": {
                "left_elbow": 88.0,
                "right_elbow": 91.0,
                "left_trunk_to_leg": 172.0,
                "right_trunk_to_leg": 174.0,
            }
        }

        labels = collect_angle_labels("push_up", metrics, kpts, scores)
        texts = [label.text for label in labels]

        self.assertIn("L elbow 88", texts)
        self.assertIn("R elbow 91", texts)
        self.assertIn("trunk 173", texts)

    def test_render_overlay_returns_canvas_and_draws_floor_guides(self):
        from project_cam.assessment.live_trainer.coach_overlay import render_coach_overlay
        from project_cam.assessment.live_trainer.rep_state import RepState

        frame = np.full((720, 1280, 3), 38, dtype=np.uint8)
        kpts, scores = _pose_2d()
        state = RepState(rep_count=2, status="DOWN", phase="BOTTOM",
                         current_angle=96.0, depth_pct=82.0,
                         tracking_quality=0.9, tracking_ok=True,
                         cue="Good rep")
        metrics = {"angles_deg": {"left_knee": 96.0, "right_knee": 101.0}}

        canvas = render_coach_overlay(frame, "squat", state, metrics, kpts, scores)

        self.assertEqual(canvas.shape, frame.shape)
        self.assertEqual(canvas.dtype, np.uint8)
        self.assertGreater(np.count_nonzero(canvas != frame), 1000)

    def test_render_overlay_handles_missing_pose_without_crashing(self):
        from project_cam.assessment.live_trainer.coach_overlay import render_coach_overlay
        from project_cam.assessment.live_trainer.rep_state import RepState

        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        kpts = np.full((17, 2), np.nan, dtype=np.float32)
        scores = np.zeros((17,), dtype=np.float32)

        canvas = render_coach_overlay(frame, "push_up", RepState(), {}, kpts, scores)

        self.assertEqual(canvas.shape, frame.shape)

    def test_render_overlay_shows_acquire_prompt_when_not_acquired(self):
        from project_cam.assessment.live_trainer.coach_overlay import render_coach_overlay
        from project_cam.assessment.live_trainer.rep_state import RepState

        frame = np.full((720, 1280, 3), 38, dtype=np.uint8)
        kpts, scores = _pose_2d()
        state = RepState(status="UP", phase="GET IN POSITION",
                         tracking_quality=0.9, tracking_ok=True,
                         acquired=False, cue="Get into push-up position")

        canvas = render_coach_overlay(frame, "push_up", state, {}, kpts, scores)

        self.assertEqual(canvas.shape, frame.shape)
        self.assertGreater(np.count_nonzero(canvas != frame), 1000)


def _kpts_with(positions, score=0.9):
    kpts = np.full((17, 2), np.nan, dtype=np.float32)
    scores = np.zeros((17,), dtype=np.float32)
    for idx, pos in positions.items():
        kpts[idx] = pos
        scores[idx] = score
    return kpts, scores


_EMPTY_KPTS = np.full((17, 2), np.nan, dtype=np.float32)
_EMPTY_SCORES = np.zeros((17,), dtype=np.float32)


class LegChainValidationTests(unittest.TestCase):
    def test_keeps_anatomically_plausible_legs(self):
        from project_cam.assessment.live_trainer.coach_overlay import validate_leg_chain

        kpts, scores = _pose_2d()
        _pts, out_scores = validate_leg_chain("push_up", kpts, scores)
        for idx in (13, 14, 15, 16):
            self.assertGreaterEqual(float(out_scores[idx]), 0.5)

    def test_drops_knee_off_body_axis(self):
        from project_cam.assessment.live_trainer.coach_overlay import validate_leg_chain

        kpts, scores = _pose_2d()
        # Knee yanked sideways from the hip (e.g. attached to floor clutter):
        # direction-from-hip no longer follows the body's long axis.
        kpts[13] = [kpts[11, 0] - 280.0, kpts[11, 1]]

        _pts, out_scores = validate_leg_chain("push_up", kpts, scores)

        self.assertEqual(float(out_scores[13]), 0.0)

    def test_drops_ankle_with_implausibly_long_bone(self):
        from project_cam.assessment.live_trainer.coach_overlay import validate_leg_chain

        kpts, scores = _pose_2d()
        # Ankle teleported far below the knee: bone length far exceeds torso.
        kpts[15] = [kpts[13, 0], kpts[13, 1] + 600.0]

        _pts, out_scores = validate_leg_chain("push_up", kpts, scores)

        self.assertEqual(float(out_scores[15]), 0.0)

    def test_drops_low_confidence_leg_joint(self):
        from project_cam.assessment.live_trainer.coach_overlay import validate_leg_chain

        kpts, scores = _pose_2d()
        scores[14] = 0.30  # below the push-up leg score bar

        _pts, out_scores = validate_leg_chain("push_up", kpts, scores)

        self.assertEqual(float(out_scores[14]), 0.0)

    def test_squat_is_not_validated(self):
        from project_cam.assessment.live_trainer.coach_overlay import validate_leg_chain

        kpts, scores = _pose_2d()
        kpts[13] = [kpts[11, 0] - 280.0, kpts[11, 1]]  # would fail for push-up

        _pts, out_scores = validate_leg_chain("squat", kpts, scores)

        self.assertEqual(float(out_scores[13]), float(scores[13]))


class OverlayKeypointStabilizerTests(unittest.TestCase):
    def test_steady_input_tracks_position(self):
        from project_cam.assessment.live_trainer.coach_overlay import OverlayKeypointStabilizer

        stab = OverlayKeypointStabilizer(alpha=0.5)
        kpts, scores = _kpts_with({11: (400.0, 350.0)})
        out_kpts, out_scores = None, None
        for _ in range(20):
            out_kpts, out_scores = stab.update(kpts, scores)
        self.assertTrue(np.allclose(out_kpts[11], [400.0, 350.0], atol=1.0))
        self.assertGreaterEqual(out_scores[11], 0.35)

    def test_ema_reduces_jitter(self):
        from project_cam.assessment.live_trainer.coach_overlay import OverlayKeypointStabilizer

        stab = OverlayKeypointStabilizer(alpha=0.4)
        xs_in, xs_out = [], []
        for i in range(30):
            x = 300.0 + (40.0 if i % 2 == 0 else -40.0)
            kpts, scores = _kpts_with({13: (x, 200.0)})
            out_kpts, _ = stab.update(kpts, scores)
            xs_in.append(x)
            xs_out.append(float(out_kpts[13][0]))
        # ignore the EMA settling head; steady-state spread must shrink
        self.assertLess(np.std(xs_out[10:]), np.std(xs_in[10:]))

    def test_coasts_through_brief_dropout(self):
        from project_cam.assessment.live_trainer.coach_overlay import OverlayKeypointStabilizer

        stab = OverlayKeypointStabilizer(alpha=1.0, coast_frames=4)
        valid_kpts, valid_scores = _kpts_with({15: (300.0, 400.0)})
        stab.update(valid_kpts, valid_scores)
        out_kpts, out_scores = None, None
        for _ in range(3):  # 3 missing frames, within the coast window of 4
            out_kpts, out_scores = stab.update(_EMPTY_KPTS, _EMPTY_SCORES)
        self.assertTrue(np.isfinite(out_kpts[15]).all())
        self.assertGreaterEqual(out_scores[15], 0.35)
        self.assertTrue(np.allclose(out_kpts[15], [300.0, 400.0]))

    def test_releases_joint_after_sustained_loss(self):
        from project_cam.assessment.live_trainer.coach_overlay import OverlayKeypointStabilizer

        stab = OverlayKeypointStabilizer(coast_frames=4)
        valid_kpts, valid_scores = _kpts_with({15: (300.0, 400.0)})
        stab.update(valid_kpts, valid_scores)
        out_kpts, out_scores = None, None
        for _ in range(6):  # 6 missing frames, past the coast window of 4
            out_kpts, out_scores = stab.update(_EMPTY_KPTS, _EMPTY_SCORES)
        self.assertFalse(np.isfinite(out_kpts[15]).all())
        self.assertEqual(float(out_scores[15]), 0.0)

    def test_jump_gate_rejects_teleport_and_coasts(self):
        from project_cam.assessment.live_trainer.coach_overlay import OverlayKeypointStabilizer

        stab = OverlayKeypointStabilizer(alpha=1.0, coast_frames=6, max_jump_px=150.0)
        near_kpts, near_scores = _kpts_with({13: (300.0, 300.0)})
        for _ in range(3):
            stab.update(near_kpts, near_scores)
        far_kpts, far_scores = _kpts_with({13: (700.0, 700.0)})
        out_kpts, out_scores = stab.update(far_kpts, far_scores)
        # the teleport is rejected; the joint coasts on its last good position
        self.assertTrue(np.allclose(out_kpts[13], [300.0, 300.0]))
        self.assertGreaterEqual(out_scores[13], 0.35)

    def test_jump_gate_allows_normal_motion(self):
        from project_cam.assessment.live_trainer.coach_overlay import OverlayKeypointStabilizer

        stab = OverlayKeypointStabilizer(alpha=1.0, coast_frames=6, max_jump_px=150.0)
        out_kpts = None
        for x in (300.0, 340.0, 385.0, 430.0):  # steady ~45 px/frame travel
            kpts, scores = _kpts_with({13: (x, 300.0)})
            out_kpts, _ = stab.update(kpts, scores)
        self.assertTrue(np.allclose(out_kpts[13], [430.0, 300.0]))

    def test_reacquire_after_release_snaps_without_smear(self):
        from project_cam.assessment.live_trainer.coach_overlay import OverlayKeypointStabilizer

        stab = OverlayKeypointStabilizer(alpha=0.5, coast_frames=2)
        far_kpts, far_scores = _kpts_with({13: (100.0, 100.0)})
        stab.update(far_kpts, far_scores)
        for _ in range(5):  # release the joint (past the coast window)
            stab.update(_EMPTY_KPTS, _EMPTY_SCORES)
        new_kpts, new_scores = _kpts_with({13: (800.0, 600.0)})
        out_kpts, _ = stab.update(new_kpts, new_scores)
        self.assertTrue(np.allclose(out_kpts[13], [800.0, 600.0]))


class FloorAnchorIdsTests(unittest.TestCase):
    """A push-up floor guide must default to the wrists (the actual hand-floor
    contacts); ankles are advisory and only joined in after a temporal-validity
    gate. Squat behaviour is unchanged."""

    def test_pushup_floor_defaults_to_wrists_only(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            compute_floor_anchor_ids,
        )

        kpts, scores = _pose_2d()
        ids = compute_floor_anchor_ids("push_up", kpts, scores, allow_ankles=False)
        self.assertEqual(sorted(ids), [9, 10])

    def test_pushup_floor_adds_ankles_only_when_explicitly_allowed(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            compute_floor_anchor_ids,
        )

        kpts, scores = _pose_2d()
        ids = compute_floor_anchor_ids("push_up", kpts, scores, allow_ankles=True)
        self.assertEqual(sorted(ids), [9, 10, 15, 16])

    def test_pushup_floor_drops_ankles_that_fail_validation(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            compute_floor_anchor_ids,
        )

        kpts, scores = _pose_2d()
        scores[15] = 0.0  # validate_leg_chain zeroed this ankle
        ids = compute_floor_anchor_ids("push_up", kpts, scores, allow_ankles=True)
        # The remaining valid ankle (16) is still added; the dropped one isn't.
        self.assertEqual(sorted(ids), [9, 10, 16])

    def test_squat_floor_uses_ankles_regardless_of_flag(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            compute_floor_anchor_ids,
        )

        kpts, scores = _pose_2d()
        ids_default = compute_floor_anchor_ids("squat", kpts, scores, allow_ankles=False)
        ids_allow = compute_floor_anchor_ids("squat", kpts, scores, allow_ankles=True)
        self.assertEqual(sorted(ids_default), [15, 16])
        self.assertEqual(sorted(ids_allow), [15, 16])


class PushupFloorAnchorTests(unittest.TestCase):
    """Ankle floor anchoring needs a sustained streak of valid ankles, not a
    single fluke frame."""

    def test_anchor_blocks_ankles_until_streak_reached(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            PushupFloorAnchor,
        )

        anchor = PushupFloorAnchor(required_streak=5)
        kpts, scores = _pose_2d()
        for _ in range(4):
            self.assertFalse(anchor.update(kpts, scores))
        self.assertTrue(anchor.update(kpts, scores))

    def test_anchor_resets_on_invalid_frame(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            PushupFloorAnchor,
        )

        anchor = PushupFloorAnchor(required_streak=5)
        kpts, scores = _pose_2d()
        for _ in range(6):
            anchor.update(kpts, scores)
        self.assertTrue(anchor.allow_ankles)

        bad_kpts, bad_scores = _pose_2d()
        bad_scores[15] = 0.0  # one ankle invalidated by leg-chain validator
        self.assertFalse(anchor.update(bad_kpts, bad_scores))
        self.assertFalse(anchor.allow_ankles)

    def test_anchor_is_only_satisfied_when_both_ankles_are_valid(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            PushupFloorAnchor,
        )

        anchor = PushupFloorAnchor(required_streak=3)
        kpts, scores = _pose_2d()
        only_left, only_left_scores = _pose_2d()
        only_left_scores[16] = 0.0  # right ankle missing for several frames
        for _ in range(5):
            self.assertFalse(anchor.update(only_left, only_left_scores))
        # Now both ankles valid -> streak builds from scratch.
        self.assertFalse(anchor.update(kpts, scores))
        self.assertFalse(anchor.update(kpts, scores))
        self.assertTrue(anchor.update(kpts, scores))


class RenderOverlayFloorAnchorTests(unittest.TestCase):
    """``render_coach_overlay`` must default the push-up floor to wrists when
    no anchor is supplied, and forward an anchor through to the floor guide."""

    def test_pushup_floor_y_is_pulled_to_wrists_without_anchor(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            render_coach_overlay,
        )
        from project_cam.assessment.live_trainer.rep_state import RepState

        frame = np.full((720, 1280, 3), 38, dtype=np.uint8)
        kpts, scores = _pose_2d(center_x=640.0, center_y=340.0)
        state = RepState(rep_count=0, status="DOWN", phase="BOTTOM",
                         current_angle=96.0, depth_pct=82.0,
                         tracking_quality=0.9, tracking_ok=True,
                         acquired=True, cue="")

        canvas = render_coach_overlay(frame, "push_up", state, {}, kpts, scores)

        floor_y = _floor_line_y(canvas, frame)
        wrist_y = int(kpts[9, 1])
        ankle_y = int(kpts[15, 1])
        self.assertIsNotNone(floor_y)
        # The floor line must sit on the wrists' y-level (within a few px for
        # rounding), not pulled down toward the ankles.
        self.assertLess(abs(floor_y - wrist_y), 8)
        self.assertGreater(abs(floor_y - ankle_y), 80)

    def test_pushup_floor_includes_ankles_when_anchor_streak_satisfied(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            PushupFloorAnchor,
            render_coach_overlay,
        )
        from project_cam.assessment.live_trainer.rep_state import RepState

        frame = np.full((720, 1280, 3), 38, dtype=np.uint8)
        kpts, scores = _pose_2d(center_x=640.0, center_y=340.0)
        state = RepState(rep_count=0, status="DOWN", phase="BOTTOM",
                         current_angle=96.0, depth_pct=82.0,
                         tracking_quality=0.9, tracking_ok=True,
                         acquired=True, cue="")
        anchor = PushupFloorAnchor(required_streak=1)
        anchor.update(kpts, scores)  # immediately satisfies the streak

        canvas = render_coach_overlay(
            frame, "push_up", state, {}, kpts, scores,
            pushup_floor_anchor=anchor,
        )

        floor_y = _floor_line_y(canvas, frame)
        wrist_y = int(kpts[9, 1])
        ankle_y = int(kpts[15, 1])
        self.assertIsNotNone(floor_y)
        # With both wrists and ankles contributing, the median y sits between
        # them -- specifically *below* both wrists.
        self.assertGreater(floor_y, wrist_y + 10)
        self.assertLess(floor_y, ankle_y - 10)

    def test_squat_floor_unchanged_when_anchor_is_present(self):
        from project_cam.assessment.live_trainer.coach_overlay import (
            PushupFloorAnchor,
            render_coach_overlay,
        )
        from project_cam.assessment.live_trainer.rep_state import RepState

        frame = np.full((720, 1280, 3), 38, dtype=np.uint8)
        kpts, scores = _pose_2d(center_x=640.0, center_y=340.0)
        state = RepState(rep_count=0, status="DOWN", phase="BOTTOM",
                         current_angle=96.0, depth_pct=82.0,
                         tracking_quality=0.9, tracking_ok=True,
                         acquired=True, cue="")
        anchor = PushupFloorAnchor(required_streak=1)
        anchor.update(kpts, scores)

        canvas = render_coach_overlay(
            frame, "squat", state, {}, kpts, scores,
            pushup_floor_anchor=anchor,  # must be ignored for squats
        )

        floor_y = _floor_line_y(canvas, frame)
        ankle_y = int(kpts[15, 1])
        self.assertIsNotNone(floor_y)
        self.assertLess(abs(floor_y - ankle_y), 8)


def _floor_line_y(canvas: np.ndarray, original: np.ndarray) -> int | None:
    """Locate the y-coordinate of the cyan floor line drawn by the overlay.

    The floor guide is the only near-horizontal cyan band added by the
    overlay; isolating pixels that match the floor-line color and were
    not present in the input frame gives a robust y-locator without
    re-implementing the drawing code in the test.
    """
    diff = np.any(canvas != original, axis=2)
    # Floor-line BGR is (76, 210, 228); allow small tolerance.
    floor_mask = (
        (np.abs(canvas[..., 0].astype(np.int16) - 76) < 25)
        & (np.abs(canvas[..., 1].astype(np.int16) - 210) < 25)
        & (np.abs(canvas[..., 2].astype(np.int16) - 228) < 25)
        & diff
    )
    rows = np.where(np.any(floor_mask, axis=1))[0]
    if rows.size == 0:
        return None
    # The brightest band sits at the median y of the matched pixels.
    return int(np.median(rows))


if __name__ == "__main__":
    unittest.main()
