"""Tests for per-camera left/right keypoint relabeling (fix_lr_swaps_for_cam).

The 'both legs rise' artifact: a camera facing the person mirrors YOLO's
left/right labels; triangulating mixed labels collapses both 3D limbs onto
their average. The fix relabels each camera's L/R pairs against the previous
3D state before triangulation.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def load_live_module():
    path = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")
    spec = importlib.util.spec_from_file_location("live_4cam_arena_view_parallel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_cam():
    """Identity-rotation camera at the origin looking down +Z, no distortion."""
    R = np.eye(3)
    tvec = np.zeros(3)
    K = np.array([[800.0, 0.0, 320.0], [0.0, 800.0, 180.0], [0.0, 0.0, 1.0]])
    D = np.zeros(5)
    return R, tvec, K, D


def make_state_and_kpts(live, ankle_l=(-300.0, 0.0, 3000.0), ankle_r=(300.0, 0.0, 3000.0)):
    """3D state with distinct L/R ankles and the matching (correct) 2D kpts."""
    R, tvec, K, D = make_cam()
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    joints_state[15] = ankle_l  # left ankle
    joints_state[16] = ankle_r  # right ankle
    kpts = np.zeros((17, 2), dtype=np.float64)
    kpts[15] = live.project_world_to_pixel(joints_state[15], R, tvec, K, D)
    kpts[16] = live.project_world_to_pixel(joints_state[16], R, tvec, K, D)
    scores = np.zeros(17, dtype=np.float64)
    scores[15] = 0.9
    scores[16] = 0.8
    return joints_state, kpts, scores, (R, tvec, K, D)


def test_mirrored_labels_get_swapped_back():
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(live)
    correct = kpts.copy()
    # Simulate the camera mirroring left/right (labels swapped).
    kpts[[15, 16]] = kpts[[16, 15]]
    scores[15], scores[16] = scores[16], scores[15]
    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 1
    assert kpts[15] == pytest.approx(correct[15])
    assert kpts[16] == pytest.approx(correct[16])
    assert scores[15] == pytest.approx(0.9)  # confidence follows the point


def test_correct_labels_left_alone():
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(live)
    before = kpts.copy()
    n = live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam)
    assert n == 0
    assert kpts == pytest.approx(before)


def test_no_3d_state_means_no_swap():
    live = load_live_module()
    _, kpts, scores, cam = make_state_and_kpts(live)
    empty_state = np.full((17, 3), np.nan, dtype=np.float32)
    kpts[[15, 16]] = kpts[[16, 15]]
    assert live.fix_lr_swaps_for_cam(kpts, scores, empty_state, *cam) == 0


def test_low_confidence_pairs_skipped():
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(live)
    kpts[[15, 16]] = kpts[[16, 15]]
    scores[15] = 0.05  # below min_conf
    assert live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam, min_conf=0.2) == 0


def test_ambiguous_geometry_not_dithered():
    # L and R nearly coincident in this view: cross is not CLEARLY better,
    # so the margin must prevent a swap.
    live = load_live_module()
    joints_state, kpts, scores, cam = make_state_and_kpts(
        live, ankle_l=(-5.0, 0.0, 3000.0), ankle_r=(5.0, 0.0, 3000.0))
    kpts[15, 0] += 1.0  # tiny noise
    assert live.fix_lr_swaps_for_cam(kpts, scores, joints_state, *cam) == 0
