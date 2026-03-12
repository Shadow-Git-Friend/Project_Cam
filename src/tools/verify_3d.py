
import cv2
import numpy as np
import json
import time
from ultralytics import YOLO
import sys
import os
from pathlib import Path

# --- CONFIG ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CAL_FILE = PROJECT_ROOT / "cal" / "calibration_full.json"
MODEL_PATH = PROJECT_ROOT / "yolo11s_custom_ball.pt"
CAM0_ID = 0
CAM1_ID = 2

# Verify imports
sys.path.append(str(PROJECT_ROOT / "src"))
try:
    from core.hybrid_goal_detector import Triangulator, Detection3D
except ImportError:
    # Minimal Triangulator if import fails or path issues
    print("[WARN] Could not import Triangulator. Using local minimal version.")
    class Triangulator:
        def __init__(self): self.projection_matrices = {}
        def add_camera(self, cam_id, K, extrinsics):
            R, t = extrinsics[:3, :3], extrinsics[:3, 3]
            self.projection_matrices[cam_id] = K @ np.hstack([R, t.reshape(3,1)])
        def triangulate(self, obs):
            if len(obs) < 2: return None
            A = []
            for cam_id, (x, y) in obs.items():
                P = self.projection_matrices.get(cam_id)
                if P is None: continue
                A.append(x * P[2] - P[0])
                A.append(y * P[2] - P[1])
            if len(A) < 4: return None
            _, _, Vt = np.linalg.svd(np.array(A))
            X = Vt[-1]
            return X[:3] / X[3]

def load_calibration(cal_file):
    with open(cal_file, 'r') as f:
        data = json.load(f)
    return data

def main():
    print(f"--- 3D Verification Tool ---")
    print(f"Calibration: {CAL_FILE}")
    
    # 1. Load Cal
    cal_data = load_calibration(CAL_FILE)
    triangulator = Triangulator()
    
    # Setup Cameras in Triangulator
    # JSON has "cam_0" and "cam_2" keys
    cam0_key = f"cam_{CAM0_ID}"
    cam1_key = f"cam_{CAM1_ID}"
    
    # helper to parse JSON arrays to numpy
    def to_np(arr): return np.array(arr)
    
    # Cam 0 (Reference)
    c0 = cal_data[cam0_key]
    K0 = to_np(c0["K"])
    # Extrinsics in JSON are R, T. Construct 4x4
    E0 = np.eye(4)
    E0[:3, :3] = to_np(c0["R"])
    E0[:3, 3] = to_np(c0["T"]).flatten()
    # Note: hybrid_goal_detector expects WORLD-TO-CAMERA for add_camera?
    # Let's check logic: P = K @ [R|t]. Usually [R|t] transforms World -> Camera.
    # Our calibration_offline produced: R_1to0, T_1to0.
    # This transforms points in Cam1 to Cam0.
    # If we treat Cam0 as World Origin (World = Cam0), then:
    # Cam0 Extrinsics: Identity. (World->Cam0 is Identity)
    # Cam1 Extrinsics: R_1to0, T_1to0 ?? OR Inverse?
    # P_cam1 = K1 * [R_w2c | T_w2c] * P_world
    # If P_world = P_cam0.
    # We want P_cam1 coordinates.
    # We know P_cam0 = R_1to0 * P_cam1 + T_1to0 (from offline calc)
    # So P_cam1 = R_1to0^T * (P_cam0 - T_1to0)
    # P_cam1 = R_1to0^T * P_world - R_1to0^T * T_1to0
    # So R_w2c = R_1to0^T, T_w2c = -R_1to0^T * T_1to0.
    
    # Wait, let's verify `calibration_extrinsics_offline.py` output.
    # It saved out_data[cam_1]["R"] = R_1to0.
    # This matrix P0 = R * P1 + T.
    # So it converts P1 (Cam 2) -> P0 (Cam 0).
    # If World = Cam 0.
    # Then P_world = P0.
    # We need matrix that converts P_world -> P1 (Cam 2).
    # P1 = R^T * (P0 - T) = R^T * P0 - R^T * T.
    # So for Cam 2, Extrinsics matrix should be:
    # R_ext = R_1to0.T
    # T_ext = -R_1to0.T @ T_1to0
    
    # HOWEVER, `hybrid_goal_detector.py` usually expects standard matrices.
    # Let's check `_load_camera_calibration` in `hybrid_goal_detector.py`.
    # It reads "R" and "T" directly and passes to `add_camera`.
    # `add_camera` computes P = K @ [R|t].
    # So `hybrid_goal_detector` assumes the JSON contains World-to-Camera matrices?
    # If so, my offline calibration script might have saved Camera-to-World (or relative).
    # offline script saved: R = R_1to0, T = T_1to0.
    # Which is Cam2 -> Cam0.
    # If World=Cam0, then Cam2->World is R, T? No, Cam2->Cam0 is R,T.
    # World->Cam2 is inverse.
    # I MUST INVERT IT for proper projection if logic assumes P = K[R|t] (World->Cam).
    
    # Inverting for Cam 1 (ID 2):
    R_rel = to_np(cal_data[cam1_key]["R"])
    T_rel = to_np(cal_data[cam1_key]["T"])
    
    R_inv = R_rel.T
    T_inv = -R_inv @ T_rel
    
    E1 = np.eye(4)
    E1[:3, :3] = R_inv
    E1[:3, 3] = T_inv.flatten()
    
    triangulator.add_camera(CAM0_ID, K0, E0)      # Cam 0 (World Origin)
    triangulator.add_camera(CAM1_ID, to_np(cal_data[cam1_key]["K"]), E1) # Cam 2 (Inverted Rel)

    print("Loaded Calibration.")

    # 2. Init Cameras
    cap0 = cv2.VideoCapture(CAM0_ID)
    cap1 = cv2.VideoCapture(CAM1_ID)
    
    for c in [cap0, cap1]:
        c.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    
    # 3. Init YOLO
    model = YOLO(MODEL_PATH)

    print("\n--- 3D Tracking Started ---")
    print("Show ball to BOTH cameras. Press 'q' to quit.")

    while True:
        ret0, frame0 = cap0.read()
        ret1, frame1 = cap1.read()
        
        if not ret0 or not ret1:
            print("Frame error")
            break
            
        # Detect
        results0 = model(frame0, verbose=False, stream=False, conf=0.4)
        results1 = model(frame1, verbose=False, stream=False, conf=0.4)
        
        obs = {}
        
        # Parse Cam 0
        boxes0 = results0[0].boxes
        if len(boxes0) > 0:
            # Take highest conf
            box = boxes0[0]
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            cx, cy = (x1+x2)/2, (y1+y2)/2
            obs[CAM0_ID] = (cx, cy)
            # Visualize
            cv2.rectangle(frame0, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            
        # Parse Cam 1
        boxes1 = results1[0].boxes
        if len(boxes1) > 0:
            box = boxes1[0]
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            cx, cy = (x1+x2)/2, (y1+y2)/2
            obs[CAM1_ID] = (cx, cy)
            cv2.rectangle(frame1, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            
        # Triangulate
        pos_str = "No Fix"
        if len(obs) == 2:
            try:
                # Need to implement simple triangulate if minimal class used
                # If using real class, it returns Detection3D object
                res = triangulator.triangulate(obs)
                
                pt = None
                if hasattr(res, 'position'): # Real class
                     pt = res.position
                elif isinstance(res, np.ndarray): # Minimal class
                     pt = res
                     
                if pt is not None:
                    # Convert to mm
                    X, Y, Z = pt
                    dist = np.linalg.norm(pt)
                    pos_str = f"X:{X:.0f} Y:{Y:.0f} Z:{Z:.0f} D:{dist:.0f}"
                    
                    # Log for user
                    # print(f"3D: {pos_str}")
            except Exception as e:
                print(e)
        
        # Display
        vis0 = cv2.resize(frame0, (640, 360))
        vis1 = cv2.resize(frame1, (640, 360))
        
        cv2.putText(vis0, f"Cam {CAM0_ID}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
        cv2.putText(vis1, f"Cam {CAM1_ID}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
        
        combined = np.hstack([vis0, vis1])
        status = np.zeros((100, 1280, 3), dtype=np.uint8)
        cv2.putText(status, f"3D POS (mm): {pos_str}", (50, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 255), 3)
        
        final = np.vstack([combined, status])
        cv2.imshow("3D Triangulation Verify", final)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap0.release()
    cap1.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
