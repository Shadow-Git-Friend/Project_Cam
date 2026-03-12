
import cv2
import numpy as np
import json
import time
import sys
import os
from pathlib import Path
from ultralytics import YOLO

# --- CONFIG ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

# Paths
CAL_FILE = PROJECT_ROOT / "cal" / "calibration_full.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "motion_capture_data.json"
BALL_MODEL_PATH = PROJECT_ROOT / "data" / "models" / "yolo11s_custom_ball.pt"

# Cameras (calibrated pair)
CAM_IDS = [0, 2] 
CAM_NAMES = ["cam0", "cam2"] # Must match keys in calibration_full.json logic (cam_0, cam_2)

# --- IMPORTS ---
try:
    from core.hybrid_goal_detector import Triangulator, Detection3D
except ImportError:
    print("[ERROR] perform 'mv src/core/hybrid_goal_detector.py src/core/hybrid_raw.py' if needed")
    # Fallback to local definition if import issues
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

# Check MMPOSE
MMPOSE_AVAILABLE = False
try:
    from mmpose.apis import MMPoseInferencer
    MMPOSE_AVAILABLE = True
    print("[INFO] MMPose available. Human tracking enabled.")
except ImportError:
    print("[WARN] MMPose NOT found. Only Ball tracking will be recorded.")

# --- UTILS ---
def load_calibration(cal_file, triangulator):
    with open(cal_file, 'r') as f:
        data = json.load(f)
        
    for cam_id in CAM_IDS:
        key = f"cam_{cam_id}"
        if key not in data:
            print(f"[ERROR] Camera {cam_id} not in {cal_file}")
            continue
            
        c_data = data[key]
        K = np.array(c_data["K"])
        
        # INVERT EXTRINSICS logic (same as verify_3d.py)
        # JSON has R, T representing Cam -> World (or Relative)
        # We need World -> Cam for P = K[R|t]
        
        # NOTE: For Cam 0 (Ref), it's identity, so inverse is identity.
        # For Cam 2, if it's relative Cam2->Cam0, we need to invert it to get P_w -> P_c2
        
        R_raw = np.array(c_data["R"])
        T_raw = np.array(c_data["T"])
        
        R_inv = R_raw.T
        T_inv = -R_inv @ T_raw
        
        E = np.eye(4)
        E[:3, :3] = R_inv
        E[:3, 3] = T_inv.flatten()
        
        triangulator.add_camera(cam_id, K, E)
        print(f"[OK] Loaded Cam {cam_id}")

def get_ball_detections(model, frames):
    # Batch inference
    results = model(frames, verbose=False, conf=0.4, stream=False)
    detections = []
    for res in results:
        boxes = res.boxes
        if len(boxes) > 0:
            best_idx = np.argmax(boxes.conf.cpu().numpy())
            x1, y1, x2, y2 = boxes.xyxy[best_idx].cpu().numpy()
            conf = float(boxes.conf[best_idx].cpu().numpy())
            cx, cy = (x1+x2)/2, (y1+y2)/2
            # Return full box for visualization
            detections.append((x1, y1, x2, y2, cx, cy, conf))
        else:
            detections.append(None)
    return detections

def main():
    print("--- 3D Recorder (2 Cameras) ---")
    
    # 1. Setup
    triangulator = Triangulator()
    load_calibration(CAL_FILE, triangulator)
    
    ball_model = YOLO(BALL_MODEL_PATH)
    
    pose_model = None
    if MMPOSE_AVAILABLE:
        # Use lightweight model for speed if possible, else default
        try:
            pose_model = MMPoseInferencer(pose2d='rtmpose-m_8xb256-420e-coco-256x192', det_model='rtmdet-m', device='cuda')
        except Exception as e:
            print(f"[WARN] Could not load specific RTMPose model: {e}")
            print("[INFO] Falling back to default 'human' model...")
            try:
                pose_model = MMPoseInferencer(pose2d='human', device='cuda')
            except Exception as e2:
                print(f"[ERROR] Could not load MMPose 'human' model: {e2}")
                pose_model = None

    caps = []
    for cid in CAM_IDS:
        cap = cv2.VideoCapture(cid)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280) # Use 720p for speed/storage balance? Or 1080p
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720) # Legacy script used 704x576 (PAL?) - let's use HD
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        caps.append(cap)
        
    recorded_data = [] # List of frame dictionaries
    is_recording = False
    
    print("\n[READY] Press 'R' to toggle Record, 'Q' to Quit.")
    
    while True:
        frames = []
        for cap in caps:
            ret, frame = cap.read()
            if not ret: frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            frames.append(frame)
            
        vis_frames = [f.copy() for f in frames]
        
        # 2. Detect
        balls = get_ball_detections(ball_model, frames)
        
        skeletons = [None] * len(frames)
        if pose_model:
             # Generator output for batch
             res_gen = pose_model(frames, return_vis=False, batch_size=len(frames))
             # Convert generator to list to get results
             try:
                 results = list(res_gen)
                 for i, res in enumerate(results):
                     preds = res['predictions']
                     if preds:
                         # Extract keypoints
                         item = preds[0]
                         if isinstance(item, list): item = item[0] # handle batch nesting
                         
                         kpts = np.array(item['keypoints'])
                         scores = np.array(item['keypoint_scores'])
                         
                         # Ensure consistent shape (17, 3)
                         if len(kpts) > 17: kpts = kpts[:17]
                         if len(scores) > 17: scores = scores[:17]
                         
                         # Stack to make (x, y, score)
                         kpts_combined = np.hstack([kpts, scores.reshape(-1, 1)])
                         skeletons[i] = kpts_combined
             except Exception as e:
                 pass
                 
        # 3. Vis & Triangulate
        current_frame_data = {"ball": None, "joints": []}
        
        # Draw Ball
        ball_obs = {}
        for i, val in enumerate(balls):
            if val:
                # Unpack extended tuple
                x1, y1, x2, y2, cx, cy, conf = val
                
                # Draw Box
                cv2.rectangle(vis_frames[i], (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 2)
                # Draw Center
                cv2.circle(vis_frames[i], (int(cx), int(cy)), 5, (0, 0, 255), -1)
                # Draw Text
                cv2.putText(vis_frames[i], f"BALL: {conf:.2f}", (int(x1), int(y1)-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                           
                ball_obs[CAM_IDS[i]] = (cx, cy)
                
        # Triangulate Ball
        if len(ball_obs) >= 2:
            try:
                pt_ball = triangulator.triangulate(ball_obs)
                if pt_ball is not None:
                     # Handle return type (Detection3D object or array)
                     if hasattr(pt_ball, 'position'): pt_ball = pt_ball.position
                     current_frame_data["ball"] = pt_ball.tolist() # in mm?
                     
                     # Draw 3D text
                     for vf in vis_frames:
                         cv2.putText(vf, "3D BALL OK", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            except Exception: pass

        # Draw Skeleton (Optional) & Triangulate
        if pose_model:
            # We have detections in 'skeletons' list [kpts_cam0, kpts_cam1]
            # kpts shape: (17, 3) -> x, y, score
            
            # Prepare data structure for all 17 joints
            joints_3d = []
            
            for j_idx in range(17):
                obs_j = {}
                # Collect valid observations for this joint from both cameras
                for c_idx, kpts in enumerate(skeletons):
                    if kpts is not None:
                        # Safety check for index
                        if j_idx < len(kpts):
                            x, y, score = kpts[j_idx]
                            if score > 0.4: # Low confidence threshold
                                obs_j[CAM_IDS[c_idx]] = (x, y)
                                
                # Triangulate if we have 2 views
                pt_joint = None
                if len(obs_j) >= 2:
                    try:
                        res = triangulator.triangulate(obs_j)
                        if res is not None:
                            if hasattr(res, 'position'): pt_joint = res.position.tolist()
                            else: pt_joint = res.tolist()
                    except: pass
                
                joints_3d.append(pt_joint)
            
            current_frame_data["joints"] = joints_3d

            # Draw 2D skeletons for feedback
            for i, k in enumerate(skeletons):
                if k is not None:
                    # Draw connections
                    CONNECTIONS = [(5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), (12, 14), (14, 16), (5, 6), (11, 12)]
                    for s, e in CONNECTIONS:
                        if s < len(k) and e < len(k) and k[s][2]>0.4 and k[e][2]>0.4:
                            p1 = (int(k[s][0]), int(k[s][1]))
                            p2 = (int(k[e][0]), int(k[e][1]))
                            cv2.line(vis_frames[i], p1, p2, (0, 255, 0), 2)
                            
                    for pt in k:
                         if pt[2] > 0.4:
                            cv2.circle(vis_frames[i], (int(pt[0]), int(pt[1])), 4, (0, 0, 255), -1)

        # UI
        grid = np.hstack(vis_frames)
        scale = 0.5
        grid_small = cv2.resize(grid, (0,0), fx=scale, fy=scale)
        
        if is_recording:
            cv2.putText(grid_small, f"REC: {len(recorded_data)}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            recorded_data.append(current_frame_data)
        
        cv2.imshow("3D Recorder", grid_small)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            is_recording = not is_recording
            if is_recording:
                print("Recording STARTED")
                recorded_data = []
            else:
                print(f"Recording STOPPED. Captured {len(recorded_data)} frames.")

    # Save
    if recorded_data:
        print(f"Saving {len(recorded_data)} frames to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(recorded_data, f, indent=4)
        print("Save Complete.")

    for c in caps: c.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
