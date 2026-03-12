import cv2
import numpy as np
import json
import os

def load_full_calibration(filepath):
    """
    Загружает матрицы K, D, R, T из JSON файла.
    Ожидает формат, где R и T описывают трансформацию World -> Camera.
    """
    print(f"[INFO] Loading calibration data from: {filepath}")
    if not os.path.exists(filepath):
        print(f"[ERROR] Calibration file not found: {filepath}")
        return None

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read JSON: {e}")
        return None
        
    calib_data = {}
    
    for cam_key, cam_info in data.items():
        # Пропускаем, если данные неполные
        if any(k not in cam_info for k in ["K", "D", "R", "T"]):
            print(f"[WARN] Camera {cam_key} incomplete. Skipping.")
            continue
            
        calib_data[cam_key] = {
            "K": np.array(cam_info["K"], dtype=np.float64),
            "D": np.array(cam_info["D"], dtype=np.float64),
            "R": np.array(cam_info["R"], dtype=np.float64),
            "T": np.array(cam_info["T"], dtype=np.float64),
        }
        
    print(f"[SUCCESS] Loaded calibration for {len(calib_data)} cameras.")
    return calib_data

def triangulate_point(calib_data, cam_id_1, cam_id_2, point_2d_1, point_2d_2):
    """
    Триангуляция 3D-точки из двух 2D-наблюдений.
    Возвращает координаты в миллиметрах (так как калибровка была 40мм/30мм).
    """
    
    # Приводим ключи к строковому формату (на случай "0" или "cam_0")
    key1 = str(cam_id_1)
    if key1 not in calib_data: key1 = f"cam_{cam_id_1}"
    
    key2 = str(cam_id_2)
    if key2 not in calib_data: key2 = f"cam_{cam_id_2}"

    if key1 not in calib_data or key2 not in calib_data:
        return None

    cam1 = calib_data[key1]
    cam2 = calib_data[key2]

    # 1. Undistort Points (Исправление дисторсии)
    # Превращаем искаженные пиксели (от рыбы) в идеальные линейные пиксели
    pt1_array = np.array([[[point_2d_1[0], point_2d_1[1]]]], dtype=np.float64)
    pt2_array = np.array([[[point_2d_2[0], point_2d_2[1]]]], dtype=np.float64)

    # P=K означает, что мы хотим получить координаты в той же пиксельной сетке, но выпрямленной
    pt1_rect = cv2.undistortPoints(pt1_array, cam1["K"], cam1["D"], P=cam1["K"])
    pt2_rect = cv2.undistortPoints(pt2_array, cam2["K"], cam2["D"], P=cam2["K"])

    # 2. Матрицы проекции P = K * [R | T]
    mat_R1 = cam1["R"]
    mat_T1 = cam1["T"]
    
    mat_R2 = cam2["R"]
    mat_T2 = cam2["T"]
    
    P1 = cam1["K"] @ np.hstack((mat_R1, mat_T1))
    P2 = cam2["K"] @ np.hstack((mat_R2, mat_T2))

    # 3. Триангуляция
    pts1_in = pt1_rect[0].T
    pts2_in = pt2_rect[0].T
    
    points_4d = cv2.triangulatePoints(P1, P2, pts1_in, pts2_in)
    
    # 4. Перевод в 3D (деление на W)
    X, Y, Z, W = points_4d[:, 0]
    
    if abs(W) < 1e-6:
        return None
        
    X /= W
    Y /= W
    Z /= W
    
    return np.array([X, Y, Z], dtype=np.float32)