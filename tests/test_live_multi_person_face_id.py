"""Hardware-free integration contracts for multi-person/Face-ID viewer wiring."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from project_cam.closed_loop.firing_line import evaluate_firing_line
from project_cam.tracking import PersonTrack

VIEWER_PATH = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")


def load_viewer():
    spec = importlib.util.spec_from_file_location("live_multi_person_contract", VIEWER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def top_level_function_source(source, function_name):
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function_name
    )
    return ast.get_source_segment(source, node)


def test_viewer_help_exposes_multi_person_and_local_face_id_flags():
    result = subprocess.run(
        [sys.executable, str(VIEWER_PATH), "--help"],
        text=True,
        capture_output=True,
        check=True,
    )
    for flag in (
        "--multi-person",
        "--mp-gate-px",
        "--face-id",
        "--face-gallery",
        "--face-id-every",
        "--primary-person",
    ):
        assert flag in result.stdout


def test_primary_selection_prefers_locked_requested_name_then_keeps_current():
    viewer = load_viewer()
    tracks = {
        1: PersonTrack(1, np.zeros(3), 0, hits=20, name="Alice"),
        2: PersonTrack(2, np.ones(3), 0, hits=8, name="Bob"),
    }

    assert viewer.choose_primary_track_id(tracks, 1, "Bob", {1, 2}) == 2
    assert viewer.choose_primary_track_id(tracks, 1, "Missing", {1, 2}) == 1
    # A brief occlusion must not hand control to another person.  The
    # currently selected track stays primary while alive; the viable set only
    # gates *new* switches (including a requested Face-ID name).
    assert viewer.choose_primary_track_id(tracks, 1, "Alice", {2}) == 1
    assert viewer.choose_primary_track_id(tracks, 1, "Bob", {1}) == 1
    assert viewer.choose_primary_track_id(tracks, 1, "Bob", set()) == 1


def test_primary_selection_is_deterministic_when_current_track_disappears():
    viewer = load_viewer()
    tracks = {
        4: PersonTrack(4, np.zeros(3), 0, hits=3),
        2: PersonTrack(2, np.ones(3), 0, hits=9),
        3: PersonTrack(3, np.ones(3) * 2, 0, hits=9),
    }
    assert viewer.choose_primary_track_id(tracks, 99, "", {2, 3, 4}) == 2


def test_person_head_point_uses_visible_face_then_shoulder_fallback():
    viewer = load_viewer()
    joints = np.full((17, 3), np.nan, dtype=np.float32)
    joints[0] = (10, 20, 30)
    joints[1] = (12, 20, 32)
    np.testing.assert_allclose(
        viewer.person_head_point(joints, pelvis_mm=(0, 0, 0)), (11, 20, 31)
    )

    joints[:] = np.nan
    joints[5] = (0, 0, 1000)
    joints[6] = (100, 0, 1000)
    np.testing.assert_allclose(
        viewer.person_head_point(joints, pelvis_mm=(50, 0, 700)), (50, 0, 1350)
    )


def test_person_pelvis_point_uses_hips_or_torso_never_distal_joints():
    viewer = load_viewer()
    points = {
        9: np.array((900.0, 0.0, 1400.0)),
        10: np.array((-900.0, 0.0, 1400.0)),
    }
    assert viewer.person_pelvis_point(points) is None

    points[5] = np.array((100.0, 200.0, 1300.0))
    points[6] = np.array((300.0, 200.0, 1300.0))
    np.testing.assert_allclose(
        viewer.person_pelvis_point(points), (200.0, 200.0, 1300.0)
    )

    points[11] = np.array((120.0, 200.0, 900.0))
    points[12] = np.array((280.0, 200.0, 900.0))
    np.testing.assert_allclose(
        viewer.person_pelvis_point(points), (200.0, 200.0, 900.0)
    )


def test_cv2_renderer_accepts_secondary_people_labels_and_roster():
    viewer = load_viewer()
    parameters = inspect.signature(viewer.draw_live_scene_cv2).parameters
    assert {"extra_people", "primary_label", "face_roster"} <= set(parameters)

    primary = np.zeros((17, 3), dtype=np.float32)
    primary[:, 0] = np.linspace(700, 1000, 17)
    primary[:, 1] = 1200
    primary[:, 2] = np.linspace(1700, 100, 17)
    secondary = primary.copy()
    secondary[:, 0] += 900
    image = viewer.draw_live_scene_cv2(
        img_w=640,
        img_h=480,
        dims={"X": 5000.0, "Y": 4000.0, "Z": 2500.0},
        tags={},
        extr={},
        ball_pt=None,
        ball_traj=[],
        joints=primary,
        frame_idx=1,
        fps_est=15.0,
        extra_people=[
            {
                "joints": secondary,
                "label": "Bob",
                "identified": True,
                "color": (90, 200, 255),
            }
        ],
        primary_label={"text": "Alice", "identified": True, "color": (80, 220, 120)},
        face_roster=[
            {"label": "Alice", "identified": True, "color": (80, 220, 120)},
            {"label": "Bob", "identified": True, "color": (90, 200, 255)},
        ],
    )
    assert image.shape == (480, 640, 3)
    assert image.dtype == np.uint8


def test_secondary_pose_state_smooths_measurements_and_expires_stale_joints():
    viewer = load_viewer()
    state = viewer.make_secondary_pose_state()
    measurement = {
        0: {"point": np.array((10.0, 20.0, 30.0)), "conf": 0.8, "cams": 2}
    }

    viewer.update_secondary_pose_state(
        state, measurement, frame_idx=1, stale_frames=2,
        ema_alpha=1.0, snap_thresh_mm=0.0, display_alpha=1.0,
    )
    np.testing.assert_allclose(state["joints"][0], (10, 20, 30))
    np.testing.assert_allclose(state["display"][0], (10, 20, 30))
    assert state["conf"][0] == np.float32(0.8)
    assert state["cams"][0] == 2

    viewer.update_secondary_pose_state(
        state, {}, frame_idx=3, stale_frames=2,
        ema_alpha=1.0, snap_thresh_mm=0.0, display_alpha=1.0,
    )
    assert np.isfinite(state["display"][0]).all()
    viewer.update_secondary_pose_state(
        state, {}, frame_idx=4, stale_frames=2,
        ema_alpha=1.0, snap_thresh_mm=0.0, display_alpha=1.0,
    )
    assert np.isnan(state["joints"][0]).all()
    assert np.isnan(state["display"][0]).all()


def test_assigned_person_triangulation_keeps_joint_confidence_and_camera_count(monkeypatch):
    viewer = load_viewer()
    kpts_a = np.stack((np.arange(17), np.arange(17) + 10), axis=1).astype(float)
    kpts_b = kpts_a + 2.0
    candidates = {
        "A": [{"kpts": kpts_a, "scores": np.full(17, 0.9)}],
        "B": [{"kpts": kpts_b, "scores": np.full(17, 0.7)}],
    }
    monkeypatch.setattr(
        viewer,
        "undistort_points_batch",
        lambda points, _k, _d: [np.asarray(point) for point in points],
    )

    def fake_triangulate(obs, _obs_px, _proj, _extr, _intr, **_kwargs):
        mean = np.mean(np.asarray(list(obs.values())), axis=0)
        return np.array((mean[0], mean[1], 1000.0)), list(obs)

    monkeypatch.setattr(viewer, "robust_triangulate_joint", fake_triangulate)
    intr = {cam: {"K": np.eye(3), "D": np.zeros(5)} for cam in ("A", "B")}

    measured = viewer.triangulate_person_assignment(
        {"A": 0, "B": 0},
        candidates,
        intr=intr,
        proj={},
        extr={},
        joint_indices=(0, 11, 12),
        pose_conf=0.5,
        min_cams=2,
        max_reproj_px=40.0,
    )

    assert set(measured) == {0, 11, 12}
    assert measured[0]["cams"] == 2
    assert measured[0]["conf"] == 0.8
    np.testing.assert_allclose(measured[0]["point"], (1.0, 11.0, 1000.0))


def test_face_identity_tick_votes_for_nearest_projected_track_head():
    viewer = load_viewer()
    tracks = {
        1: PersonTrack(1, np.array((0.0, 0.0, 0.0)), 0),
        2: PersonTrack(2, np.array((100.0, 0.0, 0.0)), 0),
    }
    track_joints = {}
    for tid, x in ((1, 10.0), (2, 100.0)):
        joints = np.full((17, 3), np.nan)
        joints[0] = (x, 20.0, 30.0)
        track_joints[tid] = joints

    class Identifier:
        def detect_and_encode(self, _frame):
            return [
                {"center": np.array((12.0, 20.0)), "embedding": np.array([1.0])},
                {"center": np.array((98.0, 20.0)), "embedding": np.array([2.0])},
            ]

    class Gallery:
        def match(self, emb, min_score):
            return ("Alice", 0.9) if emb[0] == 1 else ("Bob", 0.8)

    from project_cam.tracking import NameVoter

    voters = {}
    assignments = viewer.apply_face_identity_tick(
        identifier=Identifier(),
        gallery=Gallery(),
        voters=voters,
        tracks=tracks,
        track_joints=track_joints,
        frame_bgr=np.zeros((40, 120, 3), dtype=np.uint8),
        camera_name="cam",
        project_fn=lambda point, _cam: np.asarray(point)[:2],
        gate_px=20.0,
        min_score=0.3,
        voter_factory=lambda: NameVoter(
            lock_score=0.5, min_votes=1, margin=0.1, max_misses=2, decay=1.0
        ),
    )

    assert assignments == {1: 0, 2: 1}
    assert tracks[1].name == "Alice"
    assert tracks[2].name == "Bob"


def test_single_person_face_context_requires_a_current_finite_pose():
    viewer = load_viewer()
    track = PersonTrack(0, np.zeros(3), -10_000_000)
    missing = np.full((17, 3), np.nan, dtype=np.float32)

    tracks, joints = viewer.single_person_identity_context(
        track, missing, missing.copy(), frame_idx=10
    )
    assert tracks == {}
    assert joints == {}
    assert track.last_seen_frame == -10_000_000

    distal_only = missing.copy()
    distal_only[9] = (100, 200, 1200)
    distal_only[10] = (140, 200, 1200)
    tracks, joints = viewer.single_person_identity_context(
        track, distal_only, distal_only.copy(), frame_idx=11
    )
    assert tracks == {}
    assert joints == {}

    current = missing.copy()
    current[11] = (100, 200, 900)
    current[12] = (140, 200, 900)
    tracks, joints = viewer.single_person_identity_context(
        track, current, current.copy(), frame_idx=11
    )
    assert tracks == {0: track}
    assert set(joints) == {0}
    np.testing.assert_allclose(track.pelvis_mm, (120, 200, 900))
    assert track.last_seen_frame == 11


def test_main_loop_wires_association_identity_and_secondary_render_payloads():
    viewer = load_viewer()
    source = inspect.getsource(viewer.main)
    for call in (
        "mp_tracker.step(",
        "triangulate_person_assignment(",
        "apply_face_identity_tick(",
        "extra_people=extra_people_render",
        "primary_label=primary_label_render",
        "face_roster=face_roster_render",
    ):
        assert call in source
    assert "if mp_tracker is None and face_identifier is not None" in source
    assert "len(camera_selection) >= 2" in source


def test_primary_switch_resets_person_specific_runtime_components():
    viewer = load_viewer()
    source = inspect.getsource(viewer.main)
    start = source.index("if next_primary_tid != mp_primary_tid:")
    end = source.index("mp_primary_tid = next_primary_tid", start)
    switch_block = source[start:end]

    for reset_contract in (
        "coach_counter = _coach_make_counter(",
        "leg_raise_tracker = type(leg_raise_tracker)(leg_raise_tracker.config)",
        "leg_raise_identity_tracker.reset()",
        "leg_raise_prior_acc.reset()",
        "leg_raise_contact_interpreter.reset()",
        "smpl_fitter.reset()",
    ):
        assert reset_contract in switch_block


def test_firing_line_snapshot_serializes_all_active_tracks_without_face_data():
    viewer = load_viewer()
    primary_state = viewer.make_secondary_pose_state()
    primary_state["joints"][0] = (100.0, 250.0, 1500.0)
    primary_state["conf"][0] = 0.95
    primary_state["cams"][0] = 4
    primary_state["last_seen"][0] = 41

    secondary_state = viewer.make_secondary_pose_state()
    secondary_state["joints"][5] = (900.0, 1200.0, 1300.0)
    secondary_state["conf"][5] = 0.8
    secondary_state["cams"][5] = 3
    secondary_state["last_seen"][5] = 40

    tracks = {
        3: PersonTrack(
            3,
            np.array((2000.0, 2000.0, 900.0)),
            39,
            name="Unlocalized Name",
            extras={"embedding": np.ones(4)},
        ),
        1: PersonTrack(
            1,
            np.array((100.0, 250.0, 900.0)),
            41,
            name="Primary Name",
        ),
        2: PersonTrack(
            2,
            np.array((900.0, 1200.0, 900.0)),
            40,
            name="Secondary Name",
        ),
    }

    snapshot = viewer.build_firing_line_safety_snapshot(
        snapshot_ts=1_800_000_000.25,
        frame_idx=42,
        y_max_mm=4000.0,
        y_mirrored=True,
        multi_person=True,
        primary_track_id=1,
        primary_epoch=4,
        tracks=tracks,
        primary_state=primary_state,
        secondary_states={2: secondary_state},
        ambiguous_detections=True,
        unassigned_candidate_count=2,
    )

    assert snapshot == {
        "schema": "project_cam.firing_line.v1",
        "snapshot_ts": 1_800_000_000.25,
        "frame": 42,
        "geometry_id": "world_mm",
        "y_mirrored": True,
        "mode": "multi_person",
        "primary_track_id": 1,
        "primary_epoch": 4,
        "observed_person_count": 3,
        "ambiguous_detections": True,
        "unassigned_candidate_count": 2,
        "people": [
            {
                "track_id": 1,
                "primary": True,
                "track_last_seen_frame": 41,
                "joints": {
                    "nose": {
                        "x_mm": 100.0,
                        "y_mm": 3750.0,
                        "z_mm": 1500.0,
                        "conf": pytest.approx(0.95),
                        "cams": 4,
                        "last_seen_frame": 41,
                    }
                },
            },
            {
                "track_id": 2,
                "primary": False,
                "track_last_seen_frame": 40,
                "joints": {
                    "left_shoulder": {
                        "x_mm": 900.0,
                        "y_mm": 2800.0,
                        "z_mm": 1300.0,
                        "conf": pytest.approx(0.8),
                        "cams": 3,
                        "last_seen_frame": 40,
                    }
                },
            },
            {
                "track_id": 3,
                "primary": False,
                "track_last_seen_frame": 39,
                "joints": {},
            },
        ],
    }
    encoded = json.dumps(snapshot, allow_nan=False)
    assert "Name" not in encoded
    assert "embedding" not in encoded


def test_firing_line_snapshot_explicitly_supports_single_person_pseudo_track_zero():
    viewer = load_viewer()
    state = viewer.make_secondary_pose_state()
    state["joints"][12] = (500.0, 750.0, 900.0)
    state["conf"][12] = 0.75
    state["cams"][12] = 2
    state["last_seen"][12] = 17

    snapshot = viewer.build_firing_line_safety_snapshot(
        snapshot_ts=123.5,
        frame_idx=17,
        y_max_mm=3000.0,
        y_mirrored=False,
        multi_person=False,
        primary_track_id=0,
        primary_epoch=0,
        tracks={0: {"last_seen_frame": 17, "name": "diagnostic only"}},
        primary_state=state,
        secondary_states={},
        ambiguous_detections=False,
        unassigned_candidate_count=0,
    )

    assert snapshot["mode"] == "single_person"
    assert snapshot["primary_track_id"] == 0
    assert snapshot["primary_epoch"] == 0
    assert snapshot["observed_person_count"] == 1
    assert snapshot["people"][0]["track_id"] == 0
    assert snapshot["people"][0]["primary"] is True
    assert snapshot["people"][0]["joints"]["right_hip"]["y_mm"] == 750.0
    assert "diagnostic only" not in json.dumps(snapshot)

    with pytest.raises(ValueError, match="positive"):
        viewer.build_firing_line_safety_snapshot(
            snapshot_ts=123.5,
            frame_idx=17,
            y_max_mm=3000.0,
            y_mirrored=False,
            multi_person=True,
            primary_track_id=0,
            primary_epoch=1,
            tracks={0: {"last_seen_frame": 17}},
            primary_state=state,
            secondary_states={},
            ambiguous_detections=False,
            unassigned_candidate_count=0,
        )


def test_firing_line_snapshot_rejects_missing_active_primary_track():
    viewer = load_viewer()
    state = viewer.make_secondary_pose_state()
    state["joints"][0] = (100.0, 200.0, 1500.0)
    state["conf"][0] = 0.9
    state["cams"][0] = 3
    state["last_seen"][0] = 20

    with pytest.raises(ValueError, match="active tracks"):
        viewer.build_firing_line_safety_snapshot(
            snapshot_ts=1_800_000_000.0,
            frame_idx=20,
            y_max_mm=4000.0,
            y_mirrored=False,
            multi_person=True,
            primary_track_id=1,
            primary_epoch=1,
            tracks={},
            primary_state=state,
            secondary_states={},
            ambiguous_detections=False,
            unassigned_candidate_count=0,
        )

    blocked = evaluate_firing_line(
        None,
        np.array([[0.0, 0.0, 1000.0], [4000.0, 0.0, 1000.0]]),
        now=1_800_000_000.0,
        expected_primary_track_id=1,
        expected_primary_epoch=1,
        expected_y_mirrored=False,
    )
    assert blocked.ok is False
    assert blocked.reason == "clearance_missing"


def test_firing_line_snapshot_never_invents_track_or_joint_freshness():
    viewer = load_viewer()
    state = viewer.make_secondary_pose_state()
    state["joints"][0] = (100.0, 200.0, 1500.0)
    state["conf"][0] = 0.9
    state["cams"][0] = 3
    state["last_seen"][0] = 20
    kwargs = {
        "snapshot_ts": 1_800_000_000.0,
        "frame_idx": 20,
        "y_max_mm": 4000.0,
        "y_mirrored": False,
        "multi_person": True,
        "primary_track_id": 1,
        "primary_epoch": 1,
        "tracks": {1: {}},
        "primary_state": state,
        "secondary_states": {},
        "ambiguous_detections": False,
        "unassigned_candidate_count": 0,
    }

    with pytest.raises(ValueError, match="track_last_seen_frame"):
        viewer.build_firing_line_safety_snapshot(**kwargs)

    kwargs["tracks"] = {1: {"last_seen_frame": 20}}
    state_without_freshness = dict(state)
    state_without_freshness.pop("last_seen")
    kwargs["primary_state"] = state_without_freshness
    with pytest.raises(ValueError, match="joint last_seen"):
        viewer.build_firing_line_safety_snapshot(**kwargs)


def test_valid_firing_line_snapshot_is_accepted_by_real_clearance_evaluator():
    viewer = load_viewer()
    primary = viewer.make_secondary_pose_state()
    primary["joints"][0] = (4000.0, 0.0, 1400.0)
    primary["conf"][0] = 0.9
    primary["cams"][0] = 3
    primary["last_seen"][0] = 42
    secondary = viewer.make_secondary_pose_state()
    for joint, point in {
        5: (1000.0, 2200.0, 1400.0),
        6: (1200.0, 2200.0, 1400.0),
        11: (1050.0, 2200.0, 900.0),
        12: (1150.0, 2200.0, 900.0),
    }.items():
        secondary["joints"][joint] = point
        secondary["conf"][joint] = 0.9
        secondary["cams"][joint] = 3
        secondary["last_seen"][joint] = 42

    snapshot = viewer.build_firing_line_safety_snapshot(
        snapshot_ts=1_800_000_000.0,
        frame_idx=42,
        y_max_mm=4000.0,
        y_mirrored=False,
        multi_person=True,
        primary_track_id=1,
        primary_epoch=2,
        tracks={
            1: PersonTrack(1, np.zeros(3), 42),
            2: PersonTrack(2, np.ones(3), 42),
        },
        primary_state=primary,
        secondary_states={2: secondary},
        ambiguous_detections=False,
        unassigned_candidate_count=0,
    )
    result = evaluate_firing_line(
        snapshot,
        np.array([[0.0, 0.0, 1000.0], [4000.0, 0.0, 1000.0]]),
        now=1_800_000_000.0,
        expected_primary_track_id=1,
        expected_primary_epoch=2,
        expected_y_mirrored=False,
        corridor_radius_mm=500.0,
    )

    assert result.ok is True


def test_primary_epoch_advances_for_every_real_change_including_initial_acquisition():
    viewer = load_viewer()

    epoch = viewer.advance_primary_epoch(
        primary_epoch=0, current_track_id=None, next_track_id=None
    )
    assert epoch == 0
    epoch = viewer.advance_primary_epoch(
        primary_epoch=epoch, current_track_id=None, next_track_id=7
    )
    assert epoch == 1
    epoch = viewer.advance_primary_epoch(
        primary_epoch=epoch, current_track_id=7, next_track_id=7
    )
    assert epoch == 1
    epoch = viewer.advance_primary_epoch(
        primary_epoch=epoch, current_track_id=7, next_track_id=3
    )
    assert epoch == 2
    epoch = viewer.advance_primary_epoch(
        primary_epoch=epoch, current_track_id=3, next_track_id=None
    )
    assert epoch == 3


def test_unassigned_pose_candidate_count_is_per_camera_and_assignment_aware():
    viewer = load_viewer()
    candidates = {
        "camA": [object(), object(), object()],
        "camB": [object(), object()],
        "camC": [],
    }
    assignments = {
        1: {"camA": 0, "camB": 1},
        2: {"camA": 2},
    }

    assert viewer.count_unassigned_pose_candidates(candidates, assignments) == 2


def test_unassigned_count_includes_raw_person_rejected_for_four_keypoints():
    viewer = load_viewer()
    keypoints = np.zeros((17, 2), dtype=np.float32)
    scores = np.zeros(17, dtype=np.float32)
    scores[:4] = 0.9

    rejected = viewer.extract_person_pose(
        {"keypoints": keypoints, "keypoint_scores": scores}
    )
    assert rejected is None
    assert viewer.count_unassigned_pose_candidates(
        {"camA": []},
        {},
        pose_raw_counts={"camA": 1},
    ) == 1


def test_pose_safety_observation_clock_advances_only_on_inference_success():
    viewer = load_viewer()

    assert viewer.update_pose_safety_observation(
        inference_succeeded=False,
        observation_ts=200.0,
        frame_idx=20,
        previous_ts=100.0,
        previous_frame=10,
    ) == (100.0, 10)
    assert viewer.update_pose_safety_observation(
        inference_succeeded=True,
        observation_ts=200.0,
        frame_idx=20,
        previous_ts=100.0,
        previous_frame=10,
    ) == (200.0, 20)


def test_pose_inference_completeness_requires_one_valid_result_per_camera():
    viewer = load_viewer()
    result_a = object()
    result_b = object()

    assert viewer.pose_inference_results_complete(
        [], expected_count=2, require_dict=False
    ) is False
    assert viewer.pose_inference_results_complete(
        [result_a], expected_count=2, require_dict=False
    ) is False
    assert viewer.pose_inference_results_complete(
        [result_a, None], expected_count=2, require_dict=False
    ) is False
    assert viewer.pose_inference_results_complete(
        [result_a, result_b], expected_count=2, require_dict=False
    ) is True

    empty_result = {"predictions": []}
    assert viewer.pose_inference_results_complete(
        [empty_result, None], expected_count=2, require_dict=True
    ) is False
    assert viewer.pose_inference_results_complete(
        [empty_result, result_b], expected_count=2, require_dict=True
    ) is False
    assert viewer.pose_inference_results_complete(
        [{}, empty_result], expected_count=2, require_dict=True
    ) is False
    assert viewer.pose_inference_results_complete(
        [empty_result, {"predictions": []}],
        expected_count=2,
        require_dict=True,
    ) is True


def test_pose_safety_ambiguity_preserves_previous_observation_on_failure():
    viewer = load_viewer()

    assert viewer.update_pose_safety_ambiguity(
        inference_succeeded=False,
        previous_unassigned_candidate_count=1,
        observed_unassigned_candidate_count=0,
    ) == (1, True)
    assert viewer.update_pose_safety_ambiguity(
        inference_succeeded=True,
        previous_unassigned_candidate_count=1,
        observed_unassigned_candidate_count=0,
    ) == (0, False)


def test_main_wires_pose_time_ambiguity_epoch_and_additive_safety_snapshot():
    viewer = load_viewer()
    source = inspect.getsource(viewer.main)

    for contract in (
        "pose_inference_succeeded = False",
        "pose_inference_results_complete(",
        "require_dict=False",
        "require_dict=True",
        "update_pose_safety_observation(",
        "update_pose_safety_ambiguity(",
        "advance_primary_epoch(",
        "count_unassigned_pose_candidates(",
        "pose_raw_counts=pose_raw_counts",
        "latest_safety_snapshot = None",
        "latest_safety_snapshot = build_firing_line_safety_snapshot(",
        'pkt["safety"] = latest_safety_snapshot',
    ):
        assert contract in source
    assert "last_pose_safety_ts = t_now" not in source
    success_index = source.index("pose_inference_results_complete(")
    clock_index = source.index("update_pose_safety_observation(")
    assert success_index < clock_index

    tree = ast.parse(source)
    joint_indices_assignment = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "triangulated_joint_indices"
            for target in node.targets
        )
    )
    expression = ast.unparse(joint_indices_assignment.value)
    assert "args.multi_person > 1 and udp_sock is not None" in expression
    assert "list(range(17))" in expression

    successful_pose_guards_tracker = any(
        "pose_inference_succeeded" in ast.unparse(if_node.test)
        and "mp_tracker.step(" in ast.unparse(if_node)
        for if_node in ast.walk(tree)
        if isinstance(if_node, ast.If)
    )
    assert successful_pose_guards_tracker

    successful_pose_guards_ambiguity = any(
        "pose_inference_succeeded" in ast.unparse(if_node.test)
        and "count_unassigned_pose_candidates(" in ast.unparse(if_node)
        for if_node in ast.walk(tree)
        if isinstance(if_node, ast.If)
    )
    assert successful_pose_guards_ambiguity

    guarded_safety_build = any(
        any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "latest_safety_snapshot"
                for target in node.targets
            )
            and "build_firing_line_safety_snapshot(" in ast.unparse(node)
            for statement in try_node.body
            for node in ast.walk(statement)
        )
        and any(
            isinstance(handler.type, ast.Name)
            and handler.type.id == "ValueError"
            for handler in try_node.handlers
        )
        for try_node in ast.walk(tree)
        if isinstance(try_node, ast.Try)
    )
    assert guarded_safety_build

    cached_snapshot_is_optional = any(
        "latest_safety_snapshot is not None" in ast.unparse(if_node.test)
        and any(
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Name)
            and node.value.id == "latest_safety_snapshot"
            and any(
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "pkt"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "safety"
                for target in node.targets
            )
            for node in ast.walk(if_node)
        )
        for if_node in ast.walk(tree)
        if isinstance(if_node, ast.If)
    )
    assert cached_snapshot_is_optional


def test_protected_viewer_functions_remain_byte_for_byte_equal_to_git_baseline():
    current_source = VIEWER_PATH.read_text()
    baseline_source = subprocess.run(
        ["git", "show", f"HEAD:{VIEWER_PATH.as_posix()}"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    for function_name in (
        "triangulate_multi",
        "transform_world_point_y",
        "ema_update",
    ):
        current = top_level_function_source(current_source, function_name)
        baseline = top_level_function_source(baseline_source, function_name)
        assert current == baseline
        assert ast.dump(ast.parse(current), include_attributes=False) == ast.dump(
            ast.parse(baseline), include_attributes=False
        )
