
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
OUTPUT_DIR = PROJECT_ROOT / "output" / "frames" / "render_output_robot"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Tuning
VELOCITY_LIMIT_BALL = 800.0 # mm/frame
VELOCITY_LIMIT_HUMAN = 200.0 # mm/frame
SAVGOL_WINDOW = 5
FINAL_FPS = 15 # Lowered from 30 to match actual recording speed
ZOOM = 2000 # mm box radius

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
        # Rotation that aligns v_source to v_target
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
    # We use average Hip-to-Shoulder vector
    # 5:LShoulder, 6:RShoulder, 11:LHip, 12:RHip
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
        # Target is +Z [0, 0, 1]
        R_align = compute_rotation_matrix(avg_up, np.array([0, 0, 1]))
    else:
        print("[WARN] No skeleton found for alignment. Using default rotation.")
        R_align = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]]) # Approx
        
    # Apply Rotation
    def apply_rot(traj, R):
        shape = traj.shape
        flat = traj.reshape(-1, 3)
        rot = flat @ R.T
        return rot.reshape(shape)

    traj_ball_rot = apply_rot(traj_ball, R_align)
    traj_skel_rot = apply_rot(traj_skel, R_align)
    
    # 2. Floor Leveling (Shift Z so lowest ankle is at 0)
    # 15:LAnkle, 16:RAnkle
    ankles = traj_skel_rot[:, [15, 16], :].reshape(-1, 3)
    valid_ankles = ankles[~np.isnan(ankles[:, 2])]
    
    z_offset = 0
    if len(valid_ankles) > 0:
        # We take the 5th percentile to ignore outliers
        floor_z = np.percentile(valid_ankles[:, 2], 5)
        z_offset = -floor_z
        print(f"[INFO] Floor detected at Z={floor_z:.1f}, shifting to 0.")
    
    # Apply to Ball (Shape: Frames x 3)
    traj_ball_rot[:, 2] += z_offset
    # Apply to Skeleton (Shape: Frames x Joints x 3)
    traj_skel_rot[:, :, 2] += z_offset
            
    # 3. Dynamic Center (XY only)
    # We want to center on the person in XY, but keep Z=0 as floor
    all_pts = []
    valid_skel = traj_skel_rot.reshape(-1, 3)
    valid_skel = valid_skel[~np.isnan(valid_skel[:,0])]
    if len(valid_skel) > 0: all_pts.append(valid_skel)
    
    cx, cy = 0, 0
    if len(all_pts) > 0:
        all_pts_concat = np.vstack(all_pts)
        median_pos = np.median(all_pts_concat, axis=0)
        cx, cy = median_pos[0], median_pos[1]
        
    print(f"[INFO] Centering View XY at: {cx:.0f}, {cy:.0f}")
    
    # 4. ZOOM (2x Bigger -> Half the Limit)
    LIMIT = 500 
    
    print(f"Rendering {len(data)} frames with ROBOT STYLE...")
    plt.style.use('dark_background')
    
    # Pre-calculate Sphere (Size 5 Football: Radius ~110mm -> / 1.5 = 73.3mm)
    radius = 110 / 1.5
    u, v = np.mgrid[0:2*np.pi:12j, 0:np.pi:8j] # Slightly higher poly for nice spheres
    sphere_x_base = np.cos(u) * np.sin(v)
    sphere_y_base = np.sin(u) * np.sin(v)
    sphere_z_base = np.cos(v)
    
    # Ball Specifics
    ball_x = radius * sphere_x_base
    ball_y = radius * sphere_y_base
    ball_z = radius * sphere_z_base

    for i in range(len(data)):
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')
        ax.set_box_aspect([1,1,1])
        
        # Set limits
        ax.set_xlim(cx - LIMIT, cx + LIMIT)
        ax.set_ylim(cy - LIMIT, cy + LIMIT)
        ax.set_zlim(0, 2*LIMIT) 
        
        # Draw Floor Grid
        step = 200
        gx = np.arange(cx-LIMIT, cx+LIMIT+step, step)
        gy = np.arange(cy-LIMIT, cy+LIMIT+step, step)
        for g_x in gx:
            ax.plot([g_x, g_x], [cy-LIMIT, cy+LIMIT], [0, 0], color='#222222', linewidth=0.8)
        for g_y in gy:
            ax.plot([cx-LIMIT, cx+LIMIT], [g_y, g_y], [0, 0], color='#222222', linewidth=0.8)

        # Helper: Draw Sphere
        def draw_sphere(pt, r, color, alpha=1.0):
            if pt is None or np.isnan(pt).any(): return
            X = r * sphere_x_base + pt[0]
            Y = r * sphere_y_base + pt[1]
            Z = r * sphere_z_base + pt[2]
            ax.plot_surface(X, Y, Z, color=color, alpha=alpha, shade=True)

        # Draw Ball Trace
        start_trace = max(0, i - FINAL_FPS)
        valid_mask = ~np.isnan(traj_ball_rot[start_trace:i+1, 0])
        ball_pts = traj_ball_rot[start_trace:i+1][valid_mask]
        
        if len(ball_pts) > 1:
            ax.plot(ball_pts[:,0], ball_pts[:,1], ball_pts[:,2], c='orange', linewidth=2)            
            
        # Draw Current Ball (Solid Sphere)
        curr_ball = traj_ball_rot[i]
        if not np.isnan(curr_ball[0]):
             ax.plot_surface(ball_x + curr_ball[0], 
                             ball_y + curr_ball[1], 
                             ball_z + curr_ball[2], 
                             color='yellow', alpha=0.9, shade=True)
            
        # Draw Skeleton (Robot Style)
        current_skel = traj_skel_rot[i] 
        valid_joints = ~np.isnan(current_skel[:, 0])
        
        # Bones (Thick White Lines)
        for s, e in CONNECTIONS:
            if valid_joints[s] and valid_joints[e]:
                p1 = current_skel[s]
                p2 = current_skel[e]
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], c='white', linewidth=4, alpha=0.9)
                
        # Joints (Cyan Spheres)
        for j_idx in range(17):
            if valid_joints[j_idx]:
                # Custom sizes per joint type?
                # Head parts smaller?
                r = 30 # Default radius
                col = 'cyan'
                
                # Head (0-4)
                if j_idx <= 4: 
                    r = 15
                    col = '#0088aa' # Darker cyan
                    
                # Hips/Shoulders (5,6,11,12) -> Big
                if j_idx in [5, 6, 11, 12]:
                    r = 40
                    
                # Knees/Elbows (7,8,13,14) -> Medium
                if j_idx in [7, 8, 13, 14]:
                    r = 30
                    
                # Hands/Feet (9,10,15,16) -> Small
                if j_idx in [9, 10, 15, 16]:
                    r = 25
                    col = '#00ffff' # Bright cyan
                
                draw_sphere(current_skel[j_idx], r, col)

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
    out_vid = PROJECT_ROOT / "output" / "videos" / "final_3d_robot.mp4"
    if out_vid.exists(): os.remove(out_vid)
    os.system(f"ffmpeg -y -framerate {FINAL_FPS} -i {OUTPUT_DIR}/frame_%04d.png -c:v libx264 -pix_fmt yuv420p {out_vid}")
    print(f"[SUCCESS] {out_vid}")

if __name__ == "__main__":
    main()
