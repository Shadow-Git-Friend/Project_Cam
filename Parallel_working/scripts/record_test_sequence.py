#!/usr/bin/env python3
"""Record a synchronized multi-camera test sequence for offline evaluation.

Can save raw frames, MP4 videos, or both, plus timestamps/metadata.

Usage:
    python Parallel_working/scripts/record_test_sequence.py \
        --config garage_lab_combined/config/cameras.yaml \
        --output Parallel_working/output/test_sequences/walk_01 \
        --duration 30 --fps 30 --output-format video

Output structure:
    walk_01/
        camEast.mp4              # when --output-format video/both
        camNorth.mp4             # when --output-format video/both
        mosaic.mp4               # when --video-mode mosaic/both
        camEast/frame_000000.jpg # when --output-format frames/both
        timestamps.jsonl          # per-frame timestamps
        metadata.json             # recording parameters
"""

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import yaml


DEFAULT_CAM_ORDER = ["camEast", "camNorth", "camSouth", "camWest"]


def make_mosaic(frames, width, height, cam_order):
    panels = []
    tile_w, tile_h = 640, 360
    cols = 2 if len(cam_order) <= 4 else 3
    rows = int(np.ceil(max(1, len(cam_order)) / cols))
    for cam in cam_order:
        if cam in frames:
            f = frames[cam].copy()
            cv2.putText(f, cam, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            f = np.zeros((height, width, 3), dtype=np.uint8)
            cv2.putText(f, cam, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 2)
        panels.append(cv2.resize(f, (tile_w, tile_h)))
    while len(panels) < rows * cols:
        panels.append(np.zeros((tile_h, tile_w, 3), dtype=np.uint8))
    return np.vstack([
        np.hstack(panels[row * cols:(row + 1) * cols])
        for row in range(rows)
    ])


class ThreadedCapture:
    """Threaded camera reader — always holds the latest frame."""

    def __init__(self, cap, name):
        self.cap = cap
        self.name = name
        self.frame = None
        self.ts = 0.0
        self._has_unconsumed = False
        self.lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.frame = frame
                    self.ts = time.time()
                    self._has_unconsumed = True

    def grab(self):
        with self.lock:
            if not self._has_unconsumed:
                return None, self.ts
            self._has_unconsumed = False
            return self.frame.copy() if self.frame is not None else None, self.ts

    def stop(self):
        self._running = False
        self._thread.join(timeout=2.0)
        self.cap.release()


def open_camera_capture(device):
    if sys.platform.startswith("linux") and str(device).startswith("/dev/"):
        return cv2.VideoCapture(device, cv2.CAP_V4L2)
    return cv2.VideoCapture(device)


def apply_uvc_low_latency_controls(device, cam, args, log=False):
    if args.no_uvc_controls:
        return
    if not sys.platform.startswith("linux") or not str(device).startswith("/dev/"):
        return
    v4l2_ctl = shutil.which("v4l2-ctl")
    if not v4l2_ctl:
        return

    controls = [
        ("power_line_frequency", int(args.uvc_power_line_frequency)),
        ("exposure_dynamic_framerate", 0),
        ("auto_exposure", 1),
        ("exposure_time_absolute", int(args.uvc_exposure)),
    ]
    if int(args.uvc_gain) >= 0:
        controls.append(("gain", int(args.uvc_gain)))
    if int(args.uvc_focus) >= 0:
        controls.extend([
            ("focus_automatic_continuous", 0),
            ("focus_absolute", int(args.uvc_focus)),
        ])

    applied = []
    failed = []
    for name, value in controls:
        proc = subprocess.run(
            [v4l2_ctl, "-d", str(device), f"--set-ctrl={name}={value}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        (applied if proc.returncode == 0 else failed).append(name)

    if log and applied:
        msg = (
            f"[INFO] {cam}: UVC low-latency controls applied "
            f"(exposure={args.uvc_exposure}, gain={args.uvc_gain}, "
            f"focus={args.uvc_focus}, power_line={args.uvc_power_line_frequency})"
        )
        if failed:
            msg += f"; skipped unsupported: {','.join(failed)}"
        print(msg)


def main():
    ap = argparse.ArgumentParser(description="Record synchronized multi-camera test sequence.")
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--cams", default="",
                    help="Comma-separated camera roles to record. Default: old 4-cam order plus any extra config keys.")
    ap.add_argument("--output", required=True, help="Output directory for recorded sequence")
    ap.add_argument("--duration", type=float, default=30.0, help="Recording duration in seconds")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--no-uvc-controls", action="store_true",
                    help="Do not apply low-latency V4L2 controls to USB webcams.")
    ap.add_argument("--uvc-exposure", type=int, default=200,
                    help="Manual UVC exposure_time_absolute. 200 = about 20 ms; keeps C920 at 30 FPS.")
    ap.add_argument("--uvc-gain", type=int, default=160,
                    help="Manual UVC gain. Use -1 to leave gain unchanged.")
    ap.add_argument("--uvc-focus", type=int, default=0,
                    help="Manual UVC focus_absolute. Use -1 to leave focus unchanged.")
    ap.add_argument("--uvc-power-line-frequency", type=int, default=1,
                    help="UVC power_line_frequency: 1=50 Hz, 2=60 Hz.")
    ap.add_argument("--output-format", choices=["frames", "video", "both"], default="frames",
                    help="Save image frames, MP4 video files, or both.")
    ap.add_argument("--video-mode", choices=["per-cam", "mosaic", "both"], default="both",
                    help="When saving video, write one MP4 per camera, a 2x2 mosaic MP4, or both.")
    ap.add_argument("--video-codec", default="mp4v",
                    help="OpenCV VideoWriter codec for MP4 output, e.g. mp4v or avc1.")
    ap.add_argument("--quality", type=int, default=95, help="JPEG quality (1-100)")
    ap.add_argument("--preview", action="store_true", help="Show live preview during recording")
    ap.add_argument("--countdown", type=int, default=3, help="Countdown seconds before recording")
    ap.add_argument("--warmup", type=float, default=2.0, help="Warmup seconds to stabilize cameras")
    args = ap.parse_args()

    # Load camera config
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    cams_cfg = cfg["cameras"]
    if isinstance(cams_cfg, dict):
        cam_devs = {name: info["device"] for name, info in cams_cfg.items()}
    else:
        cam_devs = {c["name"]: c["device"] for c in cams_cfg}
    if args.cams.strip():
        cam_order = [c.strip() for c in args.cams.split(",") if c.strip()]
    else:
        cam_order = [c for c in DEFAULT_CAM_ORDER if c in cam_devs]
        cam_order.extend(c for c in cam_devs if c not in cam_order)

    save_frames = args.output_format in ("frames", "both")
    save_video = args.output_format in ("video", "both")
    save_per_cam_video = save_video and args.video_mode in ("per-cam", "both")
    save_mosaic_video = save_video and args.video_mode in ("mosaic", "both")

    # Create output dirs
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if save_frames:
        for cam in cam_order:
            (out / cam).mkdir(parents=True, exist_ok=True)

    # Open cameras with threaded capture
    readers = {}
    for cam in cam_order:
        dev = cam_devs.get(cam)
        if dev is None:
            print(f"[WARN] {cam} not in config, skipping")
            continue
        apply_uvc_low_latency_controls(dev, cam, args, log=False)
        cap = open_camera_capture(dev)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FPS, args.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            apply_uvc_low_latency_controls(dev, cam, args, log=True)
            readers[cam] = ThreadedCapture(cap, cam)
            eff_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            eff_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            eff_fps = cap.get(cv2.CAP_PROP_FPS)
            eff_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            eff_fourcc_str = "".join(chr((eff_fourcc >> (8 * i)) & 0xFF) for i in range(4))
            print(f"[OK] {cam} opened on {dev} ({eff_w}x{eff_h}@{eff_fps:.1f}, {eff_fourcc_str})")
        else:
            print(f"[FAIL] {cam} on {dev}")
            cap.release()

    if len(readers) < 2:
        print("[ERROR] Need at least 2 cameras")
        for r in readers.values():
            r.stop()
        return

    # Warmup — let auto-exposure settle
    print(f"Warming up cameras for {args.warmup}s...")
    time.sleep(args.warmup)

    # Countdown
    if args.countdown > 0:
        print(f"Recording in {args.countdown}s...")
        for i in range(args.countdown, 0, -1):
            print(f"  {i}...")
            time.sleep(1.0)

    print(f"RECORDING — {args.duration}s at {args.fps} FPS ({len(readers)} cameras)")

    # Record
    ts_file = open(out / "timestamps.jsonl", "w")
    t_start = time.time()
    frame_idx = 0
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, args.quality]
    target_dt = 1.0 / args.fps
    video_fourcc = cv2.VideoWriter_fourcc(*args.video_codec)
    video_writers = {}
    video_frame_counts = {}
    video_paths = {}
    mosaic_writer = None
    mosaic_frame_count = 0
    mosaic_path = out / "mosaic.mp4"
    latest_frames = {}

    try:
        while (time.time() - t_start) < args.duration:
            t_cap = time.time()
            frames = {}
            for cam, reader in readers.items():
                frame, ts = reader.grab()
                if frame is not None:
                    frames[cam] = frame

            if not frames:
                time.sleep(0.001)
                continue
            latest_frames.update(frames)

            if save_frames:
                for cam, frame in frames.items():
                    fname = out / cam / f"frame_{frame_idx:06d}.jpg"
                    cv2.imwrite(str(fname), frame, encode_params)

            if save_per_cam_video:
                for cam, frame in latest_frames.items():
                    writer = video_writers.get(cam)
                    if writer is None:
                        h, w = frame.shape[:2]
                        path = out / f"{cam}.mp4"
                        writer = cv2.VideoWriter(str(path), video_fourcc, args.fps, (w, h))
                        if not writer.isOpened():
                            raise RuntimeError(f"Cannot open video writer: {path}")
                        video_writers[cam] = writer
                        video_paths[cam] = str(path)
                        video_frame_counts[cam] = 0
                    writer.write(frame)
                    video_frame_counts[cam] += 1

            if save_mosaic_video:
                mosaic_for_video = make_mosaic(latest_frames, args.width, args.height, cam_order)
                if mosaic_writer is None:
                    h, w = mosaic_for_video.shape[:2]
                    mosaic_writer = cv2.VideoWriter(str(mosaic_path), video_fourcc, args.fps, (w, h))
                    if not mosaic_writer.isOpened():
                        raise RuntimeError(f"Cannot open video writer: {mosaic_path}")
                    video_paths["mosaic"] = str(mosaic_path)
                mosaic_writer.write(mosaic_for_video)
                mosaic_frame_count += 1

            # Log timestamp
            ts_entry = {
                "frame": frame_idx,
                "ts": t_cap,
                "elapsed_s": t_cap - t_start,
                "cameras": list(frames.keys()),
                "video_cameras": list(latest_frames.keys()),
            }
            ts_file.write(json.dumps(ts_entry) + "\n")

            # Preview
            if args.preview and latest_frames:
                mosaic = make_mosaic(latest_frames, args.width, args.height, cam_order)
                elapsed = time.time() - t_start
                cv2.putText(mosaic, f"REC {elapsed:.1f}s / {args.duration:.0f}s  Frame {frame_idx}",
                            (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                cv2.imshow("Recording", mosaic)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("[INFO] Recording stopped by user")
                    break

            frame_idx += 1

            # Pace to target FPS
            dt = time.time() - t_cap
            if dt < target_dt:
                time.sleep(target_dt - dt)

    finally:
        ts_file.close()
        for writer in video_writers.values():
            writer.release()
        if mosaic_writer is not None:
            mosaic_writer.release()

    actual_dur = time.time() - t_start

    # Save metadata
    metadata = {
        "cameras": list(readers.keys()),
        "width": args.width,
        "height": args.height,
        "fps": args.fps,
        "duration_s": args.duration,
        "total_frames": frame_idx,
        "actual_duration_s": actual_dur,
        "effective_fps": frame_idx / max(actual_dur, 0.001),
        "config": args.config,
        "output_format": args.output_format,
        "video_mode": args.video_mode if save_video else "",
        "video_codec": args.video_codec if save_video else "",
        "video_paths": video_paths,
        "video_frame_counts": {
            **video_frame_counts,
            **({"mosaic": mosaic_frame_count} if mosaic_frame_count else {}),
        },
        "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(out / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Cleanup
    for r in readers.values():
        r.stop()
    cv2.destroyAllWindows()

    if save_frames and save_video:
        print(f"\nDone: {frame_idx} batches saved as frames + video to {out}")
    elif save_video:
        print(f"\nDone: {frame_idx} batches saved as video to {out}")
    else:
        print(f"\nDone: {frame_idx} frame batches saved to {out}")
    print(f"Actual duration: {actual_dur:.1f}s")
    print(f"Effective FPS: {metadata['effective_fps']:.1f}")
    if video_paths:
        print("Videos:")
        for label, path in video_paths.items():
            count = metadata["video_frame_counts"].get(label, 0)
            print(f"  {label}: {path} ({count} frames)")


if __name__ == "__main__":
    main()
