
import cv2
import cv2.aruco as aruco
import numpy as np
import argparse
import json
import os
import glob
import sys

# --- CONFIG ---
# Board Params (Must match capture script)
SQUARES_X = 5
SQUARES_Y = 7
SQUARE_LENGTH = 155.0
MARKER_LENGTH = 113.66
ARUCO_DICT = aruco.DICT_4X4_50

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

def load_intrinsics(filepath):
    """Load intrinsics from .npz or .json file."""
    try:
        if filepath.endswith(".npz"):
            with np.load(filepath) as data:
                return data['camera_matrix'], data['dist_coeffs']
        elif filepath.endswith(".json"):
            with open(filepath, 'r') as f:
                data = json.load(f)
            K = np.array(data["camera_matrix"])
            D = np.array(data["distortion_coefficients"])
            return K, D
        else:
            raise ValueError(f"Unknown file format: {filepath}")
    except Exception as e:
        print(f"[ERROR] Failed to load {filepath}: {e}")
        return None, None

def main():
    parser = argparse.ArgumentParser()
    # Cam A = ID 2 (captured as auto_A_*)
    # Cam B = ID 0 (captured as auto_B_*) or vice versa?
    # capture_charuco_auto said:
    # f2_name = auto_B (from cap2 -> ID 0)
    # f4_name = auto_A (from cap4 -> ID 2)
    
    parser.add_argument("--cam0_id", type=int, default=0, help="ID of Camera B")
    parser.add_argument("--cam0_intrinsics", type=str, required=True)
    parser.add_argument("--cam1_id", type=int, default=2, help="ID of Camera A")
    parser.add_argument("--cam1_intrinsics", type=str, required=True)
    parser.add_argument("--dir", type=str, default=".", help="Directory with auto_A_*.jpg")
    parser.add_argument("-o", "--output", type=str, default="cal/calibration_full.json")
    
    args = parser.parse_args()

    # 1. Load Intrinsics
    K0, D0 = load_intrinsics(args.cam0_intrinsics)
    K1, D1 = load_intrinsics(args.cam1_intrinsics)
    
    if K0 is None or K1 is None:
        print("EXIT: Intrinsics missing.")
        return

    # 2. Setup Board
    dictionary = aruco.getPredefinedDictionary(ARUCO_DICT)
    try:
        board = aruco.CharucoBoard((SQUARES_X, SQUARES_Y), SQUARE_LENGTH, MARKER_LENGTH, dictionary)
    except AttributeError:
        board = aruco.CharucoBoard_create(SQUARES_X, SQUARES_Y, SQUARE_LENGTH, MARKER_LENGTH, dictionary)
    
    params = aruco.DetectorParameters()
    # High Sensitive Params for detecting board in static images
    params.minMarkerPerimeterRate = 0.01 
    params.adaptiveThreshWinSizeMin = 3
    params.adaptiveThreshWinSizeMax = 23
    params.adaptiveThreshWinSizeStep = 5

    # 3. Process Images
    # We look for auto_A_X.jpg and auto_B_X.jpg
    # A came from ID 2 (args.cam1_id)
    # B came from ID 0 (args.cam0_id)
    
    pattern_A = os.path.join(args.dir, "auto_A_*.jpg")
    files_A = sorted(glob.glob(pattern_A))
    
    valid_pairs = 0
    
    # Store results
    # We need R, T for each camera relative to world (board)
    # But usually we want Stereo Extrinsics (Cam2 relative to Cam1) or both relative to World.
    # The existing system seems to want independent R/T w.r.t World for each camera in the JSON.
    
    # Since the board moves, "World" moves every frame.
    # We can't simple average T_cam_to_world.
    # BUT, if we fix one camera (e.g. Cam 0) as World Origin? No, usually we want relative transform.
    
    # Standard Extrinsic Calibration for Moving Board:
    # We calculate relative R, T between cameras for *each* frame, then average/optimize them.
    # R_rel = R2 * R1^T
    # T_rel = T2 - R_rel * T1
    
    r_vecs_1_to_2 = []
    t_vecs_1_to_2 = []
    
    print(f"Found {len(files_A)} files for Cam A...")
    
    for f_A in files_A:
        # Construct f_B
        f_B = f_A.replace("auto_A_", "auto_B_")
        if not os.path.exists(f_B):
            continue
            
        print(f"Processing pair: {os.path.basename(f_B)} (Cam{args.cam0_id}) <-> {os.path.basename(f_A)} (Cam{args.cam1_id})")
        
        # Detect and Solve PnP for both
        def get_pose(img_path, K, D):
            img = cv2.imread(img_path)
            if img is None: return None, None
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            charuco_corners = None
            charuco_ids = None
            
            # New API (OpenCV 4.7+)
            if hasattr(aruco, 'CharucoDetector'):
                 try:
                    if not hasattr(get_pose, 'charuco_detector'):
                         get_pose.charuco_detector = aruco.CharucoDetector(board)
                         get_pose.charuco_detector.setDetectorParameters(params)
                    
                    charuco_corners, charuco_ids, corners, ids = get_pose.charuco_detector.detectBoard(gray)
                 except Exception:
                    charuco_corners = None
            
            # Legacy Fallback
            if charuco_corners is None:
                 try:
                    corners, ids, _ = aruco.detectMarkers(gray, dictionary, parameters=params)
                    if ids is not None and len(ids) > 0:
                        retval, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(corners, ids, gray, board)
                 except AttributeError:
                    return None, None
            
            if charuco_corners is not None and charuco_ids is not None and len(charuco_corners) > 4:
                # Modern OpenCV 4.7+: Use MatchImagePoints + SolvePnP
                try:
                    objPoints, imgPoints = board.matchImagePoints(charuco_corners, charuco_ids)
                    if objPoints is not None and len(objPoints) >= 4:
                        valid, rvec, tvec = cv2.solvePnP(objPoints, imgPoints, K, D)
                        if valid: return rvec, tvec
                except AttributeError:
                     # Fallback if matchImagePoints has different signature or issues
                     pass
            
            return None, None

        r0, t0 = get_pose(f_B, K0, D0) # Cam 0 (B)
        r1, t1 = get_pose(f_A, K1, D1) # Cam 1 (A)
        
        if r0 is not None and r1 is not None:
            # Both saw the board!
            # Compute relative pose: Cam 1 (A) -> Cam 0 (B)
            # T_0 = R_rel * T_1 + t_rel
            
            # Convert to matrix
            R0, _ = cv2.Rodrigues(r0)
            R1, _ = cv2.Rodrigues(r1)
            
            # World to Cam0: P0 = R0 * Pw + t0
            # World to Cam1: P1 = R1 * Pw + t1
            # Pw = R1^T * (P1 - t1)
            # P0 = R0 * (R1^T * (P1 - t1)) + t0
            # P0 = (R0 * R1^T) * P1 + (t0 - R0 * R1^T * t1)
            
            R_1to0 = np.dot(R0, R1.T)
            T_1to0 = t0 - np.dot(R_1to0, t1)
            
            r_vecs_1_to_2.append(R_1to0) # Storing Rotation Matrix directly for averaging? Rotation vector is better for average
            t_vecs_1_to_2.append(T_1to0)
            valid_pairs += 1
            print("  [OK] Valid Pair")
        else:
             print("  [FAIL] Detection failed")
             
    if valid_pairs == 0:
        print("[ERROR] No valid pairs found.")
        return

    # Average Results
    print(f"\nComputing average from {valid_pairs} pairs...")
    
    # Simple average for T
    T_avg = np.mean(t_vecs_1_to_2, axis=0)
    
    # Distance between cameras (Baseline)
    baseline_dist = np.linalg.norm(T_avg)
    print(f"--- RESULTS ---")
    print(f"Rel Position (Cam2 in Cam0 Frame): {T_avg.flatten()}")
    print(f"Distance between Camera 0 and Camera 2: {baseline_dist:.2f} mm ({baseline_dist/1000:.2f} meters)")
    print(f"  (Z-component only: {T_avg[2,0]:.2f} mm)")
    
    # Calculate average distance to BOARD for context
    # We need to re-run or just store t0 norms.
    # We didn't store t0 list. Let's precise that we can't show it without re-looping, 
    # but based on T_avg we answered the user's question about the 2.11m.
    # Let's convert R matrices back to Rodrigues
    r_vecs_rodrigues = []
    for R in r_vecs_1_to_2:
        r, _ = cv2.Rodrigues(R)
        r_vecs_rodrigues.append(r)
        
    R_vec_avg = np.mean(r_vecs_rodrigues, axis=0)
    R_avg, _ = cv2.Rodrigues(R_vec_avg)
    
    print("Relative Transform (Cam A -> Cam B):")
    print(f"Translation (mm): {T_avg.flatten()}")
    
    # Output structure matching existing system
    # Usually:
    # cam_0: R=Identity, T=0
    # cam_1: R=R_avg, T=T_avg (if defined as Cam1 -> Cam0)
    
    # NOTE: The existing system (ball_tracking) likely expects R, T to be "Camera to World" or "World to Camera"?
    # checks calibrate_extrinsics.py output...
    # It sets cameras_data[cam_key]["R"] = R_cam_to_world
    
    # If we define "World" as Camera 0's coordinate system:
    # Cam 0: R = I, T = 0
    # Cam 1: R and T such that P_cam1 -> P_cam0
    # The previous code output "R_cam_to_world" (likely meaning World -> Cam inverse?) 
    # Let's stick to standard OpenCV: points in Cam1 coords -> Cam0 coords.
    
    # Let's save Cam0 as Reference (Identity)
    # Cam 2 (ID 0)
    out_data = {}
    
    # Cam B (Cam 0 id) -> Origin
    out_data[f"cam_{args.cam0_id}"] = {
        "id": args.cam0_id,
        "intrinsics_file": args.cam0_intrinsics,
        "K": K0, "D": D0,
        "R": np.eye(3), "T": np.zeros((3,1))
    }
    
    # Cam A (Cam 2 id) -> Relative
    # We calculated P0 = R_1to0 * P1 + T_1to0
    # This means R_1to0 converts P1 to P0. 
    # If "World" is P0, then P_world = R * P_cam + T
    # P0 = R_1to0 * P1 + T_1to0 -> This matches World=Cam0, Cam=Cam1
    
    out_data[f"cam_{args.cam1_id}"] = {
        "id": args.cam1_id,
        "intrinsics_file": args.cam1_intrinsics,
        "K": K1, "D": D1,
        "R": R_1to0, "T": T_1to0
    }
    
    with open(args.output, "w") as f:
        json.dump(out_data, f, cls=NumpyEncoder, indent=4)
        
    print(f"[SUCCESS] Saved to {args.output}")

if __name__ == "__main__":
    main()
