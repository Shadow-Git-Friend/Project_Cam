
import cv2
import time
from ultralytics import YOLO
import sys

# CONFIG
MODEL_PATH = "yolo11s_custom_ball.pt"
CAM_ID = 0 # Testing on Cam 0 first
CONF_THRESHOLD = 0.4
IMG_SIZE = 640

def main():
    print(f"--- 2D Detection Verification ---")
    print(f"Model: {MODEL_PATH}")
    print(f"Camera: {CAM_ID}")
    
    # Load Model
    try:
        model = YOLO(MODEL_PATH)
        print("[OK] Model loaded.")
    except Exception as e:
        print(f"[ERROR] Could not load model: {e}")
        return

    # Open Camera
    cap = cv2.VideoCapture(CAM_ID)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    
    if not cap.isOpened():
        print(f"[ERROR] Could not open Camera {CAM_ID}")
        return

    print("Press 'q' to exit.")
    
    prev_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Frame drop")
            break
            
        # Inference
        # stream=True is efficient for video
        results = model(frame, conf=CONF_THRESHOLD, imgsz=IMG_SIZE, verbose=False, stream=False)
        
        # Annotate
        annotated_frame = results[0].plot()
        
        # FPS Calculation
        curr_time = time.time()
        fps = 1 / (curr_time - prev_time)
        prev_time = curr_time
        
        # Draw FPS
        cv2.putText(annotated_frame, f"FPS: {fps:.1f}", (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        # Display
        cv2.imshow('2D Verification (Cam 0)', annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
