import cv2
import numpy as np
import json
import time
import sys
from pathlib import Path

# --- НАСТРОЙКИ ---
CURRENT_FILE = Path(__file__).resolve()
SRC_DIR = CURRENT_FILE.parent
PROJECT_ROOT = SRC_DIR.parent
sys.path.append(str(SRC_DIR))

from triangulate_3d import load_full_calibration, triangulate_point

CAM_ID_1 = 0
CAM_ID_2 = 6
OUTPUT_FILE = PROJECT_ROOT / "motion_capture_data.json"
CALIB_FILE = PROJECT_ROOT / "cal" / "calibration_full_2cam.json"

# --- ИМПОРТ RTMPose (MMPose) ---
try:
    from mmpose.apis import MMPoseInferencer
except ImportError:
    print("[CRITICAL ERROR] Библиотека MMPose не найдена!")
    sys.exit(1)

# --- ВЫБОР МОДЕЛИ ---
# Используем полный путь, чтобы избежать ошибок поиска
POSE_MODEL = 'rtmpose-m_8xb256-420e-coco-256x192' 
DET_MODEL = 'rtmdet-m' 

# Цвета
GREEN = (0, 255, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)

def init_rtmpose():
    """Инициализация инференсера MMPose"""
    print(f"[INFO] Загрузка RTMPose ({POSE_MODEL}) + RTMDet...")
    try:
        # Попытка загрузить конкретную модель
        inferencer = MMPoseInferencer(
            pose2d=POSE_MODEL,
            det_model=DET_MODEL,
            device='cuda'
        )
    except Exception as e:
        print(f"[WARN] Не удалось загрузить конкретную модель: {e}")
        print("[INFO] Переключаюсь на алиас 'human' (стандартный RTMPose)...")
        inferencer = MMPoseInferencer(pose2d='human', device='cuda')
    return inferencer

def get_keypoints_rtmpose(inferencer, frame):
    """
    Получает ключевые точки через RTMPose и приводит их к формату (17, 3)
    Возвращает: np.array([[x, y, conf], ...]) или None
    """
    # inferencer возвращает генератор
    result_generator = inferencer(frame, return_vis=False)
    result = next(result_generator)
    
    predictions = result['predictions']
    
    if not predictions:
        return None
        
    # --- FIX: Умная распаковка (Handling Batch Dimension) ---
    # MMPose может вернуть [Person1] или [[Person1]]
    first_item = predictions[0]
    
    if isinstance(first_item, list):
        # Если внутри списка лежит еще один список (batch dim)
        if not first_item: return None
        person = first_item[0]
    else:
        # Если сразу словарь
        person = first_item
        
    # Проверка на то, что person это действительно словарь
    if not isinstance(person, dict):
        # Если вдруг это объект класса, попробуем превратить в dict (редкий кейс)
        try:
            person = person.to_dict()
        except:
            return None

    # Извлечение данных
    try:
        kpts = np.array(person['keypoints'])
        scores = np.array(person['keypoint_scores'])
    except KeyError:
        return None
    
    # Берем только первые 17 точек (COCO формат)
    if len(kpts) > 17:
        kpts = kpts[:17]
        scores = scores[:17]
    
    # Объединяем в формат (17, 3) -> [x, y, conf]
    # score reshape: (17,) -> (17, 1)
    kpts_with_conf = np.hstack([kpts, scores.reshape(-1, 1)])
    
    return kpts_with_conf

def draw_skeleton(frame, kpts, color):
    if kpts is None: return
    # Связи COCO
    connections = [(5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), (12, 14), (14, 16), (5, 6), (11, 12)]
    
    for kp in kpts:
        x, y, conf = int(kp[0]), int(kp[1]), kp[2]
        if conf > 0.4: 
            cv2.circle(frame, (x, y), 4, color, -1)
            
    for i, j in connections:
        if i < len(kpts) and j < len(kpts):
            if kpts[i][2] > 0.4 and kpts[j][2] > 0.4:
                pt1 = (int(kpts[i][0]), int(kpts[i][1]))
                pt2 = (int(kpts[j][0]), int(kpts[j][1]))
                cv2.line(frame, pt1, pt2, color, 2)

def is_good_detection(kpts, conf_thresh=0.5, min_kpts=6):
    if kpts is None: return False
    valid_count = np.sum(kpts[:, 2] > conf_thresh)
    return valid_count >= min_kpts

def main():
    calib = load_full_calibration(str(CALIB_FILE))
    if not calib:
        print("[ERROR] Нет калибровки!")
        return
    
    # 1. Инициализация RTMPose
    rtmpose_inferencer = init_rtmpose()
    
    cap1 = cv2.VideoCapture(CAM_ID_1)
    cap2 = cv2.VideoCapture(CAM_ID_2)
    
    for c in [cap1, cap2]:
        c.set(cv2.CAP_PROP_FRAME_WIDTH, 704)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 576)

    recorded_frames = []
    is_recording = False
    
    print("\n" + "="*50)
    print(f"[MODEL] RTMPose System Ready.")
    print("[R] - Старт/Стоп записи")
    print("[Q] - Выход")
    print("="*50 + "\n")

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()
        if not ret1 or not ret2: break

        vis1 = frame1.copy()
        vis2 = frame2.copy()
        
        # 1. Детекция (RTMPose)
        kpts1 = get_keypoints_rtmpose(rtmpose_inferencer, frame1)
        kpts2 = get_keypoints_rtmpose(rtmpose_inferencer, frame2)
        
        # 2. Проверка качества
        is_valid_1 = is_good_detection(kpts1, conf_thresh=0.5) 
        is_valid_2 = is_good_detection(kpts2, conf_thresh=0.5)
        user_visible = is_valid_1 and is_valid_2
        
        status_color = GREEN if user_visible else RED
        
        cv2.rectangle(vis1, (0,0), (704,576), status_color, 4)
        cv2.rectangle(vis2, (0,0), (704,576), status_color, 4)
        
        draw_skeleton(vis1, kpts1, status_color)
        draw_skeleton(vis2, kpts2, status_color)
        
        if not user_visible:
            msg = "POOR VISIBILITY"
            if kpts1 is None and kpts2 is None: msg = "USER NOT FOUND"
            cv2.putText(vis1, msg, (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, RED, 2)
            cv2.putText(vis2, msg, (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, RED, 2)
            
        elif is_recording:
            cv2.circle(vis1, (30, 30), 15, RED, -1)
            cv2.putText(vis1, f"REC: {len(recorded_frames)}", (60, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, RED, 2)
            cv2.putText(vis1, "RTMPose ACTIVE", (200, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, GREEN, 2)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            if not user_visible and not is_recording:
                print("[WARN] Не вижу человека четко. Запись заблокирована.")
            else:
                is_recording = not is_recording
                if is_recording:
                    recorded_frames = []
                    print("[REC] >>> ЗАПИСЬ <<<")
                else:
                    print(f"[STOP] Сохранено {len(recorded_frames)} кадров.")

        if is_recording:
            frame_data = {"joints": []}
            if user_visible:
                for i in range(17):
                    pt1 = kpts1[i]
                    pt2 = kpts2[i]
                    
                    if pt1[2] > 0.5 and pt2[2] > 0.5:
                        p3d = triangulate_point(calib, CAM_ID_1, CAM_ID_2, (pt1[0], pt1[1]), (pt2[0], pt2[1]))
                        if p3d is not None:
                            frame_data["joints"].append(p3d.tolist())
                        else:
                            frame_data["joints"].append(None)
                    else:
                        frame_data["joints"].append(None)
            else:
                frame_data["joints"] = [None] * 17
            
            recorded_frames.append(frame_data)

        preview = np.hstack((vis1, vis2))
        cv2.imshow("PRO Recorder (RTMPose)", preview)

    if recorded_frames:
        print(f"[INFO] Сохраняем JSON...")
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(recorded_frames, f)
        print("[SUCCESS] Файл сохранен.")

    cap1.release()
    cap2.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()