#!/usr/bin/env python3
"""Capture per-camera AprilTag still frames for the extrinsics solver.

The arena has stationary AprilTag-36h11 markers on all four walls (positions in
Dimensions_fixed.txt). For extrinsics calibration we need a small batch of
sharp stills per camera from the new mount position. The robust solver expects
images at:

    <out-dir>/camNorth/frame_*.png
    <out-dir>/camEast/frame_*.png
    <out-dir>/camSouth/frame_*.png
    <out-dir>/camWest/frame_*.png

Defaults: 1920x1080 MJPG @ 30 FPS, 30 frames per camera, ~0.3 s between saves
to give auto-exposure time to settle between shots.

Usage:
    ./venv/bin/python Remounted_West_East/scripts/apriltag_capture.py \
        [--out-dir Remounted_West_East/cal/captures/apriltag_remount_20260525] \
        [--frames 30]
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import cv2
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "garage_lab_combined" / "config" / "cameras.yaml"

WIDTH = 1920
HEIGHT = 1080
FPS = 30

ROLES = ["camNorth", "camEast", "camSouth", "camWest"]


def open_cam(role: str, device: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print(f"FAIL: {role} did not open at {device}", file=sys.stderr)
        sys.exit(1)
    return cap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out-dir",
        default="Remounted_West_East/cal/captures/apriltag_remount_20260525",
    )
    ap.add_argument("--frames", type=int, default=30, help="Frames per camera")
    ap.add_argument(
        "--interval-sec", type=float, default=0.30,
        help="Seconds between saved frames per cam",
    )
    ap.add_argument(
        "--warmup-frames", type=int, default=30,
        help="Frames to read and discard per cam before saving (lets AE settle)",
    )
    args = ap.parse_args()

    if not CONFIG.exists():
        print(f"FAIL: cameras.yaml not at {CONFIG}", file=sys.stderr)
        return 1
    cfg = yaml.safe_load(CONFIG.read_text())

    out_root = Path(args.out_dir)
    for role in ROLES:
        (out_root / role).mkdir(parents=True, exist_ok=True)
    print(f"Output: {out_root}")

    caps: dict[str, cv2.VideoCapture] = {}
    for role in ROLES:
        device = cfg["cameras"][role]["device"]
        caps[role] = open_cam(role, device)
        print(f"OK: {role:9s} {device}")

    stop = False

    def handle_sig(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    print(f"\nWarming up auto-exposure ({args.warmup_frames} frames per cam)...")
    for _ in range(args.warmup_frames):
        for role in ROLES:
            caps[role].read()

    print(f"\nCapturing {args.frames} frames per cam at "
          f"{args.interval_sec:.2f} s intervals (~{args.frames * args.interval_sec:.0f}s total)...")

    for i in range(args.frames):
        if stop:
            print("Interrupted.")
            break
        t0 = time.time()
        for role in ROLES:
            ok, frame = caps[role].read()
            if not ok or frame is None:
                print(f"  WARN: {role} no frame at i={i}")
                continue
            out_path = out_root / role / f"frame_{i:04d}.png"
            cv2.imwrite(str(out_path), frame)
        elapsed = time.time() - t0
        remaining = args.interval_sec - elapsed
        if remaining > 0:
            time.sleep(remaining)
        if (i + 1) % 5 == 0 or i == args.frames - 1:
            print(f"  saved frame {i+1}/{args.frames}")

    for cap in caps.values():
        cap.release()

    print("\nDone. Per-cam frame counts:")
    for role in ROLES:
        count = len(list((out_root / role).glob("frame_*.png")))
        print(f"  {role}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
