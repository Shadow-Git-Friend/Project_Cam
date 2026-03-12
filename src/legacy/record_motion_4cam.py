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

# Импортируем математику (V2)
try:
    from triangulate_v2 import triangulate_point, build_projection_matrices
    from calibration_utils import load_all_intrinsics, load_extrinsics
except ImportError as e:
    print(f"[CRITICAL ERROR] Не найдены файлы v2: {e}")
    sys.exit(1)

# --- КОНФИГУРАЦИЯ КАМЕР ---
# ID камер в системе (проверь через v4l2-ctl --list-devices или методом тыка)
# Обычно это 0, 2, 4, 6 или 0, 1, 2, 3. 
# ВНИМАНИЕ: Поставь сюда свои реальные индексы USB портов!
CAM_IDS = [0, 2, 4, 6] 

# Имена камер, соответствующие файлам json (cam0_intrinsics.json и т.д.)
# Порядок должен совпадать с CAM_IDS!
CAM_NAMES = ["cam0", "cam2", "cam4", "cam6"]

OUTPUT_FILE = PROJECT_ROOT / "motion_capture_4cam_data.json"
CALIB_DIR = PROJECT_ROOT / "cal" / "calibration_v2" # Папка с файлами коллеги
EXTRINSICS_FILE = CALIB_DIR / "extrinsics.json"

# --- ИМПОРТ RTMPose ---
try:
    from mmpose.apis import MMPoseInferencer
except ImportError:
    print("[CRITICAL] MMPose not installed!")
    sys.exit(1)

POSE_MODEL = 'rtmpose-m_8xb256-420e-coco-256x192' 
DET_MODEL = 'rtmdet-m' 

GREEN = (0, 255, 0); RED = (0, 0, 255); BLUE = (255, 0, 0)

def init_rtmpose():
    print(f"[INFO] Загрузка RTMPose 4-CAM Edition...")
    try:
        inferencer = MMPoseInferencer(pose2d=POSE_MODEL, det_model=DET_MODEL, device='cuda')
    except:
        inferencer = MMPoseInferencer(pose2d='human', device='cuda')
    return inferencer

def get_keypoints_batch(inferencer, frames):
    """
    Обрабатывает сразу список кадров (Batch Inference).
    Возвращает список результатов для каждого кадра.
    """
    # MMPose умеет работать с батчем, это быстрее
    result_gen = inferencer(frames, return_vis=False, batch_size=4)
    
    batch_kpts = []
    
    # Собираем результаты для всех камер
    # inferencer возвращает генератор, мы должны пройтись по нему
    results = list(result_gen)
    
    for res in results:
        preds = res['predictions']
        if not preds:
            batch_kpts.append(None)
            continue
            
        # Распаковка (как мы делали раньше)
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
            # [17, 3] -> x, y, conf
            kpts_combined = np.hstack([kpts, scores.reshape(-1, 1)])
            batch_kpts.append(kpts_combined)
        except:
            batch_kpts.append(None)
            
    return batch_kpts

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
    
    # Строим матрицы проекции (P) для ВСЕХ камер
    projections = build_projection_matrices(intrinsics_map, extrinsics, ref_cam)
    
    # Проверка наличия матриц для всех наших имен
    active_projections = []
    for name in CAM_NAMES:
        if name not in projections:
            print(f"[ERROR] Нет калибровки для камеры {name}. Доступны: {list(projections.keys())}")
            return
        active_projections.append(projections[name])
    
    print(f"[SUCCESS] Матрицы готовы для: {CAM_NAMES}")

    # 2. ЗАПУСК RTMPose
    rtmpose = init_rtmpose()

    # 3. ОТКРЫТИЕ КАМЕР
    caps = []
    print("[INFO] Открываю камеры...")
    for cam_id in CAM_IDS:
        cap = cv2.VideoCapture(cam_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 704) # Или 640/1280
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 576) # Или 480/720
        # cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')) # Если лагает USB
        if not cap.isOpened():
            print(f"[WARN] Не удалось открыть камеру ID {cam_id}")
        caps.append(cap)

    recorded_frames = []
    is_recording = False
    
    print("\n" + "="*60)
    print(f"[READY] 4-Camera System Active.")
    print(f"Cameras: {len(caps)} connected.")
    print("[R] - Record | [Q] - Quit")
    print("="*60 + "\n")

    while True:
        frames = []
        # Читаем кадры со всех камер
        for cap in caps:
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    frames.append(frame)
                else:
                    frames.append(np.zeros((576, 704, 3), dtype=np.uint8)) # Черный экран при ошибке
            else:
                frames.append(np.zeros((576, 704, 3), dtype=np.uint8))

        if not frames: break

        # AI (Batch processing)
        all_kpts = get_keypoints_batch(rtmpose, frames) # Список из 4 наборов точек

        # Визуализация (Сетка 2x2)
        # Рисуем скелеты на каждом кадре
        vis_frames = []
        valid_cams_count = 0
        
        for i, frame in enumerate(frames):
            vis = frame.copy()
            kpts = all_kpts[i]
            
            # Проверка видимости
            if kpts is not None and np.sum(kpts[:, 2] > 0.5) > 6:
                color = GREEN
                valid_cams_count += 1
            else:
                color = RED
            
            draw_skeleton(vis, kpts, color)
            cv2.rectangle(vis, (0,0), (vis.shape[1], vis.shape[0]), color, 3)
            cv2.putText(vis, f"{CAM_NAMES[i]}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            vis_frames.append(vis)

        # Склеиваем 2x2
        top_row = np.hstack((vis_frames[0], vis_frames[1]))
        bot_row = np.hstack((vis_frames[2], vis_frames[3]))
        grid_view = np.vstack((top_row, bot_row))
        
        # Ресайз для экрана, если слишком большое
        grid_view_small = cv2.resize(grid_view, (0,0), fx=0.6, fy=0.6)

        # --- ЗАПИСЬ ---
        if is_recording:
            cv2.putText(grid_view_small, f"REC: {len(recorded_frames)}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, RED, 2)
            
            frame_entry = {"joints": []}
            
            # Проходим по 17 суставам
            for j in range(17):
                # Собираем данные со всех 4 камер для этого сустава
                measurements = []
                
                for cam_idx in range(4):
                    kpts = all_kpts[cam_idx]
                    # Если камера видит этот сустав уверенно (>0.5)
                    if kpts is not None and kpts[j][2] > 0.5:
                        u, v = kpts[j][0], kpts[j][1]
                        P = active_projections[cam_idx] # Матрица этой камеры
                        measurements.append((P, u, v))
                
                # Если сустав виден МИНИМУМ 2 камерами -> Триангулируем
                if len(measurements) >= 2:
                    try:
                        # Эта функция из v2 умеет принимать N камер!
                        p3d = triangulate_point(measurements) 
                        
                        # Конвертируем в мм (обычно калибровка в метрах)
                        p3d_mm = p3d * 1000.0
                        frame_entry["joints"].append(p3d_mm.tolist())
                    except:
                        frame_entry["joints"].append(None)
                else:
                    frame_entry["joints"].append(None) # Недостаточно данных
            
            recorded_frames.append(frame_entry)

        cv2.imshow("4-Cam Motion Capture", grid_view_small)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        if key == ord('r'):
            if valid_cams_count < 2 and not is_recording:
                print("[WARN] Меньше 2 камер видят человека. Запись невозможна.")
            else:
                is_recording = not is_recording
                if is_recording: recorded_frames = []
                else: print(f"[STOP] Записано {len(recorded_frames)} кадров.")

    if recorded_frames:
        print(f"[INFO] Сохраняем мультикамерные данные...")
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(recorded_frames, f)
        print(f"[SUCCESS] Сохранено в {OUTPUT_FILE}")

    for cap in caps: cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()