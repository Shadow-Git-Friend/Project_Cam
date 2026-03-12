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
INPUT_FILE = PROJECT_ROOT / "motion_capture_data.json"
OUTPUT_DIR = PROJECT_ROOT / "render_output"

OUTPUT_DIR.mkdir(exist_ok=True)

# Скелет (соединения точек COCO)
SKELETON_CONNECTIONS = [
    (5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), 
    (12, 14), (14, 16), (5, 6), (11, 12), (5, 11), (6, 12)
]

# Иерархия костей для кинематики (Родитель -> Ребенок)
BONE_HIERARCHY = [
    (11, 13), (13, 15), # Левая нога
    (12, 14), (14, 16), # Правая нога
    (5, 7), (7, 9),     # Левая рука
    (6, 8), (8, 10),    # Правая рука
]

class MocapProcessor:
    def __init__(self, raw_data):
        self.raw_data = raw_data
        self.num_frames = len(raw_data)
        self.num_joints = 17
        
        self.trajectory = np.full((self.num_frames, self.num_joints, 3), np.nan)
        
        for f_idx, frame in enumerate(raw_data):
            for j_idx, joint in enumerate(frame["joints"]):
                if joint is not None:
                    self.trajectory[f_idx, j_idx] = joint

    def process(self):
        """Продвинутый пайплайн очистки"""
        print("[1/6] Удаление нефизических скачков (Velocity Rejection)...")
        # Удаляем точки, которые движутся слишком быстро (телепортации)
        self._remove_velocity_outliers(limit_mm=800) 

        print("[2/6] Заполнение пропусков (Interpolation)...")
        self._fill_missing_values()
        
        print("[3/6] Удаление шума (Median Filter)...")
        self._apply_median_filter(kernel_size=7) # Увеличили окно до 7
        
        print("[4/6] Глобальное выравнивание (Robust Auto-Upright)...")
        self._auto_orient_upright()
        
        print("[5/6] Плавное сглаживание (Butterworth)...")
        self._apply_butterworth_filter()
        
        print("[6/6] Фиксация длины костей (Kinematics)...")
        self._enforce_bone_lengths()

    def _remove_velocity_outliers(self, limit_mm=800):
        """Если точка смещается > limit_mm за 1 кадр, удаляем её."""
        count = 0
        for j in range(self.num_joints):
            for f in range(1, self.num_frames):
                prev = self.trajectory[f-1, j]
                curr = self.trajectory[f, j]
                
                if np.isnan(prev).any() or np.isnan(curr).any():
                    continue
                
                # Расстояние между кадрами
                dist = np.linalg.norm(curr - prev)
                if dist > limit_mm:
                    self.trajectory[f, j] = [np.nan, np.nan, np.nan] # Убиваем точку
                    count += 1
        print(f"   -> Удалено {count} выбросов.")

    def _fill_missing_values(self):
        for j in range(self.num_joints):
            for axis in range(3):
                col = self.trajectory[:, j, axis]
                nans = np.isnan(col)
                if np.sum(nans) > 0 and np.sum(~nans) > 0:
                    x_all = np.arange(len(col))
                    col[nans] = np.interp(x_all[nans], x_all[~nans], col[~nans])
                    self.trajectory[:, j, axis] = col

    def _apply_median_filter(self, kernel_size=5):
        pad = kernel_size // 2
        filtered = np.copy(self.trajectory)
        for f in range(pad, self.num_frames - pad):
            window = self.trajectory[f-pad : f+pad+1]
            median_val = np.nanmedian(window, axis=0)
            filtered[f] = median_val
        self.trajectory = filtered

    def _auto_orient_upright(self):
        """Робастный поворот скелета вертикально"""
        # Используем MEDIAN вместо MEAN, чтобы выбросы не портили ориентацию
        mean_pose = np.nanmedian(self.trajectory, axis=0) 
        
        hip_center = (mean_pose[11] + mean_pose[12]) / 2.0
        # Используем середину плеч, так как она стабильнее носа
        shoulder_center = (mean_pose[5] + mean_pose[6]) / 2.0
        
        # Вектор тела
        body_up_vector = shoulder_center - hip_center
        norm = np.linalg.norm(body_up_vector)
        if norm < 1e-6: return
        body_up_vector /= norm
        
        # Цель: Z вверх
        target_up = np.array([0, 0, 1])
        
        # Вычисляем поворот
        v = np.cross(body_up_vector, target_up)
        c = np.dot(body_up_vector, target_up)
        s = np.linalg.norm(v)
        
        if s < 1e-6: 
            if c < 0: R = np.diag([-1, -1, 1])
            else: R = np.eye(3)
        else:
            kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
            R = np.eye(3) + kmat + kmat.dot(kmat) * ((1 - c) / (s ** 2))

        flat_traj = self.trajectory.reshape(-1, 3)
        rotated_traj = np.dot(flat_traj, R.T)
        self.trajectory = rotated_traj.reshape(self.num_frames, self.num_joints, 3)
        print(f"   -> Скелет переориентирован.")

    def _apply_butterworth_filter(self):
        try:
            from scipy.signal import butter, filtfilt
            # Более агрессивный фильтр (0.1) для плавности
            b, a = butter(2, 0.1, btype='low', analog=False)
            for j in range(self.num_joints):
                for ax in range(3):
                    col = self.trajectory[:, j, ax]
                    mask = np.isnan(col)
                    col[mask] = np.nanmean(col)
                    self.trajectory[:, j, ax] = filtfilt(b, a, col)
        except ImportError:
            print("[WARN] Scipy не установлен! Качество сглаживания будет хуже.")
            # Фолбэк на One Euro если нет scipy
            self._apply_one_euro_filter()

    def _apply_one_euro_filter(self, min_cutoff=0.05, beta=0.005):
        # Запасной вариант сглаживания
        filtered = np.copy(self.trajectory)
        x_prev = filtered[0]
        dx_prev = np.zeros_like(x_prev)
        dt = 1.0/30.0
        
        def smoothing_factor(t_e, cutoff):
            r = 2 * np.pi * cutoff * t_e
            return r / (r + 1)
        
        def exponential_smoothing(a, x, x_prev):
            return a * x + (1 - a) * x_prev

        for i in range(1, self.num_frames):
            x_curr = self.trajectory[i]
            mask = ~np.isnan(x_curr) & ~np.isnan(x_prev)
            if np.any(mask):
                dx = (x_curr - x_prev) / dt
                dx_hat = exponential_smoothing(0.5, dx, dx_prev) # simple cutoff for deriv
                speed = np.linalg.norm(dx_hat, axis=1)
                cutoff = min_cutoff + beta * speed
                for j in range(self.num_joints):
                    if mask[j].all():
                        a = smoothing_factor(dt, cutoff[j])
                        x_prev[j] = exponential_smoothing(a, x_curr[j], x_prev[j])
            filtered[i] = x_prev
        self.trajectory = filtered

    def _enforce_bone_lengths(self):
        bone_lengths = {}
        # Считаем медианные длины (более устойчиво к выбросам)
        for (parent, child) in BONE_HIERARCHY:
            vecs = self.trajectory[:, child, :] - self.trajectory[:, parent, :]
            lengths = np.linalg.norm(vecs, axis=1)
            target_len = np.nanmedian(lengths)
            bone_lengths[(parent, child)] = target_len
            
        for f in range(self.num_frames):
            for (parent, child) in BONE_HIERARCHY:
                p_loc = self.trajectory[f, parent]
                c_loc = self.trajectory[f, child]
                
                if np.isnan(p_loc).any() or np.isnan(c_loc).any(): continue
                    
                direction = c_loc - p_loc
                current_len = np.linalg.norm(direction)
                if current_len < 1e-6: continue
                
                direction_norm = direction / current_len
                target_len = bone_lengths[(parent, child)]
                
                # Принудительно ставим сустав на нужное расстояние
                self.trajectory[f, child] = p_loc + (direction_norm * target_len)

    def get_data_list(self):
        output = []
        for f in range(self.num_frames):
            joints_list = []
            for j in range(self.num_joints):
                pt = self.trajectory[f, j]
                if np.isnan(pt).any():
                    joints_list.append(None)
                else:
                    joints_list.append(pt.tolist())
            output.append({"joints": joints_list})
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
        print(f"[ERROR] Файл {INPUT_FILE} не найден.")
        return

    print(f"[INFO] Загрузка сырых данных...")
    with open(INPUT_FILE, 'r') as f:
        raw_data = json.load(f)

    # 1. ОБРАБОТКА (Новый пайплайн)
    processor = MocapProcessor(raw_data)
    processor.process()
    data = processor.get_data_list()

    # 2. ПОИСК ЦЕНТРА
    all_points = []
    for frame in data:
        for pt in frame["joints"]:
            if pt is not None: all_points.append(pt)
    
    if not all_points: return

    all_points_np = np.array(all_points)
    # Median центр
    center_vals = np.nanmedian(all_points_np, axis=0)
    
    # 3. АВТО-МАСШТАБ
    p_min = np.percentile(all_points_np, 2, axis=0)
    p_max = np.percentile(all_points_np, 98, axis=0)
    body_size = np.max(p_max - p_min)
    
    scale_factor = 1.0
    if body_size < 10: 
        print("[INFO] Масштабирую метры -> мм")
        scale_factor = 1000.0
        body_size *= 1000.0
        center_vals *= 1000.0
        
    LIMIT = max(1000, body_size / 1.3)
    floor_level = p_min[2] * scale_factor # Z-минимум это пол (после поворота)
    
    print(f"[INFO] Центр: {center_vals.astype(int)}")

    def transform(pt):
        if pt is None: return None
        p_scaled = np.array(pt) * scale_factor
        
        # Центрируем X, Y. Z ставим от пола.
        x = p_scaled[0] - center_vals[0]
        y = p_scaled[1] - center_vals[1]
        z = p_scaled[2] - floor_level 
        
        # ПРЯМОЙ МАППИНГ (Раз мы уже повернули скелет программно)
        return [x, y, z]

    trace_lh = Trace(12); trace_rh = Trace(12)
    trace_lf = Trace(12); trace_rf = Trace(12)
    
    plt.style.use('dark_background')
    total_frames = len(data)

    print(f"[INFO] Рендеринг {total_frames} кадров...")

    for i, frame in enumerate(data):
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # Камера
        ax.set_box_aspect([1,1,1])
        ax.set_xlim(-LIMIT, LIMIT)
        ax.set_ylim(-LIMIT, LIMIT)
        ax.set_zlim(0, LIMIT*2)

        # Сетка
        ax.xaxis.set_pane_color((0,0,0,0))
        ax.yaxis.set_pane_color((0,0,0,0))
        ax.zaxis.set_pane_color((0,0,0,0))
        
        grid_c = (1, 1, 1, 0.15)
        ax.xaxis._axinfo["grid"]['color'] = grid_c
        ax.yaxis._axinfo["grid"]['color'] = grid_c
        ax.zaxis._axinfo["grid"]['color'] = grid_c
        
        ax.set_facecolor('#050505')
        fig.patch.set_facecolor('#050505')
        
        # Пол
        grid_range = np.linspace(-LIMIT, LIMIT, 5)
        xx, yy = np.meshgrid(grid_range, grid_range)
        zz = np.zeros_like(xx) 
        ax.plot_wireframe(xx, yy, zz, color='gray', alpha=0.15)

        joints = [transform(p) for p in frame["joints"]]
        
        # Кости
        for start, end in SKELETON_CONNECTIONS:
            p1 = joints[start]
            p2 = joints[end]
            if p1 and p2:
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], 
                        color='white', linewidth=2, alpha=0.9)

        # Суставы
        xs = [p[0] for p in joints if p]
        ys = [p[1] for p in joints if p]
        zs = [p[2] for p in joints if p]
        if xs:
            ax.scatter(xs, ys, zs, c='#00ffcc', s=25, depthshade=True, edgecolor='none')

        # Следы
        if len(joints) > 16:
            trace_lh.update(joints[9])
            trace_rh.update(joints[10])
            trace_lf.update(joints[15])
            trace_rf.update(joints[16])
            
            for tr, col in [(trace_lh, '#ff00ff'), (trace_rh, '#ffff00'), 
                            (trace_lf, '#00ffff'), (trace_rf, '#ffaa00')]:
                tx, ty, tz = tr.get_data()
                if len(tx): ax.plot(tx, ty, tz, c=col, linewidth=1.5)

        # Вращение
        ax.view_init(elev=15, azim=i * 0.4)

        filename = OUTPUT_DIR / f"frame_{i:04d}.png"
        plt.savefig(filename, dpi=80)
        plt.close(fig)
        
        if i % 20 == 0:
            sys.stdout.write(f"\rProgress: {i}/{total_frames}")
            sys.stdout.flush()

    print(f"\n[SUCCESS] Склейка видео...")
    video_path = PROJECT_ROOT / "my_3d_pose_movie_final1.mp4"
    if video_path.exists(): os.remove(video_path)
    
    os.system(f"ffmpeg -y -framerate 30 -i {OUTPUT_DIR}/frame_%04d.png -c:v libx264 -pix_fmt yuv420p {video_path}")
    print(f"[DONE] Видео готово: {video_path}")

if __name__ == "__main__":
    main()