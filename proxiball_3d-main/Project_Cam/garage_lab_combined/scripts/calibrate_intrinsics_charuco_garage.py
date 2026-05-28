import cv2
import cv2.aruco as aruco
import numpy as np
import time
import argparse
import os

def calibrate_charuco_camera(camera_id, board_params):
    """
    Выполняет калибровку одной камеры с использованием ChArUco.
    """
    
    # --- 1. Настройка параметров вашей доски ---
    SQUARES_X = board_params["SQUARES_X"]
    SQUARES_Y = board_params["SQUARES_Y"]
    SQUARE_SIZE_MM = board_params["SQUARE_SIZE_MM"]
    MARKER_SIZE_MM = board_params["MARKER_SIZE_MM"]
    ARUCO_DICT = board_params["ARUCO_DICT"]

    print("[INFO] Создание ChArUco доски в памяти...")
    # Создаем словарь ArUco
    dictionary = aruco.getPredefinedDictionary(ARUCO_DICT)
    
    # Создаем объект доски ChArUco
    # ВАЖНО: OpenCV < 4.7.0 использует cv2.aruco.CharucoBoard_create
    # OpenCV >= 4.7.0 использует cv2.aruco.CharucoBoard
    # Пытаемся использовать новый синтаксис, если не выйдет - старый
    try:
        board = aruco.CharucoBoard((SQUARES_X, SQUARES_Y), SQUARE_SIZE_MM, MARKER_SIZE_MM, dictionary)
        print("[INFO] Используется синтаксис cv2.aruco.CharucoBoard (OpenCV >= 4.7)")
    except AttributeError:
        print("[INFO] Используется синтаксис cv2.aruco.CharucoBoard_create (OpenCV < 4.7)")
        board = aruco.CharucoBoard_create(SQUARES_X, SQUARES_Y, SQUARE_SIZE_MM, MARKER_SIZE_MM, dictionary)
        
    # Параметры детектора ArUco
    detector_parameters = aruco.DetectorParameters()
    try:
        # Пытаемся использовать новый синтаксис (OpenCV >= 4.7)
        detector = aruco.ArucoDetector(dictionary, detector_parameters)
        print("[INFO] Используется синтаксис cv2.aruco.ArucoDetector")
        use_new_detector = True
    except AttributeError:
        # Используем старый (OpenCV < 4.7)
        print("[INFO] Используется старый синтаксис детектора (detectMarkers)")
        use_new_detector = False

    # Массивы для хранения всех найденных углов и их ID
    all_corners = []
    all_ids = []
    
    image_size = None # Сохраним здесь размер изображения (Ш, В)

    # --- 3. Захват и обработка видео ---
    
    print(f"[INFO] Открываю камеру с ID: {camera_id}...")
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"[ERROR] Не могу открыть камеру {camera_id}. Проверьте ID.")
        return

    # Устанавливаем высокое разрешение
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("\n" + "="*50)
    print("Начните показывать ChArUco доску камере.")
    print("Двигайте ее по всему кадру, под разными углами.")
    print("\nНажмите 'space' (пробел), чтобы 'сфотографировать' хороший кадр.")
    print("Нажмите 'c', чтобы выполнить калибровку (нужно > 10 кадров).")
    print("Нажмите 'q', чтобы выйти.")
    print("="*50 + "\n")

    saved_image_count = 0
    calibration_done = False

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Не могу прочитать кадр.")
            time.sleep(0.1)
            continue

        if image_size is None:
            image_size = frame.shape[:2][::-1] # (ширина, высота)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        display_frame = frame.copy()

        # --- Детекция маркеров ArUco ---
        if use_new_detector:
            marker_corners, marker_ids, rejected_img_points = detector.detectMarkers(gray)
        else:
            marker_corners, marker_ids, rejected_img_points = aruco.detectMarkers(gray, dictionary, parameters=detector_parameters)
        
        found_markers = False
        
        # Если найдено хотя бы несколько маркеров
        if marker_ids is not None and len(marker_ids) > 0:
            # --- Интерполяция углов ChArUco ---
            # Это находит углы шахматной доски, используя маркеры как "якоря"
            ret_charuco, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
                marker_corners, marker_ids, gray, board
            )
            
            # Если найдено достаточно углов для кадра
            if ret_charuco and charuco_corners is not None and charuco_ids is not None and len(charuco_corners) > 4:
                found_markers = True
                # Рисуем найденные углы ChArUco
                aruco.drawDetectedCornersCharuco(display_frame, charuco_corners, charuco_ids, (0, 255, 0))

                cv2.putText(display_frame, "ДОСКА НАЙДЕНА! Нажмите 'space' для сохранения", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        if not found_markers:
            cv2.putText(display_frame, "Доска не найдена", 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.putText(display_frame, f"Сохранено кадров: {saved_image_count}", 
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
        cv2.imshow('ChArUco Calibration - Press "q" to quit', display_frame)
        
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        
        elif key == ord(' '):
            # --- Сохранение кадра (точек) ---
            if found_markers:
                all_corners.append(charuco_corners)
                all_ids.append(charuco_ids)
                saved_image_count += 1
                print(f"[INFO] Кадр {saved_image_count} сохранен (найдено {len(charuco_corners)} углов).")
            else:
                print("[WARN] Попытка сохранить, но доска не найдена!")

        elif key == ord('c'):
            # --- Выполнение калибровки ---
            if saved_image_count < 10:
                print(f"[WARN] Нужно как минимум 10 хороших кадров. У вас {saved_image_count}.")
                continue
                
            print(f"\n[INFO] Выполняется калибровка на {saved_image_count} кадрах...")
            print(f"[INFO] Размер изображения: {image_size}")
            
            # Создаем пустые переменные для результатов
            mtx = np.zeros((3, 3), dtype=np.float64)
            dist = np.zeros((1, 5), dtype=np.float64) # k1, k2, p1, p2, k3
            
            try:
                # --- ГЛАВНАЯ ФУНКЦИЯ ---
                ret, mtx, dist, rvecs, tvecs = aruco.calibrateCameraCharuco(
                    all_corners,  # 2D точки на изображении
                    all_ids,      # ID этих 2D точек
                    board,        # Объект ChArUco (он знает 3D точки)
                    image_size,   # Размер изображения
                    mtx,          # Вход/Выход Матрица K
                    dist          # Вход/Выход Коэффициенты D
                )
            except Exception as e:
                print(f"[ERROR] Ошибка во время cv2.aruco.calibrateCameraCharuco: {e}")
                print("[ERROR] Убедитесь, что у вас последняя версия opencv-contrib-python.")
                print("[ERROR] Попробуйте: pip install --upgrade opencv-contrib-python")
                continue

            if not ret:
                print("[ERROR] Калибровка не удалась. Попробуйте собрать кадры заново.")
                continue
                
            print("[SUCCESS] Калибровка завершена!")
            
            # --- Оценка ошибки (Reprojection Error) ---
            # calibrateCameraCharuco уже возвращает нам ошибку (ret)
            mean_error = ret
            
            print(f"\n[RESULT] Матрица камеры (K):\n{mtx}")
            print(f"\n[RESULT] Коэффициенты дисторсии (D):\n{dist}")
            print(f"\n[QUALITY] Средняя ошибка репроекции (Mean Reprojection Error): {mean_error} px")
            
            if mean_error < 0.5:
                print("[QUALITY] Это ОТЛИЧНЫЙ результат.")
            elif mean_error < 1.0:
                print("[QUALITY] Это хороший, приемлемый результат.")
            else:
                print("[QUALITY] Это плохой результат. Рекомендуется переделать калибровку.")
            
            calibration_done = True
            break # Выходим из цикла

    cap.release()
    cv2.destroyAllWindows()

    if calibration_done:
        return mtx, dist, mean_error
    else:
        return None, None, None

def main():
    parser = argparse.ArgumentParser(description="Калибровка внутренних параметров камеры (ChArUco).")
    parser.add_argument("-i", "--id", type=int, required=True,
                        help="ID камеры (e.g., 0, 1, 2).")
    parser.add_argument("-o", "--output", type=str, required=True,
                        help="Имя выходного файла (e.g., cal/cam0_intrinsics.npz).")
    
    args = vars(parser.parse_args())

    cam_id = args["id"]
    output_file = args["output"]

    # --- ПАРАМЕТРЫ ВАШЕЙ ДОСКИ ---
    board_params = {
        "SQUARES_X": 7,      # 7 квадратов в ширину
        "SQUARES_Y": 10,     # 10 квадратов в высоту
        "SQUARE_SIZE_MM": 40.0,  # 40mm
        "MARKER_SIZE_MM": 30.0,  # 30mm
        "ARUCO_DICT": aruco.DICT_4X4_1000 # 4x4, 1000 markers (matches garage board PDF)
    }
    
    print("--- Запуск скрипта калибровки ChArUco ---")
    print(f"Камера: {cam_id}")
    print(f"Доска: {board_params['SQUARES_X']}x{board_params['SQUARES_Y']} (квадраты)")
    print(f"Размер квадрата: {board_params['SQUARE_SIZE_MM']} мм")
    print(f"Размер маркера: {board_params['MARKER_SIZE_MM']} мм")
    print(f"Словарь: {board_params['ARUCO_DICT']}")
    print(f"Выходной файл: {output_file}")
    print("---------------------------------")
    
    mtx, dist, error = calibrate_charuco_camera(cam_id, board_params)
    
    if mtx is not None:
        print(f"\n[INFO] Сохранение результатов в файл: {output_file}")
        # Сохраняем в сжатый .npz файл
        np.savez(output_file, mtx=mtx, dist=dist, error=error)
        print("[INFO] Готово.")
    else:
        print("\n[INFO] Калибровка не была завершена. Файл не сохранен.")

if __name__ == "__main__":
    main()
