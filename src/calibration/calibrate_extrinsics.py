import cv2
import cv2.aruco as aruco
import numpy as np
import time
import argparse
import json
import os

# --- 0. Утилиты для работы с данными ---

# Класс для удобной работы с JSON (чтобы сохранять NumPy массивы)
class NumpyEncoder(json.JSONEncoder):
    """Класс для сериализации массивов NumPy в JSON-совместимый формат (списки)"""
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist() 
        return json.JSONEncoder.default(self, obj)

def load_intrinsics(filepath):
    """Загружает матрицу камеры (K) и коэффициенты искажения (D) из .npz файла"""
    try:
        with np.load(filepath) as data:
            mtx = data['mtx']
            dist = data['dist']
            return mtx, dist
    except Exception as e:
        # Критическая ошибка при загрузке файла, приводит к выходу из программы
        print(f"[ERROR] Не могу загрузить файл {filepath}. Ошибка: {e}")
        return None, None

def setup_charuco_board():
    """Настраивает параметры НАШЕЙ доски ChArUco (7x10)"""
    # --- ПАРАМЕТРЫ ВАШЕЙ ДОСКИ ---
    board_params = {
        "SQUARES_X": 5,
        "SQUARES_Y": 7,
        "SQUARE_SIZE_MM": 155.0,
        "MARKER_SIZE_MM": 113.66,
        "ARUCO_DICT": aruco.DICT_4X4_50
    }
    
    dictionary = aruco.getPredefinedDictionary(board_params["ARUCO_DICT"])
    
    # Создание доски
    try:
        board = aruco.CharucoBoard((board_params["SQUARES_X"], board_params["SQUARES_Y"]),
                                   board_params["SQUARE_SIZE_MM"],
                                   board_params["MARKER_SIZE_MM"],
                                   dictionary)
    except AttributeError:
        # Fallback для старых версий OpenCV
        board = aruco.CharucoBoard_create(board_params["SQUARES_X"], board_params["SQUARES_Y"],
                                          board_params["SQUARE_SIZE_MM"],
                                          board_params["MARKER_SIZE_MM"],
                                          dictionary)
    
    detector_parameters = aruco.DetectorParameters()
    # Tuning for small/distant markers (A3 board at 2m)
    detector_parameters.minMarkerPerimeterRate = 0.01
    detector_parameters.adaptiveThreshWinSizeMin = 3
    detector_parameters.adaptiveThreshWinSizeMax = 23
    detector_parameters.adaptiveThreshWinSizeStep = 5
    
    try:
        detector = aruco.ArucoDetector(dictionary, detector_parameters)
        use_new_detector = True
    except AttributeError:
        detector = None 
        use_new_detector = False
        
    return board, dictionary, detector, detector_parameters, use_new_detector

# --- 1. Основная логика калибровки ---

def main():
    parser = argparse.ArgumentParser(description="Калибровка внешних параметров (Extrinsics) для N-камер.")
    parser.add_argument("-i", "--id", type=int, required=True, action="append",
                        help="ID камеры (e.g., --id 0 --id 6).")
    parser.add_argument("-f", "--file", type=str, required=True, action="append",
                        help="Путь к .npz файлу с Intrinsics (e.g., --file cal/cam0.npz).")
    parser.add_argument("-o", "--output", type=str, default="cal/calibration_full.json",
                        help="Имя выходного JSON файла с полной калибровкой.")
    
    args = vars(parser.parse_args())

    camera_ids = args["id"]
    intrinsics_files = args["file"]
    output_file = args["output"]

    if len(camera_ids) != len(intrinsics_files):
        print("[ERROR] Количество --id должно совпадать с количеством --file!")
        return

    num_cameras = len(camera_ids)
    print(f"[INFO] Загрузка {num_cameras} камер...")

    # --- 1. Загружаем все Intrinsics и открываем камеры ---
    cameras_data = {}
    caps = []
    
    for cam_id, int_file in zip(camera_ids, intrinsics_files):
        mtx, dist = load_intrinsics(int_file)
        if mtx is None:
            return # Выходим, если не удалось загрузить файл
        
        # Попытка открыть камеру
        cap = cv2.VideoCapture(cam_id)
        if not cap.isOpened():
            print(f"[ERROR] Не могу открыть камеру {cam_id}")
            return # Выходим, если не удалось открыть камеру
            
        # Установка разрешения (для стабильности и скорости)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        caps.append(cap)
        cameras_data[f"cam_{cam_id}"] = {
            "id": cam_id,
            "intrinsics_file": int_file,
            "K": mtx, 
            "D": dist, 
            "R": None, # Здесь будут храниться внешние параметры
            "T": None
        }
        print(f"  > Камера {cam_id} (из {int_file}) ... OK")

    # --- 2. Настраиваем нашу доску ---
    board, dictionary, detector, detector_params, use_new_detector = setup_charuco_board()

    print("\n" + "="*50)
    print("КАМЕРЫ И ДОСКА ДОЛЖНЫ БЫТЬ АБСОЛЮТНО НЕПОДВИЖНЫ!")
    print("Убедитесь, что доску видно всем камерам.")
    print("\nНажмите 'space' (пробел), чтобы захватить кадр и вычислить позы.")
    print("Нажмите 'q', чтобы выйти.")
    print("="*50 + "\n")
    
    PREVIEW_WIDTH = 640
    PREVIEW_HEIGHT = 360

    while True:
        frames = []
        all_ret = True
        
        # --- 3. Читаем по одному кадру со ВСЕХ камер ---
        for i, cap in enumerate(caps):
            ret, frame = cap.read()
            if not ret:
                print(f"[WARN] Не могу прочитать кадр с камеры {camera_ids[i]}")
                all_ret = False
                break
            frames.append(frame)
        
        if not all_ret:
            time.sleep(0.1)
            continue

        # --- 4. Обработка и создание сетки (1x2 или 2x2) ---
        
        processed_frames = [] 

        for i, frame in enumerate(frames):
            cam_id = camera_ids[i]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Обнаружение маркеров
            if use_new_detector:
                marker_corners, marker_ids, _ = detector.detectMarkers(gray)
            else:
                marker_corners, marker_ids, _ = aruco.detectMarkers(gray, dictionary, parameters=detector_params)
            
            display_frame = frame.copy()
            
            # --- ФИКС: Используем АНГЛИЙСКИЙ текст ---
            if marker_ids is not None and len(marker_ids) > 0:
                aruco.drawDetectedMarkers(display_frame, marker_corners, marker_ids)
                cv2.putText(display_frame, f"CAM {cam_id}: BOARD FOUND", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(display_frame, f"CAM {cam_id}: BOARD NOT FOUND", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            # ------------------------------------------
                
            small_frame = cv2.resize(display_frame, (PREVIEW_WIDTH, PREVIEW_HEIGHT))
            processed_frames.append(small_frame)

        
        # Адаптивный вид
        if num_cameras == 4:
            # 4 камеры (2x2): Предполагаем порядок ввода: [0, 2, 4, 6]
            top_row = np.hstack((processed_frames[3], processed_frames[0])) # 6 и 0
            bottom_row = np.hstack((processed_frames[1], processed_frames[2])) # 2 и 4
            combined_view = np.vstack((top_row, bottom_row))
            cv2.imshow("Extrinsic Calibration (2x2 View)", combined_view)

        elif num_cameras == 2:
            # 2 камеры (1x2)
            combined_view = np.hstack((processed_frames[0], processed_frames[1]))
            cv2.imshow("Extrinsic Calibration (1x2 View)", combined_view)
        
        else:
            # Fallback для 1 или 3 камер: отдельные окна
            for i, frame in enumerate(processed_frames):
                cv2.imshow(f"Camera ID {camera_ids[i]}", frame)
        
        # --- 5. Обработка нажатий клавиш ---

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        
        elif key == ord(' '):
            print("\n[INFO] Захват... Вычисление поз...")
            all_poses_found = True
            
            # --- ГЛАВНЫЙ ШАГ: Вычисление позы для каждой камеры ---
            for i, frame in enumerate(frames):
                cam_id = camera_ids[i]
                cam_key = f"cam_{cam_id}"
                
                K = cameras_data[cam_key]["K"]
                D = cameras_data[cam_key]["D"]
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                if use_new_detector:
                    marker_corners, marker_ids, _ = detector.detectMarkers(gray)
                else:
                    marker_corners, marker_ids, _ = aruco.detectMarkers(gray, dictionary, parameters=detector_params)
                
                if marker_ids is not None and len(marker_ids) > 0:
                    ret_charuco, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
                        marker_corners, marker_ids, gray, board
                    )
                    
                    if ret_charuco and charuco_corners is not None and charuco_ids is not None and len(charuco_corners) > 4:
                        # Находим позу
                        success, rvec, tvec = aruco.estimatePoseCharucoBoard(
                            charuco_corners, charuco_ids, board, K, D, None, None
                        )
                        
                        if success:
                            print(f"  > Поза для камеры {cam_id} ... НАЙДЕНА")
                            
                            # Преобразование Rvec и Tvec (камера -> мир) в World->Camera (R, T)
                            R_world_to_cam, _ = cv2.Rodrigues(rvec)
                            
                            # Матрицы, которые нам нужны для 3D-восстановления
                            R_cam_to_world = R_world_to_cam.T
                            T_cam_to_world = -np.dot(R_cam_to_world, tvec)
                            
                            cameras_data[cam_key]["R"] = R_cam_to_world
                            cameras_data[cam_key]["T"] = T_cam_to_world
                            continue 
                            
                print(f"[ERROR] Не могу найти позу для камеры {cam_id}. Убедитесь, что доска видна и неподвижна.")
                all_poses_found = False
                break 
            
            if all_poses_found:
                print("[SUCCESS] Все позы найдены!")
                print(f"[INFO] Сохранение результатов в {output_file}...")
                
                with open(output_file, 'w') as f:
                    json.dump(cameras_data, f, cls=NumpyEncoder, indent=4)
                
                print("[INFO] Готово. Теперь вы можете закрыть программу ('q').")
            else:
                print("[WARN] Не все позы найдены. Попробуйте нажать 'space' еще раз, убедившись в неподвижности.")

    # --- 6. Очистка ---
    print("[INFO] Закрытие камер...")
    for cap in caps:
        cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()