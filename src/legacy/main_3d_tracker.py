import cv2
import numpy as np
import argparse
import time
import os
import sys
from pathlib import Path

# --- НАСТРОЙКА ПУТЕЙ ---
# Получаем путь к текущему файлу (src/main_3d_tracker.py)
CURRENT_FILE = Path(__file__).resolve()
SRC_DIR = CURRENT_FILE.parent       # папка src/
PROJECT_ROOT = SRC_DIR.parent       # папка Project_Cam/

# Добавляем src в path, чтобы импорты работали корректно
sys.path.append(str(SRC_DIR))

# Импорт математики из соседнего файла src/triangulate_3d.py
from triangulate_3d import load_full_calibration, triangulate_point

try:
    from ultralytics import YOLO
except ImportError:
    print("[CRITICAL] 'ultralytics' not installed. pip install ultralytics")
    sys.exit(1)

# --- КОНФИГУРАЦИЯ ---
CAM_ID_1 = 0
CAM_ID_2 = 6

FRAME_WIDTH = 704
FRAME_HEIGHT = 576

# Пути по умолчанию (автоматически строятся от корня проекта)
DEFAULT_CALIB = PROJECT_ROOT / "cal" / "calibration_full_2cam.json"
# Используем вашу кастомную модель, если она есть, иначе базовую
DEFAULT_MODEL = PROJECT_ROOT / "yolo11s_custom_ball.pt" 
if not DEFAULT_MODEL.exists():
    DEFAULT_MODEL = PROJECT_ROOT / "yolov8n.pt"

TARGET_CLASS_ID = 0  # Обычно 0 для кастомных моделей с одним классом

def init_cameras(id1, id2):
    print(f"[INFO] Connecting to cameras {id1} and {id2}...")
    c1 = cv2.VideoCapture(id1)
    c2 = cv2.VideoCapture(id2)
    
    # Настройка разрешения
    for c in [c1, c2]:
        c.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    
    if not c1.isOpened() or not c2.isOpened():
        print("[ERROR] Failed to open cameras.")
        return None, None
    return c1, c2

def detect_ball(model, frame, conf_thresh):
    """Возвращает (x, y) и confidence."""
    results = model.predict(frame, verbose=False, conf=conf_thresh, classes=[TARGET_CLASS_ID])
    if not results or len(results[0].boxes) == 0:
        return None, None
        
    # Лучший бокс
    box = results[0].boxes[0] # ultralytics обычно сортирует по conf, берем 0-й
    x, y, w, h = box.xywh[0].cpu().numpy()
    conf = float(box.conf[0].cpu().numpy())
    
    return (int(x), int(y)), conf

def draw_info(frame, text, pos, color=(0,255,0), scale=0.6):
    x, y = pos
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    cv2.rectangle(frame, (x-5, y-h-5), (x+w+5, y+5), (0,0,0), -1)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calib", type=str, default=str(DEFAULT_CALIB), help="Path to json calibration")
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL), help="Path to .pt model")
    parser.add_argument("--conf", type=float, default=0.5, help="YOLO confidence")
    args = parser.parse_args()

    # 1. Загрузка калибровки
    calib_data = load_full_calibration(args.calib)
    if calib_data is None:
        return

    # 2. Загрузка модели
    print(f"[INFO] Loading Model: {args.model}")
    model = YOLO(args.model)

    # 3. Камеры
    cap1, cap2 = init_cameras(CAM_ID_1, CAM_ID_2)
    if not cap1: return

    print("[INFO] Started. Press 'q' to quit.")
    
    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()
        if not ret1 or not ret2:
            print("[WARN] Frame drop.")
            break

        start_t = time.time()

        # Детекция
        pt1, conf1 = detect_ball(model, frame1, args.conf)
        pt2, conf2 = detect_ball(model, frame2, args.conf)

        # Триангуляция
        p3d = None
        if pt1 and pt2:
            p3d = triangulate_point(calib_data, CAM_ID_1, CAM_ID_2, pt1, pt2)

        # Отрисовка Cam 1
        if pt1:
            cv2.circle(frame1, pt1, 6, (0,255,255), 2)
            draw_info(frame1, f"C:{conf1:.2f}", (pt1[0]+10, pt1[1]))
            
        # Отрисовка Cam 2
        if pt2:
            cv2.circle(frame2, pt2, 6, (0,255,255), 2)
            draw_info(frame2, f"C:{conf2:.2f}", (pt2[0]+10, pt2[1]))

        combined = np.hstack((frame1, frame2))

        # Вывод 3D
        if p3d is not None:
            X, Y, Z = p3d
            dist_m = np.sqrt(X**2 + Y**2 + Z**2) / 1000.0
            
            # Текст: Координаты в ММ, Дистанция в Метрах
            text = f"X:{X:.0f} Y:{Y:.0f} Z:{Z:.0f} (mm) | Dist: {dist_m:.2f}m"
            
            # Рисуем по центру
            tw = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0][0]
            cx = (combined.shape[1] - tw) // 2
            draw_info(combined, text, (cx, 40), (0, 255, 0), 0.8)
        else:
            draw_info(combined, "NO 3D LOCK", (10, 40), (0, 0, 255), 0.7)

        # FPS
        fps = 1.0 / (time.time() - start_t)
        draw_info(combined, f"FPS: {fps:.1f}", (10, combined.shape[0]-20), (200,200,200))

        cv2.imshow("Stereo 3D Tracker", combined)
        if cv2.waitKey(1) == ord('q'):
            break
            
    cap1.release()
    cap2.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()