import cv2
import os
import datetime
import time
import sys

# ------------------------
#  SETTINGS
# ------------------------

# ID of the camera to use (0 is usually the default/first camera)
CAM_ID = 0

# Use the exact resolution you need (704x576 from previous context)
FRAME_WIDTH = 704
FRAME_HEIGHT = 576

# Reduced FPS for better I/O stability
FPS = 15.0 

# Folder to save the video file
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "recordings_uncompressed")

def main():
    # 1. Setup Output Directory and Filename
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"[INFO] Created directory: {OUTPUT_DIR}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Using .avi file extension
    file_path = os.path.join(OUTPUT_DIR, f"cam{CAM_ID}_{timestamp}_UNCOMPRESSED.avi")

    # 2. Initialize Camera
    print(f"[INFO] Opening camera {CAM_ID}...")
    cap = cv2.VideoCapture(CAM_ID)

    # Set properties
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    
    # Optional: Request MJPG input from the camera for fast reading
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')) 

    if not cap.isOpened():
        print(f"[CRITICAL ERROR] Failed to open camera {CAM_ID}.")
        sys.exit(1)

    # 3. Initialize Video Writer for UNCOMPRESSED Output
    # The 'I420' codec is a widely supported uncompressed YUV format
    fourcc = cv2.VideoWriter_fourcc(*'I420') 
    
    out = cv2.VideoWriter(file_path, fourcc, FPS, (FRAME_WIDTH, FRAME_HEIGHT))

    if not out.isOpened():
        print(f"[CRITICAL ERROR] Failed to initialize video writer with uncompressed I420 codec.")
        print("                 This suggests a fundamental issue with FFmpeg libraries.")
        cap.release()
        sys.exit(1)

    print(f"[INFO] Recording started (Target FPS: {FPS})...")
    print(f"[NOTE] OUTPUT FILE WILL BE VERY LARGE (UNCOMPRESSED).")
    print(f"       Saving to: {file_path}")
    print("Press 'q' to stop recording.")

    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                print("[WARN] Failed to read frame. Exiting loop.")
                break

            # Write the frame to the file
            out.write(frame)

            # Draw status and display preview
            cv2.putText(frame, f"REC | UNCOMPRESSED ({FPS:.0f} FPS)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.imshow("Single Camera Recorder (UNCOMPRESSED)", frame)

            frame_count += 1

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[INFO] Stop signal received.")
                break

    except Exception as e:
        print(f"[CRITICAL ERROR] An unexpected exception occurred: {e}")

    # 4. Cleanup
    print("[INFO] Cleaning up resources...")
    cap.release()
    out.release()
    cv2.destroyAllWindows()

    print(f"[INFO] Saved {frame_count} frames.")
    print("[INFO] Recording complete.")

if __name__ == "__main__":
    main()