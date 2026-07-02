import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import math
import multiprocessing as mp
import re
import shutil
import os
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from queue import Full
from pathlib import Path
from typing import Optional, Dict, Tuple

import cv2
import matplotlib.pyplot as plt
import numpy as np
import yaml
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


CONNECTIONS = [
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (5, 6),
    (11, 12),
    (5, 11),
    (6, 12),
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
]

# --- skeleton side classification + cinematic palette (BGR) ---
LEFT_JOINTS = {1, 3, 5, 7, 9, 11, 13, 15}
RIGHT_JOINTS = {2, 4, 6, 8, 10, 12, 14, 16}
COL_LEFT = (40, 170, 255)    # warm orange  (left side)
COL_RIGHT = (255, 200, 40)   # cyan         (right side)
COL_SPINE = (240, 240, 240)  # near-white   (torso/head links)
COL_HEAD = (150, 255, 170)   # mint         (face)
TRAIL_JOINTS = (9, 10, 15, 16)  # wrists + ankles get motion trails


def _bone_color(s, e):
    if s in LEFT_JOINTS and e in LEFT_JOINTS:
        return COL_LEFT
    if s in RIGHT_JOINTS and e in RIGHT_JOINTS:
        return COL_RIGHT
    if s <= 4 or e <= 4:
        return COL_HEAD
    return COL_SPINE


def _shade(color, f):
    """Scale a BGR colour brightness by f (for glow / depth shading)."""
    return tuple(int(max(0, min(255, c * f))) for c in color)


def _heat_color(speed_mm_s, vmax=2500.0):
    """Map a joint speed (mm/s) to a blue->cyan->green->yellow->red BGR ramp."""
    t = float(np.clip(speed_mm_s / max(1e-6, vmax), 0.0, 1.0))
    stops = [(255, 80, 0), (255, 255, 0), (0, 255, 0), (0, 220, 255), (0, 40, 255)]  # BGR
    p = t * (len(stops) - 1)
    i = int(p); f = p - i
    if i >= len(stops) - 1:
        return stops[-1]
    a, b = stops[i], stops[i + 1]
    return tuple(int(a[k] * (1 - f) + b[k] * f) for k in range(3))


class OneEuroVec:
    """One-Euro filter for a 3D point: low lag on fast motion, smooth when slow.
    Far better than a fixed EMA for live display (Casiez et al., CHI 2012).
    Also exposes the last per-axis velocity estimate (dx) for heat-colouring."""

    def __init__(self, mincutoff=1.2, beta=0.3, dcutoff=1.0):
        self.mincutoff = float(mincutoff)
        self.beta = float(beta)
        self.dcutoff = float(dcutoff)
        self.x_prev = None
        self.dx_prev = np.zeros(3, dtype=np.float64)
        self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * np.pi * max(1e-6, cutoff))
        return 1.0 / (1.0 + tau / max(1e-6, dt))

    def reset(self):
        self.x_prev = None
        self.t_prev = None
        self.dx_prev = np.zeros(3, dtype=np.float64)

    def __call__(self, x, t):
        x = np.asarray(x, dtype=np.float64)
        if self.x_prev is None or self.t_prev is None:
            self.x_prev = x.copy()
            self.t_prev = t
            return x.copy()
        dt = t - self.t_prev
        if dt <= 0:
            dt = 1e-3
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.dcutoff, dt)
        edx = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.mincutoff + self.beta * np.abs(edx)
        a = np.array([self._alpha(c, dt) for c in cutoff])
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev = x_hat
        self.dx_prev = edx
        self.t_prev = t
        return x_hat

    def speed(self):
        return float(np.linalg.norm(self.dx_prev))


CAM_ORDER = ["camEast", "camNorth", "camSouth", "camWest"]


def camera_order_from_config(cams_cfg):
    """Keep legacy 4-cam ordering, then append any additional configured cameras."""
    legacy = [cam for cam in CAM_ORDER if cam in cams_cfg]
    extras = [cam for cam in cams_cfg if cam not in CAM_ORDER]
    return legacy + extras


def iter_frame_batches(frames, max_batch_size):
    max_batch_size = max(1, int(max_batch_size))
    for start in range(0, len(frames), max_batch_size):
        yield frames[start:start + max_batch_size]


def run_yolopose_batched(model, frames, max_batch_size, **kwargs):
    results = []
    for batch in iter_frame_batches(frames, max_batch_size):
        batch_results = model(batch, **kwargs)
        batch_results = [] if batch_results is None else list(batch_results)
        if len(batch_results) < len(batch):
            batch_results.extend([None] * (len(batch) - len(batch_results)))
        results.extend(batch_results[:len(batch)])
    return results

JOINT_NAME_TO_IDX = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}

DERIVED_UDP_JOINTS = {"body_center"}

IDX_TO_JOINT_NAME = {v: k for k, v in JOINT_NAME_TO_IDX.items()}
BALL_FLIGHT_AIRBORNE = "AIRBORNE"
BALL_FLIGHT_FLOOR = "FLOOR"
BALLISTIC_VZ_EMA_ALPHA = 0.35
BALLISTIC_MAX_VZ_MM_S = 12000.0
# Frames the push-up coach keeps its camera locked after acquisition is lost.
# A short grace window (~2 s at 15 FPS) rides out a posture-gate flicker so a
# brief loss cannot trigger a disorienting mid-set camera switch.
COACH_CAMERA_LOCK_HOLD_FRAMES = 30


def ensure_project_src_on_path():
    src_dir = Path(__file__).resolve().parent.parent.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    return src_dir

# --------------- BLM Demo: ballistic math + correction ---------------

def _blm_forward_right(yaw_deg):
    yaw = math.radians(yaw_deg)
    fwd = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    right = np.array([fwd[1], -fwd[0], 0.0])
    return fwd, right


def _blm_world_to_launcher(target_mm, launcher_mm, yaw_deg):
    d = np.asarray(target_mm, dtype=np.float64) - np.asarray(launcher_mm, dtype=np.float64)
    fwd, right = _blm_forward_right(yaw_deg)
    x_lat = float(np.dot(d[:2], right[:2])) / 1000.0
    y_fwd = float(np.dot(d[:2], fwd[:2])) / 1000.0
    dz = float(d[2]) / 1000.0
    return x_lat, y_fwd, dz


def _blm_solve(x_lat_m, y_fwd_m, dz_m, v_ms, g=9.81):
    if y_fwd_m <= 0.15:
        return None
    d = math.sqrt(x_lat_m**2 + y_fwd_m**2)
    if d <= 1e-6:
        return None
    h_deg = math.degrees(math.atan2(x_lat_m, y_fwd_m))
    disc = v_ms**4 - g * (g * d**2 + 2.0 * dz_m * v_ms**2)
    if disc < 0.0:
        return None
    v_rad = math.atan((v_ms**2 - math.sqrt(disc)) / (g * d))
    v_deg = math.degrees(v_rad)
    return v_deg, h_deg


def _blm_load_correction(path):
    try:
        with open(path) as f:
            data = json.load(f)
        model = {"bias": np.array([data["global_bias_add_mm"]["x"],
                                   data["global_bias_add_mm"]["y"],
                                   data["global_bias_add_mm"]["z"]])}
        if "axis_linear_gt_from_est" in data:
            model["linear"] = data["axis_linear_gt_from_est"]
        return model
    except Exception:
        return None


def _blm_correct(xyz, model, mode):
    if model is None or mode == "none":
        return xyz.copy()
    xyz = np.array(xyz, dtype=np.float64)
    if mode == "bias":
        return xyz + model["bias"]
    if mode == "linear" and "linear" in model:
        for i, ax in enumerate(["x", "y", "z"]):
            if ax in model["linear"]:
                xyz[i] = model["linear"][ax]["a"] * xyz[i] + model["linear"][ax]["b"]
    return xyz


@dataclass
class BallFlightState:
    mode: str = BALL_FLIGHT_FLOOR
    last_multicam_pos_mm: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    last_multicam_vel_mm_s: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    t_last_multicam: float = 0.0
    frames_since_multicam: int = 0


class StageTimer:
    def __init__(self, window=60):
        self.window = max(1, int(window))
        self._t0 = {}
        self._hist = {}

    def start(self, stage):
        self._t0[stage] = time.perf_counter()

    def stop(self, stage):
        t0 = self._t0.get(stage)
        if t0 is None:
            return 0.0
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if stage not in self._hist:
            self._hist[stage] = deque(maxlen=self.window)
        self._hist[stage].append(dt_ms)
        return dt_ms

    def avg_ms(self, stage):
        h = self._hist.get(stage)
        if not h:
            return 0.0
        return float(sum(h) / len(h))

    def report(self, frame_idx, every):
        if every <= 0 or frame_idx == 0 or frame_idx % every != 0:
            return None
        order = ["capture", "ball", "ballwait", "pose", "triang", "coach", "udp", "viz3d", "mosaic", "total"]
        parts = []
        payload = {"frame": int(frame_idx)}
        for stage in order:
            val = self.avg_ms(stage)
            if val > 0:
                parts.append(f"{stage}={val:.1f}")
                payload[f"{stage}_ms"] = val
        if not parts:
            return None
        line = f"[PERF f={frame_idx}] " + " | ".join(parts)
        return line, payload


class ThreadedCapture:
    def __init__(self, cap, name="cam"):
        self.cap = cap
        self.name = name
        self.lock = threading.Lock()
        self.running = True
        self.frame = None
        self.ts = 0.0
        self.total_frames = 0
        self.dropped_frames = 0
        self._has_unconsumed = False
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        while self.running:
            ret, fr = self.cap.read()
            if not ret or fr is None:
                time.sleep(0.01)
                continue
            now = time.perf_counter()
            with self.lock:
                if self._has_unconsumed:
                    self.dropped_frames += 1
                self.frame = fr
                self.ts = now
                self.total_frames += 1
                self._has_unconsumed = True

    def read_latest(self):
        # Return the camera's MOST RECENT frame every call (staleness is gated by
        # the caller via --max-frame-age-ms). Previously this returned a frame only
        # if brand-new+unconsumed, so a multi-cam batch required >=2 async cameras
        # to deliver within the same loop iteration — rare at low fps -> the 3D
        # skeleton updated ~1 Hz with 6 cameras. The is_new flag lets the caller
        # tell whether the frame changed since the last read.
        with self.lock:
            if self.frame is None:
                return False, None, 0.0, False
            fr = self.frame
            ts = self.ts
            is_new = self._has_unconsumed
            self._has_unconsumed = False
        return True, fr, ts, is_new

    def stats(self):
        with self.lock:
            return {"total": int(self.total_frames), "dropped": int(self.dropped_frames)}

    def release(self):
        self.running = False
        self.cap.release()
        self.thread.join(timeout=1.0)


def load_cameras(config_path):
    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}
    cams = data.get("cameras", {})
    return cams


def open_camera_capture(device):
    if sys.platform.startswith("linux") and str(device).startswith("/dev/"):
        return cv2.VideoCapture(device, cv2.CAP_V4L2)
    return cv2.VideoCapture(device)


def v4l2_device_ready(device, timeout_s=3.0, run_fn=subprocess.run, v4l2_ctl=None):
    """Return whether a Linux V4L2 node responds before OpenCV opens it."""
    if timeout_s is None or float(timeout_s) <= 0:
        return True, "disabled"
    if not sys.platform.startswith("linux") or not str(device).startswith("/dev/"):
        return True, "not_v4l2"
    tool = v4l2_ctl or shutil.which("v4l2-ctl")
    if not tool:
        return True, "v4l2-ctl missing"
    cmd = [tool, "-d", str(device), "--info"]
    try:
        result = run_fn(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=float(timeout_s),
        )
    except subprocess.TimeoutExpired:
        return False, f"v4l2-ctl --info timed out after {float(timeout_s):.1f}s"
    except OSError as exc:
        return False, str(exc)
    if int(getattr(result, "returncode", 1)) != 0:
        detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "").strip()
        return False, detail or f"v4l2-ctl --info exited {result.returncode}"
    return True, "ok"


def apply_uvc_low_latency_controls(device, cam, args, log=False):
    """Stabilize USB webcams so auto exposure cannot silently drop FPS."""
    if args.no_uvc_controls:
        return
    if not sys.platform.startswith("linux") or not str(device).startswith("/dev/"):
        return
    v4l2_ctl = shutil.which("v4l2-ctl")
    if not v4l2_ctl:
        return

    controls = [
        ("power_line_frequency", int(args.uvc_power_line_frequency)),
        ("exposure_dynamic_framerate", 0),
        ("auto_exposure", 1),  # V4L2 manual exposure mode for UVC cameras.
        ("exposure_time_absolute", int(args.uvc_exposure)),
    ]
    if int(args.uvc_gain) >= 0:
        controls.append(("gain", int(args.uvc_gain)))
    if int(args.uvc_focus) >= 0:
        controls.extend([
            ("focus_automatic_continuous", 0),
            ("focus_absolute", int(args.uvc_focus)),
        ])

    applied = []
    failed = []
    for name, value in controls:
        proc = subprocess.run(
            [v4l2_ctl, "-d", str(device), f"--set-ctrl={name}={value}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        (applied if proc.returncode == 0 else failed).append(name)

    if log and applied:
        msg = (
            f"[INFO] {cam}: UVC low-latency controls applied "
            f"(exposure={args.uvc_exposure}, gain={args.uvc_gain}, "
            f"focus={args.uvc_focus}, power_line={args.uvc_power_line_frequency})"
        )
        if failed:
            msg += f"; skipped unsupported: {','.join(failed)}"
        print(msg)


def parse_dimensions(filepath):
    dims = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    tags = {}
    with open(filepath, "r") as f:
        content = f.read()

    m = re.search(r"X\s*=\s*(\d+(?:\.\d+)?)\s*cm", content)
    if m:
        dims["X"] = float(m.group(1)) * 10.0
    m = re.search(r"Y\s*=\s*(\d+(?:\.\d+)?)\s*cm", content)
    if m:
        dims["Y"] = float(m.group(1)) * 10.0
    m = re.search(r"Z\s*=\s*(\d+(?:\.\d+)?)\s*cm", content)
    if m:
        dims["Z"] = float(m.group(1)) * 10.0

    parts = re.split(r"ID=(\d+):", content)
    for i in range(1, len(parts), 2):
        tag_id = int(parts[i])
        sec = parts[i + 1]
        hits = re.findall(
            r"c\d\s*\(\s*([\d\.]+)\s*,\s*([\d\.]+)\s*,\s*([\d\.]+)\s*\)", sec
        )
        if len(hits) != 4:
            continue
        corners = []
        for x, y, z in hits:
            corners.append([float(x) * 10.0, float(y) * 10.0, float(z) * 10.0])
        tags[tag_id] = np.array(corners, dtype=np.float32)
    return dims, tags


def load_intrinsics(path):
    with open(path, "r") as f:
        data = json.load(f)
    k = np.array(data["camera_matrix"], dtype=np.float64)
    d = np.array(data["distortion_coefficients"], dtype=np.float64)
    if d.ndim == 2:
        d = d[0]
    w = int(data.get("image_width", 0) or 0)
    h = int(data.get("image_height", 0) or 0)
    return k, d, w, h


def scale_intrinsics_matrix(k, src_w, src_h, dst_w, dst_h):
    if src_w <= 0 or src_h <= 0:
        return np.array(k, copy=True, dtype=np.float64)
    sx = float(dst_w) / float(src_w)
    sy = float(dst_h) / float(src_h)
    kk = np.array(k, copy=True, dtype=np.float64)
    kk[0, 0] *= sx
    kk[1, 1] *= sy
    kk[0, 2] *= sx
    kk[1, 2] *= sy
    return kk


def load_extrinsics(path):
    with open(path, "r") as f:
        data = json.load(f)
    cams = {}
    for name, cam in data.items():
        rvec = np.array(cam["rvec"], dtype=np.float64).reshape(3, 1)
        tvec = np.array(cam["tvec"], dtype=np.float64).reshape(3, 1) * 1000.0
        rmat, _ = cv2.Rodrigues(rvec)
        p = np.hstack([rmat, tvec])
        cam_pos = np.array(cam.get("camera_position", [0, 0, 0]), dtype=np.float64) * 1000.0
        cams[name] = {"rvec": rvec, "R": rmat, "tvec": tvec, "P": p, "pos": cam_pos}
    return cams


def undistort_points(pt, k, d):
    pts = np.array([[pt]], dtype=np.float64)
    und = cv2.undistortPoints(pts, k, d)
    return und[0, 0]


def undistort_points_batch(pts, k, d):
    if not pts:
        return []
    arr = np.array(pts, dtype=np.float64).reshape(-1, 1, 2)
    und = cv2.undistortPoints(arr, k, d)
    return [und[i, 0] for i in range(und.shape[0])]


def triangulate_multi(observations, proj_mats):
    if len(observations) < 2:
        return None
    a = []
    for cam, (x, y) in observations.items():
        p = proj_mats[cam]
        a.append(x * p[2] - p[0])
        a.append(y * p[2] - p[1])
    a = np.array(a, dtype=np.float64)
    if a.shape[0] < 4:
        return None
    _, _, vt = np.linalg.svd(a)
    x = vt[-1]
    if abs(x[3]) < 1e-9:
        return None
    return x[:3] / x[3]


def project_world_to_pixel(point_w, R, tvec, K, D):
    rvec, _ = cv2.Rodrigues(R)
    pt = np.asarray(point_w, dtype=np.float64).reshape(1, 1, 3)
    uv, _ = cv2.projectPoints(pt, rvec, tvec, K, D)
    return uv.reshape(2)


def parse_coach_zone_mm(value):
    if not value:
        return None
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    if len(parts) != 4:
        raise RuntimeError("--coach-zone-mm must be x_min,y_min,x_max,y_max")
    try:
        x1, y1, x2, y2 = [float(p) for p in parts]
    except ValueError as exc:
        raise RuntimeError("--coach-zone-mm values must be numbers") from exc
    return np.array(
        [[x1, y1, 0.0], [x2, y1, 0.0], [x2, y2, 0.0], [x1, y2, 0.0]],
        dtype=np.float64,
    )


def joints_array_to_frame(joints, conf, cams, frame_idx, fps):
    out = []
    arr = np.asarray(joints, dtype=np.float64)
    for idx in range(17):
        pt = arr[idx] if idx < len(arr) else np.full((3,), np.nan)
        if np.isfinite(pt).all():
            out.append([float(pt[0]), float(pt[1]), float(pt[2])])
        else:
            out.append(None)
    return {
        "frame_index": int(frame_idx),
        "time_s": float(frame_idx) / max(1.0, float(fps)),
        "joints": out,
        "joint_conf": [float(v) for v in np.asarray(conf).reshape(-1)[:17]],
        "joint_cams": [int(v) for v in np.asarray(cams).reshape(-1)[:17]],
    }


def project_zone_to_overlay(zone_mm, cam, extr, intr, roi, output_size):
    if zone_mm is None or cam not in extr or cam not in intr:
        return None
    out_w, out_h = output_size
    sx = float(out_w) / max(1, roi.width)
    sy = float(out_h) / max(1, roi.height)
    projected = []
    for pt in zone_mm:
        try:
            uv = project_world_to_pixel(pt, extr[cam]["R"], extr[cam]["tvec"], intr[cam]["K"], intr[cam]["D"])
        except Exception:
            return None
        if not np.isfinite(uv).all():
            return None
        projected.append(((float(uv[0]) - roi.x1) * sx, (float(uv[1]) - roi.y1) * sy))
    return projected


def project_joints_to_overlay(joints, conf, cams, cam, extr, intr, roi, output_size, min_conf=0.35, min_cams=2):
    kpts = np.full((17, 2), np.nan, dtype=np.float32)
    scores = np.zeros((17,), dtype=np.float32)
    if cam not in extr or cam not in intr:
        return kpts, scores
    out_w, out_h = output_size
    sx = float(out_w) / max(1, roi.width)
    sy = float(out_h) / max(1, roi.height)
    joints_arr = np.asarray(joints, dtype=np.float64)
    conf_arr = np.asarray(conf, dtype=np.float64).reshape(-1)
    cams_arr = np.asarray(cams, dtype=np.int32).reshape(-1)
    for idx in range(min(17, len(joints_arr))):
        if idx >= len(conf_arr) or idx >= len(cams_arr):
            continue
        if conf_arr[idx] < min_conf or cams_arr[idx] < min_cams:
            continue
        pt = joints_arr[idx]
        if not np.isfinite(pt).all():
            continue
        try:
            uv = project_world_to_pixel(pt, extr[cam]["R"], extr[cam]["tvec"], intr[cam]["K"], intr[cam]["D"])
        except Exception:
            continue
        if not np.isfinite(uv).all():
            continue
        kpts[idx] = [(float(uv[0]) - roi.x1) * sx, (float(uv[1]) - roi.y1) * sy]
        scores[idx] = float(np.clip(conf_arr[idx], 0.0, 1.0))
    return kpts, scores


def ballistic_predict_z(z0, vz, dt_s, g, floor):
    dt_s = max(0.0, float(dt_s))
    z_new = float(z0) + float(vz) * dt_s - 0.5 * float(g) * dt_s * dt_s
    return max(z_new, float(floor))


def estimate_ballistic_multicam_velocity(prev_pos_mm, prev_vel_mm_s, curr_pos_mm, dt_s):
    """Estimate velocity from accepted multi-cam locks with a conservative vz filter."""
    if dt_s <= 1e-6:
        return np.zeros(3, dtype=np.float64), 0.0
    prev_pos_mm = np.asarray(prev_pos_mm, dtype=np.float64)
    prev_vel_mm_s = np.asarray(prev_vel_mm_s, dtype=np.float64)
    curr_pos_mm = np.asarray(curr_pos_mm, dtype=np.float64)
    raw_vel = (curr_pos_mm - prev_pos_mm) / float(dt_s)
    if not np.isfinite(raw_vel).all():
        return np.zeros(3, dtype=np.float64), 0.0
    raw_vz = float(raw_vel[2])
    filt_vz = raw_vz
    if np.isfinite(prev_vel_mm_s[2]):
        filt_vz = ((1.0 - BALLISTIC_VZ_EMA_ALPHA) * float(prev_vel_mm_s[2])
                   + BALLISTIC_VZ_EMA_ALPHA * raw_vz)
    vel = raw_vel.copy()
    vel[2] = float(np.clip(filt_vz, -BALLISTIC_MAX_VZ_MM_S, BALLISTIC_MAX_VZ_MM_S))
    return vel, raw_vz


def project_ray_to_z_plane(obs_norm, R, tvec, target_z):
    """Intersect a single-camera ray with the world plane Z = target_z.

    obs_norm: (u, v) undistorted normalized image coords (output of cv2.undistortPoints).
    R: 3x3 world->cam rotation. tvec: 3x1 world->cam translation (mm).
    Returns 3D world point (mm) on the Z-plane, or None if the ray is parallel.

    Geometry: a pixel ray in cam frame at depth s is X_c = s * [u, v, 1].
    Then X_w = R^T (X_c - t). Solving X_w[2] = target_z for s gives a single
    intersection point. Gracefully handles rays near-parallel to the Z-plane.
    """
    u, v = float(obs_norm[0]), float(obs_norm[1])
    t = np.asarray(tvec, dtype=np.float64).reshape(3)
    # Third row of R^T == third column of R.
    r2 = R[:, 2]
    A = r2[0] * u + r2[1] * v + r2[2]
    if abs(A) < 1e-6:
        return None
    B = r2[0] * t[0] + r2[1] * t[1] + r2[2] * t[2]
    s = (target_z + B) / A
    if s <= 0:
        # Ray pointing backward from the camera — plane is behind the lens.
        return None
    X_c = np.array([u * s, v * s, s], dtype=np.float64)
    X_w = R.T @ (X_c - t)
    return X_w


def robust_triangulate_ball(obs_norm, obs_px, proj_mats, extr, intr, min_cams=2, max_reproj_px=15.0):
    """Iteratively reject the worst-reprojection camera until all are within tolerance."""
    if len(obs_norm) < min_cams:
        return None, [], None
    active = dict(obs_norm)
    while len(active) >= min_cams:
        X = triangulate_multi(active, proj_mats)
        if X is None:
            return None, [], None
        if max_reproj_px <= 0:
            return X, sorted(active.keys()), 0.0
        reproj = {}
        for cam in list(active.keys()):
            uv = project_world_to_pixel(X, extr[cam]["R"], extr[cam]["tvec"], intr[cam]["K"], intr[cam]["D"])
            reproj[cam] = float(np.linalg.norm(uv - obs_px[cam]))
        worst_cam = max(reproj, key=reproj.get)
        if reproj[worst_cam] <= max_reproj_px:
            return X, sorted(active.keys()), float(np.mean(list(reproj.values())))
        if len(active) == min_cams:
            return None, [], reproj[worst_cam]
        del active[worst_cam]
    return None, [], None


def robust_triangulate_joint(obs_norm, obs_px, proj_mats, extr, intr,
                             min_cams=2, max_reproj_px=40.0):
    """Per-joint robust triangulation: iteratively reject the worst-reprojection
    camera until every remaining ray agrees within max_reproj_px. Mirrors
    robust_triangulate_ball so a single bad camera pose (e.g. a high-RMSE cam) or
    a transient 2D keypoint mis-detection cannot fling a joint to a random 3D
    point. Returns (X | None, used_cams). Does NOT modify triangulate_multi."""
    if len(obs_norm) < min_cams:
        return None, []
    active = dict(obs_norm)
    while len(active) >= min_cams:
        X = triangulate_multi(active, proj_mats)
        if X is None:
            return None, []
        if max_reproj_px <= 0:
            return X, sorted(active.keys())
        reproj = {}
        for cam in list(active.keys()):
            uv = project_world_to_pixel(X, extr[cam]["R"], extr[cam]["tvec"],
                                        intr[cam]["K"], intr[cam]["D"])
            reproj[cam] = float(np.linalg.norm(uv - obs_px[cam]))
        worst_cam = max(reproj, key=reproj.get)
        if reproj[worst_cam] <= max_reproj_px:
            return X, sorted(active.keys())
        if len(active) == min_cams:
            return None, []
        del active[worst_cam]
    return None, []


def select_ball_box_for_cam(boxes_xyxyc, kf_pred_uv, kf_gate_px,
                            min_side_px, max_side_px):
    """Pick one ball bbox for a single camera from its raw YOLO candidates.

    boxes_xyxyc: iterable of (x1, y1, x2, y2, conf) in source-pixel coords.
    kf_pred_uv : (u, v) KF-predicted reprojection in this cam, or None.
    kf_gate_px : accept distance (px) from kf_pred_uv; <=0 disables the gate.
    min_side_px / max_side_px : accept boxes with max(w, h) in [min, max].
                                0 on either side disables that bound.
    Returns (x1, y1, x2, y2, conf) or None.
    """
    candidates = []
    for box in boxes_xyxyc:
        x1, y1, x2, y2, conf = box
        w = float(x2 - x1)
        h = float(y2 - y1)
        side = max(w, h)
        if min_side_px > 0 and side < min_side_px:
            continue
        if max_side_px > 0 and side > max_side_px:
            continue
        candidates.append((float(x1), float(y1), float(x2), float(y2), float(conf)))
    if not candidates:
        return None

    if kf_pred_uv is not None and kf_gate_px > 0:
        gated = []
        pu, pv = float(kf_pred_uv[0]), float(kf_pred_uv[1])
        for x1, y1, x2, y2, conf in candidates:
            cx = 0.5 * (x1 + x2)
            cy = 0.5 * (y1 + y2)
            if np.hypot(cx - pu, cy - pv) <= kf_gate_px:
                gated.append((x1, y1, x2, y2, conf))
        if gated:
            gated.sort(key=lambda b: -b[4])
            return gated[0]

    candidates.sort(key=lambda b: -b[4])
    return candidates[0]


def transform_world_point_y(world_pt, y_max, enabled=True):
    if world_pt is None or not enabled:
        return world_pt
    out = np.array(world_pt, copy=True)
    out[..., 1] = y_max - out[..., 1]
    return out


def flatten_predictions(preds):
    out = []
    if not preds:
        return out
    for item in preds:
        if isinstance(item, list):
            for sub in item:
                if isinstance(sub, dict):
                    out.append(sub)
        elif isinstance(item, dict):
            out.append(item)
    return out


def extract_person_pose(person):
    kpts = np.array(person.get("keypoints", []), dtype=np.float32)
    scores = np.array(person.get("keypoint_scores", []), dtype=np.float32)
    if kpts.ndim != 2 or kpts.shape[0] < 17 or kpts.shape[1] < 2:
        return None
    kpts = kpts[:17, :2]
    if scores.ndim == 0:
        scores = np.zeros((17,), dtype=np.float32)
    if len(scores) < 17:
        scores = np.pad(scores, (0, 17 - len(scores)), mode="constant")
    scores = scores[:17]
    valid = np.isfinite(kpts[:, 0]) & np.isfinite(kpts[:, 1]) & (scores > 0.05)
    if np.count_nonzero(valid) < 5:
        return None
    pts = kpts[valid]
    min_xy = pts.min(axis=0)
    max_xy = pts.max(axis=0)
    area = float(max(1.0, (max_xy[0] - min_xy[0]) * (max_xy[1] - min_xy[1])))
    mean_score = float(np.mean(scores[valid]))
    return {
        "kpts": kpts,
        "scores": scores,
        "area": area,
        "mean_score": mean_score,
    }


def pose_distance(curr, prev, conf_thresh):
    valid_curr = curr["scores"] > conf_thresh
    valid_prev = prev["scores"] > conf_thresh
    common = valid_curr & valid_prev
    if np.count_nonzero(common) < 4:
        return np.inf
    diff = curr["kpts"][common] - prev["kpts"][common]
    d = np.linalg.norm(diff, axis=1)
    return float(np.mean(d))


def select_target_person(candidates, prev_state, conf_thresh, switch_area_ratio):
    if not candidates:
        return None
    if prev_state is None:
        return max(candidates, key=lambda c: c["area"] * max(0.1, c["mean_score"]))
    tracked = min(candidates, key=lambda c: pose_distance(c, prev_state, conf_thresh))
    tracked_dist = pose_distance(tracked, prev_state, conf_thresh)
    dominant = max(candidates, key=lambda c: c["area"] * max(0.1, c["mean_score"]))
    if np.isinf(tracked_dist):
        return dominant
    if dominant is not tracked:
        if dominant["mean_score"] >= conf_thresh and dominant["area"] > tracked["area"] * switch_area_ratio:
            return dominant
    return tracked


def pose_health_payload(
    *,
    run_pose,
    pose_error,
    batch_order,
    pose_raw_counts,
    per_cam_pose_curr,
    pose_und_by_cam,
    joints_3d_now,
    joints_display,
):
    selected_cams = sorted(str(cam) for cam in per_cam_pose_curr.keys())
    raw_counts = {str(cam): int(pose_raw_counts.get(cam, 0)) for cam in batch_order}
    high_conf_counts = {
        str(cam): int(len(pose_und_by_cam.get(cam, {})))
        for cam in batch_order
    }
    visible = 0
    if joints_display is not None:
        arr = np.asarray(joints_display, dtype=np.float64)
        if arr.ndim == 2 and arr.shape[1] == 3:
            visible = int(np.count_nonzero(np.isfinite(arr).all(axis=1)))
    payload = {
        "pose_run": bool(run_pose),
        "pose_raw_person_count": int(sum(raw_counts.values())),
        "pose_raw_person_count_per_cam": raw_counts,
        "pose_selected_cam_count": int(len(selected_cams)),
        "pose_selected_cams": selected_cams,
        "pose_high_conf_keypoint_count": int(sum(high_conf_counts.values())),
        "pose_high_conf_keypoint_count_per_cam": high_conf_counts,
        "pose_triangulated_joint_count": int(len(joints_3d_now)),
        "pose_visible_joint_count": visible,
    }
    if pose_error:
        payload["pose_error"] = str(pose_error)
    return payload


def draw_arena_static(ax, dims, tags, extr, world_y_mirror=True):
    x_max, y_max, z_max = dims["X"], dims["Y"], dims["Z"]
    corners = np.array(
        [
            [0, 0, 0],
            [x_max, 0, 0],
            [x_max, y_max, 0],
            [0, y_max, 0],
            [0, 0, z_max],
            [x_max, 0, z_max],
            [x_max, y_max, z_max],
            [0, y_max, z_max],
        ],
        dtype=np.float32,
    )
    corners = transform_world_point_y(corners, y_max, enabled=world_y_mirror)
    floor = Poly3DCollection(
        [[corners[0], corners[1], corners[2], corners[3]]],
        alpha=0.07,
        facecolors="#d7e1e8",
        edgecolors="none",
    )
    ax.add_collection3d(floor)

    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    for a, b in edges:
        ax.plot(*zip(corners[a], corners[b]), color="#6b6b6b", linewidth=1.0, alpha=0.7)

    for tag_id, pts in tags.items():
        pts_vis = transform_world_point_y(pts, y_max, enabled=world_y_mirror)
        poly = Poly3DCollection([pts_vis], alpha=0.28, facecolors="#53c4f5", edgecolors="#0c74a8")
        ax.add_collection3d(poly)
        c = pts_vis.mean(axis=0)
        ax.text(c[0], c[1], c[2], str(tag_id), color="#0c74a8", fontsize=6)

    cam_colors = {"camNorth": "red", "camEast": "green", "camSouth": "blue", "camWest": "orange"}
    for name, cam in extr.items():
        pos = transform_world_point_y(cam["pos"], y_max, enabled=world_y_mirror)
        fwd = cam["R"].T[:, 2]
        if world_y_mirror:
            fwd = fwd.copy()
            fwd[1] = -fwd[1]
        col = cam_colors.get(name, "black")
        ax.scatter(pos[0], pos[1], pos[2], c=col, s=60, marker="^")
        ax.quiver(pos[0], pos[1], pos[2], fwd[0], fwd[1], fwd[2], length=500, color=col)
        ax.text(pos[0], pos[1], pos[2], name, color=col, fontsize=8)


def draw_global_axes(ax, dims, world_y_mirror=True, axis_len_mm=800.0):
    x_max, y_max, z_max = dims["X"], dims["Y"], dims["Z"]
    axis_len_mm = float(max(100.0, min(axis_len_mm, x_max, y_max, z_max)))

    o = transform_world_point_y(np.array([0.0, 0.0, 0.0], dtype=np.float32), y_max, enabled=world_y_mirror)
    px = transform_world_point_y(np.array([axis_len_mm, 0.0, 0.0], dtype=np.float32), y_max, enabled=world_y_mirror)
    py = transform_world_point_y(np.array([0.0, axis_len_mm, 0.0], dtype=np.float32), y_max, enabled=world_y_mirror)
    pz = transform_world_point_y(np.array([0.0, 0.0, axis_len_mm], dtype=np.float32), y_max, enabled=world_y_mirror)

    vx = px - o
    vy = py - o
    vz = pz - o

    # X (green), Y (red), Z (blue) from a single global origin.
    ax.quiver(o[0], o[1], o[2], vx[0], vx[1], vx[2], color="#3ecf4f", linewidth=2.5, arrow_length_ratio=0.08)
    ax.quiver(o[0], o[1], o[2], vy[0], vy[1], vy[2], color="#ff3b3b", linewidth=2.5, arrow_length_ratio=0.08)
    ax.quiver(o[0], o[1], o[2], vz[0], vz[1], vz[2], color="#3b82f6", linewidth=2.5, arrow_length_ratio=0.08)

    ax.text(o[0], o[1], o[2], "O(0,0,0)", color="black", fontsize=9, weight="bold")
    ax.text(px[0], px[1], px[2], "+X", color="#2ea043", fontsize=9, weight="bold")
    ax.text(py[0], py[1], py[2], "+Y", color="#d7263d", fontsize=9, weight="bold")
    ax.text(pz[0], pz[1], pz[2], "+Z", color="#1d4ed8", fontsize=9, weight="bold")


def draw_live_scene(
    ax,
    dims,
    tags,
    extr,
    ball_pt,
    ball_traj,
    joints,
    frame_idx,
    fps_est,
    world_y_mirror=True,
    invert_y_axis_display=False,
    draw_global_axes_flag=True,
    global_axis_len_mm=800.0,
    view_elev=22.0,
    view_azim=-58.0,
):
    ax.cla()
    x_max, y_max, z_max = dims["X"], dims["Y"], dims["Z"]
    ax.set_facecolor("#f7f7f7")
    ax.grid(True, color="#c0c0c0", linewidth=0.6, alpha=0.6)
    ax.set_box_aspect([x_max, y_max, z_max])
    draw_arena_static(ax, dims, tags, extr, world_y_mirror=world_y_mirror)
    if draw_global_axes_flag:
        draw_global_axes(ax, dims, world_y_mirror=world_y_mirror, axis_len_mm=global_axis_len_mm)

    if len(ball_traj) >= 2:
        tr = transform_world_point_y(np.array(ball_traj, dtype=np.float32), y_max, enabled=world_y_mirror)
        ax.plot(tr[:, 0], tr[:, 1], tr[:, 2], c="#f4b400", linewidth=2.2, alpha=0.9)

    if ball_pt is not None and np.isfinite(ball_pt).all():
        ball_vis = transform_world_point_y(ball_pt, y_max, enabled=world_y_mirror)
        ax.scatter(ball_vis[0], ball_vis[1], ball_vis[2], c="#f4b400", s=110, edgecolors="white", linewidths=1.0)

    if joints is not None:
        joints_vis = transform_world_point_y(joints, y_max, enabled=world_y_mirror)
        valid = np.isfinite(joints_vis[:, 0])
        for s, e in CONNECTIONS:
            if valid[s] and valid[e]:
                p1, p2 = joints_vis[s], joints_vis[e]
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], c="#111111", linewidth=2.2)
        for j in range(17):
            if valid[j]:
                ax.scatter(joints_vis[j, 0], joints_vis[j, 1], joints_vis[j, 2], c="#222222", s=20, edgecolors="white", linewidths=0.5)

    ax.set_xlim(0, x_max)
    if invert_y_axis_display:
        ax.set_ylim(y_max, 0)
    else:
        ax.set_ylim(0, y_max)
    ax.set_zlim(0, z_max)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title("Live 4-Cam Garage: Arena + Ball + Skeleton")
    ax.view_init(elev=float(view_elev), azim=float(view_azim))
    ax.text2D(0.02, 0.02, f"Frame: {frame_idx} | FPS: {fps_est:.2f}", transform=ax.transAxes, fontsize=10, color="#444444")


# ---------------------------------------------------------------------------
# OpenCV-based 3D renderer (replaces matplotlib for live use)
# ---------------------------------------------------------------------------

def make_orbit_view(elev_deg, azim_deg, dist_mm, look_at):
    """Build a 3x4 view matrix matching matplotlib's view_init(elev, azim).

    Matplotlib convention:
      azim=0  → camera on +Y axis (looking toward -Y)
      azim=90 → camera on +X axis
      elev    → angle above the XY plane
    Our spherical coords use cos/sin from +X, so we offset by 270° to align.
    """
    e = np.radians(elev_deg)
    a = np.radians(270.0 + azim_deg)  # convert matplotlib azim → standard spherical
    eye = look_at + dist_mm * np.array([
        np.cos(e) * np.cos(a),
        np.cos(e) * np.sin(a),
        np.sin(e),
    ])
    fwd = look_at - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0.0, 0.0, 1.0])
    rn = np.linalg.norm(right)
    if rn < 1e-6:
        right = np.array([1.0, 0.0, 0.0])
    else:
        right /= rn
    up = np.cross(right, fwd)
    R = np.stack([right, -up, fwd])  # camera X=right, Y=down, Z=forward
    t = -R @ eye
    return np.hstack([R, t.reshape(3, 1)])


def _cv2_project(pts_3d, view_34, fx, fy, cx, cy):
    """Project Nx3 world points to Nx2 screen coords + validity mask.

    X is mirrored (cx - ...) to match matplotlib's left-handed display convention,
    where +Y appears to the right and +X appears to the left on screen.
    """
    pts = np.asarray(pts_3d, dtype=np.float64)
    if pts.ndim == 1:
        pts = pts.reshape(1, 3)
    N = pts.shape[0]
    cam = view_34 @ np.hstack([pts, np.ones((N, 1))]).T  # 3xN
    z = cam[2]
    ok = z > 1.0
    scr = np.full((N, 2), np.nan)
    scr[ok, 0] = cx - fx * cam[0, ok] / z[ok]   # mirror X for matplotlib match
    scr[ok, 1] = fy * cam[1, ok] / z[ok] + cy
    return scr, ok


def draw_live_scene_cv2(
    img_w, img_h, dims, tags, extr,
    ball_pt, ball_traj, joints,
    frame_idx, fps_est,
    world_y_mirror=False,
    view_elev=22.0, view_azim=-58.0,
    draw_axes=True, axis_len=800.0,
    ghost_joints=None,
    predict_ahead_ms=0.0,
    blm_aim=None,
    theme="cinematic",
    trails=None,
    cams_tracking=None,
    joint_speeds=None,
    limb_heat=False,
    heat_vmax=2500.0,
    metrics=None,
    thumbnails=None,
    recording=False,
    avatar_body=False,
    avatar_markers=False,
    avatar_alpha=0.85,
    smpl_mesh_vertices=None,
    smpl_mesh_faces=None,
    smpl_mesh_alpha=0.45,
    smpl_mesh_max_faces=1500,
):
    """Render the 3D arena scene onto a cv2 BGR image (~1-3 ms)."""
    cine = (theme == "cinematic")
    if cine:
        # vertical gradient "stage" background (dark navy -> near black)
        img = np.empty((img_h, img_w, 3), dtype=np.uint8)
        top = np.array([46, 34, 28], dtype=np.float32)
        bot = np.array([20, 16, 16], dtype=np.float32)
        ramp = np.linspace(0.0, 1.0, img_h, dtype=np.float32)[:, None]
        col = (top[None, :] * (1 - ramp) + bot[None, :] * ramp).astype(np.uint8)
        img[:] = col[:, None, :]
    else:
        img = np.full((img_h, img_w, 3), 247, dtype=np.uint8)  # light grey bg
    x_max, y_max, z_max = dims["X"], dims["Y"], dims["Z"]
    center = np.array([x_max / 2, y_max / 2, z_max / 2])
    diag = np.sqrt(x_max**2 + y_max**2 + z_max**2)
    dist = diag * 1.6

    view = make_orbit_view(view_elev, view_azim, dist, center)
    f_px = img_w * 1.1
    cx, cy = img_w / 2.0, img_h / 2.0

    def proj(p3d):
        return _cv2_project(p3d, view, f_px, f_px, cx, cy)

    def line(p1, p2, color, thick=1):
        if np.isfinite(p1).all() and np.isfinite(p2).all():
            cv2.line(img, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])),
                     color, thick, cv2.LINE_AA)

    # --- arena wireframe ---
    corners = np.array([
        [0, 0, 0], [x_max, 0, 0], [x_max, y_max, 0], [0, y_max, 0],
        [0, 0, z_max], [x_max, 0, z_max], [x_max, y_max, z_max], [0, y_max, z_max],
    ], dtype=np.float64)
    corners = transform_world_point_y(corners, y_max, enabled=world_y_mirror)
    sc, ok = proj(corners)
    verticals = {(0, 4), (1, 5), (2, 6), (3, 7)}
    if cine:
        if np.all(ok[:4]):
            cv2.fillPoly(img, [sc[:4].astype(np.int32)], (40, 32, 28))
        # studio floor grid every 1 m
        for x in np.arange(0, x_max + 1, 1000.0):
            p = transform_world_point_y(np.array([[x, 0, 0], [x, y_max, 0]]), y_max, enabled=world_y_mirror)
            s2, o2 = proj(p)
            if o2[0] and o2[1]:
                line(s2[0], s2[1], (72, 60, 48), 1)
        for y in np.arange(0, y_max + 1, 1000.0):
            p = transform_world_point_y(np.array([[0, y, 0], [x_max, y, 0]]), y_max, enabled=world_y_mirror)
            s2, o2 = proj(p)
            if o2[0] and o2[1]:
                line(s2[0], s2[1], (72, 60, 48), 1)
        edge_col, vcol = (95, 80, 62), (150, 128, 92)
    else:
        if np.all(ok[:4]):
            cv2.fillPoly(img, [sc[:4].astype(np.int32)], (235, 230, 225))
        edge_col, vcol = (160, 160, 160), (160, 160, 160)
    arena_edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    for a, b in arena_edges:
        if ok[a] and ok[b]:
            line(sc[a], sc[b], vcol if (a, b) in verticals else edge_col, 1)

    # --- AprilTag planes ---
    for tag_id, pts in tags.items():
        pts_v = transform_world_point_y(pts, y_max, enabled=world_y_mirror)
        sp, sok = proj(pts_v)
        if np.all(sok):
            if cine:
                cv2.polylines(img, [sp.astype(np.int32)], True, (92, 80, 56), 1, cv2.LINE_AA)
            else:
                cv2.fillPoly(img, [sp.astype(np.int32)], (200, 230, 245))
                cv2.polylines(img, [sp.astype(np.int32)], True, (168, 116, 12), 1, cv2.LINE_AA)
                c2d = sp.mean(axis=0).astype(int)
                cv2.putText(img, str(tag_id), (c2d[0]-4, c2d[1]+4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (168, 116, 12), 1, cv2.LINE_AA)

    # --- camera markers ---
    cam_colors_bgr = {
        "camNorth": (0, 0, 200), "camEast": (0, 160, 0),
        "camSouth": (200, 0, 0), "camWest": (0, 140, 255),
    }
    for name, cam_data in extr.items():
        pos = transform_world_point_y(cam_data["pos"], y_max, enabled=world_y_mirror)
        sp, sok = proj(pos.reshape(1, 3))
        if sok[0]:
            pt = (int(sp[0, 0]), int(sp[0, 1]))
            col = cam_colors_bgr.get(name, (200, 180, 120))
            cv2.circle(img, pt, 6, col, -1, cv2.LINE_AA)
            cv2.putText(img, name, (pt[0]+8, pt[1]-4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1, cv2.LINE_AA)

    # --- ball trajectory ---
    if len(ball_traj) >= 2:
        tr = np.array(ball_traj, dtype=np.float64)
        tr = transform_world_point_y(tr, y_max, enabled=world_y_mirror)
        sp, sok = proj(tr)
        for i in range(1, len(tr)):
            if sok[i-1] and sok[i]:
                line(sp[i-1], sp[i], (0, 160, 220), 2)

    # --- ball point ---
    if ball_pt is not None and np.isfinite(ball_pt).all():
        bp = transform_world_point_y(ball_pt, y_max, enabled=world_y_mirror)
        sp, sok = proj(bp.reshape(1, 3))
        if sok[0]:
            cv2.circle(img, (int(sp[0,0]), int(sp[0,1])), 10, (0, 180, 244), -1, cv2.LINE_AA)
            cv2.circle(img, (int(sp[0,0]), int(sp[0,1])), 11, (255,255,255), 1, cv2.LINE_AA)

    # --- optional SMPL mesh avatar ---
    if smpl_mesh_vertices is not None and smpl_mesh_faces is not None:
        ensure_project_src_on_path()
        from project_cam.avatar.mesh_renderer import draw_mesh_cv2  # noqa: E402

        mesh_vertices_vis = transform_world_point_y(
            np.asarray(smpl_mesh_vertices, dtype=np.float64),
            y_max,
            enabled=world_y_mirror,
        )
        draw_mesh_cv2(
            img,
            mesh_vertices_vis,
            smpl_mesh_faces,
            proj,
            color_bgr=(224, 224, 218) if cine else (205, 205, 200),
            edge_bgr=None,
            alpha=float(smpl_mesh_alpha),
            max_faces=int(smpl_mesh_max_faces),
        )

    # --- skeleton ---
    if joints is not None:
        jv = transform_world_point_y(np.asarray(joints, dtype=np.float64), y_max, enabled=world_y_mirror)
        sp, sok = proj(jv)
        avatar_enabled = bool(avatar_body or avatar_markers)
        avatar_draw = None
        avatar_cfg = None
        if avatar_enabled:
            ensure_project_src_on_path()
            from project_cam.assessment.live_trainer.avatar_renderer import (  # noqa: E402
                AvatarRenderConfig,
                draw_avatar_body_cv2,
            )
            avatar_draw = draw_avatar_body_cv2
            avatar_cfg = AvatarRenderConfig(body_alpha=float(avatar_alpha))
            if avatar_body:
                avatar_draw(
                    img,
                    jv,
                    proj,
                    avatar_cfg,
                    draw_body=True,
                    draw_markers=False,
                )

        if not cine and not avatar_body:
            for s, e in CONNECTIONS:
                if s < len(sok) and e < len(sok) and sok[s] and sok[e]:
                    line(sp[s], sp[e], (30, 30, 30), 2)
            for j in range(min(17, len(sok))):
                if sok[j]:
                    cv2.circle(img, (int(sp[j,0]), int(sp[j,1])), 4, (50, 50, 50), -1, cv2.LINE_AA)
        elif cine and not avatar_body:
            # camera-space depth per joint -> node size + shading
            jhom = np.hstack([jv, np.ones((jv.shape[0], 1))])
            zc = (view @ jhom.T)[2]
            zf = zc[np.isfinite(zc) & (zc > 1)]
            znear, zfar = (float(zf.min()), float(zf.max())) if len(zf) else (1.0, 2.0)
            zspan = max(1e-3, zfar - znear)

            # floor shadow (joints dropped to z=0)
            jfloor = jv.copy(); jfloor[:, 2] = 0.0
            fsp, fok = proj(jfloor)
            for s, e in CONNECTIONS:
                if s < len(fok) and e < len(fok) and fok[s] and fok[e]:
                    line(fsp[s], fsp[e], (26, 22, 20), 6)

            # motion trails for wrists/ankles
            if trails:
                for jidx, hist in trails.items():
                    if hist is None or len(hist) < 2:
                        continue
                    hv = transform_world_point_y(np.asarray(hist, dtype=np.float64),
                                                 y_max, enabled=world_y_mirror)
                    tsp, tok = proj(hv)
                    base = COL_LEFT if jidx in LEFT_JOINTS else COL_RIGHT
                    n = len(tsp)
                    for i in range(1, n):
                        if tok[i-1] and tok[i]:
                            f = i / n
                            line(tsp[i-1], tsp[i], _shade(base, 0.20 + 0.6 * f),
                                 max(1, int(1 + 3 * f)))

            heat = limb_heat and joint_speeds is not None

            # glowing bones — coloured by body side, or by joint speed in heat mode
            for s, e in CONNECTIONS:
                if s < len(sok) and e < len(sok) and sok[s] and sok[e]:
                    if heat:
                        spd = 0.5 * (float(joint_speeds[s]) + float(joint_speeds[e]))
                        c = _heat_color(spd, heat_vmax)
                    else:
                        c = _bone_color(s, e)
                    line(sp[s], sp[e], _shade(c, 0.30), 7)   # outer glow
                    line(sp[s], sp[e], c, 2)                  # bright core

            # depth-shaded joint nodes (white core + coloured halo)
            for j in range(min(17, len(sok))):
                if not sok[j] or not np.isfinite(zc[j]):
                    continue
                t = 1.0 - float(np.clip((zc[j] - znear) / zspan, 0, 1))  # 1 = nearest
                r = int(3 + 4 * t)
                if heat:
                    c = _heat_color(float(joint_speeds[j]), heat_vmax)
                else:
                    c = COL_LEFT if j in LEFT_JOINTS else (COL_RIGHT if j in RIGHT_JOINTS else COL_HEAD)
                p = (int(sp[j, 0]), int(sp[j, 1]))
                cv2.circle(img, p, r + 3, _shade(c, 0.30), -1, cv2.LINE_AA)   # halo
                cv2.circle(img, p, r, (255, 255, 255), -1, cv2.LINE_AA)       # core
                cv2.circle(img, p, r, c, 1, cv2.LINE_AA)

        if avatar_markers and avatar_draw is not None and avatar_cfg is not None:
            avatar_draw(
                img,
                jv,
                proj,
                avatar_cfg,
                draw_body=False,
                draw_markers=True,
            )

    # --- ghost skeleton (predicted position) ---
    if ghost_joints is not None:
        gj = np.asarray(ghost_joints, dtype=np.float64)
        if gj.shape == (17, 3):
            gv = transform_world_point_y(gj, y_max, enabled=world_y_mirror)
            gsp, gsok = proj(gv)
            # Draw translucent connections
            for s, e in CONNECTIONS:
                if s < len(gsok) and e < len(gsok) and gsok[s] and gsok[e]:
                    if np.isfinite(gj[s]).all() and np.isfinite(gj[e]).all():
                        line(gsp[s], gsp[e], (200, 160, 80), 1)
            # Draw joints as hollow circles
            for j in range(min(17, len(gsok))):
                if gsok[j] and np.isfinite(gj[j]).all():
                    cv2.circle(img, (int(gsp[j, 0]), int(gsp[j, 1])), 5,
                               (200, 160, 80), 1, cv2.LINE_AA)
            # Connect real skeleton to ghost with dotted leader lines (shoulders + hips)
            if joints is not None:
                for j_idx in [5, 6, 11, 12]:  # shoulders and hips
                    if (j_idx < len(sok) and sok[j_idx] and gsok[j_idx]
                            and np.isfinite(joints[j_idx]).all()
                            and np.isfinite(gj[j_idx]).all()):
                        p1 = (int(sp[j_idx, 0]), int(sp[j_idx, 1]))
                        p2 = (int(gsp[j_idx, 0]), int(gsp[j_idx, 1]))
                        cv2.line(img, p1, p2, (200, 160, 80), 1, cv2.LINE_AA)
            if predict_ahead_ms > 0:
                cv2.putText(img, f"Pred: +{predict_ahead_ms:.0f}ms", (12, 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 160, 80), 1, cv2.LINE_AA)

    # --- global axes ---
    if draw_axes:
        al = float(axis_len)
        axis_pts = np.array([
            [0, 0, 0], [al, 0, 0], [0, al, 0], [0, 0, al],
        ], dtype=np.float64)
        axis_pts = transform_world_point_y(axis_pts, y_max, enabled=world_y_mirror)
        sp, sok = proj(axis_pts)
        if sok[0]:
            if sok[1]: line(sp[0], sp[1], (62, 207, 80), 2)    # X green
            if sok[2]: line(sp[0], sp[2], (59, 59, 255), 2)    # Y red
            if sok[3]: line(sp[0], sp[3], (246, 130, 59), 2)   # Z blue
            cv2.putText(img, "O", (int(sp[0,0])-14, int(sp[0,1])+5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,0), 1, cv2.LINE_AA)

    # --- BLM Aim Overlay ---
    if blm_aim is not None:
        launcher_pos = blm_aim.get("launcher_pos")
        target_pos = blm_aim.get("target_pos")
        y_max_v = dims["Y"]

        # Draw launcher position marker
        if launcher_pos is not None:
            lp = transform_world_point_y(launcher_pos.reshape(1, 3), y_max_v, enabled=world_y_mirror)
            lsp, lok = proj(lp)
            if lok[0]:
                pt = (int(lsp[0, 0]), int(lsp[0, 1]))
                cv2.circle(img, pt, 10, (0, 0, 220), 2, cv2.LINE_AA)
                cv2.circle(img, pt, 3, (0, 0, 220), -1, cv2.LINE_AA)
                cv2.putText(img, "BLM", (pt[0] + 14, pt[1] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 220), 1, cv2.LINE_AA)

                # Draw aim line from launcher to target
                if target_pos is not None and np.isfinite(target_pos).all():
                    tp = transform_world_point_y(target_pos.reshape(1, 3), y_max_v, enabled=world_y_mirror)
                    tsp, tok = proj(tp)
                    if tok[0]:
                        # Dashed-style aim line
                        cv2.line(img, pt, (int(tsp[0, 0]), int(tsp[0, 1])),
                                 (0, 0, 220), 2, cv2.LINE_AA)
                        # Target crosshair
                        tp2 = (int(tsp[0, 0]), int(tsp[0, 1]))
                        cv2.drawMarker(img, tp2, (0, 0, 255), cv2.MARKER_CROSS, 20, 2, cv2.LINE_AA)

        # Draw info panel
        panel_x = img_w - 320
        panel_y = 12
        panel_h = 180
        # Semi-transparent background
        overlay = img.copy()
        cv2.rectangle(overlay, (panel_x - 10, panel_y - 4), (img_w - 8, panel_y + panel_h),
                      (40, 40, 40), -1)
        cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)

        status = blm_aim.get("status", "NO_TARGET")
        joint_name = blm_aim.get("joint_name", "?")
        pitch = blm_aim.get("pitch_deg")
        yaw = blm_aim.get("yaw_deg")
        dist = blm_aim.get("distance_m")
        raw_xyz = blm_aim.get("raw_xyz")
        corrected_xyz = blm_aim.get("corrected_xyz")
        correction_mode = blm_aim.get("correction_mode", "none")

        # Status color
        if status == "AIM_OK":
            status_color = (0, 255, 100)
        elif status == "OUT_OF_RANGE":
            status_color = (0, 100, 255)
        else:
            status_color = (100, 100, 255)

        y = panel_y + 18
        cv2.putText(img, "BLM AIM DEMO", (panel_x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        y += 24
        cv2.putText(img, f"Status: {status}", (panel_x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 1, cv2.LINE_AA)
        y += 22
        cv2.putText(img, f"Target: {joint_name}", (panel_x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)

        if raw_xyz is not None:
            y += 20
            cv2.putText(img, f"Pos: ({raw_xyz[0]:.0f}, {raw_xyz[1]:.0f}, {raw_xyz[2]:.0f}) mm",
                        (panel_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1, cv2.LINE_AA)

        if correction_mode != "none" and corrected_xyz is not None:
            y += 18
            cv2.putText(img, f"Corr: ({corrected_xyz[0]:.0f}, {corrected_xyz[1]:.0f}, {corrected_xyz[2]:.0f})",
                        (panel_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 200, 180), 1, cv2.LINE_AA)

        if pitch is not None and yaw is not None:
            y += 22
            cv2.putText(img, f"Pitch: {pitch:.1f} deg   Yaw: {yaw:.1f} deg", (panel_x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 255), 1, cv2.LINE_AA)
        if dist is not None:
            y += 20
            cv2.putText(img, f"Distance: {dist:.2f} m", (panel_x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)

        if status == "AIM_OK" and pitch is not None:
            y += 22
            cmd = f"set {pitch:.1f} {yaw:.1f} 0 0"
            cv2.putText(img, f"CMD: {cmd}", (panel_x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 100), 1, cv2.LINE_AA)

    # --- live camera thumbnails (the multi-view behind the 3D) ---
    if thumbnails:
        n = max(1, len(thumbnails))
        pad = 6
        # start below the BLM aim panel (top-right) if it is shown, else under the top bar
        top = 200 if blm_aim is not None else 42
        bottom = img_h - 8
        th = int(min(84, (bottom - top - (n - 1) * pad) / n))
        th = max(38, th)
        tw = int(round(th * 16 / 9))
        x0 = img_w - (tw + pad)
        for i, (cname, tf) in enumerate(thumbnails):
            yy = top + i * (th + pad)
            if yy + th > bottom or tf is None:
                break
            img[yy:yy+th, x0:x0+tw] = cv2.resize(tf, (tw, th))
            cv2.rectangle(img, (x0, yy), (x0+tw, yy+th), (120, 120, 120), 1)
            cv2.putText(img, cname.replace("_", " ")[:14], (x0+4, yy+13),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34, (60, 255, 120), 1, cv2.LINE_AA)

    # --- HUD ---
    if cine:
        cv2.rectangle(img, (0, 0), (img_w, 34), (18, 14, 13), -1)
        pulse = 0.5 + 0.5 * float(np.sin(frame_idx * 0.3))
        cv2.circle(img, (20, 17), 7, _shade((60, 60, 255), 0.5 + 0.5 * pulse), -1, cv2.LINE_AA)
        cv2.putText(img, "LIVE", (34, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(img, "MULTI-VIEW 3D POSE", (104, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (205, 205, 205), 1, cv2.LINE_AA)
        info = f"{fps_est:4.1f} Hz"
        if cams_tracking is not None:
            info += f"   |   {cams_tracking} cams"
        cv2.putText(img, info, (img_w - 240, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (150, 255, 170), 1, cv2.LINE_AA)

        if recording:
            cv2.circle(img, (img_w - 300, 17), 7, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.putText(img, "REC", (img_w - 288, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 0, 255), 2, cv2.LINE_AA)

        # athlete metrics panel (bottom-left, dynamic height for rep counters)
        if metrics:
            mx = 14
            base_rows = (("Height", metrics.get("height_cm"), "cm"),
                         ("Reach", metrics.get("reach_cm"), "cm"),
                         ("Max spd", metrics.get("max_speed_ms"), "m/s"))
            reps = metrics.get("reps") or {}
            leg_raise = metrics.get("leg_raise") or {}
            n_rows = len(base_rows) + (2 if reps else 0) + (3 if leg_raise else 0)
            panel_h = 30 + n_rows * 24 + (12 if (reps or leg_raise) else 6)
            my = img_h - panel_h
            cv2.rectangle(img, (mx - 8, my - 6), (mx + 256, img_h - 8), (18, 14, 13), -1)
            cv2.putText(img, "ATHLETE", (mx, my + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (150, 255, 170), 1, cv2.LINE_AA)
            yy = my + 40
            for label, v, unit in base_rows:
                txt = (f"{label:8s}{v:6.1f} {unit}" if v is not None else f"{label:8s}    -- {unit}")
                cv2.putText(img, txt, (mx, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (228, 228, 228), 1, cv2.LINE_AA)
                yy += 24
            if reps:
                cv2.line(img, (mx, yy - 15), (mx + 200, yy - 15), (60, 60, 60), 1)
                yy += 4
                cv2.putText(img, f"Squats   {reps.get('squat', 0)}", (mx, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 220, 255), 2, cv2.LINE_AA)
                yy += 28
                cv2.putText(img, f"Push-ups {reps.get('push_up', 0)}", (mx, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 40), 2, cv2.LINE_AA)
                yy += 26
            if leg_raise:
                cv2.line(img, (mx, yy - 15), (mx + 242, yy - 15), (60, 60, 60), 1)
                yy += 4
                l_ang = leg_raise.get("left_angle_deg")
                r_ang = leg_raise.get("right_angle_deg")
                l_txt = "--" if l_ang is None else f"{float(l_ang):4.0f}deg"
                r_txt = "--" if r_ang is None else f"{float(r_ang):4.0f}deg"
                cv2.putText(img, f"L leg {l_txt} r{leg_raise.get('left_reps', 0)}", (mx, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (40, 170, 255), 1, cv2.LINE_AA)
                yy += 24
                cv2.putText(img, f"R leg {r_txt} r{leg_raise.get('right_reps', 0)}", (mx, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 200, 40), 1, cv2.LINE_AA)
                yy += 24
                ident = str(leg_raise.get("identity_status", "--"))[:12]
                swap = " swap" if leg_raise.get("swapped") else ""
                cv2.putText(img, f"ID {ident}{swap}", (mx, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.46, (200, 220, 255), 1, cv2.LINE_AA)
                yy += 22

        # speed heat legend
        if limb_heat:
            lx, ly = 14, 48
            for i in range(60):
                cv2.line(img, (lx + i * 2, ly), (lx + i * 2, ly + 9),
                         _heat_color(i / 60.0 * heat_vmax, heat_vmax), 2)
            cv2.putText(img, "slow", (lx, ly + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.putText(img, "fast", (lx + 98, ly + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (200, 200, 200), 1, cv2.LINE_AA)
    else:
        cv2.putText(img, f"Frame: {frame_idx}  FPS: {fps_est:.1f}", (12, img_h - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 80, 80), 1, cv2.LINE_AA)

    return img


def put_latest_snapshot(q, payload):
    try:
        q.put_nowait(payload)
    except Full:
        try:
            _ = q.get_nowait()
        except Exception:
            pass
        try:
            q.put_nowait(payload)
        except Exception:
            pass
    except Exception:
        return


def render_worker_main(queue_in, static_cfg):
    plt.ion()
    fig = plt.figure(figsize=(12.0, 9.0), facecolor="#f7f7f7")
    ax = fig.add_subplot(111, projection="3d")
    dims = static_cfg["dims"]
    tags = static_cfg["tags"]
    extr = static_cfg["extr"]
    invert_y_axis_display = static_cfg["invert_y_axis_display"]
    world_y_mirror = static_cfg["world_y_mirror"]
    draw_global_axes_flag = static_cfg["draw_global_axes_flag"]
    global_axis_len_mm = static_cfg["global_axis_len_mm"]
    view_elev = static_cfg["view_elev"]
    view_azim = static_cfg["view_azim"]
    try:
        while True:
            msg = queue_in.get()
            if msg is None:
                break
            draw_live_scene(
                ax=ax,
                dims=dims,
                tags=tags,
                extr=extr,
                ball_pt=msg.get("ball_pt"),
                ball_traj=msg.get("ball_traj", []),
                joints=msg.get("joints"),
                frame_idx=int(msg.get("frame_idx", 0)),
                fps_est=float(msg.get("fps_est", 0.0)),
                world_y_mirror=world_y_mirror,
                invert_y_axis_display=invert_y_axis_display,
                draw_global_axes_flag=draw_global_axes_flag,
                global_axis_len_mm=global_axis_len_mm,
                view_elev=view_elev,
                view_azim=view_azim,
            )
            plt.pause(0.001)
            if not plt.fignum_exists(fig.number):
                break
    finally:
        plt.close("all")


def ema_update(prev, new, alpha):
    if new is None:
        return prev
    if prev is None:
        return np.array(new, dtype=np.float32)
    return (1.0 - alpha) * prev + alpha * np.array(new, dtype=np.float32)


class JointKalmanFilter:
    """Per-joint 3D Kalman filter with constant-velocity model.

    State vector: [x, y, z, vx, vy, vz]
    Measurement:  [x, y, z]

    Provides position prediction at arbitrary time horizons for
    predictive targeting (leading the target by T_predict ms).
    """

    def __init__(self, process_noise=50.0, measurement_noise=80.0, dt=1.0 / 15.0):
        self.dt = dt
        self._initialized = False
        # State: [x, y, z, vx, vy, vz]
        self.x = np.zeros(6, dtype=np.float64)
        # State covariance
        self.P = np.eye(6, dtype=np.float64) * 1e4
        # Measurement matrix: observe [x, y, z]
        self.H = np.zeros((3, 6), dtype=np.float64)
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.H[2, 2] = 1.0
        # Measurement noise covariance
        self.R = np.eye(3, dtype=np.float64) * measurement_noise ** 2
        # Process noise (will be set in _build_Q)
        self._q_std = process_noise
        self.Q = self._build_Q(dt, process_noise)

    def _build_F(self, dt):
        """State transition matrix for constant-velocity model."""
        F = np.eye(6, dtype=np.float64)
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt
        return F

    def _build_Q(self, dt, q_std):
        """Process noise: piecewise-constant white noise acceleration model."""
        q = q_std ** 2
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt3 * dt
        Q = np.zeros((6, 6), dtype=np.float64)
        for i in range(3):
            Q[i, i] = dt4 / 4 * q
            Q[i, i + 3] = dt3 / 2 * q
            Q[i + 3, i] = dt3 / 2 * q
            Q[i + 3, i + 3] = dt2 * q
        return Q

    def predict_step(self, dt=None):
        """Predict state forward by dt seconds."""
        if dt is None:
            dt = self.dt
        F = self._build_F(dt)
        Q = self._build_Q(dt, self._q_std)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update_step(self, z, measurement_noise_scale=1.0):
        """Update with measurement z = [x, y, z] in mm."""
        z = np.asarray(z, dtype=np.float64)
        if not self._initialized:
            self.x[:3] = z
            self.x[3:] = 0.0
            self.P = np.eye(6, dtype=np.float64) * 1e4
            self._initialized = True
            return
        y = z - self.H @ self.x
        scale = max(1e-6, float(measurement_noise_scale))
        R = self.R * (scale ** 2)
        S = self.H @ self.P @ self.H.T + R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(6) - K @ self.H) @ self.P

    def get_position(self):
        """Current filtered position [x, y, z]."""
        return self.x[:3].copy()

    def get_velocity(self):
        """Current estimated velocity [vx, vy, vz] in mm/s."""
        return self.x[3:].copy()

    def predict_ahead(self, t_ahead_sec):
        """Predict position t_ahead_sec into the future WITHOUT modifying state.
        Returns predicted [x, y, z]."""
        if not self._initialized:
            return self.x[:3].copy()
        F = self._build_F(t_ahead_sec)
        x_pred = F @ self.x
        return x_pred[:3].copy()

    def prediction_uncertainty(self, t_ahead_sec):
        """Return positional uncertainty (trace of position covariance) at t_ahead."""
        F = self._build_F(t_ahead_sec)
        Q = self._build_Q(t_ahead_sec, self._q_std)
        P_pred = F @ self.P @ F.T + Q
        return float(np.sqrt(P_pred[0, 0] + P_pred[1, 1] + P_pred[2, 2]))

    @property
    def initialized(self):
        return self._initialized


# COCO L/R keypoint pairs: eyes, ears, shoulders, elbows, wrists, hips,
# knees, ankles.
COCO_LR_PAIRS = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]


def fix_lr_swaps_for_cam(kpts, scores, joints_state, R, tvec, K, D,
                         min_conf=0.2, margin=0.75):
    """Correct one camera's left/right keypoint swaps against the 3D state.

    YOLO-Pose labels left/right per view, so cameras that face the person
    (worst when prone/supine) mirror the labels. Triangulating a mixed label
    set (cam A's left ankle paired with cam B's right ankle) collapses both
    3D limbs onto their average — the "both legs rise" artifact. For each
    L/R pair with a finite previous 3D estimate, reproject 3D-left/right
    into this camera and keep the assignment (direct vs swapped) with the
    smaller total pixel error. Swaps only when clearly better (margin) so a
    noisy frame cannot dither the labels. kpts/scores are modified in place;
    returns the number of swapped pairs.
    """
    swapped = 0
    for lj, rj in COCO_LR_PAIRS:
        pl, pr = joints_state[lj], joints_state[rj]
        if not (np.isfinite(pl).all() and np.isfinite(pr).all()):
            continue
        if scores[lj] < min_conf or scores[rj] < min_conf:
            continue
        try:
            ul = np.asarray(project_world_to_pixel(pl, R, tvec, K, D), dtype=np.float64)
            ur = np.asarray(project_world_to_pixel(pr, R, tvec, K, D), dtype=np.float64)
        except Exception:
            continue
        if not (np.isfinite(ul).all() and np.isfinite(ur).all()):
            continue
        kl = np.asarray(kpts[lj, :2], dtype=np.float64)
        kr = np.asarray(kpts[rj, :2], dtype=np.float64)
        direct = np.linalg.norm(kl - ul) + np.linalg.norm(kr - ur)
        cross = np.linalg.norm(kl - ur) + np.linalg.norm(kr - ul)
        if cross < direct * margin:
            kpts[[lj, rj], :2] = kpts[[rj, lj], :2]
            scores[lj], scores[rj] = float(scores[rj]), float(scores[lj])
            swapped += 1
    return swapped


def latency_compensated_point(kf, state_pt, t_ahead_sec, max_uncertainty_mm):
    """Display-only latency compensation for one joint.

    Returns the KF's short-horizon prediction instead of the smoothed state,
    so the rendered skeleton cancels capture+inference+smoothing delay. Falls
    back to the smoothed state whenever the filter is missing, uninitialized,
    too uncertain at this horizon, or non-finite. Never mutates KF state and
    never feeds back into joints_state/UDP/triangulation.
    """
    if kf is None or t_ahead_sec <= 0.0 or not kf.initialized:
        return state_pt
    if kf.prediction_uncertainty(t_ahead_sec) >= float(max_uncertainty_mm):
        return state_pt
    pred = kf.predict_ahead(t_ahead_sec)
    if not np.isfinite(pred).all():
        return state_pt
    return pred.astype(np.float32)


def make_mosaic(cam_frames, ball_boxes, per_cam_pose, cam_order=None, tile_size=None, copy_frames=False):
    order = list(cam_order) if cam_order is not None else list(CAM_ORDER)
    panels = []
    ref_shape = None
    for fr in cam_frames.values():
        if fr is not None:
            ref_shape = fr.shape
            break
    if ref_shape is None:
        ref_shape = (720, 1280, 3)
    for cam in order:
        frame = cam_frames.get(cam)
        if frame is None:
            frame = np.zeros(ref_shape, dtype=np.uint8)
        disp = frame.copy() if copy_frames else frame
        box = ball_boxes.get(cam)
        if box is not None:
            x1, y1, x2, y2, conf = box
            cv2.rectangle(disp, (x1, y1), (x2, y2), (0, 180, 255), 2)
            cv2.putText(disp, f"ball {conf:.2f}", (x1, max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 180, 255), 2)

        pose = per_cam_pose.get(cam)
        if pose is not None:
            kpts, scores = pose
            for i in range(min(17, len(kpts))):
                if scores[i] > 0.35:
                    x, y = int(kpts[i, 0]), int(kpts[i, 1])
                    cv2.circle(disp, (x, y), 3, (20, 20, 20), -1)
            for s, e in CONNECTIONS:
                if scores[s] > 0.35 and scores[e] > 0.35:
                    p1 = (int(kpts[s, 0]), int(kpts[s, 1]))
                    p2 = (int(kpts[e, 0]), int(kpts[e, 1]))
                    cv2.line(disp, p1, p2, (10, 10, 10), 2)

        if tile_size is not None:
            disp = cv2.resize(disp, tile_size)
        cv2.putText(disp, cam, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        panels.append(disp)

    cols = 2 if len(order) <= 4 else 3
    rows = int(math.ceil(max(1, len(order)) / cols))
    while len(panels) < rows * cols:
        panels.append(np.zeros(ref_shape, dtype=np.uint8))
    return np.vstack([
        np.hstack(panels[row * cols:(row + 1) * cols])
        for row in range(rows)
    ])


def main():
    ap = argparse.ArgumentParser(description="Live 4-camera ball + pose triangulation in garage 3D arena.")
    ap.add_argument(
        "--high-performance",
        action="store_true",
        help="Enable FPS-optimized defaults (no 3D window, reduced heavy-step frequency).",
    )
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--extrinsics", default="arena_fixed/cal/extrinsics/extrinsics_fixed.json")
    ap.add_argument("--dimensions", default="arena_fixed/cal/extrinsics/Dimensions_fixed.txt")
    ap.add_argument("--ball-model", default="models/ball/yolo26m-672.engine")
    ap.add_argument("--ball-max-batch", type=int, default=4,
                    help="Max frames per ball-inference call. The TRT ball engine is exported "
                         "with a batch<=4 optimization profile, so a >4-camera rig must chunk "
                         "(mirrors --pose-max-batch). Raise only after re-exporting the engine.")
    ap.add_argument("--ball-imgsz", type=int, default=672,
                    help="Ball detector input size. 672 = default (engine was exported at this). "
                         "Try 960 for small/distant/bounce balls — dynamic-batch engine handles it, "
                         "~+8ms latency per 4-cam batch.")
    ap.add_argument("--ball-device", default="cuda:0", help="Ball detector device, e.g. cpu or cuda:0")
    ap.add_argument("--pose-device", default="cpu", help="Pose detector device, e.g. cpu or cuda:0")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--buffer-size", type=int, default=1)
    ap.add_argument("--no-uvc-controls", action="store_true",
                    help="Do not apply low-latency V4L2 controls to USB webcams.")
    ap.add_argument("--uvc-exposure", type=int, default=200,
                    help="Manual UVC exposure_time_absolute. 200 = about 20 ms; keeps C920 at 30 FPS.")
    ap.add_argument("--uvc-gain", type=int, default=160,
                    help="Manual UVC gain. Use -1 to leave gain unchanged.")
    ap.add_argument("--uvc-focus", type=int, default=0,
                    help="Manual UVC focus_absolute. Use -1 to leave focus unchanged.")
    ap.add_argument("--uvc-power-line-frequency", type=int, default=1,
                    help="UVC power_line_frequency: 1=50 Hz, 2=60 Hz.")
    ap.add_argument("--ball-conf", type=float, default=0.4)
    ap.add_argument("--ball-min-cams", type=int, default=2, help="Minimum cameras for 3D ball triangulation")
    ap.add_argument("--ball-max-reproj-px", type=float, default=25.0, help="Reject ball cams with reproj error above this (px). 0=off")
    ap.add_argument("--ball-max-speed-mps", type=float, default=40.0, help="Reject ball jumps faster than this (m/s). 0=off")
    ap.add_argument("--ball-kalman-process-noise", type=float, default=800.0, help="Ball KF process noise (higher = more reactive)")
    ap.add_argument("--ball-kalman-measurement-noise", type=float, default=25.0, help="Ball KF measurement noise (higher = more smoothing)")
    ap.add_argument("--ball-coast-frames", type=int, default=6, help="Frames to coast ball on KF prediction when detection drops")
    ap.add_argument("--ball-single-cam-fallback", action="store_true",
                    help="When only 1 cam sees the ball, project that cam's ray to the KF-predicted Z plane "
                         "(or floor if KF uninitialized). Recovers bounce/low-visibility frames at the cost of "
                         "slightly noisier single-cam depth. Off by default.")
    ap.add_argument("--ball-single-cam-max-frames", type=int, default=15,
                    help="Max consecutive frames the single-cam fallback can be used without a multi-cam re-lock. "
                         "Prevents KF depth from drifting without geometric constraint.")
    ap.add_argument("--ball-single-cam-floor-mm", type=float, default=0.0,
                    help="Floor Z (mm) used when the KF has no depth estimate yet. Default 0 (world floor).")
    ap.add_argument("--ball-ballistic-fallback", action="store_true",
                    help="Replace the single-cam KF-Z target with a gravity-aware target_z derived from the "
                         "last accepted multi-cam ball state. Off by default.")
    ap.add_argument("--ball-gravity-mm-s2", type=float, default=9810.0,
                    help="Gravity used by the ballistic single-cam fallback (mm/s^2).")
    ap.add_argument("--ball-bounce-liftoff-vz-mm-s", type=float, default=500.0,
                    help="Debounced FLOOR->AIRBORNE threshold for multi-cam vertical velocity (mm/s).")
    ap.add_argument("--ball-single-cam-meas-noise-mult", type=float, default=3.0,
                    help="Measurement-noise std multiplier applied to KF updates from ballistic single-cam fallback.")
    ap.add_argument("--pushup-ankle-single-cam-fallback", action="store_true",
                    help="When only 1 cam sees a push-up ankle AND per-athlete leg priors are locked, "
                         "project that cam's ray to the floor Z-plane and accept if the resulting "
                         "tibia length matches the prior AND the foot is within reach of the hip. "
                         "Off by default; ignored unless --coach-overlay --coach-exercise push_up is set.")
    ap.add_argument("--pushup-ankle-single-cam-max-frames", type=int, default=8,
                    help="Max consecutive frames an ankle can be filled by single-cam fallback before "
                         "the system forces a NaN drop. Prevents indefinite drift when the athlete's "
                         "foot is genuinely no longer on the floor.")
    ap.add_argument("--pushup-ankle-floor-mm", type=float, default=0.0,
                    help="World Z (mm) of the floor surface the ankle ray intersects. Override for "
                         "thick mats (e.g. 15 mm gymnastics mat -> --pushup-ankle-floor-mm 15).")
    ap.add_argument("--ball-max-box-side-px", type=float, default=220.0,
                    help="Reject ball detections whose larger bbox side exceeds this (px). A tennis ball at "
                         "arena distance is <~120px; body-sized blobs and cones exceed this. 0 = off.")
    ap.add_argument("--ball-min-box-side-px", type=float, default=0.0,
                    help="Reject ball detections whose larger bbox side is below this (px). Filters "
                         "detector-noise micro-boxes. 0 = off (default).")
    ap.add_argument("--ball-kf-gate-px", type=float, default=150.0,
                    help="When the ball KF is locked, prefer per-cam candidates within this pixel radius "
                         "of the predicted reprojection. Keeps the selector on the tracked ball when "
                         "cones, markers, or bodies produce competing detections. Falls back to highest-"
                         "conf if no candidate is within gate. 0 = off.")
    ap.add_argument(
        "--track-ball",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable ball detection/triangulation. Disable for higher FPS when only skeleton is needed.",
    )
    ap.add_argument("--pose", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--pose-backend", choices=["mmpose", "yolopose"], default="mmpose",
                     help="Pose estimation backend. yolopose is ~4-6x faster (single YOLO11-Pose model).")
    ap.add_argument("--yolopose-model", default="yolo11m-pose.pt",
                     help="YOLO-Pose model path (.pt or .engine for TensorRT).")
    ap.add_argument("--pose-max-batch", type=int, default=4,
                    help="Max frames per pose inference call. Keep 4 for TensorRT engines exported with max batch 4.")
    ap.add_argument("--pose-imgsz", type=int, default=0,
                    help="Inference size for YOLO-Pose (0 = engine/model default). WARNING: TRT "
                         "engines only decode correctly at their EXPORT imgsz — off-size calls emit "
                         "garbage detections (300/frame, NMS stalls). Match the engine or re-export.")
    ap.add_argument("--pose-min-cams", type=int, default=2,
                    help="Minimum agreeing camera rays per 3D joint. With 6 cameras, 3 rejects the "
                         "2-cam wrong-association tangles that appear on crouched/floor poses; a joint "
                         "seen by fewer cams is dropped (holds last value) instead of flung.")
    ap.add_argument("--pose-lr-fix", action=argparse.BooleanOptionalAction, default=True,
                    help="Relabel per-camera left/right keypoints against the 3D state before "
                         "triangulation (fixes 'both legs rise' when cameras facing the person "
                         "mirror YOLO's left/right, worst on prone/supine poses).")
    ap.add_argument("--parallel-inference", action=argparse.BooleanOptionalAction, default=False,
                    help="EXPERIMENTAL — known unsafe on torch 2.1 + TensorRT 10.16: concurrent "
                         "ball+pose inference from two threads races on the CUDA stream and kills "
                         "pose with 'illegal memory access' (observed live 2026-07-02). Keep off "
                         "until the ball worker gets a dedicated CUDA stream or process.")
    ap.add_argument("--pose-conf", type=float, default=0.45)
    ap.add_argument("--pose-max-reproj-px", type=float, default=40.0,
                    help="Per-joint robust triangulation: reject camera rays whose "
                         "reprojection error exceeds this (px). Stops a single bad "
                         "camera/mis-detection from flinging a joint to a random point. "
                         "0=off (old plain triangulation).")
    ap.add_argument("--pose-every", type=int, default=None, help="Run pose once every N frames (default: 2)")
    ap.add_argument(
        "--joint-stale-frames",
        type=int,
        default=None,
        help="Hide triangulated joints if not updated for this many frames (default: pose_every*3).",
    )
    ap.add_argument("--switch-area-ratio", type=float, default=1.6)
    ap.add_argument("--ema-alpha", type=float, default=0.35, help="Smoothing factor for 3D points")
    ap.add_argument(
        "--display-smooth-alpha",
        type=float,
        default=0.4,
        help="Per-frame display-only lerp factor toward latest EMA state (0=frozen, 1=instant snap). "
        "Does NOT affect triangulation, EMA, or UDP — only 3D/2D rendering.",
    )
    ap.add_argument("--trail-len", type=int, default=20)
    ap.add_argument("--ball-every", type=int, default=None, help="Run ball detector once every N frames (default: 1)")
    ap.add_argument("--viz-every", type=int, default=None, help="Update 3D view once every N frames (default: 1)")
    ap.add_argument("--mosaic-every", type=int, default=None, help="Update 2D mosaic once every N frames (default: 1)")
    ap.add_argument("--mosaic-tile-width", type=int, default=640, help="2D mosaic tile width before display/record.")
    ap.add_argument("--mosaic-tile-height", type=int, default=360, help="2D mosaic tile height before display/record.")
    ap.add_argument("--show-3d", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--show-2d", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument(
        "--world-y-mirror",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Mirror outputs by Y axis (y' = Ymax - y) for 3D/UDP. Default keeps original world frame.",
    )
    ap.add_argument(
        "--display-world-y-mirror",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override Y-mirror for 3D display only (if unset, follows --world-y-mirror).",
    )
    ap.add_argument(
        "--udp-world-y-mirror",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override Y-mirror for UDP output only (if unset, follows --world-y-mirror).",
    )
    ap.add_argument(
        "--invert-y-axis-display",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Invert Y axis ticks in 3D plot only (display: Ymax..0). Does not change triangulation or UDP.",
    )
    ap.add_argument(
        "--draw-global-axes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Draw a single global coordinate triad from O(0,0,0).",
    )
    ap.add_argument("--global-axis-len-mm", type=float, default=900.0, help="Global axes length in mm for visualization.")
    ap.add_argument("--view-elev", type=float, default=22.0, help="3D camera elevation angle.")
    ap.add_argument("--view-azim", type=float, default=-58.0, help="3D camera azimuth angle.")
    ap.add_argument("--fullscreen", action=argparse.BooleanOptionalAction, default=False,
                    help="Open the 3D arena window in true fullscreen (press q to exit). "
                         "The window is resizable/maximisable either way.")
    ap.add_argument("--camera-open-retries", type=int, default=0,
                    help="Retry opening each camera this many times before skipping it "
                         "(for slow USB / deep-hub cameras that take a while to enumerate).")
    ap.add_argument("--camera-open-retry-delay", type=float, default=5.0,
                    help="Seconds between camera-open retries.")
    ap.add_argument("--camera-preflight-timeout", type=float, default=3.0,
                    help="Seconds to wait for v4l2-ctl --info before opening a /dev/video* node. 0 disables.")
    ap.add_argument("--render-theme", choices=["cinematic", "classic"], default="cinematic",
                    help="3D arena visual style (cv2 backend): cinematic dark stage with "
                         "glowing depth-shaded skeleton + floor shadow + motion trails, or classic.")
    ap.add_argument("--avatar-body", action=argparse.BooleanOptionalAction, default=False,
                    help="Render a white/gray mannequin body from the live 3D joints.")
    ap.add_argument("--avatar-markers", action=argparse.BooleanOptionalAction, default=False,
                    help="Render blue joint and virtual body markers on the 3D avatar.")
    ap.add_argument("--avatar-alpha", type=float, default=0.85,
                    help="Mannequin body opacity in the OpenCV 3D view.")
    ap.add_argument("--smpl-avatar", action=argparse.BooleanOptionalAction, default=False,
                    help="Fit and render an optional SMPL mesh avatar from live 3D joints.")
    ap.add_argument("--smpl-model-path", default="",
                    help="Path to downloaded SMPL model files/directory. Required for --smpl-avatar.")
    ap.add_argument("--smpl-model-type", default="smpl", choices=["smpl", "smplx"],
                    help="Parametric body model type for the optional mesh avatar.")
    ap.add_argument("--smpl-gender", default="neutral", choices=["neutral", "male", "female"],
                    help="SMPL gender model to load.")
    ap.add_argument("--smpl-device", default="cpu",
                    help="Torch device for SMPL fitting. CPU is safest for live YOLO/TensorRT runs.")
    ap.add_argument("--smpl-fit-every", type=int, default=5,
                    help="Fit the optional SMPL mesh once every N live frames.")
    ap.add_argument("--smpl-fit-iters", type=int, default=8,
                    help="Adam iterations per live SMPL fit.")
    ap.add_argument("--smpl-shape-calib-frames", type=int, default=30,
                    help="Reliable SMPL fit frames used to estimate shape betas before locking them.")
    ap.add_argument("--smpl-mesh-alpha", type=float, default=0.42,
                    help="Opacity for the rendered SMPL mesh.")
    ap.add_argument("--smpl-mesh-max-faces", type=int, default=1500,
                    help="Maximum SMPL faces drawn per frame in the OpenCV renderer.")
    ap.add_argument("--smpl-async", action=argparse.BooleanOptionalAction, default=True,
                    help="Run SMPL fitting in a background thread (latest-only queue) so the live "
                         "loop never blocks on a fit. --no-smpl-async restores the old inline fit.")
    ap.add_argument("--smpl-anchor-follow", action=argparse.BooleanOptionalAction, default=True,
                    help="Between fits, translate the last fitted mesh to the current mid-hip so the "
                         "avatar tracks the person at full frame rate (pose trails, position does not).")
    ap.add_argument("--auto-orbit", action=argparse.BooleanOptionalAction, default=False,
                    help="Slowly rotate the 3D view (cinematic demo fly-around).")
    ap.add_argument("--auto-orbit-speed", type=float, default=8.0,
                    help="Auto-orbit speed, degrees/second.")
    ap.add_argument("--display-filter", choices=["oneeuro", "ema"], default="oneeuro",
                    help="Display smoothing: oneeuro (low-lag adaptive, default) or ema (legacy lerp).")
    ap.add_argument("--oneeuro-mincutoff", type=float, default=1.2,
                    help="One-Euro min cutoff Hz (lower=smoother when still).")
    ap.add_argument("--oneeuro-beta", type=float, default=0.3,
                    help="One-Euro speed coefficient (higher=less lag on fast motion).")
    ap.add_argument("--limb-heat", action=argparse.BooleanOptionalAction, default=False,
                    help="Colour skeleton bones by joint speed (blue=slow -> red=fast) instead of side colours.")
    ap.add_argument("--heat-vmax-mm-s", type=float, default=2500.0,
                    help="Joint speed (mm/s) mapped to the hottest colour.")
    ap.add_argument("--metrics-hud", action=argparse.BooleanOptionalAction, default=True,
                    help="Show live height/reach/speed panel (cinematic theme).")
    ap.add_argument("--leg-raise-mode", action=argparse.BooleanOptionalAction, default=False,
                    help="Enable supine leg-raise stabilization: lower-body left/right identity "
                         "lock before EMA plus leg-angle HUD/log metrics. Off by default.")
    ap.add_argument("--leg-raise-conf-min", type=float, default=0.25,
                    help="Minimum 3D joint confidence used by the leg-raise tracker.")
    ap.add_argument("--leg-raise-calibration-frames", type=int, default=450,
                    help="Initial live-loop frames used to learn straight-leg segment priors "
                         "(default 450, about 15 s at ~30 Hz).")
    ap.add_argument("--leg-raise-log-jsonl", default="",
                    help="Optional JSONL path for per-frame leg-raise diagnostics.")
    ap.add_argument("--count-reps", action=argparse.BooleanOptionalAction, default=False,
                    help="Run squat + push-up rep counters on the live 3D pose and show "
                         "them in the ATHLETE panel.")
    ap.add_argument("--show-thumbnails", action=argparse.BooleanOptionalAction, default=False,
                    help="Inset the live camera feeds as thumbnails in the 3D view corner.")
    ap.add_argument("--record-dir", default="Parallel_working/output/recordings",
                    help="Where 'r'-keypress MP4 captures of the 3D view are written.")
    ap.add_argument(
        "--viz-backend",
        choices=["cv2", "matplotlib"],
        default="cv2",
        help="3D visualization backend. cv2 is ~100x faster (1-3ms vs 200-500ms). Default: cv2.",
    )
    ap.add_argument("--viz-width", type=int, default=960, help="Width of cv2 3D view window.")
    ap.add_argument("--viz-height", type=int, default=720, help="Height of cv2 3D view window.")
    ap.add_argument("--record-video", default="", help="If set, write 3D arena view to this .mp4 path.")
    ap.add_argument("--record-fps", type=float, default=30.0, help="FPS for the recorded video (usually matches capture rate / viz_every).")
    ap.add_argument("--record-mosaic", default="", help="If set, also write the 4-cam 2D mosaic to this .mp4 path.")
    ap.add_argument("--coach-overlay", action=argparse.BooleanOptionalAction, default=False,
                    help="Show the low-lag in-process live coach overlay on the freshest camera ROI.")
    ap.add_argument("--coach-exercise", choices=["squat", "push_up"], default="squat",
                    help="Exercise logic and overlay labels for --coach-overlay.")
    ap.add_argument("--coach-zone-mm", default="",
                    help="Optional floor coach zone as x_min,y_min,x_max,y_max in arena millimetres.")
    ap.add_argument(
        "--ema-snap-thresh-mm",
        type=float,
        default=80.0,
        help="If a joint moves more than this between frames, increase EMA alpha to track fast motion "
        "(jumps, lunges). 0 disables adaptive EMA. Does NOT change ema_update function.",
    )
    ap.add_argument("--max-runtime-sec", type=float, default=0.0, help="0 = infinite")
    ap.add_argument("--max-frame-age-ms", type=float, default=200.0, help="Discard stale camera frames older than this age.")
    ap.add_argument("--perf-log-every", type=int, default=60, help="Print perf summary every N frames (0 disables).")
    ap.add_argument("--perf-jsonl", default="", help="Optional JSONL path for perf summaries.")
    ap.add_argument("--ball-log-jsonl", default="", help="Optional JSONL path logging ball 3D per frame (for speed calibration).")
    ap.add_argument(
        "--render-worker-process",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Render 3D view in a separate process to avoid blocking capture/inference.",
    )
    ap.add_argument(
        "--udp-target-host",
        default="",
        help="If set, stream selected 3D joints over UDP to this host",
    )
    ap.add_argument("--udp-target-port", type=int, default=5005)
    ap.add_argument(
        "--udp-target-joints",
        default="right_knee,right_hip,left_shoulder",
        help="Comma-separated joint names to stream",
    )
    ap.add_argument("--udp-target-conf-min", type=float, default=0.35)
    ap.add_argument("--udp-target-cams-min", type=int, default=2)
    ap.add_argument(
        "--session-id",
        default="",
        help="Optional session identifier. Embedded in --event-log-output records "
             "so the live-viewer stream can be joined with the launcher decision log.",
    )
    ap.add_argument(
        "--event-log-output",
        default="",
        help="Optional JSONL path for closed-loop event log "
             "(session_start, target_chosen, athlete_reacted, outcome_scored, session_end). "
             "Non-blocking writer; never affects render FPS. See src/project_cam/closed_loop/event_log.py.",
    )
    ap.add_argument("--predict-ahead-ms", type=float, default=0.0,
                     help="Predict joint position this many ms into the future (0 = disabled). "
                          "Used for predictive targeting: compensates for system + ball flight latency.")
    ap.add_argument("--kalman-process-noise", type=float, default=500.0,
                     help="Kalman filter process noise std (mm/s^2). Higher = trust measurements more. Tuned via ablation: 500 optimal.")
    ap.add_argument("--kalman-measurement-noise", type=float, default=10.0,
                     help="Kalman filter measurement noise std (mm). Lower = more responsive. Tuned via ablation: 10 optimal for EMA-smoothed input.")
    ap.add_argument("--show-ghost-skeleton", action=argparse.BooleanOptionalAction, default=None,
                     help="Show predicted-position ghost skeleton in 3D view (auto-enabled when predict-ahead-ms > 0).")
    ap.add_argument("--predict-max-uncertainty-mm", type=float, default=500.0,
                     help="Max prediction uncertainty (mm) before prediction is discarded.")
    ap.add_argument("--pose-latency-comp-ms", type=float, default=0.0,
                     help="Display-only latency compensation: render each joint from its Kalman "
                          "prediction this many ms ahead (0 = off; try 100-150 at 15 FPS). Falls back "
                          "per joint when uncertainty exceeds --predict-max-uncertainty-mm. Does NOT "
                          "change joints_state, UDP packets, or triangulation.")
    ap.add_argument("--kalman-measured-dt", action=argparse.BooleanOptionalAction, default=False,
                     help="Propagate joint KFs by measured wall-clock time between pose updates instead "
                          "of a fixed 1/fps step. Fixes velocity over-estimation (and predict-ahead "
                          "overshoot) when the loop runs below --fps or --pose-every > 1.")

    # --- BLM Demo Mode ---
    ap.add_argument("--demo-blm", action="store_true", default=False,
                     help="Enable BLM aim demo overlay on 3D view (no serial needed).")
    ap.add_argument("--demo-blm-joint", default="right_hip",
                     help="Target joint for BLM demo (default: right_hip).")
    ap.add_argument("--demo-blm-launcher-x-mm", type=float, default=600.0)
    ap.add_argument("--demo-blm-launcher-y-mm", type=float, default=1560.0)
    ap.add_argument("--demo-blm-launcher-z-mm", type=float, default=500.0)
    ap.add_argument("--demo-blm-yaw-deg", type=float, default=0.0,
                     help="Launcher yaw in world frame (0 = +X = toward south wall).")
    ap.add_argument("--demo-blm-speed-mps", type=float, default=10.0,
                     help="Ball launch speed (m/s) for ballistic solver.")
    ap.add_argument("--demo-blm-correction-mode", choices=["none", "bias", "linear"], default="linear")
    ap.add_argument("--demo-blm-correction-model",
                     default="garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/correction_model.json")

    args = ap.parse_args()

    normal_defaults = {
        "show_3d": True,
        "show_2d": True,
        "ball_every": 1,
        "pose_every": 2,
        "viz_every": 1,
        "mosaic_every": 1,
    }
    fast_defaults = {
        "show_3d": False,
        "show_2d": False,
        "ball_every": 2,
        "pose_every": 4,
        "viz_every": 4,
        "mosaic_every": 2,
    }
    profile_defaults = fast_defaults if args.high_performance else normal_defaults

    if args.coach_overlay and args.show_3d is None:
        args.show_3d = False
    if args.coach_overlay and args.show_2d is None:
        args.show_2d = False
    if args.show_3d is None:
        args.show_3d = profile_defaults["show_3d"]
    if args.show_2d is None:
        args.show_2d = profile_defaults["show_2d"]
    if args.ball_every is None:
        args.ball_every = profile_defaults["ball_every"]
    if args.pose_every is None:
        args.pose_every = profile_defaults["pose_every"]
    if args.viz_every is None:
        args.viz_every = profile_defaults["viz_every"]
    if args.mosaic_every is None:
        args.mosaic_every = profile_defaults["mosaic_every"]

    args.ball_every = max(1, int(args.ball_every))
    args.pose_every = max(1, int(args.pose_every))
    args.pose_max_batch = max(1, int(args.pose_max_batch))
    args.viz_every = max(1, int(args.viz_every))
    args.mosaic_every = max(1, int(args.mosaic_every))
    if args.joint_stale_frames is None:
        args.joint_stale_frames = max(3, args.pose_every * 3)
    else:
        args.joint_stale_frames = max(1, int(args.joint_stale_frames))

    # --- BLM Demo init ---
    blm_demo = None
    if args.demo_blm:
        blm_joint_idx = JOINT_NAME_TO_IDX.get(args.demo_blm_joint)
        if blm_joint_idx is None:
            raise RuntimeError(f"Unknown --demo-blm-joint: {args.demo_blm_joint}")
        blm_launcher = np.array([args.demo_blm_launcher_x_mm, args.demo_blm_launcher_y_mm,
                                  args.demo_blm_launcher_z_mm])
        blm_correction = None
        if args.demo_blm_correction_mode != "none":
            blm_correction = _blm_load_correction(args.demo_blm_correction_model)
            if blm_correction:
                print(f"[BLM-DEMO] Correction model loaded ({args.demo_blm_correction_mode})")
            else:
                print("[BLM-DEMO] Correction model not found, using mode=none")
                args.demo_blm_correction_mode = "none"
        blm_demo = {
            "joint_idx": blm_joint_idx,
            "joint_name": args.demo_blm_joint,
            "launcher": blm_launcher,
            "yaw_deg": args.demo_blm_yaw_deg,
            "v_mps": args.demo_blm_speed_mps,
            "correction": blm_correction,
            "correction_mode": args.demo_blm_correction_mode,
        }
        print(f"[BLM-DEMO] Targeting '{args.demo_blm_joint}' | launcher=({blm_launcher[0]:.0f}, "
              f"{blm_launcher[1]:.0f}, {blm_launcher[2]:.0f}) mm | yaw={args.demo_blm_yaw_deg}° | "
              f"v={args.demo_blm_speed_mps} m/s")

    display_world_y_mirror = (
        args.world_y_mirror if args.display_world_y_mirror is None else args.display_world_y_mirror
    )
    udp_world_y_mirror = args.world_y_mirror if args.udp_world_y_mirror is None else args.udp_world_y_mirror

    udp_sock = None
    udp_target_addr = None
    udp_target_joint_pairs = []
    if args.udp_target_host:
        names = [x.strip() for x in args.udp_target_joints.split(",") if x.strip()]
        for name in names:
            if name in JOINT_NAME_TO_IDX:
                udp_target_joint_pairs.append((name, JOINT_NAME_TO_IDX[name]))
            elif name in DERIVED_UDP_JOINTS:
                udp_target_joint_pairs.append((name, None))
            else:
                raise RuntimeError(f"Unknown joint name in --udp-target-joints: {name}")
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_target_addr = (args.udp_target_host, args.udp_target_port)
        print(
            f"[INFO] UDP target stream enabled -> {args.udp_target_host}:{args.udp_target_port} "
            f"joints={[n for n, _ in udp_target_joint_pairs]}"
        )

    # Closed-loop event logger (non-blocking writer). Tracks the demo narrative:
    # session_start, target_chosen (rising edge of AIM_OK), athlete_reacted /
    # outcome_scored (operator keypresses 'r' / 'n'), session_end. Does NOT block
    # the render loop — emit calls are O(microseconds) queue puts.
    event_logger = None
    session_id = args.session_id.strip() if args.session_id else ""
    if args.event_log_output:
        ensure_project_src_on_path()
        from project_cam.closed_loop import EventLogger  # noqa: E402

        if not session_id:
            session_id = f"viewer_{int(time.time())}"
            print(f"[INFO] --event-log-output set without --session-id; synthesizing {session_id!r}")
        event_logger = EventLogger(
            output_path=args.event_log_output,
            session_id=session_id,
            source="live_viewer",
            register_atexit=True,
        )
        event_logger.emit(
            "session_start",
            {
                "session_id": session_id,
                "udp_target_host": args.udp_target_host,
                "udp_target_port": args.udp_target_port,
                "udp_target_joints": [n for n, _ in udp_target_joint_pairs],
                "predict_ahead_ms": args.predict_ahead_ms,
            },
        )
        print(f"[OK] EventLogger enabled: {args.event_log_output} (session={session_id})")

    coach_counter = None
    coach_frame_kinematics = None
    coach_select_best_camera = None
    coach_crop_frame_to_roi = None
    coach_repair_overlay_keypoints = None
    coach_render_overlay = None
    coach_roi_cls = None
    coach_keypoint_stabilizer = None
    coach_pushup_floor_anchor = None
    coach_leg_prior_acc = None
    coach_leg_validator = None
    coach_leg_priors = None
    coach_evaluate_ankle_fallback = None
    coach_ankle_fallback_streak = {15: 0, 16: 0}
    coach_was_acquired = False
    if args.coach_overlay:
        ensure_project_src_on_path()
        from project_cam.assessment.kinematics import frame_kinematics as _coach_frame_kinematics  # noqa: E402
        from project_cam.assessment.live_trainer.coach_overlay import (  # noqa: E402
            OverlayKeypointStabilizer as _CoachKeypointStabilizer,
            PushupFloorAnchor as _PushupFloorAnchor,
            StableRoi as _CoachStableRoi,
            crop_frame_to_roi as _coach_crop_frame_to_roi,
            repair_overlay_keypoints as _coach_repair_overlay_keypoints,
            render_coach_overlay as _coach_render_overlay,
            select_best_camera as _coach_select_best_camera,
        )
        from project_cam.assessment.live_trainer.leg_priors import (  # noqa: E402
            LegChainValidator3D as _LegChainValidator3D,
            LegPriorAccumulator as _LegPriorAccumulator,
            evaluate_ankle_fallback as _evaluate_ankle_fallback,
        )
        from project_cam.assessment.live_trainer.rep_state import make_counter as _coach_make_counter  # noqa: E402
        from project_cam.assessment.rules import DEFAULT_CONFIG_PATH, exercise_rules, load_rules  # noqa: E402

        coach_rules = exercise_rules(load_rules(DEFAULT_CONFIG_PATH), args.coach_exercise)
        coach_counter = _coach_make_counter(args.coach_exercise, coach_rules)
        coach_frame_kinematics = _coach_frame_kinematics
        coach_select_best_camera = _coach_select_best_camera
        coach_crop_frame_to_roi = _coach_crop_frame_to_roi
        coach_repair_overlay_keypoints = _coach_repair_overlay_keypoints
        coach_render_overlay = _coach_render_overlay
        coach_roi_cls = _CoachStableRoi
        coach_keypoint_stabilizer = _CoachKeypointStabilizer()
        # Push-up floor anchor: gates ankles into the floor guide only after
        # they have passed leg-chain validation for a sustained streak. Left
        # None for squats so the squat floor path is bit-identical.
        if args.coach_exercise == "push_up":
            coach_pushup_floor_anchor = _PushupFloorAnchor()
            # Per-athlete leg-bone priors learned during acquisition window.
            # Validator drops 3D leg joints whose bone length is anatomically
            # impossible BEFORE the EMA blends them into joints_state, so
            # confidently-wrong triangulations cannot poison downstream
            # consumers (UDP target stream, overlay, 3D arena). Squat path
            # leaves these as None.
            coach_leg_prior_acc = _LegPriorAccumulator()
            coach_leg_validator = _LegChainValidator3D
            coach_evaluate_ankle_fallback = _evaluate_ankle_fallback
        print(f"[INFO] Coach overlay enabled for {args.coach_exercise}")

    # Lightweight squat + push-up rep counters for the cinematic ATHLETE HUD
    # (independent of the heavy --coach-overlay window).
    rep_counters = {}
    rep_frame_kinematics = None
    rep_count_state = {"squat": 0, "push_up": 0}
    if args.count_reps:
        ensure_project_src_on_path()
        from project_cam.assessment.kinematics import frame_kinematics as _rk_fk  # noqa: E402
        from project_cam.assessment.live_trainer.rep_state import make_counter as _rk_make  # noqa: E402
        from project_cam.assessment.rules import (  # noqa: E402
            DEFAULT_CONFIG_PATH as _RK_CFG, exercise_rules as _rk_rules, load_rules as _rk_load)
        _rk_all = _rk_load(_RK_CFG)
        rep_rules_map = {_ex: _rk_rules(_rk_all, _ex) for _ex in ("squat", "push_up")}
        rep_make_fn = _rk_make
        for _ex in ("squat", "push_up"):
            rep_counters[_ex] = _rk_make(_ex, rep_rules_map[_ex])
        rep_frame_kinematics = _rk_fk
        print("[INFO] Rep counters enabled: squat + push_up  (press 'c' to reset)")

    leg_raise_tracker = None
    leg_raise_identity_tracker = None
    leg_raise_apply_identity_lock = None
    leg_raise_apply_segment_drops = None
    leg_raise_lower_body_snapshot = None
    leg_raise_pose2d_snapshot = None
    leg_raise_segment_lengths_snapshot = None
    leg_raise_prior_acc = None
    leg_raise_prior_validator = None
    leg_raise_priors = None
    leg_raise_state = None
    leg_raise_contact_interpreter = None
    if args.leg_raise_mode:
        ensure_project_src_on_path()
        from project_cam.assessment.live_trainer.contact_interpreter import (  # noqa: E402
            ContactAwarePoseInterpreter as _ContactAwarePoseInterpreter,
            ContactInterpretationConfig as _ContactInterpretationConfig,
        )
        from project_cam.assessment.live_trainer.leg_raise_mode import (  # noqa: E402
            LegRaiseConfig as _LegRaiseConfig,
            LegRaiseTracker as _LegRaiseTracker,
        )
        from project_cam.assessment.live_trainer.leg_priors import (  # noqa: E402
            LegChainValidator3D as _LegRaiseLegChainValidator3D,
            LegPriorAccumulator as _LegRaiseLegPriorAccumulator,
        )
        from project_cam.assessment.live_trainer.leg_raise_stabilizer import (  # noqa: E402
            apply_leg_identity_lock as _apply_leg_identity_lock,
            apply_leg_segment_drops as _apply_leg_segment_drops,
            lower_body_pose2d_snapshot as _lower_body_pose2d_snapshot,
            lower_body_snapshot as _lower_body_snapshot,
            segment_lengths_snapshot as _segment_lengths_snapshot,
        )
        from project_cam.assessment.live_trainer.limb_identity import (  # noqa: E402
            LimbIdentityTracker as _LimbIdentityTracker,
        )

        leg_raise_calibration_frames = max(0, int(args.leg_raise_calibration_frames))
        leg_raise_tracker = _LegRaiseTracker(_LegRaiseConfig(
            conf_min=float(args.leg_raise_conf_min),
            max_reproj_px=float(args.pose_max_reproj_px),
            calibration_frames=leg_raise_calibration_frames,
        ))
        leg_raise_identity_tracker = _LimbIdentityTracker()
        leg_raise_apply_identity_lock = _apply_leg_identity_lock
        leg_raise_apply_segment_drops = _apply_leg_segment_drops
        leg_raise_lower_body_snapshot = _lower_body_snapshot
        leg_raise_pose2d_snapshot = _lower_body_pose2d_snapshot
        leg_raise_segment_lengths_snapshot = _segment_lengths_snapshot
        leg_raise_prior_acc = _LegRaiseLegPriorAccumulator(min_frames=8, std_tol_mm=50.0)
        leg_raise_prior_validator = _LegRaiseLegChainValidator3D
        leg_raise_contact_interpreter = _ContactAwarePoseInterpreter(
            _ContactInterpretationConfig(min_confidence=float(args.leg_raise_conf_min))
        )
        print(
            "[INFO] Leg-raise mode enabled: lower-body identity lock + segment gate "
            f"+ angle/contact diagnostics (calibration_frames={leg_raise_calibration_frames})"
        )

    smpl_fitter = None
    smpl_fit_result = None
    smpl_fit_pelvis = None
    smpl_async_active = False
    smpl_pelvis_fn = None
    if args.smpl_avatar:
        if not args.smpl_model_path:
            print("[WARN] --smpl-avatar requested but --smpl-model-path is empty; disabling SMPL mesh.")
        else:
            ensure_project_src_on_path()
            _OptionalAvatarDependencyError = RuntimeError
            try:
                from project_cam.avatar import (  # noqa: E402
                    OptionalAvatarDependencyError as _OptionalAvatarDependencyError,
                    SmplFitConfig as _SmplFitConfig,
                    SmplSessionFitter as _SmplSessionFitter,
                )

                smpl_fitter = _SmplSessionFitter(_SmplFitConfig(
                    model_path=str(args.smpl_model_path),
                    model_type=str(args.smpl_model_type),
                    gender=str(args.smpl_gender),
                    device=str(args.smpl_device),
                    max_iters=int(args.smpl_fit_iters),
                    learning_rate=0.04,
                    min_confidence=float(args.pose_conf),
                    include_head=False,
                    optimize_betas=False,
                    temporal_weight=1e-3,
                    floor_z_mm=0.0,
                    floor_penalty_weight=1e-7,
                ), shape_calibration_frames=int(args.smpl_shape_calib_frames))
                from project_cam.avatar import (  # noqa: E402
                    pelvis_from_coco as _smpl_pelvis_from_coco,
                )
                smpl_pelvis_fn = _smpl_pelvis_from_coco
                if args.smpl_async:
                    from project_cam.avatar import AsyncSmplFitter as _AsyncSmplFitter  # noqa: E402
                    smpl_fitter = _AsyncSmplFitter(smpl_fitter)
                    smpl_async_active = True
                print(
                    "[INFO] SMPL mesh avatar enabled "
                    f"(fit_every={max(1, int(args.smpl_fit_every))}, "
                    f"shape_calib_frames={max(0, int(args.smpl_shape_calib_frames))}, "
                    f"device={args.smpl_device}, async={smpl_async_active}, "
                    f"anchor_follow={bool(args.smpl_anchor_follow)})"
                )
            except (_OptionalAvatarDependencyError, FileNotFoundError, ValueError) as exc:
                print(f"[WARN] SMPL mesh avatar disabled: {exc}")
                smpl_fitter = None
            except Exception as exc:
                print(f"[WARN] SMPL mesh avatar failed to initialize; disabled: {exc}")
                smpl_fitter = None

    # Rising-edge tracker for target_chosen emits. We log a "target_chosen" event
    # every time blm_aim transitions from non-AIM_OK to AIM_OK (or the joint name
    # changes while still AIM_OK), not on every frame.
    _prev_aim_status = None
    _prev_aim_joint = None

    udp_joint_indices_needed = set()
    for name, idx in udp_target_joint_pairs:
        if idx is None and name == "body_center":
            udp_joint_indices_needed.add(JOINT_NAME_TO_IDX["left_hip"])
            udp_joint_indices_needed.add(JOINT_NAME_TO_IDX["right_hip"])
        elif idx is not None:
            udp_joint_indices_needed.add(idx)
    triangulated_joint_indices = list(range(17)) if (args.show_3d or args.coach_overlay) else sorted(udp_joint_indices_needed)

    ball_needed = args.track_ball and (args.show_3d or args.show_2d)
    pose_needed = args.show_2d or args.coach_overlay or bool(triangulated_joint_indices)
    if args.high_performance:
        print(
            "[INFO] High-performance profile: "
            f"show_3d={args.show_3d} show_2d={args.show_2d} "
            f"ball_every={args.ball_every} pose_every={args.pose_every} "
            f"viz_every={args.viz_every} mosaic_every={args.mosaic_every}"
        )
    if not args.track_ball:
        print("[INFO] Ball tracking disabled (--no-track-ball).")
    print(
        f"[INFO] World Y-mirror effective: display={'ON' if display_world_y_mirror else 'OFF'} "
        f"udp={'ON' if udp_world_y_mirror else 'OFF'}"
    )
    if args.invert_y_axis_display:
        print("[INFO] Y-axis display inversion enabled (3D labels only): Ymax..0")
    if args.draw_global_axes:
        print(
            "[INFO] Global triad enabled: O(0,0,0) +X +Y +Z "
            f"(len={float(args.global_axis_len_mm):.0f} mm)"
        )
    use_cv2_viz = args.viz_backend == "cv2"
    if args.show_3d:
        if use_cv2_viz:
            print(f"[INFO] 3D backend: OpenCV ({args.viz_width}x{args.viz_height}). "
                  f"Render-worker-process ignored (not needed).")
        elif args.render_worker_process:
            print("[INFO] 3D render worker process enabled (queue maxsize=1, drop-old policy).")

    use_cuda = ("cuda" in str(args.pose_device).lower()) or ("cuda" in str(args.ball_device).lower())
    if use_cuda:
        try:
            import torch

            if torch.cuda.is_available():
                torch.backends.cudnn.benchmark = True
                try:
                    torch.set_float32_matmul_precision("high")
                except Exception:
                    pass
                print("[INFO] CUDA optimization enabled: cudnn.benchmark=1")
        except Exception:
            pass

    cams_cfg = load_cameras(args.config)
    cam_order = camera_order_from_config(cams_cfg)
    active_cams = []
    for cam in cam_order:
        dev = cams_cfg.get(cam, {}).get("device")
        if dev is not None:
            active_cams.append((cam, dev))
    if len(active_cams) < 2:
        raise RuntimeError("Need at least 2 cameras in config.")

    # Early camera preflight: verify V4L2 devices BEFORE loading CUDA/TensorRT
    # models. A dead rig (config pointing at the wrong camera setup, unplugged
    # hub) must fail in seconds with a clear message — not after a ~10 s engine
    # load that then segfaults in CUDA teardown on exit.
    preflight_ok = {}
    for cam, dev in active_cams:
        ready, ready_reason = v4l2_device_ready(
            dev,
            timeout_s=float(args.camera_preflight_timeout),
        )
        preflight_ok[cam] = ready
        if not ready:
            print(f"[WARN] {cam} preflight failed: {dev} -- {ready_reason}; skipping.")
    ready_cams = [c for c, _ in active_cams if preflight_ok[c]]
    if len(ready_cams) < 2:
        raise RuntimeError(
            f"Only {len(ready_cams)}/{len(active_cams)} camera device(s) passed preflight; "
            f"need >=2 for 3D. Is --config ({args.config}) the right file for the "
            f"cameras currently plugged in?")

    intr = {}
    for cam, _ in active_cams:
        k, d, iw, ih = load_intrinsics(Path(args.intrinsics_dir) / f"{cam}_intrinsics.json")
        if iw > 0 and ih > 0 and (iw != args.width or ih != args.height):
            k_use = scale_intrinsics_matrix(k, iw, ih, args.width, args.height)
            print(f"[INFO] {cam}: scaled intrinsics {iw}x{ih} -> {args.width}x{args.height}")
        else:
            k_use = k
        intr[cam] = {"K": k_use, "D": d}
    extr = load_extrinsics(args.extrinsics)
    dims, tags = parse_dimensions(args.dimensions)
    proj = {cam: extr[cam]["P"] for cam, _ in active_cams if cam in extr}
    coach_zone_mm = parse_coach_zone_mm(args.coach_zone_mm) if args.coach_overlay else None

    ball_model = None
    if ball_needed:
        from ultralytics import YOLO

        ball_model = YOLO(args.ball_model)
    else:
        print("[INFO] Ball detector disabled (no active visualization output).")
    print(f"[INFO] Ball device: {args.ball_device} | Pose device: {args.pose_device}")

    ball_executor = None
    if args.parallel_inference and ball_model is not None:
        # Single worker: one in-flight ball batch, overlapped with the pose
        # stage. Two YOLO objects never share a predictor, so cross-thread
        # calls are safe; the GPU serializes kernels, the CPU pre/post overlap.
        ball_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ball-infer")
        print("[INFO] Parallel inference: ball runs in a worker thread overlapped with pose.")

    pose_infer = None
    yolopose_model = None
    use_yolopose = args.pose_backend == "yolopose"
    if args.pose and pose_needed:
        if use_yolopose:
            try:
                from ultralytics import YOLO as YOLO_Pose
                yolopose_model = YOLO_Pose(args.yolopose_model)
                print(f"[INFO] YOLO-Pose loaded: {args.yolopose_model} (backend=yolopose)")
            except Exception as e:
                print(f"[WARN] YOLO-Pose not available ({e}), falling back to MMPose")
                use_yolopose = False
        if not use_yolopose:
            try:
                from mmpose.apis import MMPoseInferencer

                try:
                    pose_infer = MMPoseInferencer(
                        pose2d="rtmpose-m_8xb256-420e-coco-256x192",
                        det_model="rtmdet-m",
                        device=args.pose_device,
                    )
                except Exception:
                    pose_infer = MMPoseInferencer(pose2d="human", device=args.pose_device)
            except Exception as e:
                print(f"[WARN] MMPose not available, pose disabled: {e}")
                pose_infer = None
    elif args.pose:
        print("[INFO] Pose inferencer disabled (no active 2D/3D/UDP pose consumers).")

    caps = {}
    open_retries = int(args.camera_open_retries)
    open_delay = float(args.camera_open_retry_delay)
    for cam, dev in active_cams:
        if not preflight_ok.get(cam, False):
            # Already reported by the early preflight above.
            continue
        cap = None
        for attempt in range(open_retries + 1):
            apply_uvc_low_latency_controls(dev, cam, args, log=False)
            cap = open_camera_capture(dev)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
            cap.set(cv2.CAP_PROP_FPS, args.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, args.buffer_size)
            if cap.isOpened():
                break
            try:
                cap.release()
            except Exception:
                pass
            cap = None
            if attempt < open_retries:
                print(f"[..] {cam} not ready (attempt {attempt + 1}/{open_retries + 1}); "
                      f"retrying in {open_delay:.0f}s (slow USB / deep hub): {dev}")
                time.sleep(open_delay)
        if cap is None or not cap.isOpened():
            # Graceful degrade: a flaky USB port (e.g. a camera on a deep hub chain)
            # may never come up. Skip it and run with the cameras that DO work, rather
            # than aborting the whole session. Need >=2 for 3D (checked below).
            print(f"[WARN] Cannot open {cam}: {dev} -- skipping after "
                  f"{open_retries + 1} attempt(s).")
            continue
        apply_uvc_low_latency_controls(dev, cam, args, log=True)
        eff_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        eff_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        eff_fps = cap.get(cv2.CAP_PROP_FPS)
        eff_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        eff_fourcc_str = "".join(chr((eff_fourcc >> (8 * i)) & 0xFF) for i in range(4))
        caps[cam] = ThreadedCapture(cap, name=cam)
        print(f"[OK] {cam}: {dev} ({eff_w}x{eff_h}@{eff_fps:.1f}, {eff_fourcc_str})")

    # Drop cameras that failed to open; triangulation needs at least two.
    active_cams = [(c, d) for (c, d) in active_cams if c in caps]
    if len(active_cams) < 2:
        raise RuntimeError(
            f"Only {len(active_cams)} camera(s) opened; need >=2 for 3D. "
            f"Check USB connections / config device paths.")
    print(f"[INFO] {len(active_cams)} cameras active: {[c for c, _ in active_cams]}")

    fig = None
    ax = None
    render_q = None
    render_proc = None
    mp_ctx = None
    if args.show_3d and not use_cv2_viz and not args.render_worker_process:
        plt.ion()
        fig = plt.figure(figsize=(12.0, 9.0), facecolor="#f7f7f7")
        ax = fig.add_subplot(111, projection="3d")
    elif args.show_3d and not use_cv2_viz and args.render_worker_process:
        mp_ctx = mp.get_context("spawn")
        render_q = mp_ctx.Queue(maxsize=1)
        render_proc = mp_ctx.Process(
            target=render_worker_main,
            args=(
                render_q,
                {
                    "dims": dims,
                    "tags": tags,
                    "extr": extr,
                    "world_y_mirror": display_world_y_mirror,
                    "invert_y_axis_display": args.invert_y_axis_display,
                    "draw_global_axes_flag": args.draw_global_axes,
                    "global_axis_len_mm": args.global_axis_len_mm,
                    "view_elev": args.view_elev,
                    "view_azim": args.view_azim,
                },
            ),
            daemon=True,
        )
        render_proc.start()
    prev_dropped_counts = {cam: 0 for cam, _ in active_cams}

    pose_state = {cam: None for cam, _ in active_cams}
    per_cam_pose_state = {}
    pose_lock_active = False
    pose_reacquire_every = max(1, min(args.pose_every, 2))
    pose_last_error_printed = None
    pose_last_error_print_t = 0.0
    pose_select_conf = max(0.2, args.pose_conf - 0.10)
    ball_boxes_state = {}
    ball_state = None
    ball_kf = JointKalmanFilter(
        process_noise=args.ball_kalman_process_noise,
        measurement_noise=args.ball_kalman_measurement_noise,
        dt=1.0 / max(1, args.fps),
    )
    ball_flight_state = BallFlightState()
    ball_liftoff_streak = 0
    ball_coast_count = 0
    ball_frames_since_detect = 10_000
    ball_frames_since_multicam = 10_000
    ball_flight_state.frames_since_multicam = ball_frames_since_multicam
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    joints_display = np.full((17, 3), np.nan, dtype=np.float32)
    joints_predicted = np.full((17, 3), np.nan, dtype=np.float32)
    joints_conf_state = np.zeros((17,), dtype=np.float32)
    joints_cam_state = np.zeros((17,), dtype=np.int32)
    joint_last_seen_frame = np.full((17,), -10_000_000, dtype=np.int64)
    ball_traj = deque(maxlen=args.trail_len)
    # cinematic motion trails for wrists/ankles (display-only)
    joint_trails = {j: deque(maxlen=max(2, args.trail_len)) for j in TRAIL_JOINTS}
    # One-Euro display filters (one per joint) + speed estimate for heat-colouring
    oneeuro_filters = [OneEuroVec(args.oneeuro_mincutoff, args.oneeuro_beta) for _ in range(17)]
    joint_speeds = np.zeros((17,), dtype=np.float64)
    prev_speed_pos = np.full((17, 3), np.nan, dtype=np.float64)
    prev_speed_t = None
    # 'r'-keypress MP4 recording of the cinematic 3D view
    rec_writer = None
    rec_path = None

    # Kalman filters: one per joint for predictive targeting
    use_prediction = args.predict_ahead_ms > 0
    show_ghost = args.show_ghost_skeleton if args.show_ghost_skeleton is not None else use_prediction
    kalman_dt = 1.0 / max(1, args.fps)
    joint_kfs = [
        JointKalmanFilter(
            process_noise=args.kalman_process_noise,
            measurement_noise=args.kalman_measurement_noise,
            dt=kalman_dt,
        )
        for _ in range(17)
    ]
    # Wall-clock time of each joint's last KF update (for --kalman-measured-dt).
    joint_kf_last_update_t = [None] * 17
    coach_prev_camera = None
    coach_lock_hold = 0  # frames the push-up camera stays locked after acquisition loss
    coach_rois = {}
    coach_state = coach_counter.state if coach_counter is not None else None
    coach_metrics = {}
    coach_window = f"Project_Cam Live Coach - {args.coach_exercise}"
    coach_output_size = (int(args.viz_width), int(args.viz_height))

    frame_idx = 0
    # Create the 3D window resizable (WINDOW_NORMAL lets the user drag/maximise it
    # and stretch the render to fit); optionally force true fullscreen.
    if use_cv2_viz and args.show_3d:
        cv2.namedWindow("Live 3D Arena", cv2.WINDOW_NORMAL)
        if args.fullscreen:
            cv2.setWindowProperty("Live 3D Arena", cv2.WND_PROP_FULLSCREEN,
                                  cv2.WINDOW_FULLSCREEN)

    t_start = time.time()
    t_prev = t_start
    fps_est = 0.0
    timer = StageTimer(window=max(10, args.perf_log_every))
    perf_fh = None
    if args.perf_jsonl:
        perf_path = Path(args.perf_jsonl)
        perf_path.parent.mkdir(parents=True, exist_ok=True)
        perf_fh = perf_path.open("a", encoding="utf-8")
        print(f"[INFO] Perf JSONL enabled: {perf_path}")
    ball_log_fh = None
    if args.ball_log_jsonl:
        ball_log_path = Path(args.ball_log_jsonl)
        ball_log_path.parent.mkdir(parents=True, exist_ok=True)
        ball_log_fh = ball_log_path.open("a", encoding="utf-8")
        print(f"[INFO] Ball JSONL enabled: {ball_log_path}")
    leg_raise_log_fh = None
    if args.leg_raise_log_jsonl:
        leg_raise_log_path = Path(args.leg_raise_log_jsonl)
        leg_raise_log_path.parent.mkdir(parents=True, exist_ok=True)
        leg_raise_log_fh = leg_raise_log_path.open("a", encoding="utf-8")
        print(f"[INFO] Leg-raise JSONL enabled: {leg_raise_log_path}")

    stop_hints = []
    if args.coach_overlay:
        stop_hints.append("press q in coach window")
    if args.show_2d:
        stop_hints.append("press q in 2D window")
    if args.show_3d:
        stop_hints.append("close 3D window")
    if stop_hints:
        print(f"[INFO] Live loop started. { ' or '.join(stop_hints) } to stop.")
    else:
        print("[INFO] Live loop started. Press Ctrl+C to stop.")

    video_writer_3d = None
    video_writer_mosaic = None

    import signal as _sig
    _stop_flag = {"v": False}
    def _sig_handler(signum, frame):
        _stop_flag["v"] = True
    _sig.signal(_sig.SIGTERM, _sig_handler)
    _sig.signal(_sig.SIGINT, _sig_handler)

    if args.record_video:
        Path(args.record_video).parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        video_writer_3d = cv2.VideoWriter(args.record_video, fourcc, args.record_fps,
                                          (args.viz_width, args.viz_height))
        print(f"[REC] 3D arena recording → {args.record_video} @ {args.record_fps} fps")
    if args.record_mosaic:
        Path(args.record_mosaic).parent.mkdir(parents=True, exist_ok=True)

    try:
        while not _stop_flag["v"]:
            timer.start("total")
            if args.max_runtime_sec > 0 and (time.time() - t_start) > args.max_runtime_sec:
                break

            timer.start("capture")
            cam_frames = {}
            frame_batch = []
            batch_order = []
            frame_age_ms_per_cam = {}
            dropped_frames_per_cam = {}
            stale_frames_per_cam = {}
            t_capture_now = time.perf_counter()
            any_new_frame = False
            for cam, _ in active_cams:
                ret, frame, ts, is_new = caps[cam].read_latest()
                stats = caps[cam].stats()
                dropped_total = int(stats["dropped"])
                dropped_prev = int(prev_dropped_counts.get(cam, 0))
                dropped_frames_per_cam[cam] = max(0, dropped_total - dropped_prev)
                prev_dropped_counts[cam] = dropped_total
                if not ret:
                    continue
                age_ms = (t_capture_now - ts) * 1000.0
                frame_age_ms_per_cam[cam] = age_ms
                if age_ms > float(args.max_frame_age_ms):
                    stale_frames_per_cam[cam] = age_ms
                    continue
                if is_new:
                    any_new_frame = True
                cam_frames[cam] = frame
                frame_batch.append(frame)
                batch_order.append(cam)
            timer.stop("capture")

            if len(frame_batch) < 2:
                timer.stop("total")
                time.sleep(0.002)
                continue

            # No camera produced a NEW frame since the last cycle: the inputs are
            # identical, so re-running pose/triangulation would just burn GPU on
            # the same skeleton. Skip; the async renderer keeps displaying. This
            # plus read_latest() always returning the freshest frame means the
            # skeleton now refreshes whenever ANY camera updates (~aggregate fps)
            # instead of only when >=2 cameras happen to align in one iteration.
            if not any_new_frame:
                timer.stop("total")
                time.sleep(0.002)
                continue

            frame_idx += 1
            t_now = time.time()
            dt = max(1e-6, t_now - t_prev)
            t_prev = t_now
            fps_est = 0.92 * fps_est + 0.08 * (1.0 / dt)

            ball_boxes = ball_boxes_state.copy()
            ball_obs = {}
            ball_obs_px = {}
            run_ball = ball_model is not None and (frame_idx % args.ball_every == 0)
            ball_future = None
            ball_results = None
            timer.start("ball")
            if run_ball:
                # Chunked like the pose path: the TRT engine profile caps the
                # batch, so an over-large camera count must split calls.
                ball_infer_kwargs = dict(
                    conf=args.ball_conf,
                    imgsz=args.ball_imgsz,
                    verbose=False,
                    stream=False,
                    device=args.ball_device,
                )
                if ball_executor is not None:
                    # Overlap ball inference with the pose stage below; results
                    # are collected in the "ballwait" segment before ball
                    # triangulation. Saves ~min(ball_ms, pose_ms) per frame.
                    ball_future = ball_executor.submit(
                        run_yolopose_batched, ball_model, frame_batch,
                        args.ball_max_batch, **ball_infer_kwargs)
                else:
                    ball_results = run_yolopose_batched(
                        ball_model, frame_batch, args.ball_max_batch,
                        **ball_infer_kwargs)
            timer.stop("ball")

            per_cam_pose = per_cam_pose_state.copy()
            joints_3d_now = {}
            pose_every_eff = args.pose_every if pose_lock_active else pose_reacquire_every
            run_pose = (pose_infer is not None or yolopose_model is not None) and (frame_idx % pose_every_eff == 0)
            per_cam_pose_curr = {}
            pose_und_by_cam = {}
            pose_raw_counts = {}
            pose_error = ""
            timer.start("pose")
            if run_pose and use_yolopose and yolopose_model is not None:
                # YOLO-Pose path: single model for detection + keypoints
                try:
                    yp_kwargs = dict(
                        max_batch_size=args.pose_max_batch,
                        device=args.pose_device,
                        verbose=False,
                        conf=0.15,
                    )
                    if int(args.pose_imgsz) > 0:
                        # Without this, ultralytics letterboxes every frame to
                        # the engine's default imgsz (1280) — 4x wasted compute
                        # when the capture is 640x360. Dynamic engines accept
                        # any size in the profile, so 640 is a pure speedup.
                        yp_kwargs["imgsz"] = int(args.pose_imgsz)
                    yp_results = run_yolopose_batched(
                        yolopose_model,
                        frame_batch,
                        **yp_kwargs,
                    )
                except Exception as exc:
                    pose_error = repr(exc)
                    yp_results = [None] * len(frame_batch)
                    # A permanently-failing pose stage must be loud in the
                    # terminal, not only a field in the perf JSONL — a CUDA
                    # error here previously rendered an empty arena with no
                    # visible hint. Rate-limited to one line per 5 s.
                    t_perr = time.monotonic()
                    if (pose_error != pose_last_error_printed
                            or t_perr - pose_last_error_print_t > 5.0):
                        print(f"[WARN] pose inference failing: {pose_error}")
                        pose_last_error_printed = pose_error
                        pose_last_error_print_t = t_perr
                for cam, yp_res in zip(batch_order, yp_results):
                    if yp_res is None or not hasattr(yp_res, "keypoints") or yp_res.keypoints is None:
                        pose_raw_counts[cam] = 0
                        pose_state[cam] = None
                        per_cam_pose_state.pop(cam, None)
                        continue
                    kpts_all = yp_res.keypoints.data.cpu().numpy()  # (N, 17, 3) — x, y, conf
                    pose_raw_counts[cam] = int(len(kpts_all))
                    if len(kpts_all) == 0:
                        pose_state[cam] = None
                        per_cam_pose_state.pop(cam, None)
                        continue
                    cands = []
                    for pi in range(len(kpts_all)):
                        kpts_17 = kpts_all[pi, :17, :2].astype(np.float32)
                        scores_17 = kpts_all[pi, :17, 2].astype(np.float32)
                        person_dict = {"keypoints": kpts_17, "keypoint_scores": scores_17}
                        cand = extract_person_pose(person_dict)
                        if cand is not None:
                            cands.append(cand)
                    if not cands:
                        pose_state[cam] = None
                        per_cam_pose_state.pop(cam, None)
                        continue
                    selected = select_target_person(
                        candidates=cands,
                        prev_state=pose_state[cam],
                        conf_thresh=pose_select_conf,
                        switch_area_ratio=args.switch_area_ratio,
                    )
                    pose_state[cam] = selected
                    if selected is not None:
                        pose_pair = (selected["kpts"], selected["scores"])
                        per_cam_pose_curr[cam] = pose_pair
                        per_cam_pose_state[cam] = pose_pair
                    else:
                        per_cam_pose_state.pop(cam, None)
            elif run_pose and pose_infer is not None:
                # MMPose path (original)
                try:
                    res_list = list(pose_infer(frame_batch, return_vis=False, batch_size=len(frame_batch)))
                except Exception as exc:
                    pose_error = repr(exc)
                    res_list = []

                for cam, res in zip(batch_order, res_list):
                    preds = res.get("predictions", []) if isinstance(res, dict) else []
                    persons = flatten_predictions(preds)
                    pose_raw_counts[cam] = int(len(persons))
                    cands = []
                    for p in persons:
                        cand = extract_person_pose(p)
                        if cand is not None:
                            cands.append(cand)
                    if not cands:
                        pose_state[cam] = None
                        per_cam_pose_state.pop(cam, None)
                        continue
                    selected = select_target_person(
                        candidates=cands,
                        prev_state=pose_state[cam],
                        conf_thresh=pose_select_conf,
                        switch_area_ratio=args.switch_area_ratio,
                    )
                    pose_state[cam] = selected
                    if selected is not None:
                        pose_pair = (selected["kpts"], selected["scores"])
                        per_cam_pose_curr[cam] = pose_pair
                        per_cam_pose_state[cam] = pose_pair
                    else:
                        per_cam_pose_state.pop(cam, None)

            # --- Shared post-processing for both YOLO-Pose and MMPose ---
            if run_pose:
                per_cam_pose = per_cam_pose_state.copy()
                has_pose_lock = len(per_cam_pose_curr) >= 2
                force_pose_snap = has_pose_lock and not pose_lock_active
                pose_lock_active = has_pose_lock

                if args.pose_lr_fix:
                    # Per-camera left/right relabeling against the 3D state.
                    # Cameras facing the person (worst when lying/prone) mirror
                    # YOLO's left/right; triangulating mixed labels collapses
                    # both 3D limbs together ("both legs rise" artifact).
                    for cam, kdat in per_cam_pose_curr.items():
                        if cam not in extr or cam not in intr:
                            continue
                        fix_lr_swaps_for_cam(
                            kdat[0], kdat[1], joints_state,
                            extr[cam]["R"], extr[cam]["tvec"],
                            intr[cam]["K"], intr[cam]["D"],
                            min_conf=args.pose_conf)

                for cam, kdat in per_cam_pose_curr.items():
                    kpts, scores = kdat
                    j_ids = []
                    pts = []
                    for j in triangulated_joint_indices:
                        if scores[j] >= args.pose_conf:
                            j_ids.append(j)
                            pts.append((float(kpts[j, 0]), float(kpts[j, 1])))
                    und_pts = undistort_points_batch(pts, intr[cam]["K"], intr[cam]["D"])
                    pose_und_by_cam[cam] = {jid: up for jid, up in zip(j_ids, und_pts)}
            else:
                force_pose_snap = False
            timer.stop("pose")

            # Collect ball detections (submitted before the pose stage when
            # --parallel-inference is on) and pick per-camera candidates.
            timer.start("ballwait")
            if run_ball:
                if ball_future is not None:
                    try:
                        ball_results = ball_future.result()
                    except Exception as exc:
                        print(f"[WARN] parallel ball inference failed this frame: {exc}")
                        ball_results = []
                ball_boxes = {}
                kf_pred_3d = None
                if (args.ball_kf_gate_px > 0.0
                        and ball_kf is not None and ball_kf.initialized):
                    dt_ahead = 1.0 / max(1, args.fps)
                    kf_pred_3d = ball_kf.predict_ahead(dt_ahead)

                for cam, res in zip(batch_order, ball_results or []):
                    if res is None or res.boxes is None or len(res.boxes) == 0:
                        continue
                    xyxy_arr = res.boxes.xyxy.cpu().numpy()
                    conf_arr = res.boxes.conf.cpu().numpy()
                    candidates = [
                        (float(xyxy_arr[i, 0]), float(xyxy_arr[i, 1]),
                         float(xyxy_arr[i, 2]), float(xyxy_arr[i, 3]),
                         float(conf_arr[i]))
                        for i in range(len(conf_arr))
                    ]

                    kf_pred_uv = None
                    if kf_pred_3d is not None and cam in extr and cam in intr:
                        try:
                            kf_pred_uv = project_world_to_pixel(
                                kf_pred_3d,
                                extr[cam]["R"], extr[cam]["tvec"],
                                intr[cam]["K"], intr[cam]["D"],
                            )
                        except Exception:
                            kf_pred_uv = None

                    chosen = select_ball_box_for_cam(
                        candidates,
                        kf_pred_uv,
                        args.ball_kf_gate_px,
                        args.ball_min_box_side_px,
                        args.ball_max_box_side_px,
                    )
                    if chosen is None:
                        continue
                    x1, y1, x2, y2, conf = chosen
                    cx = 0.5 * (x1 + x2)
                    cy = 0.5 * (y1 + y2)
                    und = undistort_points((cx, cy), intr[cam]["K"], intr[cam]["D"])
                    ball_obs[cam] = und
                    ball_obs_px[cam] = np.array([cx, cy], dtype=np.float64)
                    ball_boxes[cam] = (int(x1), int(y1), int(x2), int(y2), conf)
                ball_boxes_state = ball_boxes
            timer.stop("ballwait")

            timer.start("triang")
            ball_3d = None
            ball_source = "none"
            ball_debug_reason = None
            ball_state_transition = None
            ball_single_cam_used = False
            ball_single_cam_target_z = None
            ball_multicam_vz_raw = None
            ball_measurement_noise_scale = 1.0
            ball_multicam_lock_this_frame = False
            ball_floor_z_mm = float(args.ball_single_cam_floor_mm)
            ball_min_cams = max(2, args.ball_min_cams)
            if len(ball_obs) >= ball_min_cams:
                tri, _used, _rep = robust_triangulate_ball(
                    obs_norm=ball_obs,
                    obs_px=ball_obs_px,
                    proj_mats=proj,
                    extr=extr,
                    intr=intr,
                    min_cams=ball_min_cams,
                    max_reproj_px=args.ball_max_reproj_px,
                )
                if tri is None:
                    ball_debug_reason = "multicam_triangulation_failed"
                # Max-speed gate only when gap is short enough to be physically meaningful.
                # After a long drop, treat the new detection as a re-acquisition (no gate).
                if (tri is not None and ball_kf.initialized
                        and args.ball_max_speed_mps > 0
                        and ball_frames_since_detect <= 3):
                    prev_pos = ball_kf.get_position()
                    elapsed = max(1e-3, ball_frames_since_detect / max(1, args.fps))
                    speed = float(np.linalg.norm(tri - prev_pos)) / 1000.0 / elapsed
                    if speed > args.ball_max_speed_mps:
                        tri = None
                        ball_debug_reason = "multicam_speed_gate"
                ball_3d = tri
                if tri is not None:
                    ball_source = "multi"
                    ball_multicam_lock_this_frame = True
                    if ball_flight_state.t_last_multicam > 0.0:
                        dt_multicam = max(1e-3, t_now - ball_flight_state.t_last_multicam)
                        multicam_vel, ball_multicam_vz_raw = estimate_ballistic_multicam_velocity(
                            ball_flight_state.last_multicam_pos_mm,
                            ball_flight_state.last_multicam_vel_mm_s,
                            tri,
                            dt_multicam,
                        )
                    else:
                        multicam_vel = np.zeros(3, dtype=np.float64)
                        ball_multicam_vz_raw = 0.0
                    # Only accepted multi-cam frames are allowed to promote FLOOR -> AIRBORNE.
                    if multicam_vel[2] > args.ball_bounce_liftoff_vz_mm_s:
                        ball_liftoff_streak += 1
                    else:
                        ball_liftoff_streak = 0
                    if ball_liftoff_streak >= 2 and ball_flight_state.mode != BALL_FLIGHT_AIRBORNE:
                        prev_mode = ball_flight_state.mode
                        ball_flight_state.mode = BALL_FLIGHT_AIRBORNE
                        ball_state_transition = f"{prev_mode}->{BALL_FLIGHT_AIRBORNE}"
                    if tri[2] < ball_floor_z_mm + 30.0 and multicam_vel[2] < 0.0:
                        prev_mode = ball_flight_state.mode
                        ball_flight_state.mode = BALL_FLIGHT_FLOOR
                        if prev_mode != BALL_FLIGHT_FLOOR:
                            ball_state_transition = f"{prev_mode}->{BALL_FLIGHT_FLOOR}"
                        ball_liftoff_streak = 0
                    ball_flight_state.last_multicam_pos_mm = np.asarray(tri, dtype=np.float64).copy()
                    ball_flight_state.last_multicam_vel_mm_s = np.asarray(multicam_vel, dtype=np.float64).copy()
                    ball_flight_state.t_last_multicam = t_now
                    ball_frames_since_multicam = 0
                    ball_flight_state.frames_since_multicam = 0
            elif args.ball_single_cam_fallback and len(ball_obs) == 1:
                cam_solo = next(iter(ball_obs.keys()))
                tri = None
                if ball_frames_since_multicam > args.ball_single_cam_max_frames:
                    ball_debug_reason = "single_cam_max_frames_exceeded"
                elif args.ball_ballistic_fallback:
                    if ball_flight_state.mode == BALL_FLIGHT_AIRBORNE:
                        dt_ballistic = max(0.0, t_now - ball_flight_state.t_last_multicam)
                        target_z = ballistic_predict_z(
                            ball_flight_state.last_multicam_pos_mm[2],
                            ball_flight_state.last_multicam_vel_mm_s[2],
                            dt_ballistic,
                            args.ball_gravity_mm_s2,
                            ball_floor_z_mm,
                        )
                        if target_z <= ball_floor_z_mm + 1e-3:
                            prev_mode = ball_flight_state.mode
                            ball_flight_state.mode = BALL_FLIGHT_FLOOR
                            if prev_mode != BALL_FLIGHT_FLOOR:
                                ball_state_transition = f"{prev_mode}->{BALL_FLIGHT_FLOOR}"
                            ball_liftoff_streak = 0
                    else:
                        target_z = ball_floor_z_mm
                    ball_single_cam_target_z = float(target_z)
                    if target_z > 4000.0:
                        tri = None
                        ball_debug_reason = "ballistic_target_above_ceiling"
                    else:
                        tri = project_ray_to_z_plane(
                            ball_obs[cam_solo],
                            extr[cam_solo]["R"],
                            extr[cam_solo]["tvec"],
                            target_z,
                        )
                        if tri is None:
                            ball_debug_reason = "single_cam_ray_miss"
                    ball_measurement_noise_scale = args.ball_single_cam_meas_noise_mult
                else:
                    # Legacy single-cam fallback: intersect the ray with the KF-predicted Z plane.
                    # Use KF depth if we have a recent lock; else fall back to the floor plane.
                    if ball_kf.initialized:
                        dt_ahead = max(1e-3, 1.0 / max(1, args.fps))
                        target_z = float(ball_kf.predict_ahead(dt_ahead)[2])
                    else:
                        target_z = ball_floor_z_mm
                    ball_single_cam_target_z = float(target_z)
                    tri = project_ray_to_z_plane(
                        ball_obs[cam_solo],
                        extr[cam_solo]["R"],
                        extr[cam_solo]["tvec"],
                        target_z,
                    )
                    if tri is None:
                        ball_debug_reason = "single_cam_ray_miss"
                if tri is not None and np.isfinite(tri).all():
                    ball_3d = tri
                    ball_single_cam_used = True
                    ball_source = "single_ballistic" if args.ball_ballistic_fallback else "single_legacy"
            if not ball_multicam_lock_this_frame:
                # The liftoff debounce is defined strictly over consecutive accepted multi-cam locks.
                ball_liftoff_streak = 0
            if ball_3d is not None:
                # On re-acquisition after a long drop, reset KF to new measurement
                # so we don't blend with stale velocity.
                if ball_frames_since_detect > args.ball_coast_frames:
                    ball_kf = JointKalmanFilter(
                        process_noise=args.ball_kalman_process_noise,
                        measurement_noise=args.ball_kalman_measurement_noise,
                        dt=1.0 / max(1, args.fps),
                    )
                ball_kf.predict_step()
                ball_kf.update_step(ball_3d, measurement_noise_scale=ball_measurement_noise_scale)
                ball_state = ball_kf.get_position().astype(np.float32)
                ball_coast_count = 0
                ball_frames_since_detect = 0
                if ball_single_cam_used:
                    ball_frames_since_multicam += 1
                    ball_flight_state.frames_since_multicam = ball_frames_since_multicam
            elif ball_kf.initialized and ball_coast_count < args.ball_coast_frames:
                ball_kf.predict_step()
                # Damp velocity during coast so we don't fly off on bounces/stops.
                ball_kf.x[3:] *= 0.7
                ball_state = ball_kf.get_position().astype(np.float32)
                ball_coast_count += 1
                ball_frames_since_detect += 1
                ball_source = "coast"
            else:
                ball_state = None
                ball_frames_since_detect += 1
            if args.show_3d and ball_state is not None and np.isfinite(ball_state).all():
                ball_traj.append(ball_state.copy())
            if ball_log_fh is not None:
                rec = {"t": time.time(), "frame": int(frame_idx), "n_cams": int(len(ball_obs))}
                if ball_state is not None and np.isfinite(ball_state).all():
                    rec["ball_mm"] = [float(ball_state[0]), float(ball_state[1]), float(ball_state[2])]
                    rec["detected"] = (ball_3d is not None)
                else:
                    rec["ball_mm"] = None
                    rec["detected"] = False
                rec["source"] = ball_source
                rec["ball_flight_mode"] = ball_flight_state.mode
                rec["ball_state_transition"] = ball_state_transition
                rec["ball_frames_since_detect"] = int(ball_frames_since_detect)
                rec["ball_frames_since_multicam"] = int(ball_frames_since_multicam)
                rec["ball_liftoff_streak"] = int(ball_liftoff_streak)
                rec["ball_measurement_noise_scale"] = float(ball_measurement_noise_scale)
                rec["ball_single_cam_target_z_mm"] = ball_single_cam_target_z
                rec["ball_last_multicam_pos_mm"] = ball_flight_state.last_multicam_pos_mm.astype(float).tolist()
                rec["ball_last_multicam_vel_mm_s"] = ball_flight_state.last_multicam_vel_mm_s.astype(float).tolist()
                rec["ball_multicam_vz_raw_mm_s"] = ball_multicam_vz_raw
                rec["ball_fallback_reject_reason"] = ball_debug_reason
                ball_log_fh.write(json.dumps(rec) + "\n")

            leg_raise_identity_result = None
            leg_raise_pose2d_for_log = None
            leg_raise_raw_joints_for_log = None
            leg_raise_raw_lengths_for_log = None
            leg_raise_identity_joints_for_log = None
            leg_raise_identity_lengths_for_log = None
            leg_raise_dropped_joints_for_log = []
            leg_raise_prior_status_for_log = None
            leg_raise_contact_for_log = None
            if run_pose:
                for j in triangulated_joint_indices:
                    obs = {}
                    obs_px = {}
                    obs_scores = []
                    for cam in batch_order:
                        und_map = pose_und_by_cam.get(cam)
                        if not und_map or j not in und_map:
                            continue
                        obs[cam] = und_map[j]
                        kpts_cam = per_cam_pose_curr[cam][0]
                        obs_px[cam] = np.array(
                            [float(kpts_cam[j, 0]), float(kpts_cam[j, 1])],
                            dtype=np.float64)
                        obs_scores.append(float(per_cam_pose_curr[cam][1][j]))
                    if len(obs) >= 2:
                        pt, used = robust_triangulate_joint(
                            obs, obs_px, proj, extr, intr,
                            min_cams=max(2, int(args.pose_min_cams)),
                            max_reproj_px=args.pose_max_reproj_px)
                        if pt is not None:
                            joints_3d_now[j] = pt
                            joint_last_seen_frame[j] = frame_idx
                            joints_conf_state[j] = float(np.mean(obs_scores)) if obs_scores else 0.0
                            joints_cam_state[j] = int(len(used))
                        else:
                            joints_cam_state[j] = 0
                            joints_conf_state[j] = 0.0
                    else:
                        joints_cam_state[j] = 0
                        joints_conf_state[j] = 0.0

                # Per-athlete leg-prior validation: observe stable plank
                # frames to learn femur/tibia lengths, then drop any
                # post-triangulation leg joint whose parent-bone length is
                # outside +/- 15% of the learned prior. Operates on the
                # freshly triangulated joints BEFORE the EMA below, so a
                # confidently-wrong leg cannot corrupt joints_state.
                # Gated on push-up coach mode + acquired set; safe-default
                # off for squat / BLM / 3D-only runs.
                if (
                    coach_leg_prior_acc is not None
                    and coach_leg_validator is not None
                    and coach_state is not None
                    and bool(getattr(coach_state, "acquired", False))
                ):
                    coach_leg_prior_acc.observe(
                        joints_3d_now, joints_cam_state, frame_idx
                    )
                    if coach_leg_priors is None:
                        coach_leg_priors = coach_leg_prior_acc.try_lock()
                    if coach_leg_priors is not None:
                        drops = coach_leg_validator.filter_drops(
                            joints_3d_now, coach_leg_priors
                        )
                        for _drop_j in drops:
                            joints_3d_now.pop(_drop_j, None)
                            joints_cam_state[_drop_j] = 0
                            joints_conf_state[_drop_j] = 0.0

                # Single-camera ankle fallback: when an ankle has exactly one
                # contributing camera AND per-athlete priors are locked AND
                # the same-side hip/knee were multi-cam triangulated this
                # frame, project the ankle's lone ray to the floor Z-plane
                # and accept it if the proposal passes the tibia + hip-distance
                # gates. The gates are what stop the raised-foot ray from
                # landing on far floor clutter. Opt-in via flag.
                if (
                    args.pushup_ankle_single_cam_fallback
                    and coach_evaluate_ankle_fallback is not None
                    and coach_leg_priors is not None
                    and coach_state is not None
                    and bool(getattr(coach_state, "acquired", False))
                ):
                    for _ank_j, _hip_j, _knee_j in ((15, 11, 13), (16, 12, 14)):
                        # Already triangulated (>=2 cams) OR already given up.
                        if _ank_j in joints_3d_now or int(joints_cam_state[_ank_j]) != 1:
                            # Reset streak on either acceptance or N/A.
                            if _ank_j in joints_3d_now:
                                coach_ankle_fallback_streak[_ank_j] = 0
                            continue
                        if coach_ankle_fallback_streak[_ank_j] >= int(args.pushup_ankle_single_cam_max_frames):
                            # Cap reached: refuse to drift indefinitely.
                            joints_cam_state[_ank_j] = 0
                            joints_conf_state[_ank_j] = 0.0
                            continue
                        # Find the lone observation for this ankle.
                        _solo_cam = None
                        for _cam in batch_order:
                            _und_map = pose_und_by_cam.get(_cam)
                            if _und_map and _ank_j in _und_map:
                                _solo_cam = _cam
                                break
                        if _solo_cam is None:
                            continue
                        # Hip and knee must be multi-cam triangulated this frame.
                        _knee_pt = joints_3d_now.get(_knee_j)
                        _hip_pt = joints_3d_now.get(_hip_j)
                        if _knee_pt is None or _hip_pt is None:
                            continue
                        _proposal = coach_evaluate_ankle_fallback(
                            ankle_idx=_ank_j,
                            obs_norm=pose_und_by_cam[_solo_cam][_ank_j],
                            R=extr[_solo_cam]["R"],
                            tvec=extr[_solo_cam]["tvec"],
                            target_z_mm=float(args.pushup_ankle_floor_mm),
                            knee_pt=_knee_pt,
                            hip_pt=_hip_pt,
                            priors=coach_leg_priors,
                        )
                        if _proposal is None:
                            # Gate rejected: keep ankle dropped (NaN downstream).
                            joints_cam_state[_ank_j] = 0
                            joints_conf_state[_ank_j] = 0.0
                            continue
                        # Accept, but downweight confidence so the EMA leans
                        # on history more than this single-camera estimate.
                        joints_3d_now[_ank_j] = _proposal
                        joint_last_seen_frame[_ank_j] = frame_idx
                        _solo_conf = float(per_cam_pose_curr[_solo_cam][1][_ank_j])
                        joints_conf_state[_ank_j] = max(0.0, min(1.0, _solo_conf * 0.5))
                        joints_cam_state[_ank_j] = 1
                        coach_ankle_fallback_streak[_ank_j] += 1

                if leg_raise_lower_body_snapshot is not None:
                    leg_raise_raw_joints_for_log = leg_raise_lower_body_snapshot(joints_3d_now)
                    leg_raise_raw_lengths_for_log = leg_raise_segment_lengths_snapshot(joints_3d_now)
                    if leg_raise_pose2d_snapshot is not None:
                        leg_raise_pose2d_for_log = leg_raise_pose2d_snapshot(
                            {cam: per_cam_pose_curr.get(cam) for cam in batch_order}
                        )

                if (
                    leg_raise_apply_identity_lock is not None
                    and leg_raise_identity_tracker is not None
                ):
                    leg_raise_identity_result = leg_raise_apply_identity_lock(
                        joints_3d_now,
                        joints_conf_state,
                        joints_cam_state,
                        leg_raise_identity_tracker,
                    )
                    for _leg_j in (11, 12, 13, 14, 15, 16):
                        if _leg_j in joints_3d_now:
                            joint_last_seen_frame[_leg_j] = frame_idx

                if leg_raise_lower_body_snapshot is not None:
                    leg_raise_identity_joints_for_log = leg_raise_lower_body_snapshot(joints_3d_now)
                    leg_raise_identity_lengths_for_log = leg_raise_segment_lengths_snapshot(joints_3d_now)

                if (
                    leg_raise_prior_acc is not None
                    and leg_raise_prior_validator is not None
                    and leg_raise_apply_segment_drops is not None
                ):
                    if frame_idx <= int(args.leg_raise_calibration_frames):
                        leg_raise_prior_status_for_log = "calibrating"
                        leg_raise_prior_acc.observe(joints_3d_now, joints_cam_state, frame_idx)
                    elif leg_raise_priors is None:
                        leg_raise_priors = leg_raise_prior_acc.try_lock()
                        leg_raise_prior_status_for_log = "locked" if leg_raise_priors is not None else "unlocked"
                    else:
                        leg_raise_prior_status_for_log = "locked"

                    if leg_raise_priors is not None:
                        _drops = leg_raise_prior_validator.filter_drops(
                            joints_3d_now, leg_raise_priors, tol_pct=0.25
                        )
                        if _drops:
                            _expanded_drops = leg_raise_apply_segment_drops(
                                joints_3d_now,
                                joints_conf_state,
                                joints_cam_state,
                                _drops,
                            )
                            leg_raise_dropped_joints_for_log = sorted(int(j) for j in _expanded_drops)
                            for _drop_j in _expanded_drops:
                                joint_last_seen_frame[_drop_j] = -10_000_000
                                joints_state[_drop_j] = np.nan
                                joints_display[_drop_j] = np.nan
                                joints_predicted[_drop_j] = np.nan

                for j, pt in joints_3d_now.items():
                    prev = None if force_pose_snap else (joints_state[j] if np.isfinite(joints_state[j]).all() else None)
                    # Adaptive EMA: snap faster on large movements (jumps, lunges)
                    alpha_eff = args.ema_alpha
                    if prev is not None and args.ema_snap_thresh_mm > 0:
                        disp = float(np.linalg.norm(pt - prev))
                        if disp > args.ema_snap_thresh_mm:
                            alpha_eff = min(1.0, args.ema_alpha * (disp / args.ema_snap_thresh_mm))
                    joints_state[j] = ema_update(prev, pt, alpha=alpha_eff)

            for j in triangulated_joint_indices:
                if frame_idx - int(joint_last_seen_frame[j]) > args.joint_stale_frames:
                    joints_state[j] = np.nan
                    joints_conf_state[j] = 0.0
                    joints_cam_state[j] = 0

            # Kalman filter update and prediction
            if run_pose:
                t_kf_now = time.perf_counter()
                for j in triangulated_joint_indices:
                    kf = joint_kfs[j]
                    if j in joints_3d_now:
                        if args.kalman_measured_dt:
                            last_t = joint_kf_last_update_t[j]
                            # Clamp: first update falls back to the nominal step,
                            # long gaps cap at 0.5 s so a re-acquired joint does
                            # not inherit a huge covariance blow-up.
                            dt_meas = (kalman_dt if last_t is None
                                       else min(0.5, max(1e-3, t_kf_now - last_t)))
                            kf.predict_step(dt_meas)
                            joint_kf_last_update_t[j] = t_kf_now
                        else:
                            kf.predict_step()
                        kf.update_step(joints_3d_now[j])
            if use_prediction:
                t_ahead_sec = args.predict_ahead_ms / 1000.0
                for j in range(17):
                    kf = joint_kfs[j]
                    if kf.initialized and np.isfinite(joints_state[j]).all():
                        unc = kf.prediction_uncertainty(t_ahead_sec)
                        if unc < args.predict_max_uncertainty_mm:
                            joints_predicted[j] = kf.predict_ahead(t_ahead_sec).astype(np.float32)
                        else:
                            joints_predicted[j] = np.nan
                    else:
                        joints_predicted[j] = np.nan

            # Display-only interpolation: smooth joints_display toward joints_state
            # every frame, regardless of whether pose ran. Does NOT touch joints_state,
            # UDP, or triangulation — purely visual.
            # Uses adaptive alpha: fast movements (jumps) snap instantly.
            d_alpha_base = args.display_smooth_alpha
            snap_thresh = args.ema_snap_thresh_mm
            use_oneeuro = (args.display_filter == "oneeuro")
            comp_s = max(0.0, float(args.pose_latency_comp_ms)) / 1000.0
            t_disp = time.perf_counter()
            sdt = None if prev_speed_t is None else max(1e-3, t_disp - prev_speed_t)
            for j in range(17):
                src = joints_state[j]
                if comp_s > 0.0 and np.isfinite(src).all():
                    # Display-only: cancel capture+inference+smoothing delay by
                    # rendering the KF's short-horizon prediction. joints_state,
                    # UDP and triangulation are untouched.
                    src = latency_compensated_point(
                        joint_kfs[j], src, comp_s, args.predict_max_uncertainty_mm)
                if not np.isfinite(src).all():
                    joints_display[j] = np.nan
                    oneeuro_filters[j].reset()
                    joint_speeds[j] = 0.0
                    prev_speed_pos[j] = np.nan
                    continue
                # per-joint speed (mm/s) from the smoothed 3D state -> heat colour
                if sdt is not None and np.all(np.isfinite(prev_speed_pos[j])):
                    joint_speeds[j] = float(np.linalg.norm(src - prev_speed_pos[j]) / sdt)
                prev_speed_pos[j] = src.astype(np.float64)
                if use_oneeuro:
                    joints_display[j] = oneeuro_filters[j](src, t_disp).astype(np.float32)
                else:
                    dst = joints_display[j]
                    if not np.isfinite(dst).all():
                        joints_display[j] = src.copy()
                    else:
                        d_alpha = d_alpha_base
                        if snap_thresh > 0:
                            disp = float(np.linalg.norm(src - dst))
                            if disp > snap_thresh:
                                d_alpha = min(1.0, d_alpha_base * (disp / snap_thresh))
                        joints_display[j] = dst + d_alpha * (src - dst)
            prev_speed_t = t_disp
            timer.stop("triang")

            timer.start("coach")
            if args.coach_overlay and coach_counter is not None and coach_frame_kinematics is not None:
                coach_frame = joints_array_to_frame(
                    joints_state, joints_conf_state, joints_cam_state, frame_idx, args.fps
                )
                coach_metrics = coach_frame_kinematics(coach_frame)
                coach_state = coach_counter.update(coach_metrics)
                # On acquisition release (set abandoned), reset the leg-prior
                # accumulator and clear the locked priors so the next athlete /
                # next set re-learns from scratch instead of inheriting a stale
                # length.
                _acquired_now = bool(getattr(coach_state, "acquired", False))
                if (
                    coach_leg_prior_acc is not None
                    and coach_was_acquired
                    and not _acquired_now
                ):
                    coach_leg_prior_acc.reset()
                    coach_leg_priors = None
                    coach_ankle_fallback_streak[15] = 0
                    coach_ankle_fallback_streak[16] = 0
                coach_was_acquired = _acquired_now
            timer.stop("coach")

            timer.start("udp")
            if udp_sock is not None and udp_target_addr is not None and udp_target_joint_pairs:
                joints_payload = {}
                for name, idx in udp_target_joint_pairs:
                    if idx is None and name == "body_center":
                        li, ri = JOINT_NAME_TO_IDX["left_hip"], JOINT_NAME_TO_IDX["right_hip"]
                        lpt, rpt = joints_state[li], joints_state[ri]
                        if not (np.isfinite(lpt).all() and np.isfinite(rpt).all()):
                            continue
                        pt = 0.5 * (lpt + rpt)
                        conf = float(min(joints_conf_state[li], joints_conf_state[ri]))
                        cams = int(min(joints_cam_state[li], joints_cam_state[ri]))
                    else:
                        pt = joints_state[idx]
                        if not np.isfinite(pt).all():
                            continue
                        conf = float(joints_conf_state[idx])
                        cams = int(joints_cam_state[idx])
                    if conf < args.udp_target_conf_min or cams < args.udp_target_cams_min:
                        continue
                    pt_udp = transform_world_point_y(pt, dims["Y"], enabled=udp_world_y_mirror)
                    joints_payload[name] = {
                        "x_mm": float(pt_udp[0]),
                        "y_mm": float(pt_udp[1]),
                        "z_mm": float(pt_udp[2]),
                        "conf": conf,
                        "cams": cams,
                    }
                if joints_payload:
                    pkt = {
                        "type": "joints",
                        "ts": time.time(),
                        "frame": frame_idx,
                        "joints": joints_payload,
                    }
                    # Add predicted positions when prediction is active
                    if use_prediction:
                        pred_payload = {}
                        for name, idx in udp_target_joint_pairs:
                            if idx is None and name == "body_center":
                                li, ri = JOINT_NAME_TO_IDX["left_hip"], JOINT_NAME_TO_IDX["right_hip"]
                                lp, rp = joints_predicted[li], joints_predicted[ri]
                                if np.isfinite(lp).all() and np.isfinite(rp).all():
                                    pp = 0.5 * (lp + rp)
                                    pp_udp = transform_world_point_y(pp, dims["Y"], enabled=udp_world_y_mirror)
                                    pred_payload[name] = {
                                        "x_mm": float(pp_udp[0]),
                                        "y_mm": float(pp_udp[1]),
                                        "z_mm": float(pp_udp[2]),
                                    }
                            elif idx is not None:
                                pp = joints_predicted[idx]
                                if np.isfinite(pp).all():
                                    pp_udp = transform_world_point_y(pp, dims["Y"], enabled=udp_world_y_mirror)
                                    pred_payload[name] = {
                                        "x_mm": float(pp_udp[0]),
                                        "y_mm": float(pp_udp[1]),
                                        "z_mm": float(pp_udp[2]),
                                    }
                        if pred_payload:
                            pkt["predicted"] = pred_payload
                            pkt["predict_ahead_ms"] = args.predict_ahead_ms
                    try:
                        udp_sock.sendto(json.dumps(pkt).encode("utf-8"), udp_target_addr)
                    except Exception:
                        pass
            timer.stop("udp")

            timer.start("viz3d")
            # --- BLM Demo: compute aim from current joints ---
            blm_aim_data = None
            if blm_demo is not None:
                j_idx = blm_demo["joint_idx"]
                j_pos = joints_display[j_idx] if joints_display is not None else None
                if j_pos is not None and np.isfinite(j_pos).all():
                    raw_xyz = j_pos.copy()
                    corrected_xyz = _blm_correct(raw_xyz, blm_demo["correction"],
                                                  blm_demo["correction_mode"])
                    x_lat, y_fwd, dz = _blm_world_to_launcher(
                        corrected_xyz, blm_demo["launcher"], blm_demo["yaw_deg"])
                    d_m = math.sqrt(x_lat**2 + y_fwd**2)
                    sol = _blm_solve(x_lat, y_fwd, dz, blm_demo["v_mps"])
                    if sol is not None:
                        v_deg, h_deg = sol
                        v_clamped = max(0.0, min(30.0, v_deg))
                        h_clamped = max(-30.0, min(30.0, h_deg))
                        blm_aim_data = {
                            "status": "AIM_OK",
                            "joint_name": blm_demo["joint_name"],
                            "pitch_deg": v_clamped,
                            "yaw_deg": h_clamped,
                            "distance_m": d_m,
                            "raw_xyz": raw_xyz,
                            "corrected_xyz": corrected_xyz,
                            "correction_mode": blm_demo["correction_mode"],
                            "launcher_pos": blm_demo["launcher"],
                            "target_pos": corrected_xyz,
                        }
                        # Emit target_chosen on rising-edge transition or joint change.
                        if event_logger is not None and (
                            _prev_aim_status != "AIM_OK"
                            or _prev_aim_joint != blm_demo["joint_name"]
                        ):
                            event_logger.emit(
                                "target_chosen",
                                {
                                    "joint_name": blm_demo["joint_name"],
                                    "frame": frame_idx,
                                    "world_xyz_mm": [
                                        float(corrected_xyz[0]),
                                        float(corrected_xyz[1]),
                                        float(corrected_xyz[2]),
                                    ],
                                    "pitch_deg": v_clamped,
                                    "yaw_deg": h_clamped,
                                    "distance_m": d_m,
                                    "correction_mode": blm_demo["correction_mode"],
                                },
                            )
                        _prev_aim_status = "AIM_OK"
                        _prev_aim_joint = blm_demo["joint_name"]
                    else:
                        blm_aim_data = {
                            "status": "OUT_OF_RANGE",
                            "joint_name": blm_demo["joint_name"],
                            "raw_xyz": raw_xyz,
                            "corrected_xyz": corrected_xyz,
                            "correction_mode": blm_demo["correction_mode"],
                            "launcher_pos": blm_demo["launcher"],
                            "target_pos": corrected_xyz,
                        }
                        _prev_aim_status = "OUT_OF_RANGE"
                else:
                    blm_aim_data = {
                        "status": "NO_TARGET",
                        "joint_name": blm_demo["joint_name"],
                        "launcher_pos": blm_demo["launcher"],
                    }
                    _prev_aim_status = "NO_TARGET"

            # update cinematic motion trails (wrists/ankles)
            for _tj in TRAIL_JOINTS:
                _p = joints_display[_tj]
                if np.all(np.isfinite(_p)):
                    joint_trails[_tj].append(np.array(_p, copy=True))

            # --- live squat / push-up rep counters (independent of coach window) ---
            if rep_counters and rep_frame_kinematics is not None:
                rk_frame = joints_array_to_frame(
                    joints_state, joints_conf_state, joints_cam_state, frame_idx, args.fps)
                rk_metrics = rep_frame_kinematics(rk_frame)
                for _ex, _ctr in rep_counters.items():
                    try:
                        _st = _ctr.update(rk_metrics)
                        rep_count_state[_ex] = int(getattr(_st, "rep_count", 0))
                    except Exception:
                        pass

            # --- live leg-raise metrics + diagnostics ---
            if leg_raise_tracker is not None:
                _lr_frame = joints_array_to_frame(
                    joints_state, joints_conf_state, joints_cam_state, frame_idx, args.fps)
                leg_raise_state = leg_raise_tracker.process(_lr_frame)
                if leg_raise_contact_interpreter is not None:
                    leg_raise_contact_for_log = (
                        leg_raise_contact_interpreter.process(_lr_frame).to_dict()
                    )
                if leg_raise_log_fh is not None:
                    _identity_payload = None
                    if leg_raise_identity_result is not None:
                        _identity_payload = {
                            "swapped": bool(leg_raise_identity_result.swapped),
                            "status": leg_raise_identity_result.status,
                            "keep_cost": leg_raise_identity_result.keep_cost,
                            "swap_cost": leg_raise_identity_result.swap_cost,
                        }
                    _leg_indices = (11, 12, 13, 14, 15, 16)
                    _priors_payload = None
                    if leg_raise_priors is not None:
                        _priors_payload = {
                            "femur_l_mm": float(leg_raise_priors.femur_l_mm),
                            "femur_r_mm": float(leg_raise_priors.femur_r_mm),
                            "tibia_l_mm": float(leg_raise_priors.tibia_l_mm),
                            "tibia_r_mm": float(leg_raise_priors.tibia_r_mm),
                            "sample_count": int(leg_raise_priors.sample_count),
                            "locked_at_frame": int(leg_raise_priors.locked_at_frame),
                        }
                    leg_raise_log_fh.write(json.dumps({
                        "ts": time.time(),
                        "frame": int(frame_idx),
                        "identity": _identity_payload,
                        "prior_status": leg_raise_prior_status_for_log,
                        "priors": _priors_payload,
                        "dropped_joints": leg_raise_dropped_joints_for_log,
                        "raw_lower_body_3d": leg_raise_raw_joints_for_log,
                        "raw_segment_lengths_mm": leg_raise_raw_lengths_for_log,
                        "identity_lower_body_3d": leg_raise_identity_joints_for_log,
                        "identity_segment_lengths_mm": leg_raise_identity_lengths_for_log,
                        "pose2d_lower_body": leg_raise_pose2d_for_log,
                        "state": leg_raise_state.to_dict(),
                        "contact": leg_raise_contact_for_log,
                        "joint_conf": {str(i): float(joints_conf_state[i]) for i in _leg_indices},
                        "joint_cams": {str(i): int(joints_cam_state[i]) for i in _leg_indices},
                    }, ensure_ascii=True) + "\n")
                    leg_raise_log_fh.flush()

            # --- live athlete metrics (height / arm-span reach / peak joint speed) ---
            metrics_hud = None
            if args.metrics_hud:
                fin = np.isfinite(joints_display).all(axis=1)
                metrics_hud = {}
                if fin.any():
                    zs = joints_display[fin, 2]
                    metrics_hud["height_cm"] = float((zs.max() - zs.min()) / 10.0)
                if fin[9] and fin[10]:
                    metrics_hud["reach_cm"] = float(
                        np.linalg.norm(joints_display[9] - joints_display[10]) / 10.0)
                metrics_hud["max_speed_ms"] = float(np.nanmax(joint_speeds) / 1000.0)
                if rep_counters:
                    metrics_hud["reps"] = dict(rep_count_state)
                if leg_raise_state is not None:
                    metrics_hud["leg_raise"] = {
                        "left_angle_deg": leg_raise_state.left.angle_deg,
                        "right_angle_deg": leg_raise_state.right.angle_deg,
                        "left_reps": leg_raise_state.left.reps,
                        "right_reps": leg_raise_state.right.reps,
                        "identity_status": leg_raise_state.identity_status,
                        "swapped": leg_raise_state.swapped,
                    }

            if smpl_fitter is not None and frame_idx % max(1, int(args.smpl_fit_every)) == 0:
                if smpl_async_active:
                    # Non-blocking: replaces any pending snapshot; the worker
                    # thread fits at its own pace and skips stale frames.
                    smpl_fitter.submit(joints_display, joints_conf_state)
                else:
                    try:
                        smpl_fit_result = smpl_fitter.fit(
                            joints_display,
                            joints_conf_state,
                        )
                        if smpl_pelvis_fn is not None:
                            smpl_fit_pelvis = smpl_pelvis_fn(joints_display)
                    except ValueError:
                        # Not enough reliable joints this frame; keep the last mesh.
                        pass
                    except Exception as exc:
                        print(f"[WARN] SMPL mesh fit failed; disabling SMPL avatar: {exc}")
                        smpl_fitter = None
            if smpl_fitter is not None and smpl_async_active:
                smpl_err = smpl_fitter.error
                if smpl_err is not None:
                    print(f"[WARN] SMPL mesh fit failed; disabling SMPL avatar: {smpl_err}")
                    smpl_fitter.close()
                    smpl_fitter = None
                else:
                    smpl_snap = smpl_fitter.latest()
                    if smpl_snap is not None:
                        smpl_fit_result = smpl_snap.result
                        smpl_fit_pelvis = smpl_snap.pelvis_mm
            # Anchor-follow: between (slow) fits, glue the last mesh to the
            # current mid-hip so the avatar moves at full frame rate.
            smpl_render_vertices = None
            if smpl_fit_result is not None:
                smpl_render_vertices = smpl_fit_result.vertices_mm
                if (args.smpl_anchor_follow and smpl_fit_pelvis is not None
                        and smpl_pelvis_fn is not None):
                    cur_pelvis = smpl_pelvis_fn(joints_display)
                    if cur_pelvis is not None:
                        delta = np.asarray(cur_pelvis) - np.asarray(smpl_fit_pelvis)
                        if np.isfinite(delta).all():
                            smpl_render_vertices = smpl_fit_result.vertices_mm + delta.reshape(1, 3)

            if args.show_3d and (frame_idx % args.viz_every == 0):
                orbit_azim = (args.view_azim + (time.time() - t_start) * args.auto_orbit_speed
                              if args.auto_orbit else args.view_azim)
                if use_cv2_viz:
                    thumbs = ([(c, cam_frames[c]) for c in batch_order if c in cam_frames]
                              if args.show_thumbnails else None)
                    viz_img = draw_live_scene_cv2(
                        img_w=args.viz_width,
                        img_h=args.viz_height,
                        dims=dims,
                        tags=tags,
                        extr=extr,
                        ball_pt=ball_state,
                        ball_traj=list(ball_traj),
                        joints=joints_display.copy(),
                        frame_idx=frame_idx,
                        fps_est=fps_est,
                        world_y_mirror=display_world_y_mirror,
                        view_elev=args.view_elev,
                        view_azim=orbit_azim,
                        draw_axes=args.draw_global_axes,
                        axis_len=args.global_axis_len_mm,
                        ghost_joints=joints_predicted.copy() if show_ghost else None,
                        predict_ahead_ms=args.predict_ahead_ms,
                        blm_aim=blm_aim_data,
                        theme=args.render_theme,
                        trails=({j: list(joint_trails[j]) for j in TRAIL_JOINTS}
                                if args.render_theme == "cinematic" else None),
                        cams_tracking=len(batch_order),
                        joint_speeds=joint_speeds,
                        limb_heat=args.limb_heat,
                        heat_vmax=args.heat_vmax_mm_s,
                        metrics=metrics_hud,
                        thumbnails=thumbs,
                        recording=(rec_writer is not None),
                        avatar_body=args.avatar_body,
                        avatar_markers=args.avatar_markers,
                        avatar_alpha=args.avatar_alpha,
                        smpl_mesh_vertices=smpl_render_vertices,
                        smpl_mesh_faces=(
                            smpl_fit_result.faces
                            if smpl_fit_result is not None else None
                        ),
                        smpl_mesh_alpha=args.smpl_mesh_alpha,
                        smpl_mesh_max_faces=args.smpl_mesh_max_faces,
                    )
                    cv2.imshow("Live 3D Arena", viz_img)
                    if video_writer_3d is not None:
                        video_writer_3d.write(viz_img)
                    if rec_writer is not None:
                        rec_writer.write(viz_img)
                elif render_q is not None and render_proc is not None:
                    if not render_proc.is_alive():
                        print("[WARN] Render worker stopped unexpectedly; disabling 3D updates.")
                        args.show_3d = False
                    else:
                        put_latest_snapshot(
                            render_q,
                            {
                                "ball_pt": (None if ball_state is None else np.array(ball_state, copy=True)),
                                "ball_traj": np.array(ball_traj, dtype=np.float32),
                                "joints": np.array(joints_display, copy=True),
                                "frame_idx": frame_idx,
                                "fps_est": fps_est,
                            },
                        )
                else:
                    draw_live_scene(
                        ax=ax,
                        dims=dims,
                        tags=tags,
                        extr=extr,
                        ball_pt=ball_state,
                        ball_traj=list(ball_traj),
                        joints=joints_display.copy(),
                        frame_idx=frame_idx,
                        fps_est=fps_est,
                        world_y_mirror=display_world_y_mirror,
                        invert_y_axis_display=args.invert_y_axis_display,
                        draw_global_axes_flag=args.draw_global_axes,
                        global_axis_len_mm=args.global_axis_len_mm,
                        view_elev=args.view_elev,
                        view_azim=args.view_azim,
                    )
                    plt.pause(0.001)
                    if fig is not None and not plt.fignum_exists(fig.number):
                        break
            timer.stop("viz3d")

            if args.coach_overlay and coach_state is not None:
                camera_positions = {cam: extr[cam]["pos"] for cam, _ in active_cams if cam in extr}
                # Lock the camera while a push-up set is active: switching
                # mid-rep makes the overlay skeleton visually jump. The lock is
                # sticky -- it holds for a short grace window after acquisition
                # is lost, so a brief posture-gate flicker cannot trigger a
                # switch. Re-select freely once the grace window expires
                # (genuinely between sets, standing, walking).
                if args.coach_exercise == "push_up" and getattr(coach_state, "acquired", False):
                    coach_lock_hold = COACH_CAMERA_LOCK_HOLD_FRAMES
                elif coach_lock_hold > 0:
                    coach_lock_hold -= 1
                lock_camera = (
                    args.coach_exercise == "push_up"
                    and coach_lock_hold > 0
                    and coach_prev_camera is not None
                    and coach_prev_camera in cam_frames
                )
                if lock_camera:
                    selected_cam = coach_prev_camera
                else:
                    selected_cam = coach_select_best_camera(
                        args.coach_exercise,
                        joints_state,
                        per_cam_pose,
                        camera_positions,
                        previous_camera=coach_prev_camera,
                    )
                if selected_cam is None and active_cams:
                    selected_cam = active_cams[0][0]
                if selected_cam is not None and selected_cam in cam_frames:
                    coach_prev_camera = selected_cam
                    src_frame = cam_frames[selected_cam]
                    pose = per_cam_pose.get(selected_cam)
                    if pose is None:
                        pose_kpts = np.full((17, 2), np.nan, dtype=np.float32)
                        pose_scores = np.zeros((17,), dtype=np.float32)
                    else:
                        pose_kpts, pose_scores = pose
                    if selected_cam not in coach_rois:
                        coach_rois[selected_cam] = coach_roi_cls(
                            width=min(int(args.width), 960),
                            height=min(int(args.height), 640),
                            alpha=0.20,
                        )
                    roi = coach_rois[selected_cam].update(src_frame.shape, pose_kpts, pose_scores)
                    crop, crop_kpts, _scale = coach_crop_frame_to_roi(
                        src_frame, pose_kpts, roi, output_size=coach_output_size
                    )
                    projected_kpts, projected_scores = project_joints_to_overlay(
                        joints_state,
                        joints_conf_state,
                        joints_cam_state,
                        selected_cam,
                        extr,
                        intr,
                        roi,
                        coach_output_size,
                    )
                    overlay_kpts, overlay_scores = coach_repair_overlay_keypoints(
                        args.coach_exercise,
                        crop_kpts,
                        pose_scores,
                        projected_kpts,
                        projected_scores,
                    )
                    # Temporal smoothing + coast-through-dropout: stops the
                    # repaired legs from jittering between sources or vanishing
                    # when push-up camera coverage flickers.
                    overlay_kpts, overlay_scores = coach_keypoint_stabilizer.update(
                        overlay_kpts, overlay_scores
                    )
                    zone_poly = project_zone_to_overlay(
                        coach_zone_mm, selected_cam, extr, intr, roi, coach_output_size
                    )
                    coach_canvas = coach_render_overlay(
                        crop,
                        args.coach_exercise,
                        coach_state,
                        coach_metrics,
                        overlay_kpts,
                        overlay_scores,
                        projected_floor=zone_poly,
                        pushup_floor_anchor=coach_pushup_floor_anchor,
                    )
                    cv2.putText(
                        coach_canvas,
                        selected_cam,
                        (22, coach_canvas.shape[0] - 18),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.56,
                        (210, 210, 210),
                        1,
                        cv2.LINE_AA,
                    )
                    cv2.imshow(coach_window, coach_canvas)

            timer.start("mosaic")
            if args.show_2d and (frame_idx % args.mosaic_every == 0):
                mosaic = make_mosaic(
                    cam_frames,
                    ball_boxes,
                    per_cam_pose,
                    cam_order=cam_order,
                    tile_size=(args.mosaic_tile_width, args.mosaic_tile_height),
                    copy_frames=False,
                )
                cv2.putText(
                    mosaic,
                    f"FPS: {fps_est:.2f}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 255),
                    2,
                )
                cv2.imshow("Live 4Cam 2D (q to quit)", mosaic)
                if args.record_mosaic:
                    if video_writer_mosaic is None:
                        h, w = mosaic.shape[:2]
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        video_writer_mosaic = cv2.VideoWriter(args.record_mosaic, fourcc, args.record_fps, (w, h))
                        print(f"[REC] 2D mosaic recording → {args.record_mosaic} @ {args.record_fps} fps ({w}x{h})")
                    video_writer_mosaic.write(mosaic)
            timer.stop("mosaic")

            # Unified cv2 event pump (handles both 3D and 2D windows)
            if args.coach_overlay or args.show_2d or (args.show_3d and use_cv2_viz):
                _key = cv2.waitKey(1) & 0xFF
                if _key == ord("q"):
                    break
                # Closing the window with the mouse (X button) also stops cleanly.
                if use_cv2_viz and args.show_3d:
                    try:
                        if cv2.getWindowProperty("Live 3D Arena", cv2.WND_PROP_VISIBLE) < 1:
                            break
                    except cv2.error:
                        break
                if _key == ord("c") and rep_counters:
                    for _ex in list(rep_counters.keys()):
                        rep_counters[_ex] = rep_make_fn(_ex, rep_rules_map[_ex])
                        rep_count_state[_ex] = 0
                    print("[reps] counters reset")
                if _key == ord("r") and use_cv2_viz:
                    if rec_writer is None:
                        os.makedirs(args.record_dir, exist_ok=True)
                        rec_path = os.path.join(
                            args.record_dir,
                            f"arena_demo_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
                        rec_writer = cv2.VideoWriter(
                            rec_path, cv2.VideoWriter_fourcc(*"mp4v"),
                            max(5.0, float(fps_est)),
                            (int(args.viz_width), int(args.viz_height)))
                        print(f"[REC] started -> {rec_path}")
                    else:
                        rec_writer.release()
                        print(f"[REC] saved -> {rec_path}")
                        rec_writer = None
                if args.coach_overlay:
                    try:
                        if cv2.getWindowProperty(coach_window, cv2.WND_PROP_VISIBLE) < 1:
                            break
                    except cv2.error:
                        pass
                # Operator scoring for closed-loop demo (only meaningful when event log is on).
                if event_logger is not None and _key != 255:
                    if _key == ord("r"):
                        event_logger.emit(
                            "athlete_reacted",
                            {
                                "frame": frame_idx,
                                "operator_verdict": "reacted",
                                "joint_name": _prev_aim_joint,
                            },
                        )
                        print("[EVENT] athlete_reacted recorded")
                    elif _key == ord("n"):
                        event_logger.emit(
                            "outcome_scored",
                            {
                                "frame": frame_idx,
                                "operator_verdict": "no_reaction",
                                "joint_name": _prev_aim_joint,
                            },
                        )
                        print("[EVENT] no_reaction recorded")

            end_to_end_ms = timer.stop("total")
            report = timer.report(frame_idx, args.perf_log_every)
            if report is not None:
                line, payload = report
                try:
                    queue_depth = render_q.qsize() if render_q is not None else 0
                except Exception:
                    queue_depth = -1
                max_age = max(frame_age_ms_per_cam.values()) if frame_age_ms_per_cam else 0.0
                usable_cam_count = len(batch_order)
                stale_cam_count = len(stale_frames_per_cam)
                line += (
                    f" | end_to_end={end_to_end_ms:.1f} | q={queue_depth} | max_age={max_age:.1f}"
                    f" | usable={usable_cam_count} | stale={stale_cam_count}"
                )
                payload["ts"] = time.time()
                payload["end_to_end_ms"] = float(end_to_end_ms)
                payload["frame_age_ms_per_cam"] = frame_age_ms_per_cam
                payload["dropped_frames_per_cam"] = dropped_frames_per_cam
                payload["stale_frames_per_cam"] = stale_frames_per_cam
                payload["usable_cam_count"] = int(usable_cam_count)
                payload["stale_cam_count"] = int(stale_cam_count)
                payload["queue_depth"] = int(queue_depth)
                pose_health = pose_health_payload(
                    run_pose=run_pose,
                    pose_error=pose_error,
                    batch_order=batch_order,
                    pose_raw_counts=pose_raw_counts,
                    per_cam_pose_curr=per_cam_pose_curr,
                    pose_und_by_cam=pose_und_by_cam,
                    joints_3d_now=joints_3d_now,
                    joints_display=joints_display,
                )
                payload.update(pose_health)
                line += (
                    f" | pose_raw={pose_health['pose_raw_person_count']}"
                    f" | pose_cams={pose_health['pose_selected_cam_count']}"
                    f" | joints={pose_health['pose_triangulated_joint_count']}"
                    f" | visible={pose_health['pose_visible_joint_count']}"
                )
                if pose_error:
                    line += f" | pose_error={pose_error}"
                if perf_fh is not None:
                    perf_fh.write(json.dumps(payload, ensure_ascii=True) + "\n")
                    perf_fh.flush()
                print(line)

    finally:
        if rec_writer is not None:
            rec_writer.release()
            print(f"[REC] saved -> {rec_path}")
        if video_writer_3d is not None:
            video_writer_3d.release()
            print(f"[REC] Saved 3D video: {args.record_video}")
        if video_writer_mosaic is not None:
            video_writer_mosaic.release()
            print(f"[REC] Saved 2D mosaic: {args.record_mosaic}")
        for cap in caps.values():
            cap.release()
        if smpl_fitter is not None and smpl_async_active:
            smpl_fitter.close()
        if ball_executor is not None:
            ball_executor.shutdown(wait=False, cancel_futures=True)
        if udp_sock is not None:
            udp_sock.close()
        if event_logger is not None:
            try:
                event_logger.emit("session_end", {"session_id": session_id})
                event_logger.close()
            except Exception:
                pass
        if render_q is not None:
            put_latest_snapshot(render_q, None)
        if render_proc is not None:
            render_proc.join(timeout=2.0)
            if render_proc.is_alive():
                render_proc.terminate()
        if perf_fh is not None:
            perf_fh.close()
        if ball_log_fh is not None:
            ball_log_fh.close()
        if leg_raise_log_fh is not None:
            leg_raise_log_fh.close()
        cv2.destroyAllWindows()
        plt.close("all")
        print("[DONE] Live viewer stopped.")


if __name__ == "__main__":
    main()
