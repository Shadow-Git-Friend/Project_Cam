
import json
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from pathlib import Path
import os
import sys

# --- CONFIG ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "motion_capture_data.json"
GOAL_FILE = PROJECT_ROOT / "cal" / "goal_config.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "frames" / "render_output_robot_goal_coco"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Tuning
VELOCITY_LIMIT_BALL = 800.0 # mm/frame
VELOCITY_LIMIT_HUMAN = 200.0 # mm/frame
SAVGOL_WINDOW = 5
FINAL_FPS = 15
ZOOM = 2000 # Base zoom

# Skeleton Map (COCO 17)
# 0:Nose, 1:LEye, 2:REye, 3:LEar, 4:REar, 5:LShoulder, 6:RShoulder
# 7:LElbow, 8:RElbow, 9:LWrist, 10:RWrist, 11:LHip, 12:RHip
# 13:LKnee, 14:RKnee, 15:LAnkle, 16:RAnkle
CONNECTIONS = [
    (5, 7), (7, 9), (6, 8), (8, 10), # Arms
    (11, 13), (13, 15), (12, 14), (14, 16), # Legs
    (5, 6), (11, 12), (5, 11), (6, 12), # Torso
    (0, 1), (0, 2), (1, 3), (2, 4) # Head
]

class GoalDetector:
    def __init__(self, corners):
        # Corners: Shape (4, 3) -> TL, TR, BR, BL
        self.corners = np.array(corners)
        self.goal_trigger = False
        self.goal_frame_idx = -1
        
        # Define Plane from first 3 points (TL, TR, BR)
        # Vector 1: TL -> TR
        v1 = self.corners[1] - self.corners[0]
        # Vector 2: TL -> BL
        v2 = self.corners[3] - self.corners[0]
        
        # Normal
        self.normal = np.cross(v1, v2)
        self.normal = self.normal / np.linalg.norm(self.normal)
        
        # Point on plane (TL)
        self.origin = self.corners[0]
        
        # Pre-calc bounding box for simpler "in-bounds" check on the 2D plane projection
        # Or just use logic: if intersection I, check dot products
        # Project I onto v1 and v2 directions
        self.u_axis = v1 / np.linalg.norm(v1)
        self.v_axis = v2 / np.linalg.norm(v2)
        
        self.width = np.linalg.norm(v1)
        self.height = np.linalg.norm(v2)
        
        print(f"[GOAL PHYSICS] Plane Normal: {self.normal}, Size: {self.width:.0f}x{self.height:.0f}")

    def check_intersection(self, p1, p2):
        # Ray-Plane Intersection
        # Line: P(t) = p1 + t * (p2 - p1)
        # Plane: dot(P - origin, normal) = 0
        
        ray_vec = p2 - p1
        ray_len = np.linalg.norm(ray_vec)
        if ray_len < 1e-6: return None
        
        ray_dir = ray_vec / ray_len
        
        denom = np.dot(self.normal, ray_dir)
        
        # Check if parallel (denom ~ 0)
        if abs(denom) < 1e-6:
            return None
            
        # Calc t
        # t = dot(origin - p1, normal) / dot(ray_dir, normal)
        t = np.dot(self.origin - p1, self.normal) / denom
        
        # Check if t is within the segment (0 <= t <= ray_len)
        if 0 <= t <= ray_len:
            # Intersection Point
            I = p1 + t * ray_dir
            return I
            
        return None

    def is_in_goal(self, point):
        # Check if point inside the rectangle (TL, TR, BR, BL)
        # Project vector (I - TL) onto u_axis (width) and v_axis (height)
        vec = point - self.origin
        
        u_proj = np.dot(vec, self.u_axis)
        v_proj = np.dot(vec, self.v_axis)
        
        # Check dimensions with slight margin?
        return (0 <= u_proj <= self.width) and (0 <= v_proj <= self.height)

    def process_frame(self, frame_idx, p_prev, p_curr):
        if self.goal_trigger: return True # Already detected
        
        if np.isnan(p_prev).any() or np.isnan(p_curr).any():
            return False
            
        intersection = self.check_intersection(p_prev, p_curr)
        if intersection is not None:
            if self.is_in_goal(intersection):
                print(f"[GOAL!] Detected at Frame {frame_idx} | Point: {intersection}")
                self.goal_trigger = True
                self.goal_frame_idx = frame_idx
                return True
                
        return False

class Processor:
    def __init__(self, data, key="ball"):
        self.num_frames = len(data)
        self.key = key
        
        if key == "ball":
            self.trajectory = np.full((self.num_frames, 1, 3), np.nan)
            for i, frame in enumerate(data):
                ball = frame.get("ball")
                if ball: self.trajectory[i, 0] = ball
        elif key == "joints":
            self.trajectory = np.full((self.num_frames, 17, 3), np.nan)
            for i, frame in enumerate(data):
                joints = frame.get("joints", [])
                for j, pt in enumerate(joints):
                    if pt: self.trajectory[i, j] = pt
                    
    def process(self):
        limit = VELOCITY_LIMIT_BALL if self.key == "ball" else VELOCITY_LIMIT_HUMAN
        num_pts = self.trajectory.shape[1]
        
        # 1. Velocity Filter
        for j in range(num_pts):
            for f in range(1, self.num_frames):
                p1 = self.trajectory[f-1, j]
                p2 = self.trajectory[f, j]
                if not np.isnan(p1).any() and not np.isnan(p2).any():
                    if np.linalg.norm(p2 - p1) > limit:
                        self.trajectory[f, j] = np.nan
        
        # 2. Interpolate (Small gaps)
        for j in range(num_pts):
            for axis in range(3):
                col = self.trajectory[:, j, axis]
                nans = np.isnan(col)
                if np.sum(~nans) > 2:
                    x = np.arange(len(col))
                    col[nans] = np.interp(x[nans], x[~nans], col[~nans])
                    self.trajectory[:, j, axis] = col
        # 3. Smooth
        try:
            from scipy.signal import savgol_filter
            for j in range(num_pts):
                for axis in range(3):
                    self.trajectory[:, j, axis] = savgol_filter(self.trajectory[:, j, axis], SAVGOL_WINDOW, 2)
        except: pass

def main():
    if not INPUT_FILE.exists():
        print(f"[ERROR] No data found at {INPUT_FILE}")
        return

    print("Loading data...")
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)
        
    # Load Goal
    goal_detector = None
    goal_pts_raw = None
    
    if GOAL_FILE.exists():
        with open(GOAL_FILE, 'r') as f:
            gd = json.load(f)
            c = gd["corners"]
            # TL, TR, BR, BL
            goal_pts_raw = np.array([
                c["top_left"], c["top_right"], c["bottom_right"], c["bottom_left"]
            ])
            print(f"[INFO] Loaded Goal: {goal_pts_raw.shape}")
    else:
        print("[WARN] No Goal Config found. Visualization only.")

    # Process Ball & Skeleton
    proc_ball = Processor(data, "ball")
    proc_ball.process()
    traj_ball = proc_ball.trajectory[:, 0, :]
    
    proc_skel = Processor(data, "joints")
    proc_skel.process()
    traj_skel = proc_skel.trajectory
    
    # --- AUTO-ALIGNMENT ---
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

    # Avg Up from Human
    valid_count = 0
    accum_up = np.array([0.0, 0.0, 0.0])
    for f in range(len(traj_skel)):
        skel = traj_skel[f]
        if not np.isnan(skel[5]).any() and not np.isnan(skel[11]).any():
            mid_should = (skel[5]+skel[6])/2
            mid_hip = (skel[11]+skel[12])/2
            accum_up += (mid_should - mid_hip)
            valid_count += 1
            
    if valid_count > 0:
        avg_up = accum_up / valid_count
        R_align = compute_rotation_matrix(avg_up, np.array([0, 0, 1]))
    else:
        R_align = np.array([[1,0,0],[0,0,-1],[0,1,0]]) # Fallback
        
    def apply_rot(traj, R):
        shape = traj.shape
        flat = traj.reshape(-1, 3)
        rot = flat @ R.T
        return rot.reshape(shape)

    traj_ball_rot = apply_rot(traj_ball, R_align)
    traj_skel_rot = apply_rot(traj_skel, R_align)
    
    if goal_pts_raw is not None:
        goal_pts_rot = apply_rot(goal_pts_raw, R_align)
        
    # Floor Leveling
    ankles = traj_skel_rot[:, [15, 16], :].reshape(-1, 3)
    valid_ankles = ankles[~np.isnan(ankles[:, 2])]
    z_offset = 0
    if len(valid_ankles) > 0:
        floor_z = np.percentile(valid_ankles[:, 2], 5)
        z_offset = -floor_z
        print(f"[INFO] Floor Z={floor_z:.1f}, Shifting.")
        
    traj_ball_rot[:, 2] += z_offset
    traj_skel_rot[:, :, 2] += z_offset
    if goal_pts_raw is not None:
        goal_pts_rot[:, 2] += z_offset
        # Init Detector with Final Points
        goal_detector = GoalDetector(goal_pts_rot)

    # Dynamic Center
    all_pts = []
    valid_skel = traj_skel_rot.reshape(-1, 3)
    valid_skel = valid_skel[~np.isnan(valid_skel[:,0])]
    if len(valid_skel) > 0: all_pts.append(valid_skel)
    cx, cy = 0, 0
    if len(all_pts) > 0:
        arr = np.vstack(all_pts)
        med = np.median(arr, axis=0)
        cx, cy = med[0], med[1]
        
    # Goal Zoom Check
    LIMIT = ZOOM
    if goal_pts_raw is not None:
        goal_c = np.mean(goal_pts_rot, axis=0)
        dist = np.linalg.norm(goal_c[:2] - np.array([cx, cy]))
        if dist > LIMIT:
            LIMIT = dist + 1000
            print(f"[ZOOM] Expanding to {LIMIT:.0f}mm for Goal.")

    print(f"Rendering {len(data)} frames [ROBOT + GOAL]...")
    plt.style.use('dark_background')
    
    # Sphere Mesh
    radius = 110 / 1.5
    u, v = np.mgrid[0:2*np.pi:12j, 0:np.pi:8j]
    sphere_x_base = np.cos(u) * np.sin(v)
    sphere_y_base = np.sin(u) * np.sin(v)
    sphere_z_base = np.cos(v)
    
    ball_x = radius * sphere_x_base
    ball_y = radius * sphere_y_base
    ball_z = radius * sphere_z_base
    
    goal_triggered = False

    for i in range(len(data)):
        # Physics Step
        if goal_detector and not goal_triggered:
            # Check ball segment
            if i > 0:
                p_prev = traj_ball_rot[i-1]
                p_curr = traj_ball_rot[i]
                if goal_detector.process_frame(i, p_prev, p_curr):
                    goal_triggered = True
        
        # Rendering
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
        for val in gx: ax.plot([val, val], [cy-LIMIT, cy+LIMIT], [0,0], c='#222222', lw=0.8)
        for val in gy: ax.plot([cx-LIMIT, cx+LIMIT], [val, val], [0,0], c='#222222', lw=0.8)
        
        # Draw Goal
        if goal_pts_rot is not None:
            g = goal_pts_rot
            order = [0, 1, 2, 3, 0] # TL TR BR BL TL
            
            # Color logic: Static Blue, Flashing Green if GOAL
            g_color = 'deepskyblue'
            lw = 3
            if goal_triggered:
                # Flash effect every few frames or just Solid Green
                g_color = '#00ff00' 
                if (i // 2) % 2 == 0: g_color = '#ccffcc'
                
                # Draw "GOAL!" Text in 3D (above goal)
                top_mid = (g[0] + g[1]) / 2
                ax.text(top_mid[0], top_mid[1], top_mid[2] + 200, "GOAL!", color='lime', fontsize=16, weight='bold', ha='center')
                
            ax.plot(g[order,0], g[order,1], g[order,2], c=g_color, linewidth=lw)
            
        # Draw Ball Trace
        start_t = max(0, i - FINAL_FPS)
        valid_mask = ~np.isnan(traj_ball_rot[start_t:i+1, 0])
        b_pts = traj_ball_rot[start_t:i+1][valid_mask]
        if len(b_pts)>1: 
            ax.plot(b_pts[:,0], b_pts[:,1], b_pts[:,2], c='orange', lw=2)
            
        # Draw Ball
        curr_b = traj_ball_rot[i]
        if not np.isnan(curr_b[0]):
             ax.plot_surface(ball_x + curr_b[0], ball_y + curr_b[1], ball_z + curr_b[2], color='yellow', alpha=0.9, shade=True)

        # Draw Robot
        def draw_sphere(pt, r, color):
            if pt is None or np.isnan(pt).any(): return
            X = r * sphere_x_base + pt[0]
            Y = r * sphere_y_base + pt[1]
            Z = r * sphere_z_base + pt[2]
            ax.plot_surface(X, Y, Z, color=color, alpha=1.0, shade=True)

        skel = traj_skel_rot[i]
        valid_j = ~np.isnan(skel[:, 0])
        
        # Bones
        for s, e in CONNECTIONS:
            if valid_j[s] and valid_j[e]:
                p1, p2 = skel[s], skel[e]
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], c='white', lw=4)
        
        # Shoulder/Hip Joints
        for idx in range(17):
            if valid_j[idx]:
                r = 30
                col = 'cyan'
                if idx in [5,6,11,12]: r=40
                if idx <= 4: 
                    r=15
                    col='#0088aa'
                if idx in [9,10,15,16]: 
                    r=25
                    col='#00ffff'
                draw_sphere(skel[idx], r, col)

        plt.savefig(OUTPUT_DIR / f"frame_{i:04d}.png")
        plt.close(fig)
        
        if i % 10 == 0:
            sys.stdout.write(f"\r{i}/{len(data)}")
            sys.stdout.flush()

    # Encode
    print("\nEncoding video...")
    out_vid = PROJECT_ROOT / "output" / "videos" / "final_3d_robot_goal_coco.mp4"
    if out_vid.exists(): os.remove(out_vid)
    os.system(f"ffmpeg -y -framerate {FINAL_FPS} -i {OUTPUT_DIR}/frame_%04d.png -c:v libx264 -pix_fmt yuv420p {out_vid}")
    print(f"[SUCCESS] {out_vid}")

if __name__ == "__main__":
    main()
