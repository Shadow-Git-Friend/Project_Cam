#!/usr/bin/env python3
"""
Robust intrinsics calibration from a PRINTED ChArUco board when Charuco interpolation fails.

Board (from your label):
  squaresX=7, squaresY=10
  squareLength=40mm, markerLength=30mm

Key idea:
  - Use ArUco markers only (calibrateCameraAruco)
  - Infer marker ID -> board position mapping from a best reference image
  - Try multiple plausible board patterns (parity + flips) and pick the best RMS

Usage:
  python calibration_aruco_from_charuco.py --images "CamA/*.jpg" --out intrinsics.yaml

Optional:
  python calibration_aruco_from_charuco.py --images "CamA/*.jpg" --out intrinsics.yaml --drop_worst_frac 0.2
"""

import argparse
import glob
import os
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

import cv2
import numpy as np


DICT_4X4_CANDIDATES = [
    ("DICT_4X4_50", cv2.aruco.DICT_4X4_50),
    ("DICT_4X4_100", cv2.aruco.DICT_4X4_100),
    ("DICT_4X4_250", cv2.aruco.DICT_4X4_250),
    ("DICT_4X4_1000", cv2.aruco.DICT_4X4_1000),
]


@dataclass
class FrameDet:
    path: str
    size: Tuple[int, int]                 # (w, h)
    corners: List[np.ndarray]             # list of (1,4,2) float32
    ids: Optional[np.ndarray]             # (N,1) int32
    n_markers: int


def build_detector_params():
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    p.adaptiveThreshWinSizeMin = 5
    p.adaptiveThreshWinSizeMax = 75
    p.adaptiveThreshWinSizeStep = 10
    # reduce texture false positives somewhat
    p.minMarkerPerimeterRate = 0.03
    p.maxMarkerPerimeterRate = 4.0
    p.polygonalApproxAccuracyRate = 0.03
    return p


def detect_markers(image_path: str, aruco_dict, params) -> FrameDet:
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return FrameDet(image_path, (0, 0), [], None, 0)

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    corners, ids, _ = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=params)
    if ids is None or len(ids) == 0:
        return FrameDet(image_path, (w, h), [], None, 0)
    return FrameDet(image_path, (w, h), corners, ids.astype(np.int32), len(ids))


def choose_dictionary(image_paths: List[str], sample_n: int = 12) -> Tuple[str, int]:
    """Pick dict that yields highest total marker count on a sample."""
    params = build_detector_params()
    idx = np.linspace(0, len(image_paths) - 1, min(sample_n, len(image_paths))).astype(int)
    sample = [image_paths[i] for i in idx]

    best = None
    for name, did in DICT_4X4_CANDIDATES:
        aruco_dict = cv2.aruco.getPredefinedDictionary(did)
        total = 0
        for p in sample:
            d = detect_markers(p, aruco_dict, params)
            total += d.n_markers
        if best is None or total > best[0]:
            best = (total, name, did)
    return best[1], best[2]


def marker_centers(corners: List[np.ndarray]) -> np.ndarray:
    """Return (N,2) centers."""
    ctrs = []
    for c in corners:
        pts = c.reshape(-1, 2)  # (4,2)
        ctrs.append(np.mean(pts, axis=0))
    return np.array(ctrs, dtype=np.float32)


def expected_marker_centers_grid(squares_x: int, squares_y: int, square_len: float, parity: int,
                                 flip_x: bool, flip_y: bool) -> np.ndarray:
    """
    Generate expected marker-square centers in board coordinates (2D),
    for markers on alternating squares.
    """
    pts = []
    for y in range(squares_y):
        for x in range(squares_x):
            if ((x + y + parity) % 2) == 0:
                cx = (x + 0.5) * square_len
                cy = (y + 0.5) * square_len
                pts.append([cx, cy])

    pts = np.array(pts, dtype=np.float32)  # (35,2)

    # Apply flips in board coordinates (still planar)
    max_x = squares_x * square_len
    max_y = squares_y * square_len
    if flip_x:
        pts[:, 0] = max_x - pts[:, 0]
    if flip_y:
        pts[:, 1] = max_y - pts[:, 1]

    return pts


def expected_marker_corners_for_square(x: int, y: int, square_len: float, marker_len: float) -> np.ndarray:
    """
    3D corners of a marker placed centered in square (x,y), z=0 plane.
    Returns (4,3) in consistent order.
    """
    sx0 = x * square_len
    sy0 = y * square_len
    margin = (square_len - marker_len) * 0.5

    mx0 = sx0 + margin
    my0 = sy0 + margin
    mx1 = mx0 + marker_len
    my1 = my0 + marker_len

    # order: top-left, top-right, bottom-right, bottom-left (z=0)
    return np.array([
        [mx0, my0, 0.0],
        [mx1, my0, 0.0],
        [mx1, my1, 0.0],
        [mx0, my1, 0.0],
    ], dtype=np.float32)


def expected_marker_objpoints(squares_x: int, squares_y: int, square_len: float, marker_len: float,
                              parity: int, flip_x: bool, flip_y: bool) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns:
      exp_centers (M,2)
      exp_objpoints (M,4,3) marker corners in 3D for each expected marker position
    """
    centers = []
    objpts = []
    max_x = squares_x * square_len
    max_y = squares_y * square_len

    for y in range(squares_y):
        for x in range(squares_x):
            if ((x + y + parity) % 2) == 0:
                # center
                cx = (x + 0.5) * square_len
                cy = (y + 0.5) * square_len
                # obj corners
                corners3d = expected_marker_corners_for_square(x, y, square_len, marker_len)

                # apply flips by transforming coordinates
                if flip_x:
                    corners3d[:, 0] = max_x - corners3d[:, 0]
                    cx = max_x - cx
                if flip_y:
                    corners3d[:, 1] = max_y - corners3d[:, 1]
                    cy = max_y - cy

                centers.append([cx, cy])
                objpts.append(corners3d)

    return np.array(centers, dtype=np.float32), np.array(objpts, dtype=np.float32)  # (35,2), (35,4,3)


def sort_by_rows_xy(pts: np.ndarray) -> np.ndarray:
    """
    Robust-ish row-major ordering without knowing exact spacing:
    Sort by y then x.
    """
    idx = np.lexsort((pts[:, 0], pts[:, 1]))
    return idx


def make_custom_board(aruco_dict, ids_ordered: np.ndarray, objpoints_ordered: np.ndarray):
    """
    Create cv2.aruco.Board with given marker ids and marker 3D corner points.

    ids_ordered: (N,1) int32
    objpoints_ordered: (N,4,3) float32
    """
    ids_ordered = ids_ordered.reshape(-1, 1).astype(np.int32)
    objpoints_list = [objpoints_ordered[i].astype(np.float32) for i in range(len(ids_ordered))]

    # API compatibility:
    if hasattr(cv2.aruco, "Board_create"):
        board = cv2.aruco.Board_create(objpoints_list, aruco_dict, ids_ordered)
    else:
        board = cv2.aruco.Board(objpoints_list, aruco_dict, ids_ordered)
    return board


def calibrate_aruco(frames: List[FrameDet], board, image_size: Tuple[int, int]) -> Tuple[float, np.ndarray, np.ndarray, List[np.ndarray], List[np.ndarray]]:
    """
    Calibrate using markers only.
    """
    all_corners = []
    all_ids = []
    counter = []

    for f in frames:
        if f.ids is None or len(f.ids) == 0:
            continue
        all_corners.extend(f.corners)
        all_ids.extend(f.ids)
        counter.append(len(f.ids))

    if len(counter) == 0:
        raise RuntimeError("No marker detections for calibration.")

    all_ids = np.vstack(all_ids).astype(np.int32)
    counter = np.array(counter, dtype=np.int32)

    # OpenCV expects imageSize (w,h)
    w, h = image_size

    # flags can be tuned; start with 0
    rms, K, dist, rvecs, tvecs = cv2.aruco.calibrateCameraAruco(
        corners=all_corners,
        ids=all_ids,
        counter=counter,
        board=board,
        imageSize=(w, h),
        cameraMatrix=None,
        distCoeffs=None,
        flags=0
    )
    return rms, K, dist, rvecs, tvecs


def save_yaml(out_path: str, K, dist, img_size: Tuple[int, int], meta: dict):
    fs = cv2.FileStorage(out_path, cv2.FILE_STORAGE_WRITE)
    if not fs.isOpened():
        raise RuntimeError(f"Could not open {out_path} for writing")
    fs.write("image_width", int(img_size[0]))
    fs.write("image_height", int(img_size[1]))
    fs.write("camera_matrix", K)
    fs.write("dist_coeffs", dist)
    fs.startWriteStruct("meta", cv2.FILE_NODE_MAP)
    for k, v in meta.items():
        if isinstance(v, (int, float, str)):
            fs.write(k, v)
    fs.endWriteStruct()
    fs.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help='glob, e.g. "CamA/*.jpg"')
    ap.add_argument("--out", default="intrinsics.yaml")
    ap.add_argument("--squares_x", type=int, default=7)
    ap.add_argument("--squares_y", type=int, default=10)
    ap.add_argument("--square_len_m", type=float, default=0.040)
    ap.add_argument("--marker_len_m", type=float, default=0.030)
    ap.add_argument("--min_markers_ref", type=int, default=30, help="min markers required in reference image")
    ap.add_argument("--drop_worst_frac", type=float, default=0.0, help="drop worst fraction by per-frame marker count (simple)")
    args = ap.parse_args()

    # collect paths
    if os.path.isdir(args.images):
        paths = sorted(glob.glob(os.path.join(args.images, "*.*")))
    else:
        paths = sorted(glob.glob(args.images))
    if not paths:
        raise RuntimeError("No images found.")

    # choose dictionary
    dict_name, dict_id = choose_dictionary(paths)
    print(f"Selected dictionary: {dict_name}")
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
    params = build_detector_params()

    # detect on all frames
    frames: List[FrameDet] = []
    img_size0 = None
    for p in paths:
        d = detect_markers(p, aruco_dict, params)
        if d.size == (0, 0):
            continue
        if img_size0 is None:
            img_size0 = d.size
        elif d.size != img_size0:
            raise RuntimeError(f"Image size mismatch: first={img_size0}, current={d.size}, file={p}")
        frames.append(d)

    if not frames:
        raise RuntimeError("No readable images.")

    # pick reference frame = max markers (likely contains the full board)
    frames_sorted = sorted(frames, key=lambda f: f.n_markers, reverse=True)
    ref = frames_sorted[0]
    print(f"Reference image: {os.path.basename(ref.path)} markers={ref.n_markers}")

    if ref.n_markers < args.min_markers_ref:
        print("WARNING: Reference image has low marker count. Consider using a closer/clearer full-board image.")

    # remove obvious phantom detections in ref by taking top 35 markers closest to board cluster:
    # simplest robust: keep 35 markers with centers closest to median center.
    ref_centers = marker_centers(ref.corners)
    if ref_centers.shape[0] > 35:
        med = np.median(ref_centers, axis=0)
        d2 = np.sum((ref_centers - med) ** 2, axis=1)
        keep_idx = np.argsort(d2)[:35]
        ref_ids = ref.ids[keep_idx]
        ref_centers = ref_centers[keep_idx]
    else:
        ref_ids = ref.ids

    # sort detected markers row-major by image (y then x)
    det_order = sort_by_rows_xy(ref_centers)
    det_ids_sorted = ref_ids[det_order].reshape(-1, 1).astype(np.int32)

    # Try hypotheses: parity {0,1} and flips {x,y} in {False,True}
    hypotheses = []
    for parity in [0, 1]:
        for flip_x in [False, True]:
            for flip_y in [False, True]:
                exp_centers, exp_objpts = expected_marker_objpoints(
                    args.squares_x, args.squares_y, args.square_len_m, args.marker_len_m,
                    parity=parity, flip_x=flip_x, flip_y=flip_y
                )
                # sort expected centers in board coords the same way (y then x)
                exp_order = sort_by_rows_xy(exp_centers)
                exp_objpts_sorted = exp_objpts[exp_order]  # (35,4,3)

                # Map detected IDs (in sorted image order) to expected marker positions (sorted board order)
                # This gives a consistent ID->3D-corners association.
                board = make_custom_board(aruco_dict, det_ids_sorted, exp_objpts_sorted)

                # Evaluate by calibration RMS on a subset (top 30 frames by marker count)
                subset = frames_sorted[:min(30, len(frames_sorted))]
                try:
                    rms, _, _, _, _ = calibrate_aruco(subset, board, img_size0)
                except cv2.error:
                    continue

                hypotheses.append((rms, parity, flip_x, flip_y, board))

    if not hypotheses:
        raise RuntimeError("Failed to build any consistent board hypothesis. Likely dictionary mismatch or reference frame too noisy.")

    hypotheses.sort(key=lambda x: x[0])
    best_rms, best_parity, best_flip_x, best_flip_y, best_board = hypotheses[0]
    print(f"Best hypothesis: RMS={best_rms:.6f} parity={best_parity} flip_x={best_flip_x} flip_y={best_flip_y}")

    # Optionally drop worst frames by marker count (simple)
    use_frames = frames_sorted
    if args.drop_worst_frac and args.drop_worst_frac > 0.0:
        drop_n = int(round(len(use_frames) * args.drop_worst_frac))
        drop_n = min(drop_n, len(use_frames) - 8)
        if drop_n > 0:
            use_frames = use_frames[:-drop_n]
            print(f"Dropping worst {drop_n} frames by marker count. Remaining: {len(use_frames)}")

    # Final calibration on chosen frames
    rms, K, dist, rvecs, tvecs = calibrate_aruco(use_frames, best_board, img_size0)
    print(f"Final RMS: {rms:.6f}")
    print("K=\n", K)
    print("dist=\n", dist.ravel())

    meta = {
        "opencv_version": cv2.__version__,
        "dictionary": dict_name,
        "method": "calibrateCameraAruco_from_charuco_print",
        "squares_x": int(args.squares_x),
        "squares_y": int(args.squares_y),
        "square_len_m": float(args.square_len_m),
        "marker_len_m": float(args.marker_len_m),
        "best_parity": int(best_parity),
        "best_flip_x": str(best_flip_x),
        "best_flip_y": str(best_flip_y),
        "rms": float(rms),
        "ref_image": os.path.basename(ref.path),
    }
    save_yaml(args.out, K, dist, img_size0, meta)
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
