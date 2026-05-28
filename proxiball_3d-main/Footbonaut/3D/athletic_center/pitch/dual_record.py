"""
Record video from two cameras simultaneously and save to disk.

Usage examples:
    python dual_record.py --cam-a 0 --cam-b 1 --fps 30 --width 1920 --height 1080
    python dual_record.py --cam-a 0 --cam-b 1 --duration 10

Behavior:
- Opens both cameras, starts recording at the same time, writes MP4 files
  (camA.mp4, camB.mp4) in the current directory.
- Stops when you press Ctrl+C or after --duration seconds (if provided).
"""

import argparse
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2


def try_open(index: int, width: int, height: int, fps: int) -> Optional[cv2.VideoCapture]:
    """Try multiple backends for robustness on Windows."""
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    for backend in backends:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        # Probe a frame to confirm it works
        ok, _ = cap.read()
        if ok:
            return cap
        cap.release()
    return None


def find_cameras(width: int, height: int, fps: int, max_index: int = 10) -> List[int]:
    """Scan camera indices and return the first two that open."""
    found = []
    for i in range(max_index):
        cap = try_open(i, width, height, fps)
        if cap:
            found.append(i)
            cap.release()
        if len(found) >= 2:
            break
    return found


def open_camera(index: int, width: int, height: int, fps: int) -> cv2.VideoCapture:
    cap = try_open(index, width, height, fps)
    if cap is None:
        raise RuntimeError(f"Could not open camera at index {index}")
    return cap


def make_writer(path: Path, fps: int, width: int, height: int) -> cv2.VideoWriter:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(str(path), fourcc, fps, (width, height))


def measure_fps(cap: cv2.VideoCapture, requested_fps: int, sample_frames: int = 60) -> int:
    """
    Measure actual FPS by timing a set of frame grabs.
    Returns a positive int FPS; falls back to requested_fps if timing fails.
    """
    start = time.monotonic()
    grabbed = 0
    for _ in range(sample_frames):
        ok, _ = cap.read()
        if not ok:
            break
        grabbed += 1
    elapsed = time.monotonic() - start
    if grabbed >= 5 and elapsed > 0:
        fps_measured = int(round(grabbed / elapsed))
        return max(1, fps_measured)
    # fallback
    fps_prop = cap.get(cv2.CAP_PROP_FPS)
    if fps_prop and fps_prop > 0:
        return int(round(fps_prop))
    return requested_fps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simultaneous dual-camera recorder")
    parser.add_argument("--cam-a", type=int, default=None, help="Index of camera A (default: auto)")
    parser.add_argument("--cam-b", type=int, default=None, help="Index of camera B (default: auto)")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS (default: 30)")
    parser.add_argument("--width", type=int, default=1280, help="Frame width (default: 1280)")
    parser.add_argument("--height", type=int, default=720, help="Frame height (default: 720)")
    parser.add_argument("--duration", type=float, default=None, help="Stop after N seconds (optional)")
    parser.add_argument("--out-a", type=Path, default=Path("camA.mp4"), help="Output file for camera A")
    parser.add_argument("--out-b", type=Path, default=Path("camB.mp4"), help="Output file for camera B")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.cam_a is None or args.cam_b is None:
        detected = find_cameras(args.width, args.height, args.fps)
        if len(detected) < 2:
            raise RuntimeError(
                f"Auto-discovery found {len(detected)} camera(s); "
                "please specify --cam-a and --cam-b explicitly."
            )
        cam_a_idx, cam_b_idx = detected[:2]
        print(f"Auto-selected cameras: A={cam_a_idx}, B={cam_b_idx}")
    else:
        cam_a_idx, cam_b_idx = args.cam_a, args.cam_b

    cap_a = open_camera(cam_a_idx, args.width, args.height, args.fps)
    cap_b = open_camera(cam_b_idx, args.width, args.height, args.fps)

    if not cap_a.isOpened():
        raise RuntimeError(f"Could not open camera A at index {cam_a_idx}")
    if not cap_b.isOpened():
        raise RuntimeError(f"Could not open camera B at index {cam_b_idx}")

    # Measure actual FPS to avoid sped-up playback
    measured_fps_a = measure_fps(cap_a, args.fps)
    measured_fps_b = measure_fps(cap_b, args.fps)
    writer_fps = min(measured_fps_a, measured_fps_b)
    print(f"Using writer FPS: {writer_fps} (A measured {measured_fps_a}, B measured {measured_fps_b})")

    writer_a = make_writer(args.out_a, writer_fps, args.width, args.height)
    writer_b = make_writer(args.out_b, writer_fps, args.width, args.height)

    if not writer_a.isOpened() or not writer_b.isOpened():
        cap_a.release()
        cap_b.release()
        raise RuntimeError("Failed to create video writers")

    print(f"Recording started. Saving to {args.out_a} and {args.out_b}")
    start_time = time.monotonic()

    try:
        while True:
            ret_a, frame_a = cap_a.read()
            ret_b, frame_b = cap_b.read()
            if not ret_a or not ret_b:
                print("Frame grab failed; stopping.")
                break

            writer_a.write(frame_a)
            writer_b.write(frame_b)

            if args.duration is not None and (time.monotonic() - start_time) >= args.duration:
                print("Duration reached; stopping.")
                break
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        cap_a.release()
        cap_b.release()
        writer_a.release()
        writer_b.release()
        print("Recording finished.")


if __name__ == "__main__":
    main()
