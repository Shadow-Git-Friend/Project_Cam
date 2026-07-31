import importlib.util
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml


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


def test_usb6_configs_match_recovered_calibrated_roles():
    expected = {
        "camUsb01_C920": "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_9718C21F-video-index0",
        "camUsb02_1080P": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:4.1:1.0-video-index0",
        "camUsb03_C920": "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_7B879F0F-video-index0",
        "camUsb04_1080P": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:6.1.1:1.0-video-index0",
        "camUsb05_1080P": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:5.1.1:1.0-video-index0",
        "camUsb06_1080P": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:11.1.1:1.0-video-index0",
    }
    for path in (
        Path("garage_lab_combined/config/cameras_6usb_test.yaml"),
        Path("configs/cameras/cameras_6cam_usb.yaml"),
    ):
        cameras = yaml.safe_load(path.read_text())["cameras"]
        actual = {name: info["device"] for name, info in cameras.items()}
        assert actual == expected


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


def test_usb6_skeleton_launcher_requires_all_six_cameras():
    launcher = Path(
        "Parallel_working/run_live_usb6_mirrored_skeleton.sh"
    ).read_text()

    assert "--min-active-cameras 6" in launcher


def test_usb6_launchers_default_to_usb2_safe_capture_size():
    for launcher_path in [
        Path("Parallel_working/run_live_usb6_mirrored_skeleton.sh"),
        Path("Parallel_working/run_live_usb6_blm.sh"),
    ]:
        launcher = launcher_path.read_text()

        assert 'WIDTH="${PROJECT_CAM_WIDTH:-640}"' in launcher
        assert 'HEIGHT="${PROJECT_CAM_HEIGHT:-360}"' in launcher


def test_lowlag_launcher_contract_for_pose_avatar_and_ball():
    launcher = Path("Parallel_working/run_live_lowlag.sh").read_text()

    assert 'WIDTH="${PROJECT_CAM_WIDTH:-1280}"' in launcher
    assert 'HEIGHT="${PROJECT_CAM_HEIGHT:-720}"' in launcher
    assert "FPS=15" in launcher
    # Inference sizes are LOCKED to each engine's export size: TRT engines
    # decode garbage at any other imgsz (proven on real frames 2026-07-02).
    assert 'POSE_IMGSZ="${POSE_IMGSZ:-960}"' in launcher
    assert 'BALL_IMGSZ="${BALL_IMGSZ:-672}"' in launcher
    assert '--pose-imgsz "$POSE_IMGSZ"' in launcher
    assert '--pose-max-reproj-px "$POSE_REPROJ"' in launcher
    assert "--ball-ballistic-fallback" in launcher
    assert "--avatar-body" in launcher
    assert "--avatar-alpha" in launcher


def test_pose_health_payload_explains_empty_avatar_path():
    live = load_live_module()
    per_cam_pose_curr = {
        "camUsb01": (np.zeros((17, 2), dtype=np.float32), np.ones(17, dtype=np.float32)),
        "camUsb03": (np.zeros((17, 2), dtype=np.float32), np.ones(17, dtype=np.float32)),
    }
    pose_und_by_cam = {
        "camUsb01": {0: np.array([0.1, 0.2]), 5: np.array([0.2, 0.3])},
        "camUsb03": {0: np.array([0.3, 0.4])},
    }
    joints_display = np.full((17, 3), np.nan, dtype=np.float32)
    joints_display[0] = [100.0, 200.0, 300.0]

    payload = live.pose_health_payload(
        run_pose=True,
        pose_error="",
        batch_order=["camUsb01", "camUsb02", "camUsb03"],
        pose_raw_counts={"camUsb01": 1, "camUsb02": 0, "camUsb03": 2},
        per_cam_pose_curr=per_cam_pose_curr,
        pose_und_by_cam=pose_und_by_cam,
        joints_3d_now={0: np.array([100.0, 200.0, 300.0])},
        joints_display=joints_display,
    )

    assert payload["pose_run"] is True
    assert payload["pose_raw_person_count"] == 3
    assert payload["pose_selected_cam_count"] == 2
    assert payload["pose_selected_cams"] == ["camUsb01", "camUsb03"]
    assert payload["pose_high_conf_keypoint_count"] == 3
    assert payload["pose_triangulated_joint_count"] == 1
    assert payload["pose_visible_joint_count"] == 1


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
    # A ball engine's optimization profile caps the batch (e.g. 4 or 6); a
    # direct ball_model(frame_batch) call above the cap fails setInputShape
    # and crashes ultralytics. Every ball inference (inline or the
    # --parallel-inference worker submit) must go through run_yolopose_batched
    # capped by --ball-max-batch.
    import re

    src = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py").read_text()
    assert "--ball-max-batch" in src
    # Inline path: run_yolopose_batched(\n ball_model, frame_batch, args.ball_max_batch
    assert re.search(
        r"run_yolopose_batched\(\s*ball_model,\s*frame_batch,\s*args\.ball_max_batch", src
    )
    # Worker path: executor.submit(run_yolopose_batched, ball_model, frame_batch, args.ball_max_batch
    assert re.search(
        r"submit\(\s*run_yolopose_batched,\s*ball_model,\s*frame_batch,\s*args\.ball_max_batch", src
    )
    # No direct un-chunked call on the ball model remains.
    assert re.search(r"\bball_model\(\s*frame_batch", src) is None


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


def test_validate_min_active_cameras_rejects_values_outside_configured_range():
    live = load_live_module()

    assert live.validate_min_active_cameras(2, 6) == 2
    assert live.validate_min_active_cameras(6, 6) == 6
    with pytest.raises(ValueError, match="at least 2"):
        live.validate_min_active_cameras(1, 6)
    with pytest.raises(ValueError, match="configured camera count 6"):
        live.validate_min_active_cameras(7, 6)


def test_require_camera_count_reports_stage_config_and_counts():
    live = load_live_module()

    with pytest.raises(RuntimeError) as caught:
        live.require_camera_count(
            stage="passed preflight",
            available_count=2,
            configured_count=6,
            minimum=6,
            config_path="rig.yaml",
        )

    message = str(caught.value)
    assert "2/6" in message
    assert "require >=6" in message
    assert "passed preflight" in message
    assert "rig.yaml" in message


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
