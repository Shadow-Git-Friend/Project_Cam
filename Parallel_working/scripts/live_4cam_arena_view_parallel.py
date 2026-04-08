import argparse
import json
import multiprocessing as mp
import re
import socket
import threading
import time
from collections import deque
from queue import Full
from pathlib import Path

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

CAM_ORDER = ["camEast", "camNorth", "camSouth", "camWest"]

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
        order = ["capture", "ball", "pose", "triang", "udp", "viz3d", "mosaic", "total"]
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
        with self.lock:
            if self.frame is None:
                return False, None, 0.0
            fr = self.frame
            ts = self.ts
            self._has_unconsumed = False
        return True, fr, ts

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
):
    """Render the 3D arena scene onto a cv2 BGR image (~1-3 ms)."""
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
    # floor fill
    if np.all(ok[:4]):
        cv2.fillPoly(img, [sc[:4].astype(np.int32)], (235, 230, 225))
    arena_edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    for a, b in arena_edges:
        if ok[a] and ok[b]:
            line(sc[a], sc[b], (160, 160, 160), 1)

    # --- AprilTag planes ---
    for tag_id, pts in tags.items():
        pts_v = transform_world_point_y(pts, y_max, enabled=world_y_mirror)
        sp, sok = proj(pts_v)
        if np.all(sok):
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
            col = cam_colors_bgr.get(name, (0, 0, 0))
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

    # --- skeleton ---
    if joints is not None:
        jv = transform_world_point_y(np.asarray(joints, dtype=np.float64), y_max, enabled=world_y_mirror)
        sp, sok = proj(jv)
        for s, e in CONNECTIONS:
            if s < len(sok) and e < len(sok) and sok[s] and sok[e]:
                line(sp[s], sp[e], (30, 30, 30), 2)
        for j in range(min(17, len(sok))):
            if sok[j]:
                cv2.circle(img, (int(sp[j,0]), int(sp[j,1])), 4, (50, 50, 50), -1, cv2.LINE_AA)

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

    # --- HUD ---
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

    def update_step(self, z):
        """Update with measurement z = [x, y, z] in mm."""
        z = np.asarray(z, dtype=np.float64)
        if not self._initialized:
            self.x[:3] = z
            self.x[3:] = 0.0
            self.P = np.eye(6, dtype=np.float64) * 1e4
            self._initialized = True
            return
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
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


def make_mosaic(cam_frames, ball_boxes, per_cam_pose, copy_frames=False):
    panels = []
    ref_shape = None
    for fr in cam_frames.values():
        if fr is not None:
            ref_shape = fr.shape
            break
    if ref_shape is None:
        ref_shape = (720, 1280, 3)
    for cam in CAM_ORDER:
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

        cv2.putText(disp, cam, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        panels.append(disp)

    row1 = np.hstack([panels[0], panels[1]])
    row2 = np.hstack([panels[2], panels[3]])
    return np.vstack([row1, row2])


def main():
    ap = argparse.ArgumentParser(description="Live 4-camera ball + pose triangulation in garage 3D arena.")
    ap.add_argument(
        "--high-performance",
        action="store_true",
        help="Enable FPS-optimized defaults (no 3D window, reduced heavy-step frequency).",
    )
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--extrinsics", default="garage_lab_combined/cal/extrinsics/extrinsics_main.json")
    ap.add_argument("--dimensions", default="garage_lab_combined/cal/extrinsics/Dimensions.txt")
    ap.add_argument("--ball-model", default="garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt")
    ap.add_argument("--ball-device", default="cpu", help="Ball detector device, e.g. cpu or cuda:0")
    ap.add_argument("--pose-device", default="cpu", help="Pose detector device, e.g. cpu or cuda:0")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--buffer-size", type=int, default=1)
    ap.add_argument("--ball-conf", type=float, default=0.4)
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
    ap.add_argument("--pose-conf", type=float, default=0.45)
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
    ap.add_argument(
        "--viz-backend",
        choices=["cv2", "matplotlib"],
        default="cv2",
        help="3D visualization backend. cv2 is ~100x faster (1-3ms vs 200-500ms). Default: cv2.",
    )
    ap.add_argument("--viz-width", type=int, default=960, help="Width of cv2 3D view window.")
    ap.add_argument("--viz-height", type=int, default=720, help="Height of cv2 3D view window.")
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
    args.viz_every = max(1, int(args.viz_every))
    args.mosaic_every = max(1, int(args.mosaic_every))
    if args.joint_stale_frames is None:
        args.joint_stale_frames = max(3, args.pose_every * 3)
    else:
        args.joint_stale_frames = max(1, int(args.joint_stale_frames))

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

    udp_joint_indices_needed = set()
    for name, idx in udp_target_joint_pairs:
        if idx is None and name == "body_center":
            udp_joint_indices_needed.add(JOINT_NAME_TO_IDX["left_hip"])
            udp_joint_indices_needed.add(JOINT_NAME_TO_IDX["right_hip"])
        elif idx is not None:
            udp_joint_indices_needed.add(idx)
    triangulated_joint_indices = list(range(17)) if args.show_3d else sorted(udp_joint_indices_needed)

    ball_needed = args.track_ball and (args.show_3d or args.show_2d)
    pose_needed = args.show_2d or bool(triangulated_joint_indices)
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
    active_cams = []
    for cam in CAM_ORDER:
        dev = cams_cfg.get(cam, {}).get("device")
        if dev is not None:
            active_cams.append((cam, dev))
    if len(active_cams) < 2:
        raise RuntimeError("Need at least 2 cameras in config.")

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

    ball_model = None
    if ball_needed:
        from ultralytics import YOLO

        ball_model = YOLO(args.ball_model)
    else:
        print("[INFO] Ball detector disabled (no active visualization output).")
    print(f"[INFO] Ball device: {args.ball_device} | Pose device: {args.pose_device}")

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
    for cam, dev in active_cams:
        cap = cv2.VideoCapture(dev)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
        cap.set(cv2.CAP_PROP_FPS, args.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, args.buffer_size)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open {cam}: {dev}")
        caps[cam] = ThreadedCapture(cap, name=cam)
        print(f"[OK] {cam}: {dev}")

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
    pose_select_conf = max(0.2, args.pose_conf - 0.10)
    ball_boxes_state = {}
    ball_state = None
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    joints_display = np.full((17, 3), np.nan, dtype=np.float32)
    joints_predicted = np.full((17, 3), np.nan, dtype=np.float32)
    joints_conf_state = np.zeros((17,), dtype=np.float32)
    joints_cam_state = np.zeros((17,), dtype=np.int32)
    joint_last_seen_frame = np.full((17,), -10_000_000, dtype=np.int64)
    ball_traj = deque(maxlen=args.trail_len)

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

    frame_idx = 0
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

    stop_hints = []
    if args.show_2d:
        stop_hints.append("press q in 2D window")
    if args.show_3d:
        stop_hints.append("close 3D window")
    if stop_hints:
        print(f"[INFO] Live loop started. { ' or '.join(stop_hints) } to stop.")
    else:
        print("[INFO] Live loop started. Press Ctrl+C to stop.")
    try:
        while True:
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
            for cam, _ in active_cams:
                ret, frame, ts = caps[cam].read_latest()
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
                cam_frames[cam] = frame
                frame_batch.append(frame)
                batch_order.append(cam)
            timer.stop("capture")

            if len(frame_batch) < 2:
                timer.stop("total")
                continue

            frame_idx += 1
            t_now = time.time()
            dt = max(1e-6, t_now - t_prev)
            t_prev = t_now
            fps_est = 0.92 * fps_est + 0.08 * (1.0 / dt)

            ball_boxes = ball_boxes_state.copy()
            ball_obs = {}
            run_ball = ball_model is not None and (frame_idx % args.ball_every == 0)
            timer.start("ball")
            if run_ball:
                ball_boxes = {}
                ball_results = ball_model(
                    frame_batch,
                    conf=args.ball_conf,
                    verbose=False,
                    stream=False,
                    device=args.ball_device,
                )
                for cam, res in zip(batch_order, ball_results):
                    if res.boxes is None or len(res.boxes) == 0:
                        continue
                    best = int(res.boxes.conf.argmax().item())
                    box = res.boxes[best]
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(np.int32)
                    conf = float(box.conf[0].item())
                    cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
                    und = undistort_points((cx, cy), intr[cam]["K"], intr[cam]["D"])
                    ball_obs[cam] = und
                    ball_boxes[cam] = (int(x1), int(y1), int(x2), int(y2), conf)
                ball_boxes_state = ball_boxes
            timer.stop("ball")

            per_cam_pose = per_cam_pose_state.copy()
            joints_3d_now = {}
            pose_every_eff = args.pose_every if pose_lock_active else pose_reacquire_every
            run_pose = (pose_infer is not None or yolopose_model is not None) and (frame_idx % pose_every_eff == 0)
            per_cam_pose_curr = {}
            pose_und_by_cam = {}
            timer.start("pose")
            if run_pose and use_yolopose and yolopose_model is not None:
                # YOLO-Pose path: single model for detection + keypoints
                try:
                    yp_results = yolopose_model(
                        frame_batch, device=args.pose_device, verbose=False,
                        conf=0.15,
                    )
                except Exception:
                    yp_results = []
                for cam, yp_res in zip(batch_order, yp_results):
                    if not hasattr(yp_res, "keypoints") or yp_res.keypoints is None:
                        pose_state[cam] = None
                        per_cam_pose_state.pop(cam, None)
                        continue
                    kpts_all = yp_res.keypoints.data.cpu().numpy()  # (N, 17, 3) — x, y, conf
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
                except Exception:
                    res_list = []

                for cam, res in zip(batch_order, res_list):
                    preds = res.get("predictions", []) if isinstance(res, dict) else []
                    persons = flatten_predictions(preds)
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

            timer.start("triang")
            ball_3d = triangulate_multi(ball_obs, proj) if len(ball_obs) >= 2 else None
            ball_state = ema_update(ball_state, ball_3d, alpha=args.ema_alpha)
            if args.show_3d and ball_state is not None and np.isfinite(ball_state).all():
                ball_traj.append(ball_state.copy())

            if run_pose:
                for j in triangulated_joint_indices:
                    obs = {}
                    obs_scores = []
                    for cam in batch_order:
                        und_map = pose_und_by_cam.get(cam)
                        if not und_map or j not in und_map:
                            continue
                        obs[cam] = und_map[j]
                        obs_scores.append(float(per_cam_pose_curr[cam][1][j]))
                    if len(obs) >= 2:
                        pt = triangulate_multi(obs, proj)
                        if pt is not None:
                            joints_3d_now[j] = pt
                            joint_last_seen_frame[j] = frame_idx
                            joints_conf_state[j] = float(np.mean(obs_scores)) if obs_scores else 0.0
                            joints_cam_state[j] = int(len(obs))
                        else:
                            joints_cam_state[j] = 0
                            joints_conf_state[j] = 0.0
                    else:
                        joints_cam_state[j] = 0
                        joints_conf_state[j] = 0.0

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
                for j in triangulated_joint_indices:
                    kf = joint_kfs[j]
                    if j in joints_3d_now:
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
            for j in range(17):
                src = joints_state[j]
                if not np.isfinite(src).all():
                    joints_display[j] = np.nan
                    continue
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
            timer.stop("triang")

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
            if args.show_3d and (frame_idx % args.viz_every == 0):
                if use_cv2_viz:
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
                        view_azim=args.view_azim,
                        draw_axes=args.draw_global_axes,
                        axis_len=args.global_axis_len_mm,
                        ghost_joints=joints_predicted.copy() if show_ghost else None,
                        predict_ahead_ms=args.predict_ahead_ms,
                    )
                    cv2.imshow("Live 3D Arena", viz_img)
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

            timer.start("mosaic")
            if args.show_2d and (frame_idx % args.mosaic_every == 0):
                mosaic = make_mosaic(cam_frames, ball_boxes, per_cam_pose, copy_frames=False)
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
            timer.stop("mosaic")

            # Unified cv2 event pump (handles both 3D and 2D windows)
            if args.show_2d or (args.show_3d and use_cv2_viz):
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

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
                print(line)
                payload["ts"] = time.time()
                payload["end_to_end_ms"] = float(end_to_end_ms)
                payload["frame_age_ms_per_cam"] = frame_age_ms_per_cam
                payload["dropped_frames_per_cam"] = dropped_frames_per_cam
                payload["stale_frames_per_cam"] = stale_frames_per_cam
                payload["usable_cam_count"] = int(usable_cam_count)
                payload["stale_cam_count"] = int(stale_cam_count)
                payload["queue_depth"] = int(queue_depth)
                if perf_fh is not None:
                    perf_fh.write(json.dumps(payload, ensure_ascii=True) + "\n")
                    perf_fh.flush()

    finally:
        for cap in caps.values():
            cap.release()
        if udp_sock is not None:
            udp_sock.close()
        if render_q is not None:
            put_latest_snapshot(render_q, None)
        if render_proc is not None:
            render_proc.join(timeout=2.0)
            if render_proc.is_alive():
                render_proc.terminate()
        if perf_fh is not None:
            perf_fh.close()
        cv2.destroyAllWindows()
        plt.close("all")
        print("[DONE] Live viewer stopped.")


if __name__ == "__main__":
    main()
