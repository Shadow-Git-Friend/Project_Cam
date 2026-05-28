#!/usr/bin/env python3
"""Standalone 4-cam 2x2 framing check for the lateral remount workflow.

No calibration, no pose, no 3D — just raw MJPG @ 1920x1080 @ 30 FPS in a 2x2
mosaic, with role labels, a center crosshair, and a yellow "safe zone" rectangle
representing the 80-px native-frame margin you want the athlete to stay inside.

Run from the project root:
    ./venv/bin/python Remounted_West_East/scripts/framing_check.py

Quit with q in the cv2 window or Ctrl+C in the terminal.

Tile layout (matches arena world frame intuition):
    +-----------+-----------+
    |  camNorth |  camEast  |
    +-----------+-----------+
    |  camSouth |  camWest  |
    +-----------+-----------+
"""
from __future__ import annotations

import signal
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "garage_lab_combined" / "config" / "cameras.yaml"

WIDTH = 1920
HEIGHT = 1080
FPS = 30

TILE_W = 640
TILE_H = 360
SAFE_MARGIN_NATIVE_PX = 80
SAFE_MARGIN_TILE_PX = int(round(SAFE_MARGIN_NATIVE_PX * TILE_W / WIDTH))

ROLES = ["camNorth", "camEast", "camSouth", "camWest"]
LATERAL = {"camEast", "camWest"}


def open_cam(role: str, device: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        print(f"FAIL: {role} did not open at {device}", file=sys.stderr)
        sys.exit(1)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"OK: {role:9s} {device}  {actual_w}x{actual_h} @ {actual_fps:.0f} fps")
    return cap


def label_tile(tile: np.ndarray, role: str) -> None:
    is_lateral = role in LATERAL
    border = (0, 255, 255) if is_lateral else (0, 255, 0)
    cv2.rectangle(tile, (0, 0), (TILE_W - 1, TILE_H - 1), border, 1)
    cv2.putText(
        tile,
        f"{role}{' (remounted)' if is_lateral else ''}",
        (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        border,
        2,
    )
    cx, cy = TILE_W // 2, TILE_H // 2
    cv2.line(tile, (cx - 15, cy), (cx + 15, cy), (255, 255, 0), 1)
    cv2.line(tile, (cx, cy - 15), (cx, cy + 15), (255, 255, 0), 1)
    m = SAFE_MARGIN_TILE_PX
    cv2.rectangle(tile, (m, m), (TILE_W - m, TILE_H - m), (0, 255, 255), 1)


def no_frame_tile(role: str) -> np.ndarray:
    tile = np.zeros((TILE_H, TILE_W, 3), dtype=np.uint8)
    cv2.putText(
        tile,
        f"{role}: NO FRAME",
        (10, TILE_H // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 0, 255),
        2,
    )
    return tile


def main() -> int:
    if not CONFIG.exists():
        print(f"FAIL: cameras.yaml not at {CONFIG}", file=sys.stderr)
        return 1
    cfg = yaml.safe_load(CONFIG.read_text())

    caps: dict[str, cv2.VideoCapture] = {}
    for role in ROLES:
        device = cfg["cameras"][role]["device"]
        caps[role] = open_cam(role, device)

    stop = False

    def handle_sig(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    win = "Remount framing check (q to quit) — lateral cams in YELLOW"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, TILE_W * 2, TILE_H * 2)

    print("\nFraming guide:")
    print("  - Hip, knee, ankle, foot all visible on camEast + camWest")
    print("  - Body stays INSIDE the yellow safe-zone rectangle")
    print("  - Body axis roughly horizontal across the lateral frames")
    print("  - BLM, operator, other humans OUTSIDE the cone")
    print("Press q in the window to quit.\n")

    try:
        while not stop:
            tiles: list[np.ndarray] = []
            for role in ROLES:
                ok, frame = caps[role].read()
                if not ok or frame is None:
                    tiles.append(no_frame_tile(role))
                    continue
                tile = cv2.resize(frame, (TILE_W, TILE_H))
                label_tile(tile, role)
                tiles.append(tile)

            top = np.hstack([tiles[0], tiles[1]])
            bot = np.hstack([tiles[2], tiles[3]])
            mosaic = np.vstack([top, bot])

            cv2.imshow(win, mosaic)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        for cap in caps.values():
            cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
