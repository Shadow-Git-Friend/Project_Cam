# import cv2
# import yaml
# import time
# import logging
# import logging.config
# from pathlib import Path
# import numpy as np
# import sys

# # --- PATH ADJUSTMENTS ---
# # Calculate PROJECT_ROOT (up two levels from src/main.py)
# PROJECT_ROOT = Path(__file__).resolve().parent.parent 
# CONFIG_DIR = PROJECT_ROOT / "config"
# sys.path.append(str(PROJECT_ROOT)) # Add project root to sys path for imports

# # Now we can import the CameraThread module
# try:
#     from src.capture.camera_thread import CameraThread
# except ImportError as e:
#     print(f"Error importing CameraThread. Ensure `src` folder is configured correctly: {e}")
#     sys.exit(1)


# def load_yaml(path):
#     """Loads a YAML configuration file."""
#     try:
#         with open(path, "r") as f:
#             return yaml.safe_load(f)
#     except FileNotFoundError:
#         print(f"Error: Configuration file not found at {path}")
#         sys.exit(1)


# def main():
#     # --- Load logging ---
#     logging_config = load_yaml(CONFIG_DIR / "logging.yaml")
#     logging.config.dictConfig(logging_config)
#     logger = logging.getLogger("Main")

#     # --- Load camera configs ---
#     cam_cfg = load_yaml(CONFIG_DIR / "cameras.yaml")["cameras"]
#     num_cameras = len(cam_cfg)
#     logger.info(f"🎥 Loading {num_cameras} cameras...")

#     if num_cameras != 4:
#         logger.error(f"❌ Configuration must contain exactly 4 cameras for a 2x2 grid. Found: {num_cameras}")
#         return

#     # --- Start camera threads ---
#     cameras = [
#         CameraThread(
#             name=c["name"],
#             device=c["device"],
#             width=c["width"],
#             height=c["height"],
#             fps=c["fps"],
#         )
#         for c in cam_cfg
#     ]

#     for cam in cameras:
#         cam.start()

#     # Give threads a moment to initialize the VideoCapture objects
#     time.sleep(2) 

#     # --- Display loop (2x2 Grid) ---
#     logger.info("✅ All camera threads started. Entering display loop.")
    
#     # Get the expected dimensions from the first camera (assuming all are uniform)
#     cam_width = cameras[0].width
#     cam_height = cameras[0].height
    
#     # Define text overlay positions for the 2x2 grid
#     text_positions = [
#         # (x_offset, y_offset, camera_index)
#         (20, 40, 0),                           # Cam 1 (Top-Left)
#         (cam_width + 20, 40, 1),               # Cam 2 (Top-Right)
#         (20, cam_height + 40, 2),              # Cam 3 (Bottom-Left)
#         (cam_width + 20, cam_height + 40, 3),  # Cam 4 (Bottom-Right)
#     ]

#     while True:
#         # 1. Collect all available frames
#         available_frames = [cam.frame for cam in cameras if cam.frame is not None]
        
#         # Check if all 4 frames are ready
#         if len(available_frames) < num_cameras:
#             logger.debug(f"⚠️ Waiting for all {num_cameras} frames to be available.")
#             time.sleep(0.01)
#             continue

#         # Split frames into two rows (indices 0, 1 for top; 2, 3 for bottom)
#         top_row_frames = available_frames[0:2]
#         bottom_row_frames = available_frames[2:4]

#         # 2. Stack the frames into a 2x2 grid
#         try:
#             top_row = np.hstack(top_row_frames)
#             bottom_row = np.hstack(bottom_row_frames)
#             combined = np.vstack([top_row, bottom_row])
#         except ValueError as e:
#             logger.error(f"❌ Frame stacking failed. Check if all camera resolutions match: {e}")
#             time.sleep(0.5)
#             continue

#         # 3. Add text overlay
#         for x, y, i in text_positions:
#             cam = cameras[i]
#             cv2.putText(
#                 combined,
#                 cam.name,
#                 (x, y),
#                 cv2.FONT_HERSHEY_SIMPLEX,
#                 1,
#                 (0, 255, 0), # Green color
#                 2,
#             )

#         # 4. Resize and display
#         display_width = 1920
#         scale = display_width / combined.shape[1]
#         display_height = int(combined.shape[0] * scale)

#         cv2.imshow("Quad Camera System (2x2)", cv2.resize(combined, (display_width, display_height)))

#         # 5. Handle exit key (ESC or 'q')
#         key = cv2.waitKey(1)
#         if key == 27 or key == ord("q"):
#             logger.info("🛑 Shutting down cameras...")
#             for cam in cameras:
#                 cam.stop()
#             break

#     cv2.destroyAllWindows()


# if __name__ == "__main__":
#     main()