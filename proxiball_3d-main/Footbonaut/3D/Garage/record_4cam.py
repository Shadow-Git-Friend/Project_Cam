#!/usr/bin/env python3
"""
Sequential camera monitoring script.
Captures one frame from each camera in a loop (1 -> 2 -> 3 -> 4).
This avoids USB bandwidth limitations by ensuring only ONE camera is active at a time.
"""

import cv2
import time

def main():
    # Camera indices to cycle through
    # Note: Opening a camera takes time, so FPS will be low.
    camera_indices = [1, 2, 3, 4]
    
    print(f"Starting sequential monitoring for cameras: {camera_indices}")
    print("This mode opens/closes each camera in turn to save bandwidth.")
    print("Press 'q' in any window to exit.")
    print("-" * 50)
    
    running = True
    
    # Pre-create windows so they don't pop up/down constantly
    for idx in camera_indices:
        cv2.namedWindow(f'Camera {idx}')

    while running:
        for idx in camera_indices:
            # 1. Open Camera
            cap = cv2.VideoCapture(idx)
            
            # Use MJPG/Low Res even here to speed up initialization if possible
            # (Some drivers init faster with default, some with specific settings. 
            #  Let's try defaults first for speed, or MJPG if needed.)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            if not cap.isOpened():
                print(f"Skipping Camera {idx}: Could not open.")
                continue
            
            # 2. Read Frame
            # Sometimes the first frame is black/corrupt, read a couple?
            # For speed, let's try just 1. If bad, we can increase to 2.
            ret, frame = cap.read()
            
            # 3. Close Camera IMMEDIATELY to free bandwidth for next one
            cap.release()
            
            if ret:
                cv2.imshow(f'Camera {idx}', frame)
            else:
                print(f"Warning: Camera {idx} opened but returned no frame.")
                
            # 4. Handle Keypress
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                running = False
                break
                
        # Optional: Small sleep if needed, but the camera init delay is already a "sleep"
        # time.sleep(0.01)

    cv2.destroyAllWindows()
    print("Monitoring ended.")

if __name__ == "__main__":
    main()
