import cv2
import sys
import time
import os
from datetime import datetime

def main():
    # Defaults
    camera_index = 2
    width_arg = 1920
    height_arg = 1080
    output_folder = "/home/altay/Desktop/Footbonaut/Garage/Scenario2/"

    # Checks/Overrides from CLI (optional, but keeping for flexibility)
    if len(sys.argv) > 1:
        try:
            camera_index = int(sys.argv[1])
        except ValueError:
            print(f"Invalid camera index: {sys.argv[1]}")

    if len(sys.argv) > 3:
        try:
            width_arg = int(sys.argv[2])
            height_arg = int(sys.argv[3])
        except ValueError:
            print("Invalid resolution arguments. Using defaults.")

    # Ensure output directory exists
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Created directory: {output_folder}")

    print(f"Attempting to open camera {camera_index} at {width_arg}x{height_arg}...")
    cap = cv2.VideoCapture(camera_index)
   
    # Try different FOURCCs if MJPG fails, but MJPG is standard for high res USB cams
    fourcc_ok = cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    width_ok = cap.set(cv2.CAP_PROP_FRAME_WIDTH, width_arg)
    height_ok = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height_arg)
    
    print(f"Set FOURCC MJPG: {fourcc_ok}")
    print(f"Set Width {width_arg}: {width_ok}")
    print(f"Set Height {height_arg}: {height_ok}")

    if not cap.isOpened():
        print(f"Error: Could not open camera {camera_index}")
        return

    # Get actual camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        fps = 30.0 # Fallback default
        
    print(f"Successfully opened camera {camera_index}")
    print(f"Resolution: {width}x{height}")
    print(f"FPS: {fps}")
    
    # Setup Video Writer
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(output_folder, f"recording_cam{camera_index}_{timestamp}.avi")
    # MJPG is often safer for containers like AVI, or use XVID. 
    # Attempting XVID for recording.
    fourcc_writer = cv2.VideoWriter_fourcc(*'XVID') 
    out = cv2.VideoWriter(output_filename, fourcc_writer, fps, (width, height))
    
    print(f"Recording to: {output_filename}")
    print("Press 'q' to quit.")

    prev_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to read frame.")
            break

        # Write frame to video
        out.write(frame)

        # Calculate FPS for display only
        curr_time = time.time()
        fps_val = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
        prev_time = curr_time
        
        # Display FPS on the live feed (the recorded video will be clean unless we write this frame)
        # Requirement usually implies recording the raw feed, so we write 'frame' above.
        # Then we draw on 'display_frame'
        display_frame = frame.copy()
        cv2.putText(display_frame, f"FPS: {fps_val:.1f}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(display_frame, "REC", (10, 70), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        cv2.imshow(f'Camera {camera_index}', display_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print("Recording saved and resources released.")

if __name__ == "__main__":
    main()
