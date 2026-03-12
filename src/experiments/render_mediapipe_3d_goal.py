
import json
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from pathlib import Path
import os
import sys
import mediapipe as mp

# Topologies
MP_POSE_CONNECTIONS = mp.solutions.holistic.POSE_CONNECTIONS
MP_HAND_CONNECTIONS = mp.solutions.holistic.HAND_CONNECTIONS

# --- CONFIG ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "data_3d_mediapipe.json"
GOAL_FILE = PROJECT_ROOT / "cal" / "goal_config.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "frames" / "render_output_mediapipe_goal"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FINAL_FPS = 30
ZOOM = 1000 # Base zoom

class GoalDetector:
    def __init__(self, corners):
        self.corners = np.array(corners)
        self.goal_trigger = False
        
        # Plane Logic
        v1 = self.corners[1] - self.corners[0]
        v2 = self.corners[3] - self.corners[0]
        self.normal = np.cross(v1, v2)
        self.normal = self.normal / np.linalg.norm(self.normal)
        self.origin = self.corners[0]
        
        # Projection Axes
        self.u_axis = v1 / np.linalg.norm(v1)
        self.v_axis = v2 / np.linalg.norm(v2)
        self.width = np.linalg.norm(v1)
        self.height = np.linalg.norm(v2)
        
        print(f"[GOAL PHYSICS] Plane Normal: {self.normal}, Size: {self.width:.0f}x{self.height:.0f}")

    def check_intersection(self, p1, p2):
        ray_vec = p2 - p1
        ray_len = np.linalg.norm(ray_vec)
        if ray_len < 1e-6: return None
        ray_dir = ray_vec / ray_len
        
        denom = np.dot(self.normal, ray_dir)
        if abs(denom) < 1e-6: return None
            
        t = np.dot(self.origin - p1, self.normal) / denom
        
        if 0 <= t <= ray_len:
            return p1 + t * ray_dir
        return None

    def is_in_goal(self, point):
        vec = point - self.origin
        u_proj = np.dot(vec, self.u_axis)
        v_proj = np.dot(vec, self.v_axis)
        return (0 <= u_proj <= self.width) and (0 <= v_proj <= self.height)

    def process_frame(self, frame_idx, p_prev, p_curr):
        if self.goal_trigger: return True 
        if p_prev is None or p_curr is None: return False
        if np.isnan(p_prev).any() or np.isnan(p_curr).any(): return False
            
        intersection = self.check_intersection(p_prev, p_curr)
        if intersection is not None:
            if self.is_in_goal(intersection):
                print(f"[GOAL!] Detected at Frame {frame_idx} | Point: {intersection}")
                self.goal_trigger = True
                return True
        return False

def compute_rotation_matrix(v_source, v_target):
    a = v_source / np.linalg.norm(v_source)
    b = v_target / np.linalg.norm(v_target)
    if np.allclose(a, b): return np.eye(3)
    v = np.cross(a, b)
    c = np.dot(a, b)
    s = np.linalg.norm(v)
    if s < 1e-6: return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    R = np.eye(3) + vx + vx @ vx * ((1 - c) / (s ** 2))
    return R

def apply_rot(pts, R):
    if not pts: return []
    arr = np.array(pts) # Nx3
    rot = arr @ R.T
    return rot.tolist()

def main():
    if not INPUT_FILE.exists():
        print(f"[ERROR] No data found at {INPUT_FILE}")
        return

    print("Loading data...")
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)

    # Note: MediaPipe data currently DOES NOT HAVE BALL TRACKING in the JSON usually
    # But for "Goal Detection" we need a ball.
    # The user's prompt implies "record a video... me, ball and a goal".
    # The existing `test_mediapipe.py` output (data_3d_mediapipe.json) ONLY contains Body/Hand/Face.
    # It does NOT have ball data.
    
    # CRITICAL: We need Ball Data for Goal Detection.
    # Approach: Import the ball trajectory from `motion_capture_data.json` (Core Data) and map it here?
    # Assuming frames are synchronized/same video.
    # The `data_3d_mediapipe.json` came from `cam4_...mp4` and `cam2_...mp4`.
    # The `motion_capture_data.json` came from LIVE capture.
    # They might NOT be frame-synced if recorded separately.
    
    # HOWEVER: The user asked to "test both... render_3d_full.py... and mediapipe".
    # If the MediaPipe data has no ball, I cannot do goal detection on it.
    # I will attempt to load the ball from `motion_capture_data.json` as a fallback
    # assuming the USER intended to compare them on the SAME event.
    
    traj_ball = None
    CORE_FILE = PROJECT_ROOT / "data" / "processed" / "motion_capture_data.json"
    if CORE_FILE.exists():
        print("[INFO] Loading Ball Data from Core JSON (Assuming Sync)")
        with open(CORE_FILE, 'r') as f:
            core_data = json.load(f)
            # Extract ball
            b_list = []
            for fr in core_data:
                b = fr.get("ball")
                if b: b_list.append(b)
                else: b_list.append([np.nan, np.nan, np.nan])
            traj_ball = np.array(b_list)
            
            # Match lengths
            if len(traj_ball) > len(data): traj_ball = traj_ball[:len(data)]
            if len(traj_ball) < len(data):
                # Pad
                pad = np.full((len(data)-len(traj_ball), 3), np.nan)
                traj_ball = np.vstack([traj_ball, pad])
    else:
        print("[WARN] No Ball Data found! Goal detection will not trigger.")
        traj_ball = np.full((len(data), 3), np.nan)
        
    print(f"Processing {len(data)} frames with MediaPipe + Goal...")
    plt.style.use('dark_background')
    
    # Load Goal
    goal_pts_raw = None
    if GOAL_FILE.exists():
        with open(GOAL_FILE, 'r') as f:
            gd = json.load(f)
            c = gd["corners"]
            goal_pts_raw = np.array([
                c["top_left"], c["top_right"], c["bottom_right"], c["bottom_left"]
            ])

    # --- 1. Auto-Alignment ---
    valid_up_vecs = []
    for frame in data:
        pose = frame.get("pose_3d")
        if pose and len(pose) > 24:
            try:
                p11, p12 = np.array(pose[11]), np.array(pose[12])
                p23, p24 = np.array(pose[23]), np.array(pose[24])
                vec = ((p11+p12)/2) - ((p23+p24)/2)
                valid_up_vecs.append(vec)
            except: pass
            
    if valid_up_vecs:
        avg_up = np.mean(valid_up_vecs, axis=0)
        R_align = compute_rotation_matrix(avg_up, np.array([0, 0, 1]))
    else:
        R_align = np.eye(3)

    # --- 2. Process & Rotate ---
    processed_data = []
    all_z_feet = []
    
    # Goal Align
    goal_pts_rot = None
    if goal_pts_raw is not None:
        goal_pts_rot = np.array(apply_rot(goal_pts_raw.tolist(), R_align))
        
    # Ball Align
    traj_ball_rot = np.array(apply_rot(traj_ball.tolist(), R_align))
    
    # Points Align
    for frame in data:
        new_frame = frame.copy()
        new_frame["pose_3d"] = apply_rot(frame.get("pose_3d"), R_align)
        new_frame["left_hand_3d"] = apply_rot(frame.get("left_hand_3d"), R_align)
        new_frame["right_hand_3d"] = apply_rot(frame.get("right_hand_3d"), R_align)
        new_frame["face_3d"] = apply_rot(frame.get("face_3d"), R_align) 
        
        pose = new_frame["pose_3d"]
        if pose and len(pose) > 32:
            feet_pts = [pose[29], pose[30], pose[31], pose[32]]
            for p in feet_pts: all_z_feet.append(p[2])
            
        processed_data.append(new_frame)
        
    # Floor Detection
    z_offset = 0
    if all_z_feet:
        floor_z = np.percentile(all_z_feet, 5)
        z_offset = -floor_z
        print(f"[FLOOR] Detected at Z={floor_z:.1f}, shift={z_offset:.1f}")
        
    # Apply Offset
    final_data = []
    all_pts_centered = []
    
    def shift_z(pts): 
        if not pts: return []
        return [[p[0], p[1], p[2] + z_offset] for p in pts]

    for frame in processed_data:
        frame["pose_3d"] = shift_z(frame["pose_3d"])
        frame["left_hand_3d"] = shift_z(frame["left_hand_3d"])
        frame["right_hand_3d"] = shift_z(frame["right_hand_3d"])
        frame["face_3d"] = shift_z(frame["face_3d"])
        if frame["pose_3d"]: all_pts_centered.extend(frame["pose_3d"])
        final_data.append(frame)

    traj_ball_rot[:, 2] += z_offset
    if goal_pts_rot is not None:
        goal_pts_rot[:, 2] += z_offset
        
    # Init Detector
    goal_detector = None
    if goal_pts_rot is not None:
        goal_detector = GoalDetector(goal_pts_rot)

    # Center
    cx, cy = 0, 0
    if all_pts_centered:
        arr = np.array(all_pts_centered)
        median = np.median(arr, axis=0)
        cx, cy = median[0], median[1]
        
    LIMIT = ZOOM
    if goal_pts_rot is not None:
         goal_c = np.mean(goal_pts_rot, axis=0)
         dist = np.linalg.norm(goal_c[:2] - np.array([cx, cy]))
         if dist > LIMIT: LIMIT = dist + 1000

    # Pre-calc Sphere
    u, v = np.mgrid[0:2*np.pi:10j, 0:np.pi:6j] 
    sphere_x = np.cos(u) * np.sin(v)
    sphere_y = np.sin(u) * np.sin(v)
    sphere_z = np.cos(v)
    
    # Ball Sphere
    b_rad = 110 / 1.5
    ball_x = b_rad * sphere_x
    ball_y = b_rad * sphere_y
    ball_z = b_rad * sphere_z

    goal_triggered = False

    # --- 3. Render ---
    for i, frame in enumerate(final_data):
        # Physics
        if goal_detector and not goal_triggered and i > 0:
            p_prev = traj_ball_rot[i-1]
            p_curr = traj_ball_rot[i]
            if goal_detector.process_frame(i, p_prev, p_curr):
                goal_triggered = True

        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')
        ax.set_box_aspect([1,1,1])
        ax.set_xlim(cx - LIMIT, cx + LIMIT)
        ax.set_ylim(cy - LIMIT, cy + LIMIT)
        ax.set_zlim(0, 2*LIMIT) 
        
        # Grid
        step = 500
        gx = np.arange(cx-LIMIT, cx+LIMIT+step, step)
        gy = np.arange(cy-LIMIT, cy+LIMIT+step, step)
        for val in gx: ax.plot([val,val], [cy-LIMIT, cy+LIMIT], [0,0], c='#222222', lw=0.8)
        for val in gy: ax.plot([cx-LIMIT, cx+LIMIT], [val,val], [0,0], c='#222222', lw=0.8)
        
        # Goal
        if goal_pts_rot is not None:
             g = goal_pts_rot
             order = [0,1,2,3,0]
             col = 'deepskyblue'
             if goal_triggered:
                 col = 'lime' if (i//2)%2==0 else 'white'
                 tm = (g[0]+g[1])/2
                 ax.text(tm[0], tm[1], tm[2]+300, "GOAL!", color='lime', fontsize=16, ha='center', weight='bold')
             ax.plot(g[order,0], g[order,1], g[order,2], c=col, lw=3)

        # Ball Trace
        st = max(0, i - FINAL_FPS)
        valid = ~np.isnan(traj_ball_rot[st:i+1, 0])
        pts = traj_ball_rot[st:i+1][valid]
        if len(pts)>1: ax.plot(pts[:,0], pts[:,1], pts[:,2], c='orange', lw=2)

        # Ball
        cb = traj_ball_rot[i]
        if not np.isnan(cb[0]):
             ax.plot_surface(ball_x+cb[0], ball_y+cb[1], ball_z+cb[2], color='yellow', alpha=0.9)

        # Robot
        def draw_sphere(pt, r, color):
            if pt is None or len(pt) < 3: return
            X = sphere_x * r + pt[0]
            Y = sphere_y * r + pt[1]
            Z = sphere_z * r + pt[2]
            ax.plot_surface(X, Y, Z, color=color, alpha=1.0, shade=True)

        def draw_robot(pts, conns, bone_col, joint_col, bw=2, jr=30):
            if not pts: return
            arr = np.array(pts)
            if len(arr)==0: return
            for s, e in conns:
                if s<len(pts) and e<len(pts):
                    p1, p2 = pts[s], pts[e]
                    ax.plot([p1[0],p2[0]], [p1[1],p2[1]], [p1[2],p2[2]], c=bone_col, lw=bw)
            for pt in arr: draw_sphere(pt, jr, joint_col)

        draw_robot(frame.get("pose_3d"), MP_POSE_CONNECTIONS, 'white', 'cyan', 4, 35)
        draw_robot(frame.get("left_hand_3d"), MP_HAND_CONNECTIONS, '#ff4444', '#ff8800', 2, 12)
        draw_robot(frame.get("right_hand_3d"), MP_HAND_CONNECTIONS, '#ff4444', '#ff8800', 2, 12)
        
        # Head
        pose = frame.get("pose_3d")
        if pose and len(pose)>0:
            draw_sphere(pose[0], 120, 'white')

        plt.savefig(OUTPUT_DIR / f"frame_{i:04d}.png")
        plt.close(fig)
        
        if i % 10 == 0:
            sys.stdout.write(f"\r{i}/{len(data)}")
            sys.stdout.flush()
            
    # Video
    print("\nEncoding video...")
    out_vid = PROJECT_ROOT / "output" / "videos" / "final_mediapipe_3d_goal.mp4"
    if out_vid.exists(): os.remove(out_vid)
    os.system(f"ffmpeg -y -framerate {FINAL_FPS} -i {OUTPUT_DIR}/frame_%04d.png -c:v libx264 -pix_fmt yuv420p {out_vid}")
    print(f"[SUCCESS] {out_vid}")

if __name__ == "__main__":
    main()
