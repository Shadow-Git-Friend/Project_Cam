
import cv2
import numpy as np
import json
import os
import sys
from pathlib import Path

# Setup Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

# CONFIG
CAL_FILE = PROJECT_ROOT / "cal" / "calibration_full.json"
OUTPUT_FILE = PROJECT_ROOT / "cal" / "goal_config.json"
CAM0_ID = 0
CAM1_ID = 2

# CORNER NAMES
CORNERS = ["Top-Left", "Top-Right", "Bottom-Right", "Bottom-Left"]

class GoalCalibrator:
    def __init__(self):
        self.cal_data = self.load_calibration(CAL_FILE)
        self.points_cam0 = [] # [(x,y), ...]
        self.points_cam1 = [] 
        self.current_cam_points = [] # Temp list for active window
        self.img_cache = None

    def load_calibration(self, cal_file):
        with open(cal_file, 'r') as f:
            return json.load(f)

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.current_cam_points) < 4:
                self.current_cam_points.append((x, y))
                print(f"Clicked: {CORNERS[len(self.current_cam_points)-1]} at ({x}, {y})")

    def capture_points(self, cam_id, win_name, target_list):
        print(f"\n--- Capturing Camera {cam_id} ---")
        cap = cv2.VideoCapture(cam_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        
        cv2.namedWindow(win_name)
        cv2.setMouseCallback(win_name, self.mouse_callback)
        self.current_cam_points = []
        
        frozen_frame = None
        
        while True:
            if frozen_frame is None:
                ret, frame = cap.read()
                if not ret: 
                    print("Failed to read camera")
                    break
                vis = frame.copy()
            else:
                vis = frozen_frame.copy()
                
            # Draw captured points
            for i, pt in enumerate(self.current_cam_points):
                cv2.circle(vis, pt, 5, (0, 255, 0), -1)
                cv2.putText(vis, f"{i+1}:{CORNERS[i]}", (pt[0]+10, pt[1]), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # Instructions
            if len(self.current_cam_points) < 4:
                msg = f"Click {CORNERS[len(self.current_cam_points)]}"
                col = (0, 255, 255)
            else:
                msg = "Done! Press SPACE to confirm, R to reset"
                col = (0, 255, 0)
                
            cv2.putText(vis, msg, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, col, 2)
            cv2.putText(vis, "SPACE=Freeze/Confirm, R=Reset", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
            
            cv2.imshow(win_name, vis)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Quit.")
                sys.exit(0)
            elif key == ord(' '):
                if frozen_frame is None:
                    frozen_frame = frame # Freeze to make clicking easier
                    print("Frame Frozen. Click points now.")
                elif len(self.current_cam_points) == 4:
                    # Confirm
                    target_list.extend(self.current_cam_points)
                    break
            elif key == ord('r'):
                self.current_cam_points = []
                frozen_frame = None
                print("Reset.")

        cap.release()
        cv2.destroyWindow(win_name)
        
    def triangulate(self):
        print("\nTriangulating...")
        
        # Prepare Projection Matrices
        def get_P(cam_id):
            c = self.cal_data[f"cam_{cam_id}"]
            K = np.array(c["K"])
            R = np.array(c["R"])
            T = np.array(c["T"])
            
            # Calibration JSON stores R, T relative to Cam 0? Or World?
            # Assuming Cam 0 is World Origin (Identity)
            # And Cam 2 is relative to Cam 0.
            # Usually: Cam0: R=I, T=0. Cam2: R=R_rel, T=T_rel.
            # But earlier we INVERTED them for Triangulator class.
            
            # Let's check format. K, R, T.
            # Basic Triangulation Formula: x = P X
            # P = K [R|t]   (World -> Cam projection)
            
            # In our verify_3d.py, we did:
            # R_inv = R.T, T_inv = -R.T @ T
            # Because we assumed JSON R,T was Cam -> World (Extrinsics as Pose).
            # BUT standard calibration (like opencv stereoCalibrate) returns R, T as Transform from Cam1 to Cam2.
            # Let's assume the JSON follows standard Opencv Stereo format?
            # NO, we generated it from individual intrinsics + stereo cal.
            # Let's stick to the logic used in verify_3d.py which works.
            
            # Logic from verify_3d.py:
            # R_raw, T_raw from JSON.
            # R_inv = R_raw.T
            # T_inv = -R_inv @ T_raw
            # P = K @ [R_inv | T_inv]
            
            R_inv = R.T
            T_inv = -R.T @ T
            Rt = np.hstack([R_inv, T_inv.reshape(3,1)])
            P = K @ Rt
            return P

        P0 = get_P(CAM0_ID)
        P1 = get_P(CAM1_ID)
        
        points_3d = []
        for i in range(4):
            pts_cam0 = np.array(self.points_cam0[i], dtype=float)
            pts_cam1 = np.array(self.points_cam1[i], dtype=float)
            
            # DLT Triangulation
            # A = [x0 P0^3 - P0^1; y0 P0^3 - P0^2; ...]
            A = []
            A.append(pts_cam0[0] * P0[2] - P0[0])
            A.append(pts_cam0[1] * P0[2] - P0[1])
            A.append(pts_cam1[0] * P1[2] - P1[0])
            A.append(pts_cam1[1] * P1[2] - P1[1])
            A = np.array(A)
            
            _, _, Vt = np.linalg.svd(A)
            X = Vt[-1]
            X = X[:3] / X[3] # Dehomogenize
            points_3d.append(X.tolist())
            print(f"{CORNERS[i]}: {X}")
            
        return points_3d

    def save(self, points_3d):
        out_data = {
            "goal_name": "Standard Goal (Manual Click)",
            "corners": {
                "top_left": points_3d[0],
                "top_right": points_3d[1],
                "bottom_right": points_3d[2],
                "bottom_left": points_3d[3]
            }
        }
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(out_data, f, indent=4)
        print(f"\n[SUCCESS] Goal Config saved to {OUTPUT_FILE}")

def main():
    print("--- Manual Goal Calibration (Click Method) ---")
    cal = GoalCalibrator()
    
    # Cam 0
    cal.capture_points(CAM0_ID, "Camera 0 - Click Goal Corners", cal.points_cam0)
    
    # Cam 1
    cal.capture_points(CAM1_ID, "Camera 1 - Click Goal Corners", cal.points_cam1)
    
    if len(cal.points_cam0) == 4 and len(cal.points_cam1) == 4:
        points_3d = cal.triangulate()
        cal.save(points_3d)
    else:
        print("Calibration Incomplete")

if __name__ == "__main__":
    main()
