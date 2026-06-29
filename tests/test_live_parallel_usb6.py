import importlib.util
from pathlib import Path

import numpy as np


def load_live_module():
    path = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")
    spec = importlib.util.spec_from_file_location("live_4cam_arena_view_parallel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_camera_order_from_config_keeps_legacy_order_then_adds_usb_cameras():
    live = load_live_module()
    cams_cfg = {
        "camUsb01_C920": {"device": "/dev/video8"},
        "camEast": {"device": "/dev/video0"},
        "camUsb02_1080P": {"device": "/dev/video4"},
        "camWest": {"device": "/dev/video2"},
    }

    assert live.camera_order_from_config(cams_cfg) == [
        "camEast",
        "camWest",
        "camUsb01_C920",
        "camUsb02_1080P",
    ]


def test_make_mosaic_accepts_six_camera_order():
    live = load_live_module()
    cam_order = [f"camUsb{i:02d}" for i in range(1, 7)]
    frames = {
        cam: np.full((8, 10, 3), idx, dtype=np.uint8)
        for idx, cam in enumerate(cam_order)
    }

    mosaic = live.make_mosaic(
        frames,
        ball_boxes={},
        per_cam_pose={},
        cam_order=cam_order,
        copy_frames=True,
    )

    assert mosaic.shape == (16, 30, 3)


def test_make_mosaic_can_resize_six_camera_tiles_for_fast_preview():
    live = load_live_module()
    cam_order = [f"camUsb{i:02d}" for i in range(1, 7)]
    frames = {
        cam: np.full((80, 100, 3), idx, dtype=np.uint8)
        for idx, cam in enumerate(cam_order)
    }

    mosaic = live.make_mosaic(
        frames,
        ball_boxes={},
        per_cam_pose={},
        cam_order=cam_order,
        tile_size=(50, 40),
        copy_frames=True,
    )

    assert mosaic.shape == (80, 150, 3)


def test_usb6_launcher_defaults_to_3d_only_low_latency_mode():
    launcher = Path("Parallel_working/run_live_usb6_mirrored_skeleton.sh").read_text()

    assert "--no-show-2d" in launcher
    assert "--no-show-ghost-skeleton" in launcher
    assert "--predict-ahead-ms 0" in launcher
    assert "--pose-every 2" in launcher


def test_usb6_launchers_default_to_usb2_safe_capture_size():
    for launcher_path in [
        Path("Parallel_working/run_live_usb6_mirrored_skeleton.sh"),
        Path("Parallel_working/run_live_usb6_blm.sh"),
    ]:
        launcher = launcher_path.read_text()

        assert 'WIDTH="${PROJECT_CAM_WIDTH:-640}"' in launcher
        assert 'HEIGHT="${PROJECT_CAM_HEIGHT:-360}"' in launcher


def test_yolopose_batches_stay_within_tensor_rt_profile_limit():
    live = load_live_module()
    calls = []

    class FakeYoloPose:
        def __call__(self, frames, **kwargs):
            calls.append(len(frames))
            return [object() for _ in frames]

    results = live.run_yolopose_batched(
        FakeYoloPose(),
        frames=[object() for _ in range(6)],
        max_batch_size=4,
        device="cuda:0",
        verbose=False,
        conf=0.15,
    )

    assert calls == [4, 2]
    assert len(results) == 6
