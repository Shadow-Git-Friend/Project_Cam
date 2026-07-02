import importlib.util
import subprocess
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
    assert "--avatar-body" in launcher
    assert "--avatar-markers" in launcher


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


def test_ball_inference_is_batch_chunked_for_six_cameras():
    # The TRT ball engine is exported with a batch<=4 optimization profile; a
    # direct ball_model(frame_batch) call on the 6-USB rig fails setInputShape
    # ([6,3,H,W]) and crashes ultralytics. The call site must chunk through
    # run_yolopose_batched, capped by --ball-max-batch.
    src = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py").read_text()
    ball_call = src.split("ball_results = ", 1)[1][:200]
    assert ball_call.lstrip().startswith("run_yolopose_batched(")
    assert "--ball-max-batch" in src


def test_v4l2_preflight_rejects_timed_out_device():
    live = load_live_module()

    def timeout_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    ok, reason = live.v4l2_device_ready(
        "/dev/video8",
        timeout_s=0.25,
        run_fn=timeout_runner,
        v4l2_ctl="/usr/bin/v4l2-ctl",
    )

    assert ok is False
    assert "timed out" in reason


def test_v4l2_preflight_allows_non_v4l_or_disabled_timeout():
    live = load_live_module()

    def failing_runner(*args, **kwargs):
        raise AssertionError("runner should not be called")

    assert live.v4l2_device_ready("rtsp://example", run_fn=failing_runner)[0] is True
    assert live.v4l2_device_ready("/dev/video0", timeout_s=0, run_fn=failing_runner)[0] is True


def test_cv2_renderer_accepts_avatar_switches():
    live = load_live_module()
    joints = np.full((17, 3), np.nan, dtype=np.float64)
    joints[5] = [900.0, 900.0, 1500.0]
    joints[6] = [1300.0, 900.0, 1500.0]
    joints[11] = [950.0, 900.0, 950.0]
    joints[12] = [1250.0, 900.0, 950.0]
    joints[0] = [1100.0, 900.0, 1780.0]

    img = live.draw_live_scene_cv2(
        img_w=320,
        img_h=240,
        dims={"X": 2200.0, "Y": 1800.0, "Z": 2200.0},
        tags={},
        extr={},
        ball_pt=None,
        ball_traj=[],
        joints=joints,
        frame_idx=1,
        fps_est=0.0,
        theme="classic",
        draw_axes=False,
        avatar_body=True,
        avatar_markers=True,
        avatar_alpha=0.85,
    )

    assert img.shape == (240, 320, 3)
    assert int(img.sum()) > 0


def test_cv2_renderer_accepts_smpl_mesh_overlay():
    live = load_live_module()
    vertices = np.asarray([
        [900.0, 900.0, 900.0],
        [1300.0, 900.0, 900.0],
        [1100.0, 900.0, 1500.0],
    ], dtype=np.float64)
    faces = np.asarray([[0, 1, 2]], dtype=np.int32)

    img = live.draw_live_scene_cv2(
        img_w=320,
        img_h=240,
        dims={"X": 2200.0, "Y": 1800.0, "Z": 2200.0},
        tags={},
        extr={},
        ball_pt=None,
        ball_traj=[],
        joints=None,
        frame_idx=1,
        fps_est=0.0,
        theme="classic",
        draw_axes=False,
        smpl_mesh_vertices=vertices,
        smpl_mesh_faces=faces,
        smpl_mesh_alpha=1.0,
    )

    assert img.shape == (240, 320, 3)
    assert int(img.sum()) > 0


def test_live_script_exposes_optional_smpl_avatar_flags():
    script = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py").read_text()

    assert "--smpl-avatar" in script
    assert "--smpl-model-path" in script
    assert "--smpl-fit-every" in script
    assert "--smpl-fit-iters" in script
    assert "--smpl-shape-calib-frames" in script
    assert "SmplSessionFitter" in script
