import cv2
import os
import glob
import argparse

def extract_frames(video_path, output_dir, step=10):
    """
    video_path: путь к mp4
    output_dir: куда сохранять jpg
    step: сохранять каждый n-й кадр
    """
    if not os.path.exists(video_path):
        print(f"[SKIP] Файл не найден: {video_path}")
        return

    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    
    # Получаем имя файла без расширения для префикса
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    count = 0
    saved = 0
    
    print(f"[INFO] Обработка {base_name}...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Сохраняем только каждый step-й кадр
        if count % step == 0:
            frame_name = f"{base_name}_frame_{count}.jpg"
            out_path = os.path.join(output_dir, frame_name)
            cv2.imwrite(out_path, frame)
            saved += 1
            
        count += 1
        
    cap.release()
    print(f" > Сохранено {saved} изображений в {output_dir}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=10, help="Шаг сохранения кадров (по дефолту каждый 10-й)")
    args = parser.parse_args()

    # Пути из вашего дерева
    videos_cam0 = glob.glob("data/lab_captures/cam0_videos/*.mp4")
    videos_cam6 = glob.glob("data/lab_captures/cam6_videos/*.mp4")

    out_cam0 = "data/lab_captures/cam0_frames"
    out_cam6 = "data/lab_captures/cam6_frames"

    print(f"[INFO] Найдено видео Cam0: {len(videos_cam0)}")
    print(f"[INFO] Найдено видео Cam6: {len(videos_cam6)}")

    for vid in videos_cam0:
        extract_frames(vid, out_cam0, args.step)
        
    for vid in videos_cam6:
        extract_frames(vid, out_cam6, args.step)

if __name__ == "__main__":
    main()