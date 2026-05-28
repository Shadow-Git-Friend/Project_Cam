import cv2
import sys
import os
import time

def capture_50_shots(camera_index, width=1920, height=1080):
    """
    Captures 50 images from the specified camera and saves them to the current directory.
    """
    print(f"Opening Camera {camera_index} at {width}x{height}...")
    cap = cv2.VideoCapture(camera_index)
    
    # Set high resolution (MJPG)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    if not cap.isOpened():
        print(f"Error: Could not open camera {camera_index}")
        return

    # Verify actual resolution
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera Open. Actual Resolution: {actual_w}x{actual_h}")

    if actual_w != width or actual_h != height:
        print(f"WARNING: Requested {width}x{height}, but got {actual_w}x{actual_h}")

    # Warmup camera (auto-exposure/white balance)
    print("Warming up camera...")
    for _ in range(30):
        cap.read()

    print("Starting capture of 50 shots...")
    output_dir = os.getcwd()  # Current directory (root)

    for i in range(50):
        ret, frame = cap.read()
        if not ret:
            print(f"Error reading frame {i+1}")
            continue

        filename = f"camEast_3_{i:02d}.jpg"
        filepath = os.path.join('/home/altay/Desktop/Footbonaut/Garage/Scenario3/camEast', filename)
        
        cv2.imwrite(filepath, frame)
        print(f"Saved: {filename}")
        
        # Small delay to avoid identical frames if FPS is low
        time.sleep(0.1)

    cap.release()
    print("-" * 30)
    print(f"Done! 50 images saved to {output_dir}")

if __name__ == "__main__":
   capture_50_shots(2)
   # if len(sys.argv) < 2:
   #     print("Usage: python capture_50_shots.py <camera_index>")
    #    # Default to camera 2 since that was the working one before
     #   print("Example: python capture_50_shots.py 2")
    #else:
     #   cam_idx = int(sys.argv[1])
      #  capture_50_shots(cam_idx)
