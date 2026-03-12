
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
OUTPUT_DIR = PROJECT_ROOT / "render_output_ball"
OUTPUT_DIR.mkdir(exist_ok=True)

# Tuning
VELOCITY_LIMIT_BALL = 500.0 # mm/frame (aggressive outlier removal)
SAVGOL_WINDOW = 5
FINAL_FPS = 30
ZOOM = 3000 # mm box size

class Processor:
    def __init__(self, data):
        self.raw = data
        self.num_frames = len(data)
        self.trajectory = np.full((self.num_frames, 3), np.nan)
        
        for i, frame in enumerate(data):
            ball = frame.get("ball")
            if ball:
                self.trajectory[i] = ball
                
    def process(self):
        # 1. Velocity Filter
        for f in range(1, self.num_frames):
            p1 = self.trajectory[f-1]
            p2 = self.trajectory[f]
            if not np.isnan(p1).any() and not np.isnan(p2).any():
                dist = np.linalg.norm(p2 - p1)
                if dist > VELOCITY_LIMIT_BALL:
                    self.trajectory[f] = np.nan
                    
        # 2. Interpolate NaN
        for axis in range(3):
            col = self.trajectory[:, axis]
            nans = np.isnan(col)
            if np.sum(~nans) > 2: # Need at least some points
                x_all = np.arange(len(col))
                col[nans] = np.interp(x_all[nans], x_all[~nans], col[~nans])
                self.trajectory[:, axis] = col
                
        # 3. Smooth
        try:
            from scipy.signal import savgol_filter
            for axis in range(3):
                self.trajectory[:, axis] = savgol_filter(self.trajectory[:, axis], SAVGOL_WINDOW, 2)
        except ImportError:
            pass

def main():
    if not INPUT_FILE.exists():
        print(f"[ERROR] No data found at {INPUT_FILE}")
        return

    print("Loading data...")
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)
        
    proc = Processor(data)
    proc.process()
    traj = proc.trajectory
    
    print(f"Rendering {len(traj)} frames...")
    
    plt.style.use('dark_background')
    
    for i in range(len(traj)):
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')
        x, y, z = traj[i]
        
        # Setup View
        ax.set_box_aspect([1,1,1])
        # Center view on the ball mean or 0,0,0?
        # Let's fix view to 0,0,0 (Cam 0) + Z forward
        ax.set_xlim(-ZOOM, ZOOM)
        ax.set_ylim(-ZOOM, ZOOM)
        ax.set_zlim(0, ZOOM*2)
        
        # Draw Trajectory up to now
        valid_mask = ~np.isnan(traj[:i+1, 0])
        valid_pts = traj[:i+1][valid_mask]
        
        if len(valid_pts) > 1:
            ax.plot(valid_pts[:,0], valid_pts[:,1], valid_pts[:,2], c='orange', linewidth=2)
            
        # Draw ball
        if not np.isnan(x):
            ax.scatter([x], [y], [z], c='yellow', s=100)
            
        # Cam 0 indicator
        ax.text(0, 0, 0, "CAM 0", color='green')
        
        # Save
        plt.savefig(OUTPUT_DIR / f"frame_{i:04d}.png")
        plt.close(fig)
        
        if i % 10 == 0:
            sys.stdout.write(f"\r{i}/{len(traj)}")
            sys.stdout.flush()
            
    # Video
    print("\nEncoding video...")
    out_vid = PROJECT_ROOT / "final_3d_ball.mp4"
    if out_vid.exists(): os.remove(out_vid)
    os.system(f"ffmpeg -y -framerate {FINAL_FPS} -i {OUTPUT_DIR}/frame_%04d.png -c:v libx264 -pix_fmt yuv420p {out_vid}")
    print(f"[SUCCESS] {out_vid}")

if __name__ == "__main__":
    main()
