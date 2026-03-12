
import cv2
import cv2.aruco as aruco
import numpy as np
import sys
import os
import argparse

def check_image(image_path):
    if not os.path.exists(image_path):
        print(f"[ERROR] File not found: {image_path}")
        return

    print(f"\n--- Checking {image_path} ---")
    frame = cv2.imread(image_path)
    if frame is None:
        print("[ERROR] Could not read image.")
        return

    # Geometries to test (Cols, Rows)
    geometries = [
        (7, 10),
        (10, 7)
    ]
    
    SQUARE_LENGTH = 40.0 # mm
    MARKER_LENGTH = 30.0 # mm

    dicts_to_test = [
        ("DICT_4X4_50", aruco.DICT_4X4_50),
        ("DICT_4X4_100", aruco.DICT_4X4_100),
        ("DICT_4X4_250", aruco.DICT_4X4_250),
        ("DICT_4X4_1000", aruco.DICT_4X4_1000),
    ]

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Parameter sets to try
    param_sets = []
    
    # Default
    p_def = aruco.DetectorParameters()
    param_sets.append(("Default", p_def))
    
    # Aggressive for small markers
    p_small = aruco.DetectorParameters()
    p_small.minMarkerPerimeterRate = 0.01 
    p_small.adaptiveThreshWinSizeMin = 3
    p_small.adaptiveThreshWinSizeMax = 23
    p_small.adaptiveThreshWinSizeStep = 5
    param_sets.append(("Small_Markers", p_small))
    
    # Loose Polygons
    p_blur = aruco.DetectorParameters()
    p_blur.minMarkerPerimeterRate = 0.01 
    p_blur.polygonalApproxAccuracyRate = 0.08
    param_sets.append(("Loose_Polygons", p_blur))

    # VERY Aggressive
    p_agg = aruco.DetectorParameters()
    p_agg.minMarkerPerimeterRate = 0.01
    p_agg.adaptiveThreshConstant = 1
    p_agg.minCornerDistanceRate = 0.01
    param_sets.append(("Aggressive", p_agg))

    for cols, rows in geometries:
        # print(f"--- Geometry: {cols}x{rows} ---")
        
        for p_name, params in param_sets:
            for name, dict_id in dicts_to_test:
                aruco_dict = aruco.getPredefinedDictionary(dict_id)
                
                # Create Board
                try:
                    board = aruco.CharucoBoard((cols, rows), SQUARE_LENGTH, MARKER_LENGTH, aruco_dict)
                except AttributeError:
                    board = aruco.CharucoBoard_create(cols, rows, SQUARE_LENGTH, MARKER_LENGTH, aruco_dict)
                
                # Try Regular and Legacy Pattern
                patterns = [False]
                if hasattr(board, 'setLegacyPattern'):
                     patterns.append(True)
                
                for use_legacy in patterns:
                    if use_legacy:
                         board.setLegacyPattern(True)
                    
                    # Detect
                    charuco_corners = None
                    charuco_ids = None
                    
                    try:
                        # OpenCV 4.7+
                        charuco_detector = aruco.CharucoDetector(board, detectorParams=params)
                        charuco_corners, charuco_ids, marker_corners, marker_ids = charuco_detector.detectBoard(gray)
                        corners = marker_corners
                        ids = marker_ids
                    except AttributeError:
                        # OpenCV < 4.7
                        corners, ids, rejected = aruco.detectMarkers(gray, aruco_dict, parameters=params)
                        if ids is not None and len(ids) > 0:
                            retval, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(corners, ids, gray, board)
                    
                    if ids is not None and len(ids) > 0:
                        visit_ids = [ids[0][0], ids[-1][0]] if len(ids) > 1 else [ids[0][0]]
                        # print(f"    [RAW] {p_name} | {name} | Legacy={use_legacy}: {len(ids)} Markers. IDs: {visit_ids}...")
                        
                        num_charuco = len(charuco_corners) if charuco_corners is not None else 0
                        
                        if num_charuco > 4:
                            print(f"    [SUCCESS] VALID BOARD: {cols}x{rows} | {name} | {p_name} | Legacy={use_legacy} | {num_charuco} Crn")
                            return # Stop
                        # The original code had an `imwrite` block here, which is removed by the diff.
                        # The `out_name` variable would not be defined if the `except AttributeError` path was taken.
                        # Following the diff faithfully, this line is kept as provided, assuming `out_name` is defined elsewhere or this is a partial diff.
                        # For a syntactically correct and runnable code, `out_name` would need to be defined.
                        # However, since the instruction is to make the change faithfully, I will include it as given.
                        # If `out_name` is not defined, this line will cause a NameError.
                        # To avoid NameError, one might define `out_name` or remove this line if it's not intended.
                        # Given the strict instruction, I'm keeping it as is.
                        # print(f"    [SAVED] {out_name}") # This line would cause a NameError if out_name is not defined.
                
                if ids is not None and len(ids) > 0:
                    num_charuco = len(charuco_corners) if charuco_corners is not None else 0
                    
                    # Print raw markers even if no boards
                    ids_flat = ids.flatten()
                    ids_flat.sort()
                    print(f"    [RAW] {p_name} | {name}: {len(ids)} Markers Found. IDs: {ids_flat[:5]}...{ids_flat[-5:]}")
                    
                    if num_charuco > 0:
                        print(f"    [MATCH] {p_name} | {name}: {len(ids)} Markers, {num_charuco} ChArUco Corners")
                        return # Stop on first success for this image
    
    print("[FAIL] Could not detect board with any config.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", help="Specific image to check")
    args = parser.parse_args()

    files_to_check = []
    if args.image:
        files_to_check = [args.image]
    else:
        # Fallback to hardcoded if no arg
        files_to_check = ["A_6.jpg", "B_6.jpg"]
        
    for image_file in files_to_check:
        # If absolute path not given and file not found, assume local
        full_path = image_file
        if not os.path.exists(full_path) and not os.path.isabs(full_path):
             full_path = os.path.join(os.path.dirname(__file__), "..", "..", image_file)
             
        check_image(full_path)
