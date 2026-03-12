
import os
import shutil

# DIRECTORY MAPPING
structure = {
    "src/core": [
        "src/hybrid_goal_detector.py",
        "src/fast_goal_detector.py",
        "src/triangulate_3d.py",
        "src/triangulate_v2.py",
        "src/calibration_utils.py"
    ],
    "src/calibration": [
        "src/tools/calibrate_extrinsics.py",
        "src/tools/calibrate_extrinsics_offline.py",
        "src/tools/check_board_detection.py",
        "src/tools/generate_tv_board.py",
        "src/tools/rescale_calibration.py"
    ],
    "src/capture": [
        "src/tools/capture_charuco_auto.py",
        "src/capture_cam2_cam4.py",
        "src/record_stereo_video.py"
    ],
    "src/legacy": [
        "src/ball_debug_terminal.py", 
        "src/record_motion.py",
        "src/record_motion_4cam.py",
        "src/record_motion_4cam_with_ball.py",
        "src/record_motion_v2.py",
        "src/render_animation.py",
        "src/render_animation_4cam.py",
        "src/render_animation_4cam_ball.py",
        "src/main.py",
        "src/main_3d_tracker.py",
        "src/video_save.py"
    ]
}

def move_files():
    for folder, files in structure.items():
        # Create folder
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Created {folder}")
            
        # Move files
        for src in files:
            if os.path.exists(src):
                filename = os.path.basename(src)
                dst = os.path.join(folder, filename)
                shutil.move(src, dst)
                print(f"Moved {src} -> {dst}")
            else:
                print(f"Skip (Not Found): {src}")
                
    # Remove empty old dirs
    if os.path.exists("src/tools"):
        if not os.listdir("src/tools"):
            os.rmdir("src/tools")
            print("Removed empty src/tools")

if __name__ == "__main__":
    move_files()
