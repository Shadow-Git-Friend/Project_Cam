
import mediapipe as mp
from pathlib import Path
import os
import sys
import numpy as np
import json
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
MP_POSE_CONNECTIONS = mp.solutions.holistic.POSE_CONNECTIONS
MP_HAND_CONNECTIONS = mp.solutions.holistic.HAND_CONNECTIONS

# --- CONFIG ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "data_3d_mediapipe.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "frames" / "render_output_mediapipe"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FINAL_FPS = 30
ZOOM = 1000 # mm box radius (Tighter zoom)

# MediaPipe Pose Topology
# 11: left_shoulder, 12: right_shoulder
# 23: left_hip, 24: right_hip
# 27: left_ankle, 28: right_ankle
# 29: left_heel, 30: right_heel
# 31: left_foot_index, 32: right_foot_index

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

def apply_rot(pts, R):
    # pts: list of [x,y,z]
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
        
    print(f"Processing {len(data)} frames...")
    plt.style.use('dark_background')
    
    # --- 1. Auto-Alignment ---
    # Calc average Up vector
    valid_up_vecs = []
    
    for frame in data:
        pose = frame.get("pose_3d")
        if pose and len(pose) > 24:
            # Check visibility or valid Z
            # Assuming raw data is clean-ish
            try:
                p11 = np.array(pose[11])
                p12 = np.array(pose[12])
                p23 = np.array(pose[23])
                p24 = np.array(pose[24])
                
                mid_shoulder = (p11 + p12) / 2.0
                mid_hip = (p23 + p24) / 2.0
                
                vec = mid_shoulder - mid_hip
                valid_up_vecs.append(vec)
            except: pass
            
    if valid_up_vecs:
        avg_up = np.mean(valid_up_vecs, axis=0)
        print(f"[ALIGN] Found Avg Up Vector: {avg_up}")
        # Align to +Z [0,0,1]
        R_align = compute_rotation_matrix(avg_up, np.array([0, 0, 1]))
    else:
        print("[WARN] Could not compute alignment. Using Identity.")
        R_align = np.eye(3)

    # --- 2. Apply Rotation & Floor Leveling ---
    # We need to rotate ALL points first
    all_z_feet = []
    
    processed_data = []
    
    for frame in data:
        new_frame = frame.copy()
        
        # Rotate all sets
        new_frame["pose_3d"] = apply_rot(frame.get("pose_3d"), R_align)
        new_frame["left_hand_3d"] = apply_rot(frame.get("left_hand_3d"), R_align)
        new_frame["right_hand_3d"] = apply_rot(frame.get("right_hand_3d"), R_align)
        new_frame["face_3d"] = apply_rot(frame.get("face_3d"), R_align)
        
        # Collect feet Z for floor detection
        # Pose: 27-32 are feet/ankles
        pose = new_frame["pose_3d"]
        if pose and len(pose) > 32:
            feet_pts = [pose[29], pose[30], pose[31], pose[32]] # Heels + Toes
            for p in feet_pts:
                all_z_feet.append(p[2])
                
        processed_data.append(new_frame)
        
    # Floor Detection
    z_offset = 0
    if all_z_feet:
        floor_z = np.percentile(all_z_feet, 5) # 5th percentile
        z_offset = -floor_z
        print(f"[FLOOR] Detected at Z={floor_z:.1f}, shift={z_offset:.1f}")
        
    # Apply Z Offset and Calc Center
    final_data = []
    all_pts_centered = []
    
    for frame in processed_data:
        # Shift Z
        def shift_z(pts):
            if not pts: return []
            return [[p[0], p[1], p[2] + z_offset] for p in pts]
            
        frame["pose_3d"] = shift_z(frame["pose_3d"])
        frame["left_hand_3d"] = shift_z(frame["left_hand_3d"])
        frame["right_hand_3d"] = shift_z(frame["right_hand_3d"])
        frame["face_3d"] = shift_z(frame["face_3d"])
        
        if frame["pose_3d"]:
            all_pts_centered.extend(frame["pose_3d"])
            
        final_data.append(frame)
        
    # Calc Center XY
    cx, cy, cz = 0, 0, 0
    if all_pts_centered:
        arr = np.array(all_pts_centered)
        median = np.median(arr, axis=0)
        cx, cy = median[0], median[1]
        # Keep CZ at roughly waist height? Or fix camera at specific height?
        # Let's fix camera lookat at waist height ~900mm
        cz = 900 
        
    print(f"[CENTER] Focused at {cx:.0f}, {cy:.0f}, {cz:.0f}")


    # Pre-calculate Sphere Mesh for Joints (Unit Sphere)
    u, v = np.mgrid[0:2*np.pi:10j, 0:np.pi:6j] # Low poly for performance
    sphere_x = np.cos(u) * np.sin(v)
    sphere_y = np.sin(u) * np.sin(v)
    sphere_z = np.cos(v)

    # --- 3. Render ---
    for i, frame in enumerate(final_data):
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')
        ax.set_box_aspect([1,1,1])
        
        # Set limits
        ax.set_xlim(cx - ZOOM, cx + ZOOM)
        ax.set_ylim(cy - ZOOM, cy + ZOOM)
        ax.set_zlim(0, 2*ZOOM) 
        
        # Draw Floor Grid
        step = 500
        gx = np.arange(cx-ZOOM, cx+ZOOM+step, step)
        gy = np.arange(cy-ZOOM, cy+ZOOM+step, step)
        for g_x in gx:
            ax.plot([g_x, g_x], [cy-ZOOM, cy+ZOOM], [0, 0], color='#222222', linewidth=0.8)
        for g_y in gy:
            ax.plot([cx-ZOOM, cx+ZOOM], [g_y, g_y], [0, 0], color='#222222', linewidth=0.8)
        
        def draw_sphere(pt, radius, color, alpha=1.0):
            if pt is None or len(pt) < 3: return
            x = sphere_x * radius + pt[0]
            y = sphere_y * radius + pt[1]
            z = sphere_z * radius + pt[2]
            ax.plot_surface(x, y, z, color=color, alpha=alpha, shade=True)

        # Helper: Draw Skeleton (Bones + Spheres)
        def draw_robot_armature(pts, connections, bone_color, joint_color, bone_width=2, joint_radius=30):
            if not pts: return
            arr = np.array(pts)
            if len(arr) == 0: return
            
            # Draw Bones (Thick Lines)
            for start_idx, end_idx in connections:
                if start_idx < len(pts) and end_idx < len(pts):
                    p1 = pts[start_idx]
                    p2 = pts[end_idx]
                    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], c=bone_color, linewidth=bone_width, alpha=1.0)
            
            # Draw Joints (Spheres)
            # We iterate unique points involved in connections to avoid overdrawing
            # Or just draw all points
            for pt in arr:
                 draw_sphere(pt, joint_radius, joint_color)

        # Draw Pose (Body)
        # White bones, Cyan joints
        draw_robot_armature(frame.get("pose_3d"), MP_POSE_CONNECTIONS, 'white', 'cyan', bone_width=4, joint_radius=35)
        
        # Draw Hands
        # Red bones, Orange joints (smaller)
        draw_robot_armature(frame.get("left_hand_3d"), MP_HAND_CONNECTIONS, '#ff4444', '#ff8800', bone_width=2, joint_radius=12)
        draw_robot_armature(frame.get("right_hand_3d"), MP_HAND_CONNECTIONS, '#ff4444', '#ff8800', bone_width=2, joint_radius=12)
        
        # Draw Head Sphere
        # Estimate head center from Nose (0) or ears
        pose = frame.get("pose_3d")
        if pose and len(pose) > 0:
            nose = pose[0] # Landmark 0
            # Draw large sphere for head
            draw_sphere(nose, radius=120, color='white', alpha=0.9)
            # Draw simplified face points on top?
            face_pts = frame.get("face_3d")
            if face_pts:
                arr = np.array(face_pts)
                if len(arr) > 0:
                     # Subsample for performance
                     sub = arr[::10] 
                     ax.scatter(sub[:,0], sub[:,1], sub[:,2], c='blue', s=2, depthshade=False)
        
        # Save
        plt.savefig(OUTPUT_DIR / f"frame_{i:04d}.png")
        plt.close(fig)
        
        if i % 10 == 0:
            sys.stdout.write(f"\r{i}/{len(data)}")
            sys.stdout.flush()
            
    # Video
    print("\nEncoding video...")
    out_vid = PROJECT_ROOT / "output" / "videos" / "final_mediapipe_3d_robot.mp4"
    if out_vid.exists(): os.remove(out_vid)
    os.system(f"ffmpeg -y -framerate {FINAL_FPS} -i {OUTPUT_DIR}/frame_%04d.png -c:v libx264 -pix_fmt yuv420p {out_vid}")
    print(f"[SUCCESS] {out_vid}")

if __name__ == "__main__":
    main()
