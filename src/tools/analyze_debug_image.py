
import cv2
import cv2.aruco as aruco
import numpy as np

IMG_PATH = "debug_goal_view_cam0.jpg"

def check(img_path):
    print(f"--- Analyzing {img_path} ---")
    img = cv2.imread(img_path)
    if img is None:
        print("Image not found.")
        return
        
    print(f"Resolution: {img.shape}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Board Config
    SQUARES_X = 5
    SQUARES_Y = 7
    SQUARE_LENGTH = 155.0
    MARKER_LENGTH = 113.66
    ARUCO_DICT_ID = aruco.DICT_4X4_50
    dict_obj = aruco.getPredefinedDictionary(ARUCO_DICT_ID)
    
    # Test 1: Current Settings (Legacy, Relaxed)
    print("\n[Test 1] Current Settings (Legacy=True, minPerimeter=0.002)")
    board = aruco.CharucoBoard((SQUARES_X, SQUARES_Y), SQUARE_LENGTH, MARKER_LENGTH, dict_obj)
    if hasattr(board, 'setLegacyPattern'): board.setLegacyPattern(True)
    
    params = aruco.DetectorParameters()
    params.minMarkerPerimeterRate = 0.002
    params.adaptiveThreshWinSizeMin = 3
    params.adaptiveThreshWinSizeMax = 23
    params.adaptiveThreshWinSizeStep = 10
    
    detector = aruco.ArucoDetector(dict_obj, params)
    corns, ids, _ = detector.detectMarkers(gray)
    print(f"  > Markers Detected: {len(ids) if ids is not None else 0}")
    
    if ids is not None and len(ids) > 0:
        print(f"      IDs: {ids.flatten()}")
        
    # Test 2: Standard Settings (Legacy=False, Default Params)
    print("\n[Test 2] Standard Settings (Legacy=False, Default Params)")
    board2 = aruco.CharucoBoard((SQUARES_X, SQUARES_Y), SQUARE_LENGTH, MARKER_LENGTH, dict_obj)
    # No legacy set
    
    params2 = aruco.DetectorParameters() # Defaults
    detector2 = aruco.ArucoDetector(dict_obj, params2)
    corns2, ids2, _ = detector2.detectMarkers(gray)
    print(f"  > Markers Detected: {len(ids2) if ids2 is not None else 0}")
    
    # Test 3: DICT_5X5? (Just in case)
    print("\n[Test 3] DICT_5X5_50 Check")
    dict5 = aruco.getPredefinedDictionary(aruco.DICT_5X5_50)
    detector3 = aruco.ArucoDetector(dict5, params)
    corns3, ids3, _ = detector3.detectMarkers(gray)
    print(f"  > Markers Detected: {len(ids3) if ids3 is not None else 0}")

if __name__ == "__main__":
    check("debug_goal_view_cam0.jpg")
    check("debug_goal_view_cam1.jpg")
