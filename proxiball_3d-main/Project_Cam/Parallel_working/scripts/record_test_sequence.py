#!/usr/bin/env python3
"""Record a synchronized 4-camera test sequence for offline evaluation.

Saves raw frames + timestamps for reproducible ablation studies.

Usage:
    python Parallel_working/scripts/record_test_sequence.py \
        --config garage_lab_combined/config/cameras.yaml \
        --output Parallel_working/output/test_sequences/walk_01 \
        --duration 30 --fps 15

Output structure:
    walk_01/
        camEast/frame_000000.jpg  ...
        camNorth/frame_000000.jpg ...
        camSouth/frame_000000.jpg ...
        camWest/frame_000000.jpg  ...
        timestamps.jsonl          # per-frame timestamps
        metadata.json             # recording parameters
"""

import argparse
import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import yaml


CAM_ORDER = ["camEast", "camNorth", "camSouth", "camWest"]


class ThreadedCapture:
    """Threaded camera reader — always holds the latest frame."""

    def __init__(self, cap, name):
        self.cap = cap
        self.name = name
        self.frame = None
        self.ts = 0.0
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

    def grab(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None, self.ts

    def stop(self):
        self._running = False
        self._thread.join(timeout=2.0)
        self.cap.release()


def main():
    ap = argparse.ArgumentParser(description="Record synchronized 4-camera test sequence.")
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--output", required=True, help="Output directory for recorded sequence")
    ap.add_argument("--duration", type=float, default=30.0, help="Recording duration in seconds")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fourcc", default="MJPG")
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

    # Create output dirs
    out = Path(args.output)
    for cam in CAM_ORDER:
        (out / cam).mkdir(parents=True, exist_ok=True)

    # Open cameras with threaded capture
    readers = {}
    for cam in CAM_ORDER:
        dev = cam_devs.get(cam)
        if dev is None:
            print(f"[WARN] {cam} not in config, skipping")
            continue
        cap = cv2.VideoCapture(dev)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
        cap.set(cv2.CAP_PROP_FPS, args.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            readers[cam] = ThreadedCapture(cap, cam)
            print(f"[OK] {cam} opened on {dev}")
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

            # Save frames
            for cam, frame in frames.items():
                fname = out / cam / f"frame_{frame_idx:06d}.jpg"
                cv2.imwrite(str(fname), frame, encode_params)

            # Log timestamp
            ts_entry = {
                "frame": frame_idx,
                "ts": t_cap,
                "elapsed_s": t_cap - t_start,
                "cameras": list(frames.keys()),
            }
            ts_file.write(json.dumps(ts_entry) + "\n")

            # Preview
            if args.preview and frames:
                panels = []
                for cam in CAM_ORDER:
                    if cam in frames:
                        f = frames[cam].copy()
                        cv2.putText(f, cam, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    else:
                        f = np.zeros((args.height, args.width, 3), dtype=np.uint8)
                    panels.append(cv2.resize(f, (640, 360)))
                mosaic = np.vstack([np.hstack(panels[:2]), np.hstack(panels[2:])])
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
        "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(out / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Cleanup
    for r in readers.values():
        r.stop()
    cv2.destroyAllWindows()

    print(f"\nDone: {frame_idx} frames saved to {out}")
    print(f"Actual duration: {actual_dur:.1f}s")
    print(f"Effective FPS: {metadata['effective_fps']:.1f}")


if __name__ == "__main__":
    main()
