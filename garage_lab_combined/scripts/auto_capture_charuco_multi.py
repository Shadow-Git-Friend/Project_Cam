import cv2
import cv2.aruco as aruco
import time
from pathlib import Path
import yaml
import argparse
import os


DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30
DEFAULT_FOURCC = "MJPG"


def load_cameras(config_path):
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    cams = data.get('cameras', {}) if data else {}
    if not cams:
        raise ValueError(f"No cameras found in {config_path}")
    return cams


def setup_board():
    # Garage A3 board parameters
    squares_x = 7
    squares_y = 10
    square_size_mm = 40.0
    marker_size_mm = 30.0
    aruco_dict = aruco.DICT_4X4_1000

    dictionary = aruco.getPredefinedDictionary(aruco_dict)
    try:
        board = aruco.CharucoBoard((squares_x, squares_y), square_size_mm, marker_size_mm, dictionary)
    except AttributeError:
        board = aruco.CharucoBoard_create(squares_x, squares_y, square_size_mm, marker_size_mm, dictionary)
    return board, dictionary


def make_detector(dictionary, board):
    params = aruco.DetectorParameters()
    try:
        detector = aruco.CharucoDetector(board)
        detector.setDetectorParameters(params)
        return detector, None, params
    except AttributeError:
        return None, dictionary, params


def detect_charuco(gray, detector, dictionary, params, board):
    if detector is not None:
        charuco_corners, charuco_ids, marker_corners, marker_ids = detector.detectBoard(gray)
        return charuco_corners, charuco_ids

    marker_corners, marker_ids, _ = aruco.detectMarkers(gray, dictionary, parameters=params)
    if marker_ids is None or len(marker_ids) == 0:
        return None, None

    _, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
        marker_corners, marker_ids, gray, board
    )
    return charuco_corners, charuco_ids


def open_capture(device, width, height, fps, fourcc, buffer_size):
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        return None
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if buffer_size is not None:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
    return cap


def build_arg_parser():
    ap = argparse.ArgumentParser(description="Auto-capture ChArUco images when enough corners are detected.")
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml", help="Path to cameras.yaml")
    ap.add_argument("--out-dir", default="garage_lab_combined/cal/captures", help="Output directory")
    ap.add_argument("--min-corners", type=int, default=30, help="Min ChArUco corners to consider valid")
    ap.add_argument("--hold-sec", type=float, default=0.0, help="Seconds corners must stay above threshold (0 = immediate)")
    ap.add_argument("--target-count", type=int, default=30, help="Images per camera (0 for unlimited)")
    ap.add_argument("--cooldown-sec", type=float, default=0.5, help="Cooldown between saves per camera")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ap.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--fourcc", default=DEFAULT_FOURCC)
    ap.add_argument("--buffer-size", type=int, default=1)
    ap.add_argument("--show", action=argparse.BooleanOptionalAction, default=True,
                    help="Show preview window (default: on). Use --no-show to disable.")
    return ap


def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    cams = load_cameras(args.config)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    board, dictionary = setup_board()
    detector, dict_fallback, params = make_detector(dictionary, board)

    # Init captures and state
    states = {}
    caps = {}
    for cam_name, cam_cfg in cams.items():
        device = cam_cfg.get("device")
        if device is None:
            print(f"[WARN] {cam_name}: missing device entry")
            continue
        cap = open_capture(device, args.width, args.height, args.fps, args.fourcc, args.buffer_size)
        if cap is None or not cap.isOpened():
            print(f"[ERROR] {cam_name}: cannot open {device}")
            continue

        cam_dir = out_dir / cam_name
        cam_dir.mkdir(parents=True, exist_ok=True)
        caps[cam_name] = cap
        states[cam_name] = {
            "stable_since": None,
            "last_saved": 0.0,
            "count": 0,
            "dir": cam_dir,
            "device": device,
        }
        print(f"[OK] {cam_name} -> {device}")

    if not caps:
        print("[ERROR] No cameras opened. Check config and device paths.")
        return

    print("\n[INFO] Auto-capture running.")
    print(f"Mode: {args.width}x{args.height} {args.fourcc} @ {args.fps} FPS")
    print(f"Min corners: {args.min_corners}, Hold: {args.hold_sec}s, Target: {args.target_count} images per camera")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            all_done = True
            for cam_name, cap in caps.items():
                st = states[cam_name]
                if args.target_count > 0 and st["count"] >= args.target_count:
                    continue
                all_done = False

                ret, frame = cap.read()
                if not ret or frame is None:
                    st["stable_since"] = None
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                charuco_corners, charuco_ids = detect_charuco(gray, detector, dict_fallback, params, board)
                num_corners = 0 if charuco_corners is None else len(charuco_corners)

                now = time.time()
                if num_corners >= args.min_corners:
                    if args.hold_sec <= 0:
                        if (now - st["last_saved"]) >= args.cooldown_sec:
                            idx = st["count"] + 1
                            out_path = st["dir"] / f"img_{idx:04d}.jpg"
                            cv2.imwrite(str(out_path), frame)
                            st["count"] += 1
                            st["last_saved"] = now
                            print(f"[SAVE] {cam_name}: {out_path.name} (corners={num_corners})")
                    else:
                        if st["stable_since"] is None:
                            st["stable_since"] = now
                        elif (now - st["stable_since"]) >= args.hold_sec:
                            if (now - st["last_saved"]) >= args.cooldown_sec:
                                idx = st["count"] + 1
                                out_path = st["dir"] / f"img_{idx:04d}.jpg"
                                cv2.imwrite(str(out_path), frame)
                                st["count"] += 1
                                st["last_saved"] = now
                                st["stable_since"] = None
                                print(f"[SAVE] {cam_name}: {out_path.name} (corners={num_corners})")
                else:
                    st["stable_since"] = None

                if args.show:
                    display = frame.copy()
                    cv2.putText(display, f"{cam_name} corners={num_corners} saved={st['count']}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    cv2.imshow(cam_name, display)

            if args.show:
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            if all_done:
                print("[DONE] Target image count reached for all cameras.")
                break

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    finally:
        for cap in caps.values():
            cap.release()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
