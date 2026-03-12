
import cv2
import time
import os

def capture_images():
    # Configuration
    CAM_ID_2 = 0
    CAM_ID_4 = 2
    OUTPUT_DIR = os.getcwd() # Save in current directory

    # Countdown
    print("Starting 10-second countdown...")
    for i in range(10, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    print("Capturing now!")

    print(f"Initializing Camera {CAM_ID_2}...")
    cap2 = cv2.VideoCapture(CAM_ID_2)
    # Set MJPG for better compatibility/speed on some systems, though not strictly necessary for a single frame
    cap2.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap2.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap2.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    
    print(f"Initializing Camera {CAM_ID_4}...")
    cap4 = cv2.VideoCapture(CAM_ID_4)
    cap4.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap4.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap4.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    if not cap2.isOpened():
        print(f"Error: Could not open Camera {CAM_ID_2}")
    if not cap4.isOpened():
        print(f"Error: Could not open Camera {CAM_ID_4}")

    # Warmup / Buffer clear (optional but good practice)
    for _ in range(5):
        if cap2.isOpened(): cap2.read()
        if cap4.isOpened(): cap4.read()
        time.sleep(0.05)



    # Capture
    frame2 = None
    frame4 = None

    if cap2.isOpened():
        ret2, frame2 = cap2.read()
        if ret2:
            filename2 = os.path.join(OUTPUT_DIR, "B_6.jpg")
            cv2.imwrite(filename2, frame2)
            print(f"Saved {filename2}")
        else:
            print(f"Failed to grab frame from Camera {CAM_ID_2}")

    if cap4.isOpened():
        ret4, frame4 = cap4.read()
        if ret4:
            filename4 = os.path.join(OUTPUT_DIR, "A_6.jpg")
            cv2.imwrite(filename4, frame4)
            print(f"Saved {filename4}")
        else:
            print(f"Failed to grab frame from Camera {CAM_ID_4}")

    # Release
    if cap2.isOpened(): cap2.release()
    if cap4.isOpened(): cap4.release()

if __name__ == "__main__":
    capture_images()
