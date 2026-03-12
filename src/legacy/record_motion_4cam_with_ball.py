import cv2
import numpy as np
import json
import time
import sys
from pathlib import Path
from ultralytics import YOLO

# --- НАСТРОЙКИ ПУТЕЙ ---
CURRENT_FILE = Path(__file__).resolve()
SRC_DIR = CURRENT_FILE.parent
PROJECT_ROOT = SRC_DIR.parent
sys.path.append(str(SRC_DIR))

# Импорт математики
try:
    from triangulate_v2 import triangulate_point, build_projection_matrices
    from calibration_utils import load_all_intrinsics, load_extrinsics
except ImportError as e:
    print(f"[CRITICAL ERROR] Не найдены файлы v2: {e}")
    sys.exit(1)

# --- КОНФИГУРАЦИЯ КАМЕР ---
CAM_IDS = [0, 2, 4, 6] 
CAM_NAMES = ["cam0", "cam2", "cam4", "cam6"]

OUTPUT_FILE = PROJECT_ROOT / "motion_capture_4cam_data_new.json"
CALIB_DIR = PROJECT_ROOT / "cal" / "calibration_v2"
EXTRINSICS_FILE = CALIB_DIR / "extrinsics.json"

# --- МОДЕЛИ ИИ ---
# 1. Скелет (RTMPose)
try:
    from mmpose.apis import MMPoseInferencer
except ImportError:
    print("[CRITICAL] MMPose not installed!")
    sys.exit(1)

POSE_MODEL = 'rtmpose-m_8xb256-420e-coco-256x192' 
DET_MODEL = 'rtmdet-m' 

# 2. Мяч (YOLO)
# Путь к вашей обученной модели. Если её нет, используем стандартную
BALL_MODEL_PATH = PROJECT_ROOT / "yolo11s_custom_ball.pt"
if not BALL_MODEL_PATH.exists():
    print(f"[WARN] Кастомная модель мяча не найдена в {BALL_MODEL_PATH}")
    print("[INFO] Использую стандартную yolov8n.pt (будет искать 'sports ball')")
    BALL_MODEL_PATH = "yolov8n.pt"
    BALL_CLASS_ID = 32 # sports ball в COCO
else:
    print(f"[INFO] Найдена кастомная модель мяча!")
    BALL_CLASS_ID = 0 # Обычно в кастомных датасетах мяч - это класс 0

# Цвета
GREEN = (0, 255, 0); RED = (0, 0, 255); YELLOW = (0, 255, 255)

def init_rtmpose():
    print(f"[INFO] Загрузка RTMPose...")
    try:
        inferencer = MMPoseInferencer(pose2d=POSE_MODEL, det_model=DET_MODEL, device='cuda')
    except:
        inferencer = MMPoseInferencer(pose2d='human', device='cuda')
    return inferencer

def get_human_keypoints_batch(inferencer, frames):
    """Поиск людей (RTMPose)"""
    result_gen = inferencer(frames, return_vis=False, batch_size=4)
    batch_kpts = []
    results = list(result_gen)
    
    for res in results:
        preds = res['predictions']
        if not preds:
            batch_kpts.append(None)
            continue
            
        item = preds[0]
        if isinstance(item, list): item = item[0]
        if not isinstance(item, dict):
            try: item = item.to_dict()
            except: 
                batch_kpts.append(None)
                continue
        
        try:
            kpts = np.array(item['keypoints'])
            scores = np.array(item['keypoint_scores'])
            if len(kpts) > 17:
                kpts = kpts[:17]
                scores = scores[:17]
            kpts_combined = np.hstack([kpts, scores.reshape(-1, 1)])
            batch_kpts.append(kpts_combined)
        except:
            batch_kpts.append(None)
            
    return batch_kpts

def get_ball_detections_batch(model, frames):
    """
    Поиск мяча (YOLO).
    Возвращает список центров [(x, y, conf), None, (x, y, conf)...]
    """
    # Запускаем YOLO сразу на 4 кадрах
    results = model(frames, verbose=False, conf=0.4, classes=[BALL_CLASS_ID])
    
    batch_balls = []
    for res in results:
        boxes = res.boxes
        if len(boxes) > 0:
            # Берем самый уверенный мяч
            best_idx = np.argmax(boxes.conf.cpu().numpy())
            x, y, w, h = boxes.xywh[best_idx].cpu().numpy()
            conf = float(boxes.conf[best_idx].cpu().numpy())
            batch_balls.append((x, y, conf))
        else:
            batch_balls.append(None)
    return batch_balls

def draw_skeleton(frame, kpts, color):
    if kpts is None: return
    connections = [(5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), (12, 14), (14, 16), (5, 6), (11, 12)]
    for kp in kpts:
        if kp[2] > 0.4: cv2.circle(frame, (int(kp[0]), int(kp[1])), 3, color, -1)
    for i, j in connections:
        if i < len(kpts) and j < len(kpts) and kpts[i][2] > 0.4 and kpts[j][2] > 0.4:
            cv2.line(frame, (int(kpts[i][0]), int(kpts[i][1])), (int(kpts[j][0]), int(kpts[j][1])), color, 2)

def main():
    # 1. ЗАГРУЗКА КАЛИБРОВКИ
    if not CALIB_DIR.exists():
        print(f"[ERROR] Папка {CALIB_DIR} не найдена!")
        return

    print(f"[INFO] Загрузка калибровки 4 камер...")
    intrinsics_map = load_all_intrinsics(CALIB_DIR)
    extrinsics = load_extrinsics(EXTRINSICS_FILE)
    ref_cam = extrinsics[next(iter(extrinsics))].reference
    projections = build_projection_matrices(intrinsics_map, extrinsics, ref_cam)
    
    active_projections = []
    for name in CAM_NAMES:
        if name not in projections:
            print(f"[ERROR] Нет калибровки для камеры {name}")
            return
        active_projections.append(projections[name])
    
    print(f"[SUCCESS] Матрицы готовы.")

    # 2. ЗАПУСК МОДЕЛЕЙ
    rtmpose = init_rtmpose()
    print(f"[INFO] Загрузка YOLO для мяча...")
    ball_model = YOLO(str(BALL_MODEL_PATH))

    # 3. КАМЕРЫ
    caps = []
    print("[INFO] Открываю камеры...")
    for cam_id in CAM_IDS:
        cap = cv2.VideoCapture(cam_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 704)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 576)
        caps.append(cap)

    recorded_frames = []
    is_recording = False
    
    print("\n" + "="*60)
    print(f"[READY] 4-Camera Human + Ball Tracking.")
    print("[R] - Record | [Q] - Quit")
    print("="*60 + "\n")

    while True:
        frames = []
        for cap in caps:
            if cap.isOpened():
                ret, frame = cap.read()
                frames.append(frame if ret else np.zeros((576, 704, 3), dtype=np.uint8))
            else:
                frames.append(np.zeros((576, 704, 3), dtype=np.uint8))

        if not frames: break

        # --- AI INFERENCE (Double Batch) ---
        # Сначала ищем людей, потом мячи. Это нагрузит GPU.
        all_kpts = get_human_keypoints_batch(rtmpose, frames)
        all_balls = get_ball_detections_batch(ball_model, frames)

        # --- VISUALIZATION ---
        vis_frames = []
        valid_cams_count = 0
        
        for i, frame in enumerate(frames):
            vis = frame.copy()
            kpts = all_kpts[i]
            ball = all_balls[i]
            
            # Скелет
            if kpts is not None and np.sum(kpts[:, 2] > 0.5) > 6:
                color = GREEN
                valid_cams_count += 1
                draw_skeleton(vis, kpts, color)
            else:
                color = RED
                
            # Мяч (Желтый круг)
            if ball is not None:
                bx, by, bconf = ball
                cv2.circle(vis, (int(bx), int(by)), 8, YELLOW, 2)
                cv2.circle(vis, (int(bx), int(by)), 4, YELLOW, -1)
            
            cv2.rectangle(vis, (0,0), (vis.shape[1], vis.shape[0]), color, 3)
            cv2.putText(vis, f"{CAM_NAMES[i]}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            vis_frames.append(vis)

        # Grid view 2x2
        top_row = np.hstack((vis_frames[0], vis_frames[1]))
        bot_row = np.hstack((vis_frames[2], vis_frames[3]))
        grid_view = np.vstack((top_row, bot_row))
        grid_view_small = cv2.resize(grid_view, (0,0), fx=0.6, fy=0.6)

        # --- RECORDING LOGIC ---
        if is_recording:
            cv2.putText(grid_view_small, f"REC: {len(recorded_frames)}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, RED, 2)
            
            frame_entry = {"joints": [], "ball": None}
            
            # 1. ТРИАНГУЛЯЦИЯ СКЕЛЕТА
            for j in range(17):
                measurements = []
                for cam_idx in range(4):
                    kpts = all_kpts[cam_idx]
                    if kpts is not None and kpts[j][2] > 0.5:
                        measurements.append((active_projections[cam_idx], kpts[j][0], kpts[j][1]))
                
                if len(measurements) >= 2:
                    try:
                        p3d = triangulate_point(measurements)
                        frame_entry["joints"].append((p3d * 1000.0).tolist()) # Meters -> mm
                    except: frame_entry["joints"].append(None)
                else: frame_entry["joints"].append(None)
            
            # 2. ТРИАНГУЛЯЦИЯ МЯЧА
            ball_measurements = []
            for cam_idx in range(4):
                ball = all_balls[cam_idx] # (x, y, conf)
                if ball is not None:
                    ball_measurements.append((active_projections[cam_idx], ball[0], ball[1]))
            
            if len(ball_measurements) >= 2:
                try:
                    ball_3d = triangulate_point(ball_measurements)
                    frame_entry["ball"] = (ball_3d * 1000.0).tolist() # Meters -> mm
                except: pass
            
            recorded_frames.append(frame_entry)

        cv2.imshow("4-Cam Human+Ball", grid_view_small)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        if key == ord('r'):
            if valid_cams_count < 2 and not is_recording:
                print("[WARN] Человека плохо видно.")
            else:
                is_recording = not is_recording
                if is_recording: recorded_frames = []
                else: print(f"[STOP] Записано {len(recorded_frames)}.")

    if recorded_frames:
        print(f"[INFO] Сохраняем данные...")
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(recorded_frames, f)
        print(f"[SUCCESS] Готово: {OUTPUT_FILE}")

    for cap in caps: cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()