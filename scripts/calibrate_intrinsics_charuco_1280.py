#!/usr/bin/env python3
"""ChArUco intrinsics calibration at the rig's runtime resolution (1280x720),
writing the exact JSON format the live viewer loads (camera_matrix,
distortion_coefficients, image_width/height, board).

Built to re-calibrate camUsb02 whose shipped intrinsics had a wrong focal
(fx=1331 vs sibling 1080P ~750) from a degenerate checkerboard capture
(too-constant distance/angle -> focal/distance ambiguity). Auto-capture only
keeps frames where the board moved/tilted enough, forcing the distance+angle
variety that breaks that ambiguity.

Board matches the other cameras: 7 cols x 10 rows, 40mm squares, 30mm markers,
DICT_4X4_1000 (dict_id 3).

Usage (cam02 is /dev/video4 by-path right now):
  ./venv/bin/python scripts/calibrate_intrinsics_charuco_1280.py \
    --device /dev/v4l/by-path/pci-0000:00:14.0-usb-0:11.1:1.0-video-index0 \
    --output garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb02_1080P_intrinsics.json

Move the board NEAR and FAR, TILT it to all four corners, and cover every part
of the frame. Auto-saves good varied frames. Press 'c' to calibrate (>=20
frames), 's' to force-save the current frame, 'q' to quit.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import cv2.aruco as aruco
import numpy as np

DICT_ID = aruco.DICT_4X4_1000   # dict_id 3
COLS, ROWS = 7, 10              # squares
SQUARE_MM, MARKER_MM = 40.0, 30.0


def open_cam(device, w, h):
    dev = int(device) if str(device).isdigit() else device
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2) if isinstance(dev, str) and dev.startswith("/dev/") \
        else cv2.VideoCapture(dev)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", required=True, help="/dev/video path or index")
    ap.add_argument("--output", required=True, help="output intrinsics JSON path")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--min-corners", type=int, default=12,
                    help="min ChArUco corners to accept a frame")
    ap.add_argument("--auto", action=argparse.BooleanOptionalAction, default=True,
                    help="auto-save varied frames (default on)")
    ap.add_argument("--auto-interval", type=float, default=0.6)
    ap.add_argument("--target-frames", type=int, default=40,
                    help="auto-calibrate once this many frames collected")
    args = ap.parse_args()

    dictionary = aruco.getPredefinedDictionary(DICT_ID)
    board = aruco.CharucoBoard((COLS, ROWS), SQUARE_MM, MARKER_MM, dictionary)
    detector = aruco.ArucoDetector(dictionary, aruco.DetectorParameters())

    cap = open_cam(args.device, args.width, args.height)
    if not cap.isOpened():
        print(f"[ERROR] cannot open {args.device}"); sys.exit(1)

    all_corners, all_ids = [], []
    sigs = []          # (cx, cy, area) of saved boards, to enforce variety
    image_size = None
    last_auto = 0.0
    win = "cam02 intrinsics  [move near/far + tilt | c=calibrate s=save q=quit]"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    print("[INFO] Move the board NEAR/FAR and TILT to all corners. Auto-saving varied frames...")

    def variety_ok(sig):
        for s in sigs:
            if abs(sig[0]-s[0]) < 60 and abs(sig[1]-s[1]) < 60 and abs(sig[2]-s[2]) < 0.15*s[2]:
                return False
        return True

    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05); continue
        if image_size is None:
            image_size = (frame.shape[1], frame.shape[0])
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        disp = frame.copy()
        mc, mids, _ = detector.detectMarkers(gray)
        ch_corners = ch_ids = None
        n = 0
        if mids is not None and len(mids) > 0:
            ret, ch_corners, ch_ids = aruco.interpolateCornersCharuco(mc, mids, gray, board)
            if ret and ch_corners is not None and len(ch_corners) > 4:
                n = len(ch_corners)
                aruco.drawDetectedCornersCharuco(disp, ch_corners, ch_ids, (0, 255, 0))

        good = n >= args.min_corners
        save_now = False
        if good and args.auto and (time.time() - last_auto) >= args.auto_interval:
            c = ch_corners.reshape(-1, 2)
            sig = (float(c[:, 0].mean()), float(c[:, 1].mean()),
                   float((c[:, 0].max()-c[:, 0].min()) * (c[:, 1].max()-c[:, 1].min())))
            if variety_ok(sig):
                save_now = True; last_auto = time.time(); sigs.append(sig)

        col = (0, 200, 0) if good else (0, 0, 230)
        cv2.putText(disp, f"corners:{n}  saved:{len(all_corners)}/{args.target_frames}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)
        cv2.putText(disp, "move NEAR/FAR + TILT corners; auto-saving varied views",
                    (10, args.height-20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
        cv2.imshow(win, disp)
        k = cv2.waitKey(1) & 0xFF

        if k == ord('s') and good:
            save_now = True
        if save_now:
            all_corners.append(ch_corners); all_ids.append(ch_ids)
            print(f"[saved] frame {len(all_corners)} ({n} corners)")

        do_cal = (k == ord('c')) or (len(all_corners) >= args.target_frames)
        if k == ord('q'):
            print("[quit] no calibration"); break
        if do_cal:
            if len(all_corners) < 20:
                print(f"[warn] need >=20 frames, have {len(all_corners)}"); continue
            print(f"[INFO] calibrating on {len(all_corners)} frames @ {image_size} ...")
            K = np.zeros((3, 3)); D = np.zeros((1, 5))
            err, K, D, _, _ = aruco.calibrateCameraCharuco(
                all_corners, all_ids, board, image_size, K, D)
            fx, fy = K[0, 0], K[1, 1]
            print(f"[RESULT] reproj={err:.4f}px  fx={fx:.1f} fy={fy:.1f} "
                  f"cx={K[0,2]:.1f} cy={K[1,2]:.1f}")
            if not (500 < fx < 1100):
                print(f"[WARN] fx={fx:.0f} outside expected ~600-1000 for these 1080P units; "
                      "collect MORE near/far variety and recalibrate.")
            out = {
                "camera_matrix": K.tolist(),
                "distortion_coefficients": np.asarray(D).reshape(-1).tolist()[:5],
                "reprojection_error": float(err),
                "image_width": int(image_size[0]),
                "image_height": int(image_size[1]),
                "frames_used": len(all_corners),
                "board": {"rows": ROWS, "cols": COLS, "square_size_mm": SQUARE_MM,
                          "marker_size_mm": MARKER_MM, "dict_id": int(DICT_ID)},
            }
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            json.dump(out, open(args.output, "w"), indent=1)
            print(f"[DONE] wrote {args.output}")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
