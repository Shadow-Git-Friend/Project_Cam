"""Hardware-free integration contracts for multi-person/Face-ID viewer wiring."""

from __future__ import annotations

import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path

import numpy as np

from project_cam.tracking import PersonTrack

VIEWER_PATH = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")


def load_viewer():
    spec = importlib.util.spec_from_file_location("live_multi_person_contract", VIEWER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
