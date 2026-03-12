
import numpy as np
import cv2
import cv2.aruco as aruco
import glob
import os
import argparse
import json

def calibrate_intrinsics(image_dir, rows, cols, square_size, marker_size, output_file, dict_id=aruco.DICT_4X4_50):
    """
    Calibrates camera intrinsics using ChArUco board.
    """
    print(f"--- Processing {image_dir} ---")
    
    # Define Board
    dictionary = aruco.getPredefinedDictionary(dict_id)
    # Modern OpenCV ChArUco Board
    try:
        board = aruco.CharucoBoard((cols, rows), square_size, marker_size, dictionary)
        # ENABLE LEGACY PATTERN for this board
        if hasattr(board, 'setLegacyPattern'):
            board.setLegacyPattern(True)
            print("  [INFO] Legacy Pattern Enabled")
    except AttributeError:
        # Fallback
        board = aruco.CharucoBoard_create(cols, rows, square_size, marker_size, dictionary)
    
    # Detector params
    params = aruco.DetectorParameters()
    
    # Modern Detector
    try:
        detector = aruco.CharucoDetector(board)
    except AttributeError:
        detector = None # Fallback logic below

    all_charuco_corners = []
    all_charuco_ids = []
    
    images = glob.glob(os.path.join(image_dir, "*.jpg")) + glob.glob(os.path.join(image_dir, "*.png"))
    images.sort()
    
    if not images:
        print(f"[ERROR] No images found in {image_dir}")
        return
        
    print(f"Found {len(images)} images.")
    image_size = None

    for fname in images:
        img = cv2.imread(fname)
        if image_size is None:
            image_size = img.shape[:2][::-1]
        
        # Detect
        if detector:
             # OpenCV 4.7+
            charuco_corners, charuco_ids, marker_corners, marker_ids = detector.detectBoard(img)
        else:
            # Legacy
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            marker_corners, marker_ids, _ = aruco.detectMarkers(gray, dictionary, parameters=params)
            if len(marker_corners) > 0:
                _, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
                    marker_corners, marker_ids, img, board
                )
            else:
                charuco_corners = None

        if charuco_corners is not None and charuco_ids is not None and len(charuco_corners) > 4:
            all_charuco_corners.append(charuco_corners)
            all_charuco_ids.append(charuco_ids)
            # print(f"  [OK] {os.path.basename(fname)}")
        else:
            print(f"  [FAIL] {os.path.basename(fname)}")

    if len(all_charuco_corners) < 3:
        print("[ERROR] Not enough valid measurements for calibration.")
        return

    print(f"Calibrating with {len(all_charuco_corners)} valid frames...")
    
    # Collect Object Points and Image Points for cv2.calibrateCamera
    all_obj_points = []
    all_img_points = []
    
    for i in range(len(all_charuco_corners)):
        corners = all_charuco_corners[i]
        ids = all_charuco_ids[i]
        
        # Get 3D object points for the detected corners
        # board.getChessboardCorners() returns all corners
        # We filter by detected IDs
        try:
            # Modern OpenCV
            obj_pts = board.getChessboardCorners()
            current_obj = obj_pts[ids.flatten()]
        except AttributeError:
             # Legacy
            obj_pts = board.chessboardCorners
            current_obj = obj_pts[ids.flatten()]
            
        all_obj_points.append(current_obj)
        all_img_points.append(corners)

    # Initial Guess (Optional but helps if convergence creates garbage)
    # Based on Cam B result: fx~1140, cx=960, cy=540
    camera_matrix = np.array([
        [1140.0, 0.0, image_size[0]/2.0],
        [0.0, 1140.0, image_size[1]/2.0],
        [0.0, 0.0, 1.0]
    ])
    dist_coeffs = np.zeros(5)
    
    flags = cv2.CALIB_USE_INTRINSIC_GUESS
    
    try:
        # Standard Camera Calibration
        ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            all_obj_points, all_img_points, image_size, camera_matrix, dist_coeffs, flags=flags
        )
        
        print(f"Reprojection Error: {ret:.4f}")
        print(f"Camera Matrix:\n{camera_matrix}")
        print(f"Dist Coeffs:\n{dist_coeffs}")
        
        # Save to JSON (Unified Format part)
        data = {
            "camera_matrix": camera_matrix.tolist(),
            "distortion_coefficients": dist_coeffs.tolist(),
            "reprojection_error": ret,
            "image_width": image_size[0],
            "image_height": image_size[1]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=4)
            
        print(f"[SUCCESS] Saved to {output_file}")
        
    except Exception as e:
        print(f"[ERROR] Calibration failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Directory containing images")
    parser.add_argument("--out", required=True, help="Output JSON file")
    args = parser.parse_args()
    
    # USER SPECIFIED BOARD: 7x10, 40mm square, 30mm marker, DICT_4X4_50
    # Note: 'SQUARES_X' usually refers to cols (7) and 'SQUARES_Y' to rows (10) or vice versa.
    # Standard A3 ChArUco is usually 7x5 or 10x7.
    # User said: "7x10 Board". Let's assume 7 (X) by 10 (Y).
    
    calibrate_intrinsics(
        image_dir=args.dir,
        rows=10,
        cols=7,
        square_size=40.0, # mm
        marker_size=30.0, # mm
        output_file=args.out
    )
