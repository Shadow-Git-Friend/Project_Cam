
import json
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from pathlib import Path
import os
import sys

# --- CONFIG ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = PROJECT_ROOT / "motion_capture_data.json"
GOAL_FILE = PROJECT_ROOT / "cal" / "goal_config.json"
OUTPUT_DIR = PROJECT_ROOT / "render_output_goal"
OUTPUT_DIR.mkdir(exist_ok=True)

# Tuning
VELOCITY_LIMIT_BALL = 800.0 # mm/frame
VELOCITY_LIMIT_HUMAN = 200.0 # mm/frame
SAVGOL_WINDOW = 5
FINAL_FPS = 15 
ZOOM = 2000 

# Skeleton Map (COCO 17)
CONNECTIONS = [
    (5, 7), (7, 9), (6, 8), (8, 10), # Arms
    (11, 13), (13, 15), (12, 14), (14, 16), # Legs
    (5, 6), (11, 12), (5, 11), (6, 12), # Torso
    (0, 1), (0, 2), (1, 3), (2, 4) # Head
]

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
        
        # 2. Interpolate
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
        
    # Load Goal Data
    goal_pts_rot = None
    if GOAL_FILE.exists():
        with open(GOAL_FILE, 'r') as f:
            gd = json.load(f)
            # TL, TR, BR, BL
            corners = gd["corners"]
            goal_raw = np.array([
                corners["top_left"],
                corners["top_right"],
                corners["bottom_right"],
                corners["bottom_left"]
            ])
            print(f"[INFO] Loaded Goal: {goal_raw.shape}")
    else:
        print("[WARN] No Goal Config found.")

    # Process Ball
    proc_ball = Processor(data, "ball")
    proc_ball.process()
    traj_ball = proc_ball.trajectory[:, 0, :]
    
    # Process Skeleton
    proc_skel = Processor(data, "joints")
    proc_skel.process()
    traj_skel = proc_skel.trajectory
    
    # --- TRANSFORMATIONS ---
    # PROFESSIONAL AUTO-ALIGNMENT
    
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

    # 1. Estimate "Up" vector from Human data
    valid_frames_count = 0
    accumulated_up_vec = np.array([0.0, 0.0, 0.0])
    
    for f in range(len(traj_skel)):
        skel = traj_skel[f]
        if not np.isnan(skel[5]).any() and not np.isnan(skel[11]).any():
            mid_shoulder = (skel[5] + skel[6]) / 2.0
            mid_hip = (skel[11] + skel[12]) / 2.0
            vec = mid_shoulder - mid_hip
            accumulated_up_vec += vec
            valid_frames_count += 1
            
    if valid_frames_count > 0:
        avg_up = accumulated_up_vec / valid_frames_count
        R_align = compute_rotation_matrix(avg_up, np.array([0, 0, 1]))
    else:
        print("[WARN] No skeleton found for alignment. Using default rotation.")
        R_align = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]]) 
        
    # Apply Rotation
    def apply_rot(traj, R):
        shape = traj.shape
        flat = traj.reshape(-1, 3)
        rot = flat @ R.T
        return rot.reshape(shape)

    traj_ball_rot = apply_rot(traj_ball, R_align)
    traj_skel_rot = apply_rot(traj_skel, R_align)
    
    # Apply to Goal
    if 'goal_raw' in locals():
        goal_pts_rot = apply_rot(goal_raw, R_align)
    
    # 2. Floor Leveling (Shift Z so lowest ankle is at 0)
    ankles = traj_skel_rot[:, [15, 16], :].reshape(-1, 3)
    valid_ankles = ankles[~np.isnan(ankles[:, 2])]
    
    z_offset = 0
    if len(valid_ankles) > 0:
        floor_z = np.percentile(valid_ankles[:, 2], 5)
        z_offset = -floor_z
        print(f"[INFO] Floor detected at Z={floor_z:.1f}, shifting to 0.")
    
    traj_ball_rot[:, 2] += z_offset
    traj_skel_rot[:, :, 2] += z_offset
    if goal_pts_rot is not None:
        goal_pts_rot[:, 2] += z_offset
            
    # 3. Dynamic Center (XY only)
    all_pts = []
    valid_skel = traj_skel_rot.reshape(-1, 3)
    valid_skel = valid_skel[~np.isnan(valid_skel[:,0])]
    if len(valid_skel) > 0: all_pts.append(valid_skel)
    
    cx, cy = 0, 0
    if len(all_pts) > 0:
        all_pts_concat = np.vstack(all_pts)
        median_pos = np.median(all_pts_concat, axis=0)
        cx, cy = median_pos[0], median_pos[1]
        
    center = np.array([cx, cy, 0])
    print(f"[INFO] Centering View XY at: {cx:.0f}, {cy:.0f}")
    
    # 4. ZOOM / LIMITS
    # We need to see the Goal (if present) and the Person
    LIMIT = 500 # Default Zoom
    
    if goal_pts_rot is not None:
        # Calculate distance to goal
        goal_center = np.mean(goal_pts_rot, axis=0)
        dist = np.linalg.norm(goal_center[:2] - np.array([cx, cy]))
        print(f"[INFO] Goal is {dist:.0f}mm away. Expanding view.")
        LIMIT = max(LIMIT, dist + 1000) # Ensure goal is inside with margin
    
    print(f"Rendering {len(data)} frames with GOAL VISUALIZATION (Limit={LIMIT:.0f}mm)...")
    plt.style.use('dark_background')
    
    for i in range(len(data)):
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')
        ax.set_box_aspect([1,1,1])
        
        # Set limits
        ax.set_xlim(cx - LIMIT, cx + LIMIT)
        ax.set_ylim(cy - LIMIT, cy + LIMIT)
        ax.set_zlim(0, 2*LIMIT) # Floor to Head
        
        # Draw Floor Grid
        step = 200
        gx = np.arange(cx-LIMIT, cx+LIMIT+step, step)
        gy = np.arange(cy-LIMIT, cy+LIMIT+step, step)
        for g_x in gx:
            ax.plot([g_x, g_x], [cy-LIMIT, cy+LIMIT], [0, 0], color='#222222')
        for g_y in gy:
            ax.plot([cx-LIMIT, cx+LIMIT], [g_y, g_y], [0, 0], color='#222222')

        # Draw Goal
        if goal_pts_rot is not None:
            # TL, TR, BR, BL -> [0, 1, 2, 3]
            # Draw Loop: 0->1->2->3->0
            g = goal_pts_rot
            order = [0, 1, 2, 3, 0]
            ax.plot(g[order,0], g[order,1], g[order,2], c='deepskyblue', linewidth=3, label='Goal')
            
            # Draw semi-transparent surface? Matplotlib surface is hard with transparency order.
            # Just stick to wireframe.

        # Draw Ball Trace
        start_trace = max(0, i - FINAL_FPS)
        valid_mask = ~np.isnan(traj_ball_rot[start_trace:i+1, 0])
        ball_pts = traj_ball_rot[start_trace:i+1][valid_mask]
        
        if len(ball_pts) > 1:
            ax.plot(ball_pts[:,0], ball_pts[:,1], ball_pts[:,2], c='orange', linewidth=2)            
        
        # Draw Current Ball
        bx, by, bz = traj_ball_rot[i]
        if not np.isnan(bx):
            # Distance to Goal Center?
            # Simple Logic: Check if passed goal plane
            pass
            ax.scatter([bx], [by], [bz], c='yellow', s=150, edgecolors='white')
            
        # Draw Skeleton
        current_skel = traj_skel_rot[i] 
        valid_joints = ~np.isnan(current_skel[:, 0])
        
        # Bones
        for s, e in CONNECTIONS:
            if valid_joints[s] and valid_joints[e]:
                p1 = current_skel[s]
                p2 = current_skel[e]
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], c='cyan', linewidth=2)
                
        # Joints
        sx = current_skel[valid_joints, 0]
        sy = current_skel[valid_joints, 1]
        sz = current_skel[valid_joints, 2]
        if len(sx) > 0:
            ax.scatter(sx, sy, sz, c='white', s=30)
            
        # Cam 0 indicator
        ax.text(0, 0, 0, "CAM 0", color='green')
        
        # Save
        plt.savefig(OUTPUT_DIR / f"frame_{i:04d}.png")
        plt.close(fig)
        
        if i % 10 == 0:
            sys.stdout.write(f"\r{i}/{len(data)}")
            sys.stdout.flush()
            
    # Video
    print("\nEncoding video...")
    out_vid = PROJECT_ROOT / "final_3d_goal_1.mp4"
    if out_vid.exists(): os.remove(out_vid)
    os.system(f"ffmpeg -y -framerate {FINAL_FPS} -i {OUTPUT_DIR}/frame_%04d.png -c:v libx264 -pix_fmt yuv420p {out_vid}")
    print(f"[SUCCESS] {out_vid}")

if __name__ == "__main__":
    main()
