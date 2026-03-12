
import cv2
import cv2.aruco as aruco
import numpy as np
import time
import os
import sys

# --- CONFIGURATION ---
CAM_ID_2 = 0
CAM_ID_4 = 2
OUTPUT_DIR = os.getcwd() # Or specific folder
REQUIRED_MATCHES = 5  # Total pairs to capture
COOLDOWN_SEC = 5.0    # Time between captures

# Board Params
SQUARES_X = 5
SQUARES_Y = 7
SQUARE_LENGTH = 155.0 # mm (15.5 cm)
MARKER_LENGTH = 113.66 # mm (Calculated: 155 * 220/300)
TOTAL_MARKERS = 17 # (5*7)/2 = 17.5 -> 17 markers for 5x7 board
MIN_MARKERS_THRESHOLD = 12 # ~70% of 17

def main():
    print(f"--- Smart Auto-Capture ---")
    print(f"Requirements: Both cameras must see > {MIN_MARKERS_THRESHOLD} markers.")
    print(f"Goal: Capture {REQUIRED_MATCHES} pairs.")
    
    # 1. Setup Camera
    cap2 = cv2.VideoCapture(CAM_ID_2)
    cap4 = cv2.VideoCapture(CAM_ID_4)
    
    # Set MJPG/Resolution
    for cap in [cap2, cap4]:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
    if not cap2.isOpened() or not cap4.isOpened():
        print("Error: Could not open cameras.")
        return

    # 2. Setup Board & Detector
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    try:
        board = aruco.CharucoBoard((SQUARES_X, SQUARES_Y), SQUARE_LENGTH, MARKER_LENGTH, aruco_dict)
    except AttributeError:
        board = aruco.CharucoBoard_create(SQUARES_X, SQUARES_Y, SQUARE_LENGTH, MARKER_LENGTH, aruco_dict)

    # Tuning Detection (High Sensitivity)
    params = aruco.DetectorParameters()
    params.minMarkerPerimeterRate = 0.01 
    params.adaptiveThreshWinSizeMin = 3
    params.adaptiveThreshWinSizeMax = 23
    params.adaptiveThreshWinSizeStep = 5
    
    # Detector (OpenCV version compat)
    detector = None
    try:
        detector = aruco.ArucoDetector(aruco_dict, params)
    except AttributeError:
        pass # Use legacy

    captured_count = 0
    last_capture_time = time.time()
    
    while captured_count < REQUIRED_MATCHES:
        ret2, frame2 = cap2.read()
        ret4, frame4 = cap4.read()
        
        if not ret2 or not ret4:
            print("Frame error")
            break
            
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        gray4 = cv2.cvtColor(frame4, cv2.COLOR_BGR2GRAY)
        
        # --- Detect Cam 2 ---
        valid2 = False
        n_markers2 = 0
        
        # New API (OpenCV 4.7+)
        if detector and hasattr(aruco, 'CharucoDetector'): 
             try:
                # We need a CharucoDetector, not ArucoDetector for board
                if not hasattr(main, 'charuco_detector'):
                    main.charuco_detector = aruco.CharucoDetector(board)
                    main.charuco_detector.setDetectorParameters(params)
                
                charuco_corners2, charuco_ids2, corners2, ids2 = main.charuco_detector.detectBoard(gray2)
                
                if ids2 is not None:
                    n_markers2 = len(ids2)
                    if n_markers2 >= MIN_MARKERS_THRESHOLD and charuco_corners2 is not None and len(charuco_corners2) > 4:
                        valid2 = True
             except Exception as e:
                print(f"New API Error: {e}")
                ids2 = None
        
        # Old API Fallback
        else:
            corners2, ids2, _ = aruco.detectMarkers(gray2, aruco_dict, parameters=params)
            if ids2 is not None:
                n_markers2 = len(ids2)
                res2, charuco_corners2, charuco_ids2 = aruco.interpolateCornersCharuco(corners2, ids2, gray2, board)
                if res2 and charuco_corners2 is not None and len(charuco_corners2) > 4:
                    if n_markers2 >= MIN_MARKERS_THRESHOLD:
                        valid2 = True

        # --- Detect Cam 4 ---
        valid4 = False
        n_markers4 = 0
        
        if detector and hasattr(aruco, 'CharucoDetector'):
             try:
                charuco_corners4, charuco_ids4, corners4, ids4 = main.charuco_detector.detectBoard(gray4)
                
                if ids4 is not None:
                    n_markers4 = len(ids4)
                    if n_markers4 >= MIN_MARKERS_THRESHOLD and charuco_corners4 is not None and len(charuco_corners4) > 4:
                        valid4 = True
             except Exception:
                ids4 = None
        else:
            corners4, ids4, _ = aruco.detectMarkers(gray4, aruco_dict, parameters=params)
            if ids4 is not None:
                n_markers4 = len(ids4)
                res4, charuco_corners4, charuco_ids4 = aruco.interpolateCornersCharuco(corners4, ids4, gray4, board)
                if res4 and charuco_corners4 is not None and len(charuco_corners4) > 4:
                    if n_markers4 >= MIN_MARKERS_THRESHOLD:
                        valid4 = True

        # --- Visual Feedback ---
        # Draw on small copies for display
        vis2 = cv2.resize(frame2, (640, 360))
        vis4 = cv2.resize(frame4, (640, 360))
        
        # Color borders based on status
        color2 = (0, 255, 0) if valid2 else ((0, 255, 255) if n_markers2 > 0 else (0, 0, 255))
        color4 = (0, 255, 0) if valid4 else ((0, 255, 255) if n_markers4 > 0 else (0, 0, 255))
        
        cv2.rectangle(vis2, (0,0), (639, 359), color2, 5)
        cv2.rectangle(vis4, (0,0), (639, 359), color4, 5)
        
        cv2.putText(vis2, f"M: {n_markers2}/{MIN_MARKERS_THRESHOLD}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, color2, 2)
        cv2.putText(vis4, f"M: {n_markers4}/{MIN_MARKERS_THRESHOLD}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, color4, 2)

        combined = np.hstack((vis2, vis4))
        
        # Status Bar
        status_h = 50
        status_img = np.zeros((status_h, 1280, 3), dtype=np.uint8)
        
        now = time.time()
        if now - last_capture_time < COOLDOWN_SEC:
            msg = f"Cooldown... {int(COOLDOWN_SEC - (now - last_capture_time))}s"
            cv2.putText(status_img, msg, (500, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        elif valid2 and valid4:
            msg = "CAPTURING!"
            cv2.putText(status_img, msg, (500, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        else:
            msg = f"Waiting for locks... ({captured_count}/{REQUIRED_MATCHES})"
            cv2.putText(status_img, msg, (400, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (200, 200, 200), 2)

        final_display = np.vstack((combined, status_img))
        cv2.imshow("Auto Capture System", final_display)

        # --- Logic ---
        if valid2 and valid4 and (now - last_capture_time > COOLDOWN_SEC):
            # CAPTURE
            f2_name = os.path.join(OUTPUT_DIR, f"auto_B_{captured_count}.jpg")
            f4_name = os.path.join(OUTPUT_DIR, f"auto_A_{captured_count}.jpg")
            
            cv2.imwrite(f2_name, frame2)
            cv2.imwrite(f4_name, frame4)
            print(f"[SUCCESS] Captured Pair {captured_count}: {f2_name}, {f4_name}")
            
            captured_count += 1
            last_capture_time = now

        if cv2.waitKey(10) & 0xFF == ord('q'):
            break

    cap2.release()
    cap4.release()
    cv2.destroyAllWindows()
    
if __name__ == "__main__":
    main()
