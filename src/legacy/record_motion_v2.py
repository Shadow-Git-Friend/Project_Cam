import cv2
import numpy as np
import json
import time
import sys
from pathlib import Path

# --- PATH SETUP ---
CURRENT_FILE = Path(__file__).resolve()
SRC_DIR = CURRENT_FILE.parent
PROJECT_ROOT = SRC_DIR.parent
sys.path.append(str(SRC_DIR))

# --- IMPORT NEW MATH (V2) ---
# We import from the new files you copied
try:
    from triangulate_v2 import triangulate_point, build_projection_matrices
    from calibration_utils import load_all_intrinsics, load_extrinsics
except ImportError as e:
    print(f"[CRITICAL ERROR] Missing v2 files: {e}")
    print("Did you run: cp ~/Downloads/3d_projection_aza/calibration_utils.py src/?")
    sys.exit(1)

# --- SETTINGS ---
# IMPORTANT: Use the string names that match your colleague's JSON files
CAM_NAME_1 = "cam0" 
CAM_NAME_2 = "cam6"

CAM_ID_1 = 0
CAM_ID_2 = 6

OUTPUT_FILE = PROJECT_ROOT / "motion_capture_data_v2.json" # Saved as v2 data

# Path to the NEW calibration folder
CALIB_DIR = PROJECT_ROOT / "cal" / "calibration_v2"
EXTRINSICS_FILE = CALIB_DIR / "extrinsics.json"

# --- IMPORT RTMPose ---
try:
    from mmpose.apis import MMPoseInferencer
except ImportError:
    print("[CRITICAL ERROR] MMPose not installed!")
    sys.exit(1)

POSE_MODEL = 'rtmpose-m_8xb256-420e-coco-256x192' 
DET_MODEL = 'rtmdet-m' 

# Colors
GREEN = (0, 255, 0)
RED = (0, 0, 255)

def init_rtmpose():
    print(f"[INFO] Loading RTMPose ({POSE_MODEL})...")
    try:
        inferencer = MMPoseInferencer(pose2d=POSE_MODEL, det_model=DET_MODEL, device='cuda')
    except Exception:
        print("[INFO] Fallback to 'human' alias...")
        inferencer = MMPoseInferencer(pose2d='human', device='cuda')
    return inferencer

def get_keypoints_rtmpose(inferencer, frame):
    result_generator = inferencer(frame, return_vis=False)
    try:
        result = next(result_generator)
    except StopIteration:
        return None
    
    predictions = result['predictions']
    if not predictions: return None
        
    first_item = predictions[0]
    if isinstance(first_item, list):
        if not first_item: return None
        person = first_item[0]
    else:
        person = first_item
        
    if not isinstance(person, dict):
        try: person = person.to_dict()
        except: return None

    try:
        kpts = np.array(person['keypoints'])
        scores = np.array(person['keypoint_scores'])
    except KeyError:
        return None
    
    if len(kpts) > 17:
        kpts = kpts[:17]
        scores = scores[:17]
    
    # (17, 3) format: [x, y, conf]
    return np.hstack([kpts, scores.reshape(-1, 1)])

def draw_skeleton(frame, kpts, color):
    if kpts is None: return
    connections = [(5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), (12, 14), (14, 16), (5, 6), (11, 12)]
    for kp in kpts:
        if kp[2] > 0.4: cv2.circle(frame, (int(kp[0]), int(kp[1])), 4, color, -1)
    for i, j in connections:
        if i < len(kpts) and j < len(kpts) and kpts[i][2] > 0.4 and kpts[j][2] > 0.4:
            cv2.line(frame, (int(kpts[i][0]), int(kpts[i][1])), (int(kpts[j][0]), int(kpts[j][1])), color, 2)

def is_good_detection(kpts, conf_thresh=0.5, min_kpts=6):
    if kpts is None: return False
    return np.sum(kpts[:, 2] > conf_thresh) >= min_kpts

def main():
    # 1. SETUP V2 CALIBRATION
    if not CALIB_DIR.exists():
        print(f"[ERROR] Calibration dir not found: {CALIB_DIR}")
        return

    print(f"[INFO] Loading V2 Calibration from {CALIB_DIR}...")
    try:
        intrinsics_map = load_all_intrinsics(CALIB_DIR)
        extrinsics = load_extrinsics(EXTRINSICS_FILE)
        
        # Get reference camera (usually cam0)
        ref_cam = extrinsics[next(iter(extrinsics))].reference
        print(f"[INFO] Reference Camera: {ref_cam}")
        
        # Pre-calculate Projection Matrices (P)
        projections = build_projection_matrices(intrinsics_map, extrinsics, ref_cam)
        
        # Check if we have matrices for our active cameras
        if CAM_NAME_1 not in projections or CAM_NAME_2 not in projections:
            print(f"[ERROR] Missing calibration for {CAM_NAME_1} or {CAM_NAME_2}")
            print(f"Available cameras: {list(projections.keys())}")
            return
            
        P1 = projections[CAM_NAME_1]
        P2 = projections[CAM_NAME_2]
        print("[SUCCESS] Projection Matrices Built!")
        
    except Exception as e:
        print(f"[ERROR] Calibration load failed: {e}")
        return

    # 2. INIT AI
    rtmpose = init_rtmpose()
    
    # 3. CAMERAS
    cap1 = cv2.VideoCapture(CAM_ID_1)
    cap2 = cv2.VideoCapture(CAM_ID_2)
    for c in [cap1, cap2]:
        c.set(cv2.CAP_PROP_FRAME_WIDTH, 704)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 576)

    recorded_frames = []
    is_recording = False
    
    print(f"\n[READY] System V2 Live. Press 'R' to Record.")

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()
        if not ret1 or not ret2: break

        vis1 = frame1.copy()
        vis2 = frame2.copy()
        
        kpts1 = get_keypoints_rtmpose(rtmpose, frame1)
        kpts2 = get_keypoints_rtmpose(rtmpose, frame2)
        
        valid1 = is_good_detection(kpts1)
        valid2 = is_good_detection(kpts2)
        user_visible = valid1 and valid2
        
        status_color = GREEN if user_visible else RED
        
        draw_skeleton(vis1, kpts1, status_color)
        draw_skeleton(vis2, kpts2, status_color)
        
        cv2.rectangle(vis1, (0,0), (704,576), status_color, 4)
        cv2.rectangle(vis2, (0,0), (704,576), status_color, 4)

        if is_recording:
            cv2.circle(vis1, (30, 30), 15, RED, -1)
            cv2.putText(vis1, f"REC: {len(recorded_frames)}", (60, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, RED, 2)
            
            frame_data = {"joints": []}
            
            if user_visible:
                for i in range(17):
                    pt1 = kpts1[i] # [x, y, conf]
                    pt2 = kpts2[i]
                    
                    if pt1[2] > 0.5 and pt2[2] > 0.5:
                        # --- V2 TRIANGULATION LOGIC ---
                        # triangulate_point expects list of tuples: (P, u, v)
                        measurements = [
                            (P1, pt1[0], pt1[1]),
                            (P2, pt2[0], pt2[1])
                        ]
                        # Returns np.array([X, Y, Z])
                        p3d = triangulate_point(measurements)
                        
                        # Convert meters to mm if needed (colleague's code likely outputs meters)
                        # Usually formal calibration outputs METERS. 
                        # We multiply by 1000 to keep compatibility with our renderer (mm)
                        p3d_mm = p3d * 1000.0 
                        
                        frame_data["joints"].append(p3d_mm.tolist())
                    else:
                        frame_data["joints"].append(None)
            else:
                frame_data["joints"] = [None] * 17
            
            recorded_frames.append(frame_data)

        # Controls
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        if key == ord('r'):
            if not user_visible and not is_recording:
                print("[WARN] Low visibility.")
            else:
                is_recording = not is_recording
                if is_recording: recorded_frames = []
                else: print(f"[STOP] Saved {len(recorded_frames)} frames.")

        cv2.imshow("Recorder V2 (New Calibration)", np.hstack((vis1, vis2)))

    if recorded_frames:
        print(f"[INFO] Saving {len(recorded_frames)} frames to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(recorded_frames, f)
        print("[SUCCESS] Saved.")

    cap1.release()
    cap2.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()