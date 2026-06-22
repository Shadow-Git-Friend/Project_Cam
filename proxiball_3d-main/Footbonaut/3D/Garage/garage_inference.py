"""
garage_inference.py — 4-Camera Garage 3D Ball Tracking
=======================================================
Usage (from Footbonaut root):
    python Garage/garage_inference.py \\
        --scenario_dir Garage/garage/sync_records/1 \\
        --scenario_id 1 \\
        --model model/y26s_garagev2.engine

Output:
    garage_scenario{N}_{timestamp}.mp4          (2×2 grid video in root)
    garage_scenario{N}_{timestamp}_metrics.csv
    garage_scenario{N}_{timestamp}_metrics.json
"""

import os, sys, json, csv, argparse, yaml, time
import cv2, numpy as np
from pathlib import Path
from threading import Thread
from queue import Queue, Empty

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT   = Path(__file__).resolve().parent.parent  # /…/Footbonaut
GARAGE = Path(__file__).resolve().parent         # /…/Garage
sys.path.insert(0, str(ROOT))

from ultralytics import YOLO
from tracker.trackerv1 import tracker
from tracker.tracker3d import Tracker3D
from Garage.garage_reconstruction import GarageReconstructor

# ── Camera layout (video filenames inside scenario folder) ────────────────────
CAM_ORDER  = ["East", "West", "North", "South"]   # matches 2×2 grid position
CAM_EXTR   = {                                      # maps filename → extrinsics key
    "East":  "camEast",
    "West":  "camWest",
    "North": "camNorth",
    "South": "camSouth",
}
QUEUE_SIZE = 128
CELL_W, CELL_H = 960, 540    # each grid cell size
OUT_W,  OUT_H  = 1920, 1080  # output canvas


# ── Helpers ───────────────────────────────────────────────────────────────────
class VideoLoader:
    """Synchronous frame reader (simple + reliable)."""
    def __init__(self, path: str, name: str = ""):
        self.name = name
        self.cap  = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open: {path}")
        self.w          = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.h          = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps        = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total      = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.stopped    = False

    def read(self):
        if self.stopped:
            return None
        ret, frame = self.cap.read()
        if not ret:
            self.stopped = True
            return None
        return frame

    def running(self):
        return not self.stopped

    def stop(self):
        self.stopped = True
        self.cap.release()


class VideoWriter:
    """Threaded video writer."""
    def __init__(self, path: str, fps: float, size: tuple):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._wr  = cv2.VideoWriter(str(path), fourcc, fps, size)
        self._q   = Queue(maxsize=QUEUE_SIZE)
        self._t   = Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        while True:
            try:
                frame = self._q.get(timeout=0.2)
                if frame is None:
                    break
                self._wr.write(frame)
                self._q.task_done()
            except Empty:
                continue
        self._wr.release()

    def write(self, frame):
        self._q.put(frame)

    def stop(self):
        self._q.put(None)
        self._t.join()


class InferenceThread:
    """Single shared GPU inference thread (batched)."""
    def __init__(self, model, conf: float, imgsz: int):
        self.model   = model
        self.conf    = conf
        self.imgsz   = imgsz
        self._q_in   = Queue(maxsize=32)
        self._q_out  = Queue(maxsize=32)
        self._stop   = False
        self._t      = Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()
        return self

    def _run(self):
        while not self._stop:
            try:
                token, frames = self._q_in.get(timeout=0.1)
                if frames:
                    results = self.model(
                        frames, verbose=False, iou=0.5,
                        conf=self.conf, imgsz=self.imgsz, rect=False)
                else:
                    results = []
                self._q_out.put((token, results))
                self._q_in.task_done()
            except Empty:
                continue
            except Exception as e:
                print(f"[InferenceThread] Error: {e}")

    def put(self, token, frames):
        self._q_in.put((token, frames))

    def get(self):
        return self._q_out.get()

    def stop(self):
        self._stop = True


# ── Drawing helpers ───────────────────────────────────────────────────────────
def parse_dets(res):
    dets = []
    for b in res.boxes:
        dets.append({"bbox": b.xyxy[0].cpu().numpy(), "conf": float(b.conf)})
    return dets


def draw_camera_overlay(frame, track, cam_name: str, is_pred: bool, cell_size):
    """Draw bbox, trail, label on a camera frame (already cell-sized)."""
    if not track:
        cv2.putText(frame, f"{cam_name}", (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1)
        return
    x1, y1, x2, y2 = map(int, track["bbox"])
    cx,  cy         = map(int, track["centroid"])
    color = (0, 200, 255) if is_pred else (
            (0, 255, 0) if track["missed"] == 0 else (0, 80, 255))

    # Trail
    history = track.get("history", [])
    if len(history) >= 2:
        pts = np.array(history, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [pts], False, (0, 140, 255), 2)

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    spd = track.get("speed", 0.0)
    cv2.putText(frame, f"ID{track['id']} {spd:.0f}px",
                (x1, max(14, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    cv2.circle(frame, (cx, cy), 5, (0, 255, 255), -1)

    # Camera label
    cv2.putText(frame, cam_name, (8, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def build_telemetry_panel(fps, yolo_ms, pos3d, speed3d, accel3d, frame_idx):
    """Build a 960×540 dark telemetry panel."""
    panel = np.zeros((CELL_H, CELL_W, 3), dtype=np.uint8)
    panel[:] = (22, 22, 30)

    def put(text, y, color=(220, 220, 220), scale=0.75, thick=1):
        cv2.putText(panel, text, (30, y),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)

    put("=== GARAGE 3D TRACKER ===", 40,  (0, 220, 255), 0.85, 2)
    put(f"Frame:     {frame_idx}",   90,  (200, 200, 200))
    put(f"FPS:       {fps:.1f}",    130,  (0, 255, 120), 0.9, 2)
    put(f"YOLO:      {yolo_ms:.1f} ms", 170, (0, 220, 255))

    put("─── 3D Position (m) ───", 225, (180, 180, 180), 0.65)
    if pos3d is not None:
        X, Y, Z = pos3d
        put(f"  X: {X:+.3f} m", 265, (100, 255, 100))
        put(f"  Y: {Y:+.3f} m", 300, (100, 200, 255))
        put(f"  Z: {Z:+.3f} m", 335, (255, 180, 100))
        spd_col = (0, 255, 0) if speed3d > 0.1 else (150, 150, 150)
        put(f"Speed:  {speed3d:.2f} m/s",  380, spd_col, 0.9, 2)
        put(f"Accel:  {accel3d:.2f} m/s²", 420, (200, 200, 100))
    else:
        put("  Ball: NOT TRACKED",  280, (0, 80, 255), 0.85, 2)

    return panel


# ── 3D Field mini-map ─────────────────────────────────────────────────────────
class FieldMinimap:
    """Top-down 2D overhead view of the ~10×10 m Garage arena."""
    SZ = (CELL_W, CELL_H)   # 960 × 540

    def __init__(self):
        self.trail  = []
        # Arena extent in cm (matching extrinsics coordinate space → metres)
        self.arena_w = 10.0   # X range  (metres)
        self.arena_d = 10.0   # Z range  (metres)

    def _proj(self, x_m, z_m):
        """World (X,Z) metres → pixel (top-down)."""
        px = int(np.clip(x_m / self.arena_w, 0, 1) * (CELL_W - 40) + 20)
        py = int(np.clip(z_m / self.arena_d, 0, 1) * (CELL_H - 40) + 20)
        return px, py

    def update(self, pos3d):
        img = np.zeros((CELL_H, CELL_W, 3), dtype=np.uint8)
        img[:] = (18, 18, 25)

        # Grid
        gc = (45, 45, 55)
        for i in range(11):
            x = int(i / 10 * (CELL_W - 40) + 20)
            z = int(i / 10 * (CELL_H - 40) + 20)
            cv2.line(img, (x, 20), (x, CELL_H - 20), gc, 1)
            cv2.line(img, (20, z), (CELL_W - 20, z), gc, 1)

        # Arena border
        cv2.rectangle(img, (20, 20), (CELL_W - 20, CELL_H - 20), (120, 120, 120), 2)

        # Camera dots
        cam_pos = {
            "N": (5.0, 0.0), "S": (5.0, 10.0),
            "E": (10.0, 5.0), "W": (0.0, 5.0)
        }
        for lbl, (cx, cz) in cam_pos.items():
            px, py = self._proj(cx, cz)
            cv2.circle(img, (px, py), 6, (0, 200, 255), -1)
            cv2.putText(img, lbl, (px + 8, py + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

        # Trail
        if pos3d is not None:
            X, Y, Z = pos3d
            self.trail.append((X, Z))
            if len(self.trail) > 40:
                self.trail.pop(0)

        if len(self.trail) > 1:
            pts = np.array([self._proj(x, z) for x, z in self.trail],
                           dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], False, (0, 140, 255), 2)

        if pos3d is not None:
            px, py = self._proj(X, Z)
            cv2.circle(img, (px, py), 9, (0, 0, 255), -1)
            cv2.circle(img, (px, py), 9, (255, 255, 255), 1)

        cv2.putText(img, "Top-Down View", (CELL_W // 2 - 70, CELL_H - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        return img


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Garage 4-Camera 3D Ball Tracking")
    parser.add_argument("--scenario_dir", default="Garage/garage/sync_records/1")
    parser.add_argument("--scenario_id",  type=int, default=1)
    parser.add_argument("--model",        default=None,
                        help="Engine/PT path (auto-detects engine first)")
    parser.add_argument("--intrinsics",
                        default="athletic_center/Calibration/Intrinsics/unified_intrinsics.json")
    parser.add_argument("--extrinsics",
                        default="Garage/Scenario3/extrinsics_1.json")
    parser.add_argument("--out_dir",      default=".",
                        help="Directory for output files (default: Footbonaut root)")
    parser.add_argument("--device",       default="cuda:0")
    args = parser.parse_args()

    root = ROOT

    # ── Config ────────────────────────────────────────────────────────────────
    cfg_path = root / "config" / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    conf   = cfg.get("conf",   0.5)
    imgsz  = cfg.get("imgsz",  960)

    # ── Model ─────────────────────────────────────────────────────────────────
    engine_path = root / "model" / "y26s_garagev2.engine"
    pt_path     = root / "model" / "y26s_garagev2.pt"
    if args.model:
        model_path = args.model
    elif engine_path.exists():
        model_path = str(engine_path)
    else:
        print(f"[INFO] Engine not found at {engine_path}, using .pt model (slower).")
        model_path = str(pt_path)

    print(f"[Model] Loading: {model_path}")
    model = YOLO(model_path, task="detect")
    inf_thread = InferenceThread(model, conf, imgsz).start()

    # ── Calibration ───────────────────────────────────────────────────────────
    intrinsics_path = root / args.intrinsics
    extrinsics_path = root / args.extrinsics
    reconstructor   = GarageReconstructor(str(intrinsics_path), str(extrinsics_path))

    # ── Video Loaders ─────────────────────────────────────────────────────────
    scenario_dir = root / args.scenario_dir
    loaders = {}
    for cam in CAM_ORDER:
        vid_path = scenario_dir / f"{cam}.mp4"
        if not vid_path.exists():
            print(f"[WARN] Missing video: {vid_path}. Skipping camera {cam}.")
            continue
        loaders[cam] = VideoLoader(str(vid_path), cam)
        print(f"[Video] {cam}: {loaders[cam].total} frames @ {loaders[cam].fps:.1f} FPS  "
              f"({loaders[cam].w}×{loaders[cam].h})")

    if len(loaders) < 2:
        print("[ERROR] Need at least 2 cameras to run.")
        return

    fps_out = next(iter(loaders.values())).fps

    # ── Trackers ──────────────────────────────────────────────────────────────
    cam_trackers = {cam: tracker(cfg) for cam in loaders}
    tracker3d    = Tracker3D(history_len=20, alpha_smooth=0.7)
    minimap      = FieldMinimap()

    # ── Output ────────────────────────────────────────────────────────────────
    ts       = time.strftime("%Y%m%d_%H%M%S")
    out_stem = f"garage_scenario{args.scenario_id}_{ts}"
    out_dir  = Path(args.out_dir)
    vid_out  = out_dir / f"{out_stem}.mp4"
    csv_out  = out_dir / f"{out_stem}_metrics.csv"
    json_out = out_dir / f"{out_stem}_metrics.json"

    print(f"[Output] Video: {vid_out}")
    print(f"[Output] CSV:   {csv_out}")

    writer     = VideoWriter(str(vid_out), fps_out, (OUT_W, OUT_H))
    csv_file   = open(str(csv_out), "w", newline="")
    csv_w      = csv.writer(csv_file)
    csv_w.writerow([
        "frame_idx", "timestamp_s", "num_cams_detecting",
        *[f"{c}_cx" for c in CAM_ORDER],
        *[f"{c}_cy" for c in CAM_ORDER],
        *[f"{c}_speed" for c in CAM_ORDER],
        "x_m", "y_m", "z_m", "speed_mps", "accel_mps2", "yolo_ms", "fps"
    ])
    json_records = []

    # ── State ─────────────────────────────────────────────────────────────────
    frame_idx  = 0
    fps_smooth = 0.0
    last_tick  = cv2.getTickCount()
    yolo_ms    = 0.0

    adaptive_cfg     = cfg.get("adaptive_skipping", {})
    adaptive_enabled = adaptive_cfg.get("enabled", False)
    next_detect_at   = 0

    print("\n[RUN] Starting inference loop...")
    try:
        while True:
            # ── Read one frame per camera ──────────────────────────────────
            frames = {}
            for cam, ldr in loaders.items():
                f = ldr.read()
                if f is None:
                    break
                frames[cam] = f
            if len(frames) < len(loaders):
                print("[INFO] End of video(s).")
                break

            frame_idx += 1
            curr_t = (frame_idx - 1) / fps_out

            # ── YOLO inference ────────────────────────────────────────────
            run_det = frame_idx >= next_detect_at
            batch   = [frames[cam] for cam in CAM_ORDER if cam in frames]
            cam_seq = [cam for cam in CAM_ORDER if cam in frames]

            token = time.time()
            inf_thread.put(token, batch if run_det else [])

            # Retrieve results (synchronous)
            t_inf0 = time.perf_counter()
            _, results = inf_thread.get()
            t_inf1 = time.perf_counter()
            yolo_ms = (t_inf1 - t_inf0) * 1000.0

            # ── Per-camera tracking ───────────────────────────────────────
            tracks = {}
            observations = {}
            num_det = 0
            for i, cam in enumerate(cam_seq):
                dets = parse_dets(results[i]) if (run_det and len(results) > i) else []
                t    = cam_trackers[cam].update(dets, frame_idx)
                tracks[cam] = t[0] if t else None
                if tracks[cam] and tracks[cam]["missed"] == 0:
                    num_det += 1
                    observations[CAM_EXTR[cam]] = tracks[cam]["centroid"]

            # ── Triangulation ─────────────────────────────────────────────
            pos3d = reconstructor.triangulate(observations)
            s3d   = tracker3d.update(pos3d, curr_t)

            speed3d = s3d["velocity"] if s3d else 0.0
            accel3d = s3d.get("accel", 0.0) if s3d else 0.0

            # Adaptive skipping
            if adaptive_enabled and run_det:
                if speed3d > 2.0:
                    skip = 0
                elif speed3d > 0.1:
                    skip = 2
                else:
                    skip = 4
                if num_det == 0:
                    skip = 0
                next_detect_at = frame_idx + skip

            # ── FPS ───────────────────────────────────────────────────────
            now = cv2.getTickCount()
            dt  = (now - last_tick) / cv2.getTickFrequency()
            if dt > 0:
                fps_cur    = 1.0 / dt
                fps_smooth = 0.9 * fps_smooth + 0.1 * fps_cur
            last_tick = now

            # ── Build 2×2 grid ────────────────────────────────────────────
            canvas = np.zeros((OUT_H, OUT_W, 3), dtype=np.uint8)

            # Grid positions: (row, col) → pixel offset
            grid_pos = {
                "East":  (0, 0),
                "West":  (0, CELL_W),
                "North": (CELL_H, 0),
                "South": (CELL_H, CELL_W),
            }

            for cam in CAM_ORDER:
                if cam not in frames:
                    continue
                r, c = grid_pos[cam]
                cell = cv2.resize(frames[cam], (CELL_W, CELL_H))
                draw_camera_overlay(
                    cell, tracks.get(cam), cam, not run_det, (CELL_W, CELL_H))
                # FPS overlay on East (top-left)
                if cam == "East":
                    cv2.putText(cell, f"FPS {fps_smooth:.1f}",
                                (CELL_W - 140, 28),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 120), 2)
                canvas[r:r+CELL_H, c:c+CELL_W] = cell

            # Bottom-right: telemetry panel
            panel = build_telemetry_panel(
                fps_smooth, yolo_ms, pos3d, speed3d, accel3d, frame_idx)
            canvas[CELL_H:, CELL_W:] = panel

            # Overlay minimap in bottom-left corner of telemetry panel
            # (small 240×135 map inside the panel)
            mini = minimap.update(pos3d)
            mini_s = cv2.resize(mini, (240, 135))
            canvas[CELL_H + CELL_H - 150:CELL_H + CELL_H - 15,
                   CELL_W + 10:CELL_W + 250] = mini_s

            writer.write(canvas)

            # ── Metrics ───────────────────────────────────────────────────
            def _cx(cam): return tracks[cam]["centroid"][0] if tracks.get(cam) else -1
            def _cy(cam): return tracks[cam]["centroid"][1] if tracks.get(cam) else -1
            def _sp(cam): return tracks[cam].get("speed", 0) if tracks.get(cam) else 0

            x_m = float(pos3d[0]) if pos3d is not None else -1
            y_m = float(pos3d[1]) if pos3d is not None else -1
            z_m = float(pos3d[2]) if pos3d is not None else -1

            csv_w.writerow([
                frame_idx, f"{curr_t:.4f}", num_det,
                *[f"{_cx(c):.1f}" for c in CAM_ORDER],
                *[f"{_cy(c):.1f}" for c in CAM_ORDER],
                *[f"{_sp(c):.1f}" for c in CAM_ORDER],
                f"{x_m:.3f}", f"{y_m:.3f}", f"{z_m:.3f}",
                f"{speed3d:.3f}", f"{accel3d:.3f}",
                f"{yolo_ms:.1f}", f"{fps_smooth:.1f}",
            ])

            json_records.append({
                "frame": frame_idx,
                "t": round(curr_t, 4),
                "cams_detecting": num_det,
                "pos3d": {"x": round(x_m, 3), "y": round(y_m, 3), "z": round(z_m, 3)},
                "speed_mps": round(speed3d, 3),
                "accel_mps2": round(accel3d, 3),
                "yolo_ms": round(yolo_ms, 1),
                "fps": round(fps_smooth, 1),
            })

            if frame_idx % 100 == 0:
                print(f"  Frame {frame_idx:5d} | FPS {fps_smooth:5.1f} | "
                      f"YOLO {yolo_ms:5.1f} ms | cams {num_det} | "
                      f"pos ({x_m:.2f}, {y_m:.2f}, {z_m:.2f}) m | "
                      f"spd {speed3d:.2f} m/s")

    finally:
        for ldr in loaders.values():
            ldr.stop()
        inf_thread.stop()
        writer.stop()
        csv_file.close()

        with open(str(json_out), "w") as f:
            json.dump(json_records, f, indent=2)

        print(f"\n✓ Done — {frame_idx} frames processed.")
        print(f"  Video:  {vid_out}")
        print(f"  CSV:    {csv_out}")
        print(f"  JSON:   {json_out}")

        # ── Per-scenario summary ───────────────────────────────────────────
        if json_records:
            avg_fps  = np.mean([r["fps"]       for r in json_records])
            avg_yolo = np.mean([r["yolo_ms"]   for r in json_records])
            det_rate = np.mean([r["cams_detecting"] > 0 for r in json_records])
            spds     = [r["speed_mps"] for r in json_records if r["speed_mps"] > 0]
            avg_spd  = np.mean(spds) if spds else 0.0
            max_spd  = max(spds)     if spds else 0.0

            summary = {
                "scenario_id":   args.scenario_id,
                "frames":        frame_idx,
                "avg_fps":       round(float(avg_fps),  1),
                "avg_yolo_ms":   round(float(avg_yolo), 1),
                "ball_det_rate": round(float(det_rate) * 100, 1),
                "avg_speed_mps": round(float(avg_spd), 2),
                "max_speed_mps": round(float(max_spd), 2),
                "output_video":  str(vid_out),
            }

            # Write machine-readable summary for run_all_scenarios.py
            summary_path = out_dir / f"{out_stem}_summary.json"
            with open(str(summary_path), "w") as f:
                json.dump(summary, f, indent=2)

            print("\nScenario Summary:")
            for k, v in summary.items():
                print(f"  {k}: {v}")
            return summary
        return None


if __name__ == "__main__":
    main()
