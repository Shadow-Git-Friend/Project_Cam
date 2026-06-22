#!/usr/bin/env python3
"""Live camera-identification grid for the 6-USB rig.

Shows every camera from the config in one labelled mosaic so you can tell
which physical camera is which: wave a hand in front of a camera and watch
which tile reacts. Each tile also reports how many AprilTags it currently
sees and which arena walls those tags belong to (from Dimensions_fixed.txt) —
use this to re-aim the weak cameras until each sees >=4-5 tags across 2 walls
before re-shooting the extrinsics capture.

Keys: q = quit, s = save the current mosaic to /tmp.

Example:
  ./venv/bin/python scripts/identify_cameras.py
  ./venv/bin/python scripts/identify_cameras.py --width 1280 --height 720
"""
import argparse
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml


def load_camera_devices(config_path: Path):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cams = cfg.get("cameras", cfg)
    devs = {}
    if isinstance(cams, dict):
        for name, info in cams.items():
            devs[name] = info["device"] if isinstance(info, dict) else info
    else:  # list form
        for c in cams:
            devs[c["name"]] = c["device"]
    return devs


def load_tag_walls(dimensions_path: Path):
    """Map tag_id -> wall name using the ID= coordinate blocks (cm)."""
    walls = {}
    cur = None
    coords = {}
    for raw in open(dimensions_path):
        line = raw.strip()
        m = re.match(r"ID=(\d+):", line)
        if m:
            cur = int(m.group(1))
            coords[cur] = []
            continue
        c = re.match(r"c(\d+)\s*\(([^,]+),\s*([^,]+),\s*([^)]+)\)", line)
        if c and cur is not None:
            coords[cur].append(
                (float(c.group(2)), float(c.group(3)), float(c.group(4)))
            )
    for tid, pts in coords.items():
        if not pts:
            continue
        x = sum(p[0] for p in pts) / len(pts)
        y = sum(p[1] for p in pts) / len(pts)
        if x < 5:
            walls[tid] = "North"
        elif x > 600:
            walls[tid] = "South"
        elif y < 10:
            walls[tid] = "East"
        elif y > 290:
            walls[tid] = "West"
        else:
            walls[tid] = "?"
    return walls


def open_capture(device, width, height, fourcc, fps):
    if sys.platform.startswith("linux") and str(device).startswith("/dev/"):
        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(device)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="garage_lab_combined/config/cameras_6usb_test.yaml")
    ap.add_argument("--dimensions", default="arena_fixed/cal/extrinsics/Dimensions_fixed.txt")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--tile-w", type=int, default=512)
    ap.add_argument("--tile-h", type=int, default=288)
    ap.add_argument("--cols", type=int, default=3)
    args = ap.parse_args()

    devices = load_camera_devices(Path(args.config))
    tag_walls = load_tag_walls(Path(args.dimensions))
    print(f"[info] {len(devices)} cameras from {args.config}")

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())

    caps = {}
    for name, dev in devices.items():
        cap = open_capture(dev, args.width, args.height, args.fourcc, args.fps)
        if not cap.isOpened():
            print(f"[WARN] {name}: failed to open {dev}")
        caps[name] = cap
        time.sleep(0.05)

    names = list(devices.keys())
    cols = max(1, args.cols)
    rows = (len(names) + cols - 1) // cols
    tw, th = args.tile_w, args.tile_h
    win = "Camera ID grid  [wave at a camera | q quit | s save]"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    fps_t = time.time()
    frames = 0
    try:
        while True:
            tiles = []
            for name in names:
                cap = caps[name]
                ok, frame = cap.read() if cap is not None else (False, None)
                dev_short = str(devices[name]).split("/")[-1][-22:]
                if not ok or frame is None:
                    tile = np.full((th, tw, 3), 40, dtype=np.uint8)
                    cv2.putText(tile, "NO SIGNAL", (20, th // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (60, 60, 220), 2)
                    border = (60, 60, 220)
                    n_tags = 0
                    walls = set()
                else:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    corners, ids, _ = detector.detectMarkers(gray)
                    walls = set()
                    seen_ids = []
                    if ids is not None:
                        cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                        for tag_arr in ids:
                            tid = int(tag_arr[0])
                            seen_ids.append(tid)
                            walls.add(tag_walls.get(tid, "?"))
                    n_tags = len(seen_ids)
                    good = n_tags >= 4 and len({w for w in walls if w != "?"}) >= 2
                    border = (60, 200, 60) if good else (
                        (40, 200, 220) if n_tags >= 1 else (60, 60, 220))
                    tile = cv2.resize(frame, (tw, th))
                    ids_str = ",".join(str(i) for i in sorted(seen_ids))
                    walls_str = ",".join(sorted(w for w in walls if w != "?")) or "-"
                    cv2.putText(tile, f"tags:{n_tags}  walls:{walls_str}",
                                (8, th - 34), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (0, 0, 0), 4)
                    cv2.putText(tile, f"tags:{n_tags}  walls:{walls_str}",
                                (8, th - 34), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (255, 255, 255), 1)
                    if ids_str:
                        cv2.putText(tile, f"[{ids_str}]", (8, th - 12),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
                        cv2.putText(tile, f"[{ids_str}]", (8, th - 12),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)

                # name banner
                cv2.rectangle(tile, (0, 0), (tw, 30), (30, 30, 30), -1)
                cv2.putText(tile, name, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (0, 255, 0), 2)
                cv2.putText(tile, dev_short, (tw - 220, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
                cv2.rectangle(tile, (0, 0), (tw - 1, th - 1), border, 3)
                tiles.append(tile)

            # pad to full grid
            while len(tiles) < rows * cols:
                tiles.append(np.full((th, tw, 3), 20, dtype=np.uint8))
            grid_rows = [np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(rows)]
            mosaic = np.vstack(grid_rows)

            frames += 1
            if time.time() - fps_t >= 1.0:
                fps = frames / (time.time() - fps_t)
                frames = 0
                fps_t = time.time()
                cv2.setWindowTitle(win, f"Camera ID grid  {fps:.1f} FPS  [wave | q quit | s save]")

            cv2.imshow(win, mosaic)
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q"):
                break
            if k == ord("s"):
                out = f"/tmp/camera_id_grid_{int(time.time())}.jpg"
                cv2.imwrite(out, mosaic)
                print(f"[saved] {out}")
    finally:
        for cap in caps.values():
            if cap is not None:
                cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
