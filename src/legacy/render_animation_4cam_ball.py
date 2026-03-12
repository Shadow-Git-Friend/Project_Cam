import json
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from pathlib import Path
from collections import deque
import os
import sys

# --- НАСТРОЙКИ ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Читаем файл, который создал новый рекордер
INPUT_FILE = PROJECT_ROOT / "motion_capture_4cam_data_new.json"
OUTPUT_DIR = PROJECT_ROOT / "render_output_4cam_ball"

OUTPUT_DIR.mkdir(exist_ok=True)

# COCO Skeleton (Связи костей)
SKELETON_CONNECTIONS = [
    (5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), 
    (12, 14), (14, 16), (5, 6), (11, 12), (5, 11), (6, 12)
]

# ==========================================
# 🎛 TUNING (НАСТРОЙКИ ОПТИМИЗАЦИИ)
# ==========================================

# 1. ЛИМИТ СКОРОСТИ (мм/кадр)
# СНЯЛИ ОГРАНИЧЕНИЕ ПОЛНОСТЬЮ (10000 мм = 10 метров за кадр)
# Теперь скрипт НИЧЕГО не удаляет. Все удары останутся.
VELOCITY_LIMIT_HUMAN = 10000.0  
VELOCITY_LIMIT_BALL = 10000.0  

# 2. МЕДИАННЫЙ ФИЛЬТР
# Ставим 1 = ВЫКЛЮЧЕНО.
# Мы увидим "сырые" движения. Удары ногой точно будут видны.
MEDIAN_KERNEL_HUMAN = 1 
MEDIAN_KERNEL_BALL = 3 

# 3. СГЛАЖИВАНИЕ (Savitzky-Golay)
# Окно сглаживания. 3 - минимальное сглаживание (резко).
SAVGOL_WINDOW_HUMAN = 3 
SAVGOL_WINDOW_BALL = 5   

# 4. Зум камеры
# 5.0 = ОЧЕНЬ КРУПНЫЙ ПЛАН
ZOOM_FACTOR = 5.0 

# 5. Скорость финального видео (FPS)
# Меньше = Медленнее
FINAL_FPS = 12
# ==========================================

class MocapProcessor:
    def __init__(self, raw_data, key="joints"):
        self.raw_data = raw_data
        self.num_frames = len(raw_data)
        self.obj_type = key # 'joints' или 'ball'
        
        # Если обрабатываем суставы (17 точек)
        if key == "joints":
            self.num_joints = 17
            self.trajectory = np.full((self.num_frames, self.num_joints, 3), np.nan)
            for f_idx, frame in enumerate(raw_data):
                # Безопасное получение списка
                joints = frame.get("joints", [])
                for j_idx, joint in enumerate(joints):
                    if joint is not None:
                        self.trajectory[f_idx, j_idx] = joint
                        
        # Если обрабатываем мяч (1 точка)
        elif key == "ball":
            self.num_joints = 1
            self.trajectory = np.full((self.num_frames, 1, 3), np.nan)
            for f_idx, frame in enumerate(raw_data):
                ball = frame.get("ball")
                if ball is not None:
                    self.trajectory[f_idx, 0] = ball

    def process(self):
        # Настройки зависят от того, кого обрабатываем (Мяч или Человек)
        if self.obj_type == "ball":
            vel_limit = VELOCITY_LIMIT_BALL
            savgol_win = SAVGOL_WINDOW_BALL
            med_kern = MEDIAN_KERNEL_BALL
        else:
            vel_limit = VELOCITY_LIMIT_HUMAN
            savgol_win = SAVGOL_WINDOW_HUMAN
            med_kern = MEDIAN_KERNEL_HUMAN

        print(f"[{self.obj_type.upper()}] 1. Velocity Check (Limit: {vel_limit})...")
        self._remove_velocity_outliers(limit_mm=vel_limit)

        print(f"[{self.obj_type.upper()}] 2. Interpolation...")
        self._fill_missing_values()
        
        if med_kern > 1:
            print(f"[{self.obj_type.upper()}] 3. Median Filter (k={med_kern})...")
            self._apply_median_filter(kernel_size=med_kern)
        
        print(f"[{self.obj_type.upper()}] 4. Smoothing (SavGol w={savgol_win})...")
        self._apply_savgol_filter(window_length=savgol_win, polyorder=2)

    def _remove_velocity_outliers(self, limit_mm):
        for _ in range(1): 
            for f in range(1, self.num_frames):
                diff = np.linalg.norm(self.trajectory[f] - self.trajectory[f-1], axis=1)
                bad_idx = np.where(diff > limit_mm)[0]
                self.trajectory[f, bad_idx] = np.nan

    def _fill_missing_values(self):
        for j in range(self.num_joints):
            for axis in range(3):
                col = self.trajectory[:, j, axis]
                valid_idx = np.where(~np.isnan(col))[0]
                if len(valid_idx) > 0:
                    col[:valid_idx[0]] = col[valid_idx[0]]
                    col[valid_idx[-1]+1:] = col[valid_idx[-1]]
                nans = np.isnan(col)
                if np.sum(nans) > 0 and np.sum(~nans) > 0:
                    x_all = np.arange(len(col))
                    col[nans] = np.interp(x_all[nans], x_all[~nans], col[~nans])
                    self.trajectory[:, j, axis] = col

    def _apply_median_filter(self, kernel_size=3):
        pad = kernel_size // 2
        filtered = np.copy(self.trajectory)
        for f in range(pad, self.num_frames - pad):
            window = self.trajectory[f-pad : f+pad+1]
            median_val = np.nanmedian(window, axis=0)
            filtered[f] = median_val
        self.trajectory = filtered

    def _apply_savgol_filter(self, window_length=7, polyorder=2):
        try:
            from scipy.signal import savgol_filter
            for j in range(self.num_joints):
                for ax in range(3):
                    col = self.trajectory[:, j, ax]
                    mask = np.isnan(col)
                    if np.sum(~mask) > window_length:
                        self.trajectory[:, j, ax] = savgol_filter(col, window_length, polyorder)
        except ImportError:
            pass

    def rotate_upright(self, rotation_matrix):
        """Применяет матрицу поворота ко всем точкам"""
        flat = self.trajectory.reshape(-1, 3)
        rotated = np.dot(flat, rotation_matrix.T)
        self.trajectory = rotated.reshape(self.num_frames, self.num_joints, 3)

    def get_rotation_matrix(self):
        """Вычисляет матрицу поворота по данным СКЕЛЕТА"""
        mean_pose = np.nanmedian(self.trajectory, axis=0) 
        if self.num_joints < 17: return np.eye(3) 
        
        hip_center = (mean_pose[11] + mean_pose[12]) / 2.0
        shoulder_center = (mean_pose[5] + mean_pose[6]) / 2.0
        
        body_up = shoulder_center - hip_center
        norm = np.linalg.norm(body_up)
        if norm < 1e-6: return np.eye(3)
        body_up /= norm
        
        target_up = np.array([0, 0, 1])
        v = np.cross(body_up, target_up)
        c = np.dot(body_up, target_up)
        s = np.linalg.norm(v)
        
        if s < 1e-6: return np.eye(3)
        
        kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + kmat + kmat.dot(kmat) * ((1 - c) / (s ** 2))
        return R

    def get_data_list(self):
        output = []
        for f in range(self.num_frames):
            joints = []
            for j in range(self.num_joints):
                pt = self.trajectory[f, j]
                if np.isnan(pt).any(): joints.append(None)
                else: joints.append(pt.tolist())
            output.append(joints)
        return output

class Trace:
    def __init__(self, maxlen=15):
        self.history = deque(maxlen=maxlen)
    def update(self, point):
        if point is not None: self.history.append(point)
    def get_data(self):
        if not self.history: return [], [], []
        data = np.array(self.history)
        return data[:, 0], data[:, 1], data[:, 2]

def main():
    if not INPUT_FILE.exists():
        print(f"[ERROR] Файл {INPUT_FILE} не найден. Сначала запустите запись!")
        return

    print(f"[INFO] Загрузка данных...")
    with open(INPUT_FILE, 'r') as f:
        raw_data = json.load(f)

    # 1. ОБРАБОТКА ЧЕЛОВЕКА
    human_proc = MocapProcessor(raw_data, key="joints")
    human_proc.process()
    
    # Поворот
    R = human_proc.get_rotation_matrix()
    human_proc.rotate_upright(R)
    human_data = human_proc.get_data_list()

    # 2. ОБРАБОТКА МЯЧА
    ball_proc = MocapProcessor(raw_data, key="ball")
    ball_proc.process()
    ball_proc.rotate_upright(R)
    ball_data = ball_proc.get_data_list()

    # 3. ПОИСК ЦЕНТРА
    all_human_points = []
    for frame in human_data:
        for pt in frame:
            if pt is not None: all_human_points.append(pt)
    
    if not all_human_points: return

    all_points_np = np.array(all_human_points)
    center_vals = np.nanmedian(all_points_np, axis=0)
    
    p_min = np.percentile(all_points_np, 2, axis=0)
    p_max = np.percentile(all_points_np, 98, axis=0)
    body_size = np.max(p_max - p_min)
    
    scale_factor = 1.0
    if body_size < 10: 
        print("[INFO] Конвертация Метры -> Миллиметры")
        scale_factor = 1000.0
        body_size *= 1000.0
        center_vals *= 1000.0
        
    # --- АГРЕССИВНЫЙ ЗУМ ---
    # Уменьшаем лимит (приближаем камеру), но не меньше 500мм
    LIMIT = max(500, body_size / (ZOOM_FACTOR * 0.8)) 
    floor_level = p_min[2] * scale_factor
    
    print(f"[INFO] Центр: {center_vals.astype(int)}")
    print(f"[INFO] Зум радиус: {LIMIT:.0f} мм")

    def transform(pt):
        if pt is None: return None
        p_scaled = np.array(pt) * scale_factor
        x = p_scaled[0] - center_vals[0]
        y = p_scaled[1] - center_vals[1]
        z = p_scaled[2] - floor_level 
        return [x, y, z]

    trace_lh = Trace(12); trace_rh = Trace(12) 
    trace_lf = Trace(12); trace_rf = Trace(12) 
    trace_ball = Trace(25) 
    
    plt.style.use('dark_background')
    total_frames = len(human_data)

    print(f"[INFO] Рендеринг {total_frames} кадров...")

    for i in range(total_frames):
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        ax.set_box_aspect([1,1,1])
        ax.set_xlim(-LIMIT, LIMIT)
        ax.set_ylim(-LIMIT, LIMIT)
        ax.set_zlim(0, LIMIT*2)

        ax.xaxis.set_pane_color((0,0,0,0)); ax.yaxis.set_pane_color((0,0,0,0)); ax.zaxis.set_pane_color((0,0,0,0))
        grid_c = (1, 1, 1, 0.15)
        ax.xaxis._axinfo["grid"]['color'] = grid_c; ax.yaxis._axinfo["grid"]['color'] = grid_c; ax.zaxis._axinfo["grid"]['color'] = grid_c
        
        ax.set_facecolor('#050505')
        fig.patch.set_facecolor('#050505')
        
        # Floor
        grid_range = np.linspace(-LIMIT, LIMIT, 5)
        xx, yy = np.meshgrid(grid_range, grid_range)
        zz = np.zeros_like(xx) 
        ax.plot_wireframe(xx, yy, zz, color='gray', alpha=0.15)

        # --- DRAW HUMAN ---
        joints = [transform(p) for p in human_data[i]]
        
        for start, end in SKELETON_CONNECTIONS:
            p1 = joints[start]
            p2 = joints[end]
            if p1 and p2:
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], 
                        color='white', linewidth=2, alpha=0.9)

        xs = [p[0] for p in joints if p]
        ys = [p[1] for p in joints if p]
        zs = [p[2] for p in joints if p]
        if xs:
            ax.scatter(xs, ys, zs, c='#00ffcc', s=25, depthshade=True, edgecolor='none')

        if len(joints) > 16:
            trace_lh.update(joints[9]); trace_rh.update(joints[10])
            trace_lf.update(joints[15]); trace_rf.update(joints[16])
            for tr, col in [(trace_lh, '#ff00ff'), (trace_rh, '#ffff00'), 
                            (trace_lf, '#00ffff'), (trace_rf, '#ffaa00')]:
                tx, ty, tz = tr.get_data()
                if len(tx): ax.plot(tx, ty, tz, c=col, linewidth=1.5)

        # --- DRAW BALL ---
        if i < len(ball_data) and ball_data[i] and ball_data[i][0]:
            raw_ball = ball_data[i][0]
            ball_pt = transform(raw_ball)
            
            if ball_pt:
                trace_ball.update(ball_pt)
                tx, ty, tz = trace_ball.get_data()
                if len(tx): 
                    ax.plot(tx, ty, tz, c='#ff4500', linewidth=3)
                
                ax.scatter([ball_pt[0]], [ball_pt[1]], [ball_pt[2]], 
                           c='#ff8c00', s=150, edgecolors='white', alpha=1.0)

        # Статичная камера (Изометрия)
        ax.view_init(elev=15, azim=45)

        filename = OUTPUT_DIR / f"frame_{i:04d}.png"
        plt.savefig(filename, dpi=80)
        plt.close(fig)
        
        if i % 20 == 0:
            sys.stdout.write(f"\rProgress: {i}/{total_frames}")
            sys.stdout.flush()

    print(f"\n[SUCCESS] Склейка финального видео...")
    video_path = PROJECT_ROOT / "final_4cam_ball_movie_7.mp4"
    if video_path.exists(): os.remove(video_path)
    
    # ЗАМЕДЛЕННЫЙ РЕНДЕР (12 FPS)
    os.system(f"ffmpeg -y -framerate {FINAL_FPS} -i {OUTPUT_DIR}/frame_%04d.png -c:v libx264 -pix_fmt yuv420p {video_path}")
    print(f"[DONE] Видео готово и лежит здесь: {video_path.absolute()}")

if __name__ == "__main__":
    main()