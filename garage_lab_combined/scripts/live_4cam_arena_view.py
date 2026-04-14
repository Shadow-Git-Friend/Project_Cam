import argparse
import json
import re
import socket
import time
from collections import deque
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
    return k, d


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


def ema_update(prev, new, alpha):
    if new is None:
        return prev
    if prev is None:
        return np.array(new, dtype=np.float32)
    return (1.0 - alpha) * prev + alpha * np.array(new, dtype=np.float32)


def make_mosaic(cam_frames, ball_boxes, per_cam_pose):
    panels = []
    for cam in CAM_ORDER:
        frame = cam_frames.get(cam)
        if frame is None:
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        disp = frame.copy()
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
    ap.add_argument("--ball-model", default="models/ball/yolo26m-672.engine")
    ap.add_argument("--ball-device", default="cuda:0", help="Ball detector device, e.g. cpu or cuda:0")
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
    ap.add_argument("--max-runtime-sec", type=float, default=0.0, help="0 = infinite")
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
        k, d = load_intrinsics(Path(args.intrinsics_dir) / f"{cam}_intrinsics.json")
        intr[cam] = {"K": k, "D": d}
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
    if args.pose and pose_needed:
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
        caps[cam] = cap
        print(f"[OK] {cam}: {dev}")

    fig = None
    ax = None
    if args.show_3d:
        plt.ion()
        fig = plt.figure(figsize=(12.0, 9.0), facecolor="#f7f7f7")
        ax = fig.add_subplot(111, projection="3d")

    pose_state = {cam: None for cam, _ in active_cams}
    per_cam_pose_state = {}
    pose_lock_active = False
    pose_reacquire_every = max(1, min(args.pose_every, 2))
    pose_select_conf = max(0.2, args.pose_conf - 0.10)
    ball_boxes_state = {}
    ball_state = None
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    joints_conf_state = np.zeros((17,), dtype=np.float32)
    joints_cam_state = np.zeros((17,), dtype=np.int32)
    joint_last_seen_frame = np.full((17,), -10_000_000, dtype=np.int64)
    ball_traj = deque(maxlen=args.trail_len)

    frame_idx = 0
    t_start = time.time()
    t_prev = t_start
    fps_est = 0.0

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
            if args.max_runtime_sec > 0 and (time.time() - t_start) > args.max_runtime_sec:
                break

            cam_frames = {}
            frame_batch = []
            batch_order = []
            for cam, _ in active_cams:
                ret, frame = caps[cam].read()
                if not ret or frame is None:
                    continue
                cam_frames[cam] = frame
                frame_batch.append(frame)
                batch_order.append(cam)

            if len(frame_batch) < 2:
                continue

            frame_idx += 1
            t_now = time.time()
            dt = max(1e-6, t_now - t_prev)
            t_prev = t_now
            fps_est = 0.92 * fps_est + 0.08 * (1.0 / dt)

            ball_boxes = ball_boxes_state.copy()
            ball_obs = {}
            run_ball = ball_model is not None and (frame_idx % args.ball_every == 0)
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

            ball_3d = triangulate_multi(ball_obs, proj) if len(ball_obs) >= 2 else None
            ball_state = ema_update(ball_state, ball_3d, alpha=args.ema_alpha)
            if args.show_3d and ball_state is not None and np.isfinite(ball_state).all():
                ball_traj.append(ball_state.copy())

            per_cam_pose = per_cam_pose_state.copy()
            joints_3d_now = {}
            pose_every_eff = args.pose_every if pose_lock_active else pose_reacquire_every
            run_pose = pose_infer is not None and (frame_idx % pose_every_eff == 0)
            if run_pose:
                try:
                    res_list = list(pose_infer(frame_batch, return_vis=False, batch_size=len(frame_batch)))
                except Exception:
                    res_list = []

                per_cam_pose_curr = {}
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

                per_cam_pose = per_cam_pose_state.copy()
                has_pose_lock = len(per_cam_pose_curr) >= 2
                force_pose_snap = has_pose_lock and not pose_lock_active
                pose_lock_active = has_pose_lock

                for j in triangulated_joint_indices:
                    obs = {}
                    obs_scores = []
                    for cam in batch_order:
                        kdat = per_cam_pose_curr.get(cam)
                        if kdat is None:
                            continue
                        kpts, scores = kdat
                        if scores[j] < args.pose_conf:
                            continue
                        x, y = kpts[j]
                        und = undistort_points((x, y), intr[cam]["K"], intr[cam]["D"])
                        obs[cam] = und
                        obs_scores.append(float(scores[j]))
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
                    joints_state[j] = ema_update(prev, pt, alpha=args.ema_alpha)

            for j in triangulated_joint_indices:
                if frame_idx - int(joint_last_seen_frame[j]) > args.joint_stale_frames:
                    joints_state[j] = np.nan
                    joints_conf_state[j] = 0.0
                    joints_cam_state[j] = 0

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
                    try:
                        udp_sock.sendto(json.dumps(pkt).encode("utf-8"), udp_target_addr)
                    except Exception:
                        pass

            if args.show_3d and (frame_idx % args.viz_every == 0):
                draw_live_scene(
                    ax=ax,
                    dims=dims,
                    tags=tags,
                    extr=extr,
                    ball_pt=ball_state,
                    ball_traj=list(ball_traj),
                    joints=joints_state.copy(),
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

            if args.show_2d and (frame_idx % args.mosaic_every == 0):
                mosaic = make_mosaic(cam_frames, ball_boxes, per_cam_pose)
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
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    finally:
        for cap in caps.values():
            cap.release()
        if udp_sock is not None:
            udp_sock.close()
        cv2.destroyAllWindows()
        plt.close("all")
        print("[DONE] Live viewer stopped.")


if __name__ == "__main__":
    main()
