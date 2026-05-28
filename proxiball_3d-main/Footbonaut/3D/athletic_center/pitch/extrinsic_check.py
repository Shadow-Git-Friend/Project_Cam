"""
Detect ChArUco corners in sample images, calibrate each camera, and attempt a
stereo (extrinsic) calibration. Reports how many corners were found per image.

Assumes the board matches charuco_board.py:
- Squares: 20 x 11, square size 49.5 mm, marker size 34.65 mm
- Dictionary: DICT_4X4_50

Images are expected in images/extrinsic with names like 1a.jpg / 1b.jpg where
the trailing letter distinguishes the two cameras.
"""

from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np


def detect_board(
    image_path: Path,
    board: cv2.aruco.CharucoBoard,
    detector: cv2.aruco.ArucoDetector,
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Return detected charuco corners and ids (empty if not enough markers)."""
    img = cv2.imread(str(image_path))
    if img is None:
        return [], []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None or len(ids) == 0:
        return [], []
    retval, ch_corners, ch_ids = cv2.aruco.interpolateCornersCharuco(
        markerCorners=corners,
        markerIds=ids,
        image=gray,
        board=board,
    )
    if retval is None or ch_ids is None or len(ch_ids) == 0:
        return [], []
    return ch_corners, ch_ids


def calibrate_camera(
    corner_sets: List[np.ndarray],
    id_sets: List[np.ndarray],
    board: cv2.aruco.CharucoBoard,
    image_size: Tuple[int, int],
) -> Tuple[float, np.ndarray, np.ndarray]:
    """Calibrate a single camera; returns reprojection error and camera params."""
    flags = cv2.CALIB_RATIONAL_MODEL
    retval, camera_matrix, dist_coeffs, _, _ = cv2.aruco.calibrateCameraCharuco(
        charucoCorners=corner_sets,
        charucoIds=id_sets,
        board=board,
        imageSize=image_size,
        cameraMatrix=None,
        distCoeffs=None,
        flags=flags,
    )
    return retval, camera_matrix, dist_coeffs


def main() -> None:
    root = Path(__file__).parent / "images" / "extrinsic"
    files = sorted(root.glob("*[ab].jpg"))
    if not files:
        print("No images found in images/extrinsic")
        return

    # Board definition (meters)
    squares_x, squares_y = 6, 4
    square_length = 0.210
    marker_length = square_length * 0.7
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    # Tile IDs to cover the board (dict has only 50 markers)
    marker_count = (squares_x * squares_y + 1) // 2
    dictionary_size = dictionary.bytesList.shape[0]
    tiled_ids = np.arange(marker_count, dtype=np.int32) % dictionary_size
    board = cv2.aruco.CharucoBoard(
        (squares_x, squares_y),
        squareLength=square_length,
        markerLength=marker_length,
        dictionary=dictionary,
        ids=tiled_ids.reshape(-1, 1),
    )
    detector = cv2.aruco.ArucoDetector(dictionary)

    sets: Dict[str, List[Tuple[Path, List[np.ndarray], List[np.ndarray], Tuple[int, int]]]] = {
        "a": [],
        "b": [],
    }

    for f in files:
        suffix = f.stem[-1].lower()
        if suffix not in sets:
            continue
        img = cv2.imread(str(f))
        if img is None:
            continue
        image_size = (img.shape[1], img.shape[0])
        ch_corners, ch_ids = detect_board(f, board, detector)
        sets[suffix].append((f, ch_corners, ch_ids, image_size))

    for cam in ("a", "b"):
        print(f"\nCamera {cam.upper()} detections:")
        for f, ch_corners, ch_ids, _ in sets[cam]:
            count = len(ch_ids)
            print(f"  {f.name}: {count:3d} corners")

    # Require at least one detection per camera
    if not sets["a"] or not sets["b"]:
        print("\nNot enough images to calibrate.")
        return

    # Use the first image size per camera (assume all match)
    size_a = sets["a"][0][3]
    size_b = sets["b"][0][3]

    # Intrinsic calibration per camera
    corners_a = [c for _, c, _, _ in sets["a"] if len(c)]
    ids_a = [i for _, _, i, _ in sets["a"] if len(i)]
    corners_b = [c for _, c, _, _ in sets["b"] if len(c)]
    ids_b = [i for _, _, i, _ in sets["b"] if len(i)]

    if len(corners_a) < 3 or len(corners_b) < 3:
        print("\nToo few good detections for reliable calibration (need 3+ per camera).")
        return

    err_a, cam_a, dist_a = calibrate_camera(corners_a, ids_a, board, size_a)
    err_b, cam_b, dist_b = calibrate_camera(corners_b, ids_b, board, size_b)
    print(f"\nIntrinsics: Cam A reprojection error: {err_a:.3f}")
    print(f"Intrinsics: Cam B reprojection error: {err_b:.3f}")

    # Prepare matched frames for stereo calibration (matching index by stem prefix)
    matched_pairs = []
    for f_a, ch_a, ids_a_img, _ in sets["a"]:
        prefix = f_a.stem[:-1]
        f_b_candidates = [f for f, _, _, _ in sets["b"] if f.stem.startswith(prefix)]
        if not f_b_candidates:
            continue
        f_b = f_b_candidates[0]
        ch_b = next(c for f, c, _, _ in sets["b"] if f == f_b)
        ids_b_img = next(i for f, _, i, _ in sets["b"] if f == f_b)
        if len(ch_a) < 4 or len(ch_b) < 4:
            continue
        matched_pairs.append((ch_a, ids_a_img, ch_b, ids_b_img))

    if len(matched_pairs) < 3:
        print("\nToo few matched views for stereo calibration (need 3+ pairs).")
        return

    obj_points = []
    img_points_a = []
    img_points_b = []
    for ch_a, ids_a_img, ch_b, ids_b_img in matched_pairs:
        # Find common IDs between the two views
        ids_a_flat = ids_a_img.flatten()
        ids_b_flat = ids_b_img.flatten()
        common_ids = np.intersect1d(ids_a_flat, ids_b_flat, assume_unique=False)
        if len(common_ids) < 4:
            continue
        # Align order
        idx_a = np.nonzero(np.isin(ids_a_flat, common_ids))[0]
        idx_b = np.nonzero(np.isin(ids_b_flat, common_ids))[0]
        ch_a_common = ch_a[idx_a]
        ch_b_common = ch_b[idx_b]
        obj = board.chessboardCorners[common_ids]
        obj_points.append(obj)
        img_points_a.append(ch_a_common)
        img_points_b.append(ch_b_common)

    if len(obj_points) < 3:
        print("\nNot enough common corners across pairs for stereo calibration.")
        return

    stere_flags = cv2.CALIB_FIX_INTRINSIC
    retval, _, _, _, _, rvec, tvec, _, _ = cv2.stereoCalibrate(
        objectPoints=obj_points,
        imagePoints1=img_points_a,
        imagePoints2=img_points_b,
        cameraMatrix1=cam_a,
        distCoeffs1=dist_a,
        cameraMatrix2=cam_b,
        distCoeffs2=dist_b,
        imageSize=size_a,
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
        flags=stere_flags,
    )

    print(f"\nStereo reprojection error: {retval:.3f}")
    print(f"Baseline (meters): {np.linalg.norm(tvec):.3f}")
    print(f"Translation vector (m): {tvec.ravel()}")
    print(f"Rotation vector (Rodrigues): {rvec.ravel()}")


if __name__ == "__main__":
    main()