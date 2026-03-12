#!/usr/bin/env python3
"""
Open and view a single camera with FPS overlay.

Usage:
  python3 simple_cam.py [camera_index] [width height] [display_scale]

Examples:
  python3 simple_cam.py 0
  python3 simple_cam.py 2 1920 1080
  python3 simple_cam.py 2 1920 1080 0.5
"""

import cv2
import sys
import time


def main() -> int:
    # Defaults
    camera_index = 0
    width_arg = 1920
    height_arg = 1080
    display_scale = 1.0

    # Parse arguments
    if len(sys.argv) > 1:
        try:
            camera_index = int(sys.argv[1])
        except ValueError:
            print(f"Invalid camera index: {sys.argv[1]}")
            return 1

    if len(sys.argv) > 3:
        try:
            width_arg = int(sys.argv[2])
            height_arg = int(sys.argv[3])
        except ValueError:
            print("Invalid resolution arguments. Using defaults.")

    if len(sys.argv) > 4:
        try:
            display_scale = float(sys.argv[4])
        except ValueError:
            print("Invalid display_scale argument. Using default 1.0.")
            display_scale = 1.0

    if display_scale <= 0:
        print("display_scale must be > 0. Using default 1.0.")
        display_scale = 1.0

    print(f"Attempting to open camera {camera_index} at {width_arg}x{height_arg}...")
    cap = cv2.VideoCapture(camera_index)

    # Set resolution and MJPEG
    fourcc_ok = cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    width_ok = cap.set(cv2.CAP_PROP_FRAME_WIDTH, width_arg)
    height_ok = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height_arg)

    print(f"Set FOURCC MJPG: {fourcc_ok}")
    print(f"Set Width {width_arg}: {width_ok}")
    print(f"Set Height {height_arg}: {height_ok}")

    if not cap.isOpened():
        print(f"Error: Could not open camera {camera_index}")
        return 1

    # Get and print camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Successfully opened camera {camera_index}")
    print(f"Resolution: {width}x{height}")
    print(f"FPS: {fps}")
    print("Press 'q' to quit.")

    prev_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to read frame.")
            break

        # Calculate FPS
        curr_time = time.time()
        fps_val = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
        prev_time = curr_time

        # Optional display scaling (keeps capture resolution unchanged)
        if display_scale != 1.0:
            disp_w = max(1, int(frame.shape[1] * display_scale))
            disp_h = max(1, int(frame.shape[0] * display_scale))
            display_frame = cv2.resize(frame, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
        else:
            display_frame = frame

        # Display FPS on frame
        cv2.putText(
            display_frame,
            f"FPS: {fps_val:.1f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

        cv2.imshow(f"Camera {camera_index}", display_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
