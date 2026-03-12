#!/usr/bin/env python3
"""
Open 4 cameras at a fixed resolution and display them in a 2x2 grid.

Usage:
  python3 multi_cam_grid.py [cam0 cam1 cam2 cam3] [--width W] [--height H] [--scale S] [--record-seconds S] [--grid-out PATH]

Examples:
  python3 multi_cam_grid.py
  python3 multi_cam_grid.py 0 2 4 6
  python3 multi_cam_grid.py 0 2 4 6 --width 1920 --height 1080 --scale 0.4
  python3 multi_cam_grid.py 0 2 4 6 --width 1920 --height 1080 --scale 0.4 --record-seconds 30
  python3 multi_cam_grid.py 0 2 4 6 --width 1920 --height 1080 --scale 0.4 --grid-out recordings/grid_2x2.avi
"""

import argparse
import datetime as dt
import os
import time

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Display 4 cameras in a 2x2 grid.")
    p.add_argument("indices", nargs="*", type=int, help="Camera indices (default: 0 2 4 6)")
    p.add_argument("--width", type=int, default=1920, help="Capture width")
    p.add_argument("--height", type=int, default=1080, help="Capture height")
    p.add_argument("--scale", type=float, default=0.4, help="Display scale factor")
    p.add_argument("--record-seconds", type=float, default=0.0, help="Record duration in seconds (0 disables recording)")
    p.add_argument("--fps", type=float, default=30.0, help="Recording FPS for output files")
    p.add_argument("--out-dir", default=None, help="Output directory (default: recordings/opencv_YYYYMMDD_HHMMSS)")
    p.add_argument("--grid-out", default=None, help="Write a single 2x2 grid video to this path (e.g., recordings/grid_2x2.avi)")
    p.add_argument("--grid-fourcc", default="MJPG", help="FOURCC for grid output (default: MJPG)")
    return p.parse_args()


def open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def make_placeholder(width: int, height: int, text: str) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(img, text, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
    return img


def main() -> int:
    args = parse_args()

    if args.scale <= 0:
        print("scale must be > 0")
        return 1
    if args.record_seconds < 0:
        print("record-seconds must be >= 0")
        return 1

    indices = args.indices if args.indices else [0, 2, 4, 6]
    if len(indices) != 4:
        print("Please provide exactly 4 camera indices (e.g., 0 2 4 6).")
        return 1

    caps = [open_camera(i, args.width, args.height) for i in indices]

    for i, cap in zip(indices, caps):
        if not cap.isOpened():
            print(f"Error: Could not open camera {i}")
            for c in caps:
                c.release()
            return 1

    writers = []
    out_dir = None
    grid_writer = None
    if args.record_seconds > 0:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = args.out_dir or os.path.join("recordings", f"opencv_{ts}")
        os.makedirs(out_dir, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        for idx, cap in zip(indices, caps):
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or args.width
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or args.height
            out_path = os.path.join(out_dir, f"cam{idx:02d}.avi")
            writer = cv2.VideoWriter(out_path, fourcc, args.fps, (w, h))
            if not writer.isOpened():
                print(f"Error: Could not open writer for cam {idx} at {out_path}")
                for c in caps:
                    c.release()
                return 1
            writers.append(writer)

    print(f"Opened cameras: {indices}")
    print("Press 'q' to quit.")

    prev_time = time.time()
    start_time = time.time()

    try:
        while True:
            frames = []
            for i, (idx, cap) in enumerate(zip(indices, caps)):
                ret, frame = cap.read()
                if not ret:
                    frame = make_placeholder(args.width, args.height, f"No frame cam {idx}")
                else:
                    if writers:
                        writers[i].write(frame)
                # Resize for display only
                disp_w = max(1, int(frame.shape[1] * args.scale))
                disp_h = max(1, int(frame.shape[0] * args.scale))
                frame = cv2.resize(frame, (disp_w, disp_h), interpolation=cv2.INTER_AREA)

                cv2.putText(
                    frame,
                    f"cam {idx}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                frames.append(frame)

            # Calculate FPS
            curr_time = time.time()
            fps_val = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
            prev_time = curr_time

            # Build 2x2 grid
            row1 = np.hstack((frames[0], frames[1]))
            row2 = np.hstack((frames[2], frames[3]))
            grid = np.vstack((row1, row2))

            if args.grid_out and grid_writer is None:
                os.makedirs(os.path.dirname(args.grid_out) or ".", exist_ok=True)
                gh, gw = grid.shape[0], grid.shape[1]
                grid_fourcc = cv2.VideoWriter_fourcc(*args.grid_fourcc)
                grid_writer = cv2.VideoWriter(args.grid_out, grid_fourcc, args.fps, (gw, gh))
                if not grid_writer.isOpened():
                    print(f"Error: Could not open grid writer at {args.grid_out}")
                    return 1

            if grid_writer is not None:
                grid_writer.write(grid)

            cv2.putText(
                grid,
                f"FPS: {fps_val:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 255, 0),
                2,
            )

            cv2.imshow("4-Camera Grid", grid)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            if args.record_seconds > 0 and (time.time() - start_time) >= args.record_seconds:
                print(f"Recording finished: {args.record_seconds:.1f}s")
                break
    finally:
        if grid_writer is not None:
            grid_writer.release()
        for w in writers:
            w.release()
        for cap in caps:
            cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
