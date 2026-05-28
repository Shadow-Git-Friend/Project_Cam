import cv2
import glob
import numpy as np
import os
import re
from reconstruction import StereoCalibrator

def check_files(pattern):
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"ERROR: No files found for {pattern}")
    return files

def main():
    # --- 1. Define Board Parameters ---
    
    # Board 1: Intrinsics (7x10)
    # File: ChArUco__...__7x10_Board__35_Markers__40mm_SquareSize__30mm_MarkerSize...pdf
    INTRINSIC_BOARD = {
        'squares_x': 7,
        'squares_y': 10,
        'square_len': 0.040,      # 40 mm = 0.04 m
        'marker_len': 0.030,      # 30 mm = 0.03 m
        'dict_id': cv2.aruco.DICT_4X4_50
    }

    # Board 2: Extrinsics (6x4)
    # File: board.txt -> 1500x850mm canvas... square_len=210mm
    EXTRINSIC_BOARD = {
        'squares_x': 6,
        'squares_y': 4,
        'square_len': 0.1618,      # Scaled to match physical 7.07m baseline (from 9.18m)
        'marker_len': 0.11326,    # 0.7 * 0.1618
        'dict_id': cv2.aruco.DICT_4X4_50
    }

    calibrator = StereoCalibrator()

    # --- 2. Intrinsic Calibration (Cam A) ---
    print("\n=== Intrinsic Calibration: Cam A ===")
    images_a = check_files('Calibration/Intrinsics/CamA/*.jpg')
    if not images_a: return
    K_a, D_a, size_a = calibrator.calibrate_intrinsic(
        images_a,
        **INTRINSIC_BOARD
    )
    print(f"K_a:\n{K_a}")

    # --- 3. Intrinsic Calibration (Cam B) ---
    print("\n=== Intrinsic Calibration: Cam B ===")
    images_b = check_files('Calibration/Intrinsics/CamB/*.jpg')
    if not images_b: return
    K_b, D_b, size_b = calibrator.calibrate_intrinsic(
        images_b,
        **INTRINSIC_BOARD
    )
    
    if size_a != size_b:
        print("WARNING: Image sizes differ between Cam A and Cam B!")

    # --- 4. Stereo Calibration ---
    print("\n=== Stereo Calibration ===")
    ext_files = sorted(glob.glob('Calibration/Extrinsics/*.jpg'))
    
    # Pair files: 1a.jpg, 1b.jpg
    # Heuristic: Group by number in filename
    pair_map = {}
    for f in ext_files:
        basename = os.path.basename(f)
        digits = re.findall(r'\d+', basename)
        if digits:
            num = digits[0]
            if num not in pair_map: pair_map[num] = []
            pair_map[num].append(f)
            
    sorted_keys = sorted(pair_map.keys(), key=lambda x: int(x))
    
    valid_pairs = []
    for k in sorted_keys:
        flist = pair_map[k]
        if len(flist) == 2:
            f1, f2 = sorted(flist) # 'a' < 'b'
            valid_pairs.append((f1, f2))
            
    print(f"Found {len(valid_pairs)} stereo pairs.")
    if not valid_pairs:
        print("No valid stereo pairs found. Check Exstrinsics filename format.")
        return

    R, T = calibrator.calibrate_stereo(
        valid_pairs,
        K_a, D_a, K_b, D_b,
        size_a,
        **EXTRINSIC_BOARD
    )
    
    print("\nCalibration Complete!")
    print(f"Translation T: {T.flatten()} (meters)")
    print(f"Rotation R:\n{R}")
    
    np.savez("calibration.npz", K1=K_a, D1=D_a, K2=K_b, D2=D_b, R=R, T=T)
    print("Saved to calibration.npz")

if __name__ == "__main__":
    main()
