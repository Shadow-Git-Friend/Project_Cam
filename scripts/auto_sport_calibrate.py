#!/usr/bin/env python3
"""
Auto calibration helper for Sport_center images.
- Searches common Charuco board dimensions to calibrate intrinsics for two cameras.
- Estimates extrinsics from paired images using Charuco board pose estimation.

Usage:
  python scripts/auto_sport_calibrate.py --camA <path_to_intrinsics_images_for_camA> \
                                         --camB <path_to_intrinsics_images_for_camB> \
                                         --pairs <path_to_pairs_folder> \
                                         --out <output_dir>

The script will create outputs in the supplied `--out` folder (intrinsics/extrinsics JSONs).

Limitations: If the physical square size is unknown, the script grid-searches plausible values and selects the calibration with the lowest reprojection error. Absolute scale depends on chosen square size.
"""

import argparse
import os
import json
import cv2
import numpy as np
from pathlib import Path

# Typical search ranges (mm)
SQUARE_SIZES = [20, 25, 30, 40, 50, 60, 70]
ROWS = [5, 6, 7, 8, 9, 10]
COLS = [5, 6, 7, 8, 9, 10]
MARKER_RATIO = [0.5, 0.6, 0.7]
DICT_ID = cv2.aruco.DICT_4X4_50


def list_images(folder):
    p = Path(folder)
    if not p.exists():
        return []
    imgs = sorted([str(x) for x in p.iterdir() if x.suffix.lower() in ['.jpg', '.jpeg', '.png']])
    return imgs


def detect_charuco_corners(img_paths, rows, cols, square_size, marker_size):
    dictionary = cv2.aruco.getPredefinedDictionary(DICT_ID)
    try:
        board = cv2.aruco.CharucoBoard_create(cols, rows, square_size, marker_size, dictionary)
    except Exception:
        # Fallback: try older API
        board = None

    params = cv2.aruco.DetectorParameters_create()

    all_corners = []
    all_ids = []
    image_size = None

    for pth in img_paths:
        img = cv2.imread(pth)
        if img is None:
            continue
        if image_size is None:
            image_size = (img.shape[1], img.shape[0])
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary, parameters=params)
        if len(corners) > 0:
            if board is not None:
                try:
                    retval, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(corners, ids, gray, board)
                except Exception:
                    charuco_corners, charuco_ids = None, None
            else:
                charuco_corners, charuco_ids = None, None
        else:
            charuco_corners, charuco_ids = None, None

        if charuco_corners is not None and charuco_ids is not None and len(charuco_corners) > 4:
            all_corners.append(charuco_corners)
            all_ids.append(charuco_ids)

    return all_corners, all_ids, image_size, board


def calibrate_from_charuco(img_paths, rows, cols, square_size, marker_size):
    corners, ids, image_size, board = detect_charuco_corners(img_paths, rows, cols, square_size, marker_size)
    if len(corners) < 3:
        return None

    # Prepare objectPoints and imagePoints for calibrateCamera
    obj_points = []
    img_points = []
    try:
        for c, i in zip(corners, ids):
            # board.chessboardCorners or getChessboardCorners exist based on OpenCV
            try:
                board_obj = board.getChessboardCorners()
            except Exception:
                board_obj = board.chessboardCorners
            obj_pts = np.array(board_obj)[i.flatten()]
            obj_points.append(obj_pts)
            img_points.append(c.reshape(-1, 2))

        camera_matrix = np.eye(3)
        camera_matrix[0, 0] = 1000.0
        camera_matrix[1, 1] = 1000.0
        camera_matrix[0, 2] = image_size[0] / 2.0
        camera_matrix[1, 2] = image_size[1] / 2.0
        dist = np.zeros(5)
        flags = cv2.CALIB_USE_INTRINSIC_GUESS

        ret, K, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(obj_points, img_points, image_size, camera_matrix, dist, flags=flags)
        return {
            'reproj_error': float(ret),
            'K': K.tolist(),
            'dist': dist_coeffs.tolist(),
            'image_width': image_size[0],
            'image_height': image_size[1]
        }
    except Exception:
        return None


def find_best_intrinsics(img_folder, out_prefix):
    imgs = list_images(img_folder)
    if not imgs:
        print(f"No images in {img_folder}")
        return None

    best = None
    best_meta = None

    for rows in ROWS:
        for cols in COLS:
            for sq in SQUARE_SIZES:
                for ratio in MARKER_RATIO:
                    ms = sq * ratio
                    res = calibrate_from_charuco(imgs, rows, cols, sq, ms)
                    if res is None:
                        continue
                    err = res['reproj_error']
                    print(f"Tried {rows}x{cols} sq={sq}ms marker={int(ms)} -> err={err:.4f}")
                    if best is None or err < best['reproj_error']:
                        best = res
                        best_meta = {'rows': rows, 'cols': cols, 'square_mm': sq, 'marker_mm': ms}
                        # Save intermediate best
                        outp = Path(out_prefix)
                        outp.parent.mkdir(parents=True, exist_ok=True)
                        with open(outp, 'w') as f:
                            json.dump({'meta': best_meta, 'intrinsics': best}, f, indent=4)

    return best_meta, best


def estimate_extrinsics_from_pairs(pairs_folder, camA_intr, camB_intr, meta, out_path):
    """
    pairs_folder should contain images for both cams with matching names ending with _a/_b or _A/_B.
    The function looks for filenames with same prefix and suffixes ["_a","_b","_A","_B"].
    """
    p = Path(pairs_folder)
    files = sorted([x.name for x in p.iterdir() if x.suffix.lower() in ['.jpg', '.png', '.jpeg']])
    # Group by prefix
    pairs = {}
    for fn in files:
        name = fn.rsplit('.', 1)[0]
        if name.endswith('_a') or name.endswith('_A'):
            key = name[:-2]
            pairs.setdefault(key, {})['a'] = str(p / fn)
        elif name.endswith('_b') or name.endswith('_B'):
            key = name[:-2]
            pairs.setdefault(key, {})['b'] = str(p / fn)
    # If no _a/_b pattern, try paired ordering (first half/second half)
    if not pairs:
        # naive pairing
        half = len(files)//2
        for i in range(min(half, len(files)-half)):
            pairs[f'{i:04d}'] = {'a': str(p / files[i]), 'b': str(p / files[i+half])}

    if not pairs:
        print("No image pairs found in", pairs_folder)
        return None

    # Prepare camera matrices
    K0 = np.array(camA_intr['K'])
    K1 = np.array(camB_intr['K'])

    dictionary = cv2.aruco.getPredefinedDictionary(DICT_ID)
    board = cv2.aruco.CharucoBoard_create(meta['cols'], meta['rows'], meta['square_mm'], meta['marker_mm'], dictionary)

    Rrels = []
    Trels = []

    for key, pair in pairs.items():
        if 'a' not in pair or 'b' not in pair:
            continue
        img0 = cv2.imread(pair['a'])
        img1 = cv2.imread(pair['b'])
        if img0 is None or img1 is None:
            continue
        gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)

        params = cv2.aruco.DetectorParameters_create()
        corners0, ids0, _ = cv2.aruco.detectMarkers(gray0, dictionary, parameters=params)
        corners1, ids1, _ = cv2.aruco.detectMarkers(gray1, dictionary, parameters=params)

        if len(corners0) == 0 or len(corners1) == 0:
            continue

        try:
            retval0, charuco_corners0, charuco_ids0 = cv2.aruco.interpolateCornersCharuco(corners0, ids0, gray0, board)
            retval1, charuco_corners1, charuco_ids1 = cv2.aruco.interpolateCornersCharuco(corners1, ids1, gray1, board)
        except Exception:
            continue

        if charuco_corners0 is None or charuco_corners1 is None:
            continue

        if len(charuco_corners0) < 4 or len(charuco_corners1) < 4:
            continue

        # Estimate pose per camera relative to board
        try:
            ok0, rvec0, tvec0 = cv2.aruco.estimatePoseCharucoBoard(charuco_corners0, charuco_ids0, board, K0, np.array(camA_intr['dist']))
            ok1, rvec1, tvec1 = cv2.aruco.estimatePoseCharucoBoard(charuco_corners1, charuco_ids1, board, K1, np.array(camB_intr['dist']))
        except Exception:
            continue

        if not ok0 or not ok1:
            continue

        R0, _ = cv2.Rodrigues(rvec0)
        R1, _ = cv2.Rodrigues(rvec1)
        t0 = tvec0.reshape(3,)
        t1 = tvec1.reshape(3,)

        # Compute transform from cam1 -> cam0: R_rel = R0 * R1.T ; t_rel = t0 - R_rel @ t1
        R_rel = R0 @ R1.T
        t_rel = t0 - R_rel @ t1

        Rrels.append(R_rel)
        Trels.append(t_rel)
        print(f"Pair {key}: got extrinsic estimate")

    if not Rrels:
        print("No valid extrinsic pairs found.")
        return None

    R_mean = np.mean(np.stack(Rrels), axis=0)
    # Re-orthonormalize via SVD
    U, s, Vt = np.linalg.svd(R_mean)
    R_mean = U @ Vt
    t_mean = np.mean(np.stack(Trels), axis=0)

    out = {'R': R_mean.tolist(), 'T': t_mean.reshape(3,1).tolist()}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=4)

    print(f"Saved extrinsics to {out_path}")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--camA', required=True, help='Path to intrinsics images for camera A')
    parser.add_argument('--camB', required=True, help='Path to intrinsics images for camera B')
    parser.add_argument('--pairs', required=True, help='Path to folder with paired extrinsics images')
    parser.add_argument('--out', default='Sport_center/outputs', help='Output folder for results')
    args = parser.parse_args()

    outp = Path(args.out)
    outp.mkdir(parents=True, exist_ok=True)

    print('Calibrating Camera A (intrinsics search)...')
    metaA, intrA = find_best_intrinsics(args.camA, outp / 'camA_intrinsics.json')
    if intrA is None:
        print('Failed to calibrate Camera A')
        return
    print('Best Camera A meta:', metaA)

    print('Calibrating Camera B (intrinsics search)...')
    metaB, intrB = find_best_intrinsics(args.camB, outp / 'camB_intrinsics.json')
    if intrB is None:
        print('Failed to calibrate Camera B')
        return
    print('Best Camera B meta:', metaB)

    # Choose board meta: prefer meta found for pairs (we'll pick metaA by default)
    chosen_meta = metaA
    print('Estimating extrinsics using chosen board meta:', chosen_meta)

    extr_out = outp / 'camA_camB_extrinsics.json'
    extr = estimate_extrinsics_from_pairs(args.pairs, intrA['intrinsics'] if 'intrinsics' in intrA else intrA, intrB['intrinsics'] if 'intrinsics' in intrB else intrB, chosen_meta, extr_out)

    if extr is None:
        print('Extrinsics estimation failed.')
    else:
        print('Extrinsics estimation complete.')

    # Summary
    summary = {
        'camA_meta': metaA,
        'camB_meta': metaB,
    }
    with open(outp / 'summary.json', 'w') as f:
        json.dump(summary, f, indent=4)

    print('All done. Outputs in', outp)


if __name__ == '__main__':
    main()
