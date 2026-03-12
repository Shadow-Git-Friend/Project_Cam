
import cv2
import mediapipe as mp
import json
import numpy as np
from pathlib import Path

# --- CONFIG ---
TASK_LIST = [
    {
        "input": "data/raw/cam4_20251215_223702.mp4",
        "out_vid": "output/videos/output_mp_camA.mp4", 
        "out_data": "data/processed/data_mp_camA.json"
    },
    {
        "input": "data/raw/cam2_20251215_223702.mp4",
        "out_vid": "output/videos/output_mp_camB.mp4",
        "out_data": "data/processed/data_mp_camB.json"
    }
]

def process_video(input_file, output_vid, output_data, mp_holistic, mp_drawing, mp_drawing_styles):
    input_path = Path(input_file).resolve()
    if not input_path.exists():
        print(f"[ERROR] Input video not found: {input_path}")
        return

    cap = cv2.VideoCapture(str(input_path))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_vid, fourcc, fps, (width, height))
    
    print(f"Processing {input_path.name} -> {output_vid}...")
    
    data_log = []
    frame_idx = 0

    with mp_holistic.Holistic(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=1) as holistic:
        
        while cap.isOpened():
            success, image = cap.read()
            if not success:
                break

            # Process
            image.flags.writeable = False
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = holistic.process(image_rgb)

            # Draw
            image.flags.writeable = True
            image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
            
            # 1. Face
            mp_drawing.draw_landmarks(
                image,
                results.face_landmarks,
                mp_holistic.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style())
            
            # 2. Pose
            mp_drawing.draw_landmarks(
                image,
                results.pose_landmarks,
                mp_holistic.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style())

            # 3. Hands
            mp_drawing.draw_landmarks(image, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            mp_drawing.draw_landmarks(image, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            
            # Save Data
            frame_data = {"frame": frame_idx}
            if results.pose_landmarks:
                frame_data["pose"] = [[lm.x, lm.y, lm.z, lm.visibility] for lm in results.pose_landmarks.landmark]
            if results.left_hand_landmarks:
                frame_data["left_hand"] = [[lm.x, lm.y, lm.z] for lm in results.left_hand_landmarks.landmark]
            if results.right_hand_landmarks:
                frame_data["right_hand"] = [[lm.x, lm.y, lm.z] for lm in results.right_hand_landmarks.landmark]
            
            data_log.append(frame_data)

            out.write(image)
            frame_idx += 1
            if frame_idx % 50 == 0:
                print(f"Processed {frame_idx} frames...")
                
    cap.release()
    out.release()
    
    with open(output_data, 'w') as f:
        json.dump(data_log, f)
        
    print(f"Done! Saved video to {output_vid} and data to {output_data}")

def main():
    mp_holistic = mp.solutions.holistic
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles

    for task in TASK_LIST:
        process_video(task["input"], task["out_vid"], task["out_data"], mp_holistic, mp_drawing, mp_drawing_styles)


if __name__ == "__main__":
    main()
