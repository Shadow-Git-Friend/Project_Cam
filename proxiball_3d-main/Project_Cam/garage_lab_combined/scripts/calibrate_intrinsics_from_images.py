import argparse
import json
from pathlib import Path

import cv2
import cv2.aruco as aruco
import numpy as np
import yaml


def load_cameras(config_path):
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    cams = data.get('cameras', {}) if data else {}
    if not cams:
        raise ValueError(f"No cameras found in {config_path}")
    return cams


def setup_board(rows, cols, square_size_mm, marker_size_mm, dict_id):
    dictionary = aruco.getPredefinedDictionary(dict_id)
    try:
        board = aruco.CharucoBoard((cols, rows), square_size_mm, marker_size_mm, dictionary)
    except AttributeError:
        board = aruco.CharucoBoard_create(cols, rows, square_size_mm, marker_size_mm, dictionary)
    return board, dictionary


def make_detector(board):
    params = aruco.DetectorParameters()
    try:
        detector = aruco.CharucoDetector(board)
        detector.setDetectorParameters(params)
        return detector, None, params
    except AttributeError:
        return None, None, params


def detect_charuco(img, board, dictionary, detector, params):
    if detector is not None:
        # CharucoDetector is more stable on grayscale input.
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        charuco_corners, charuco_ids, marker_corners, marker_ids = detector.detectBoard(gray)
        return charuco_corners, charuco_ids

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    marker_corners, marker_ids, _ = aruco.detectMarkers(gray, dictionary, parameters=params)
    if marker_ids is None or len(marker_ids) == 0:
        return None, None
    _, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
        marker_corners, marker_ids, gray, board
    )
    return charuco_corners, charuco_ids


def calibrate_dir(image_dir, out_file, rows, cols, square_size_mm, marker_size_mm, dict_id, min_corners):
    image_dir = Path(image_dir)
    images = sorted(list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.png")))
    if not images:
        print(f"[ERROR] No images found in {image_dir}")
        return None

    board, dictionary = setup_board(rows, cols, square_size_mm, marker_size_mm, dict_id)
    detector, _, params = make_detector(board)

    all_charuco_corners = []
    all_charuco_ids = []
    image_size = None
    used = 0

    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        if image_size is None:
            image_size = img.shape[:2][::-1]

        charuco_corners, charuco_ids = detect_charuco(img, board, dictionary, detector, params)
        num = 0 if charuco_corners is None else len(charuco_corners)
        if charuco_corners is not None and charuco_ids is not None and num >= min_corners:
            all_charuco_corners.append(charuco_corners)
            all_charuco_ids.append(charuco_ids)
            used += 1

    if used < 3:
        print(f"[ERROR] Not enough valid frames in {image_dir} (used={used})")
        return None

    # Build object/image points for calibrateCamera
    all_obj_points = []
    all_img_points = []
    try:
        obj_pts = board.getChessboardCorners()
    except AttributeError:
        obj_pts = board.chessboardCorners

    for corners, ids in zip(all_charuco_corners, all_charuco_ids):
        current_obj = obj_pts[ids.flatten()]
        all_obj_points.append(current_obj)
        all_img_points.append(corners)

    # Initial guess for stability
    camera_matrix = np.array([
        [1140.0, 0.0, image_size[0] / 2.0],
        [0.0, 1140.0, image_size[1] / 2.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)
    dist_coeffs = np.zeros(5)

    flags = cv2.CALIB_USE_INTRINSIC_GUESS
    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        all_obj_points, all_img_points, image_size, camera_matrix, dist_coeffs, flags=flags
    )

    out = {
        "camera_matrix": camera_matrix.tolist(),
        "distortion_coefficients": dist_coeffs.tolist(),
        "reprojection_error": float(ret),
        "image_width": int(image_size[0]),
        "image_height": int(image_size[1]),
        "frames_used": int(used),
        "board": {
            "rows": rows,
            "cols": cols,
            "square_size_mm": square_size_mm,
            "marker_size_mm": marker_size_mm,
            "dict_id": int(dict_id),
        }
    }

    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(out, f, indent=4)

    print(f"[OK] {image_dir.name}: used={used}, reproj={ret:.4f}px -> {out_file}")
    return out


def main():
    ap = argparse.ArgumentParser(description="Calibrate intrinsics from captured ChArUco images")
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--captures-dir", default="garage_lab_combined/cal/captures")
    ap.add_argument("--out-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--min-corners", type=int, default=25)
    ap.add_argument("--rows", type=int, default=10)
    ap.add_argument("--cols", type=int, default=7)
    ap.add_argument("--square-size-mm", type=float, default=40.0)
    ap.add_argument("--marker-size-mm", type=float, default=30.0)
    ap.add_argument("--dict-id", type=int, default=int(aruco.DICT_4X4_1000))
    args = ap.parse_args()

    cams = load_cameras(args.config)
    captures_dir = Path(args.captures_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for cam_name in cams.keys():
        img_dir = captures_dir / cam_name
        out_file = out_dir / f"{cam_name}_intrinsics.json"
        calibrate_dir(
            img_dir,
            out_file,
            rows=args.rows,
            cols=args.cols,
            square_size_mm=args.square_size_mm,
            marker_size_mm=args.marker_size_mm,
            dict_id=args.dict_id,
            min_corners=args.min_corners,
        )


if __name__ == "__main__":
    main()
