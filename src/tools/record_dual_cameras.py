import cv2
import argparse
import time
import os
import numpy as np

def record_dual_video(id1: int, id2: int, out1: str, out2: str, duration: int):
    print(f"[INFO] Инициализация камер {id1} и {id2}...")

    cap1 = cv2.VideoCapture(id1)
    cap2 = cv2.VideoCapture(id2)

    if not cap1.isOpened() or not cap2.isOpened():
        print("[ERROR] Не могу открыть одну из камер!")
        return

    # --- Настройки (подгоните под ваши возможности USB) ---
    # Ставим 640x480 для стабильности двух камер на одной шине
    req_w, req_h = 640, 480 
    fps = 30.0

    for cap in [cap1, cap2]:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, req_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req_h)
        cap.set(cv2.CAP_PROP_FPS, fps)

    # Получаем реальные параметры (важно для VideoWriter)
    w1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
    h1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w2 = int(cap2.get(cv2.CAP_PROP_FRAME_WIDTH))
    h2 = int(cap2.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"[INFO] Cam {id1}: {w1}x{h1}")
    print(f"[INFO] Cam {id2}: {w2}x{h2}")

    # Кодек mp4v
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    
    writer1 = cv2.VideoWriter(out1, fourcc, fps, (w1, h1))
    writer2 = cv2.VideoWriter(out2, fourcc, fps, (w2, h2))

    if not writer1.isOpened() or not writer2.isOpened():
        print("[ERROR] Не могу создать файлы записи!")
        return

    print(f"[INFO] Начало записи на {duration} секунд...")
    print(f" > {out1}")
    print(f" > {out2}")
    print("[INFO] Нажмите 'q' для ранней остановки.")

    start_time = time.time()
    frames_written = 0

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()

        if not ret1 or not ret2:
            print("[WARN] Потеря кадра на одной из камер. Остановка.")
            break

        writer1.write(frame1)
        writer2.write(frame2)
        frames_written += 1

        # Визуализация (горизонтальный стэк)
        # Если размеры разные, ресайзим для превью
        if h1 != h2:
            frame2_resized = cv2.resize(frame2, (w1, h1))
            preview = np.hstack((frame1, frame2_resized))
        else:
            preview = np.hstack((frame1, frame2))
        
        # Уменьшаем превью, чтобы влезало в экран
        preview_small = cv2.resize(preview, (0,0), fx=0.7, fy=0.7)
        cv2.imshow("Dual Recording", preview_small)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        if time.time() - start_time > duration:
            print("[INFO] Время вышло.")
            break

    cap1.release()
    cap2.release()
    writer1.release()
    writer2.release()
    cv2.destroyAllWindows()
    print(f"[INFO] Записано {frames_written} кадров (пар).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id1", type=int, required=True, help="ID камеры 1")
    parser.add_argument("--id2", type=int, required=True, help="ID камеры 2")
    parser.add_argument("--name", type=str, required=True, help="Базовое имя файла (напр. session_01)")
    args = parser.parse_args()

    # Автоматические пути согласно вашему дереву
    base_dir = "data/lab_captures"
    path1 = os.path.join(base_dir, "cam0_videos", f"cam0_{args.name}.mp4")
    path2 = os.path.join(base_dir, "cam6_videos", f"cam6_{args.name}.mp4")

    # Создаем папки если нет
    os.makedirs(os.path.dirname(path1), exist_ok=True)
    os.makedirs(os.path.dirname(path2), exist_ok=True)

    record_dual_video(args.id1, args.id2, path1, path2, duration=120)

# **Как запустить запись:**
# Положите мяч на пол, возьмите его в руки, покатайте, побросайте. Нам нужно разнообразие.

# ```bash
# python src/tools/record_dual_cameras.py --id1 0 --id2 6 --name session_01