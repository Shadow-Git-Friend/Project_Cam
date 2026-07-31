"""Live 3D mannequin avatar helpers."""

import json

import numpy as np

from project_cam.assessment.joints import JOINT_NAME_TO_INDEX, JOINT_NAMES
from project_cam.assessment.live_trainer.avatar_renderer import (
    AvatarRenderConfig,
    build_virtual_markers,
    draw_avatar_body_cv2,
)


def _joints(points_by_name):
    joints = np.full((len(JOINT_NAMES), 3), np.nan, dtype=np.float64)
    for name, point in points_by_name.items():
        joints[JOINT_NAME_TO_INDEX[name]] = np.asarray(point, dtype=np.float64)
    return joints


def _project_front(points):
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim == 1:
        pts = pts.reshape(1, 3)
    screen = np.column_stack([100.0 + pts[:, 0] * 0.1, 160.0 - pts[:, 2] * 0.1])
    ok = np.isfinite(screen).all(axis=1)
    return screen, ok


def test_build_virtual_markers_adds_torso_and_even_limb_markers():
    joints = _joints({
        "left_shoulder": [-200.0, 0.0, 1200.0],
        "right_shoulder": [200.0, 0.0, 1200.0],
        "left_hip": [-150.0, 0.0, 700.0],
        "right_hip": [150.0, 0.0, 700.0],
        "left_elbow": [-500.0, 0.0, 1050.0],
    })

    markers = build_virtual_markers(joints, AvatarRenderConfig(segment_marker_count=2))
    by_name = {marker.name: marker.xyz_mm for marker in markers}

    assert by_name["torso_center"] == [0.0, 0.0, 950.0]
    assert by_name["upper_torso_center"] == [0.0, 0.0, 1200.0]
    assert by_name["left_upper_arm_01"] == [-300.0, 0.0, 1150.0]
    assert by_name["left_upper_arm_02"] == [-400.0, 0.0, 1100.0]
    assert [marker.name for marker in markers] == sorted(marker.name for marker in markers)


def test_build_virtual_markers_skips_only_missing_segments():
    joints = _joints({
        "left_shoulder": [-200.0, 0.0, 1200.0],
        "right_shoulder": [200.0, 0.0, 1200.0],
        "left_hip": [-150.0, 0.0, 700.0],
        "right_hip": [150.0, 0.0, 700.0],
        "left_elbow": [-500.0, 0.0, 1050.0],
    })

    names = {marker.name for marker in build_virtual_markers(joints)}

    assert "left_upper_arm_01" in names
    assert "left_forearm_01" not in names
    assert "right_upper_arm_01" not in names
    assert "torso_center" in names


def test_virtual_markers_are_json_ready():
    joints = _joints({
        "left_shoulder": [-200.0, 0.0, 1200.0],
        "right_shoulder": [200.0, 0.0, 1200.0],
        "left_hip": [-150.0, 0.0, 700.0],
        "right_hip": [150.0, 0.0, 700.0],
    })

    payload = [marker.to_dict() for marker in build_virtual_markers(joints)]

    assert payload
    json.dumps(payload, ensure_ascii=True)


def test_draw_avatar_body_cv2_draws_body_and_markers():
    joints = _joints({
        "nose": [0.0, 0.0, 1450.0],
        "left_shoulder": [-200.0, 0.0, 1200.0],
        "right_shoulder": [200.0, 0.0, 1200.0],
        "left_hip": [-150.0, 0.0, 700.0],
        "right_hip": [150.0, 0.0, 700.0],
        "left_elbow": [-500.0, 0.0, 1050.0],
        "left_wrist": [-780.0, 0.0, 1000.0],
    })
    img = np.zeros((220, 220, 3), dtype=np.uint8)

    out = draw_avatar_body_cv2(
        img,
        joints,
        _project_front,
        AvatarRenderConfig(body_alpha=1.0, marker_radius_px=4),
    )

    assert out is img
    assert int(img.sum()) > 0
    assert np.count_nonzero(img[:, :, 0] > img[:, :, 2]) > 0  # blue marker pixels


def test_draw_avatar_body_cv2_handles_ear_joints_for_head_size():
    joints = _joints({
        "nose": [0.0, 0.0, 1450.0],
        "left_ear": [-80.0, 0.0, 1430.0],
        "right_ear": [80.0, 0.0, 1430.0],
        "left_shoulder": [-200.0, 0.0, 1200.0],
        "right_shoulder": [200.0, 0.0, 1200.0],
    })
    img = np.zeros((220, 220, 3), dtype=np.uint8)

    draw_avatar_body_cv2(img, joints, _project_front)

    assert int(img.sum()) > 0
