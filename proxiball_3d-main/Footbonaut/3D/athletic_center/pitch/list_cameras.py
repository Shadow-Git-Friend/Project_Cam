"""
Quickly probe camera indices and report which ones open.

Usage:
    python list_cameras.py --max-index 10 --width 1280 --height 720 --fps 30

It tries common Windows backends (DSHOW, MSMF, ANY), grabs one frame, and
prints a list like:
    Opened: 1 (1920x1080), 2 (1920x1080)
"""

import argparse
from typing import List, Optional, Tuple

import cv2


BACKENDS = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]


def try_open(index: int, width: int, height: int, fps: int) -> Optional[Tuple[int, int]]:
    """Return (w, h) if a camera opens and provides a frame, else None."""
    for backend in BACKENDS:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            cap.release()
            return w, h
        cap.release()
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="List available camera indices")
    p.add_argument("--max-index", type=int, default=10, help="Scan indices 0..max-index-1")
    p.add_argument("--width", type=int, default=1280, help="Requested width")
    p.add_argument("--height", type=int, default=720, help="Requested height")
    p.add_argument("--fps", type=int, default=30, help="Requested FPS")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    found: List[str] = []
    for idx in range(args.max_index):
        res = try_open(idx, args.width, args.height, args.fps)
        if res:
            w, h = res
            found.append(f"{idx} ({w}x{h})")
    if found:
        print("Opened:", ", ".join(found))
    else:
        print("No cameras opened in the scanned range.")


if __name__ == "__main__":
    main()
