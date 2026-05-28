import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.lines import Line2D


CONNECTIONS = [
    (5, 7), (7, 9), (6, 8), (8, 10),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (5, 6), (11, 12), (5, 11), (6, 12),
    (0, 1), (0, 2), (1, 3), (2, 4)
]


def parse_dimensions(filepath):
    dims = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    tags = {}
    with open(filepath, 'r') as f:
        content = f.read()

    m = re.search(r'X\s*=\s*(\d+(?:\.\d+)?)\s*cm', content)
    if m:
        dims["X"] = float(m.group(1)) * 10.0
    m = re.search(r'Y\s*=\s*(\d+(?:\.\d+)?)\s*cm', content)
    if m:
        dims["Y"] = float(m.group(1)) * 10.0
    m = re.search(r'Z\s*=\s*(\d+(?:\.\d+)?)\s*cm', content)
    if m:
        dims["Z"] = float(m.group(1)) * 10.0

    sections = re.split(r'ID=(\d+):', content)
    for i in range(1, len(sections), 2):
        tag_id = int(sections[i])
        sec = sections[i + 1]
        corner_matches = re.findall(r'c\d\s*\(\s*([\d\.]+)\s*,\s*([\d\.]+)\s*,\s*([\d\.]+)\s*\)', sec)
        if len(corner_matches) == 4:
            corners = []
            for cm in corner_matches:
                x, y, z = map(float, cm)
                corners.append([x * 10.0, y * 10.0, z * 10.0])
            tags[tag_id] = np.array(corners, dtype=np.float32)

    return dims, tags


def load_extrinsics(path):
    with open(path, 'r') as f:
        data = json.load(f)
    cams = {}
    for name, cam in data.items():
        pos = np.array(cam.get("camera_position", [0, 0, 0]), dtype=np.float32) * 1000.0
        rvec = np.array(cam.get("rvec", [0, 0, 0]), dtype=np.float32)
        cams[name] = {"pos": pos, "rvec": rvec}
    return cams


def load_motion(path):
    with open(path, 'r') as f:
        data = json.load(f)

    n = len(data)
    ball = np.full((n, 3), np.nan, dtype=np.float32)
    joints = np.full((n, 17, 3), np.nan, dtype=np.float32)

    for i, frame in enumerate(data):
        b = frame.get("ball")
        if b is not None:
            ball[i] = np.array(b, dtype=np.float32)
        js = frame.get("joints", [])
        for j, pt in enumerate(js):
            if pt is not None and j < 17:
                joints[i, j] = np.array(pt, dtype=np.float32)

    return ball, joints


def auto_center_xy(ball, joints, dims):
    valid = []
    if np.isfinite(ball).any():
        valid.append(ball[np.isfinite(ball[:, 0])])
    if np.isfinite(joints).any():
        j = joints.reshape(-1, 3)
        valid.append(j[np.isfinite(j[:, 0])])
    if not valid:
        return ball, joints
    pts = np.vstack(valid)
    cx, cy = np.median(pts[:, 0]), np.median(pts[:, 1])
    tx, ty = dims["X"] / 2.0, dims["Y"] / 2.0
    dx, dy = tx - cx, ty - cy
    ball[:, 0] += dx
    ball[:, 1] += dy
    joints[:, :, 0] += dx
    joints[:, :, 1] += dy
    return ball, joints


def auto_floor_z(ball, joints):
    z_vals = []
    # Prefer ankles if available
    ankles = joints[:, [15, 16], :].reshape(-1, 3)
    if np.isfinite(ankles[:, 2]).any():
        z_vals = ankles[np.isfinite(ankles[:, 2]), 2]
    else:
        all_pts = []
        if np.isfinite(ball).any():
            all_pts.append(ball[np.isfinite(ball[:, 2])][:, 2])
        if np.isfinite(joints).any():
            all_pts.append(joints.reshape(-1, 3)[np.isfinite(joints.reshape(-1, 3)[:, 2])][:, 2])
        if all_pts:
            z_vals = np.concatenate(all_pts)
    if len(z_vals) == 0:
        return ball, joints
    floor_z = np.percentile(z_vals, 5)
    dz = -floor_z
    ball[:, 2] += dz
    joints[:, :, 2] += dz
    return ball, joints


def smooth_series(series, window):
    if window <= 1:
        return series
    out = series.copy()
    half = window // 2
    for i in range(len(series)):
        start = max(0, i - half)
        end = min(len(series), i + half + 1)
        window_vals = series[start:end]
        window_vals = window_vals[np.isfinite(window_vals)]
        if len(window_vals) > 0:
            out[i] = np.mean(window_vals)
    return out


def smooth_trajectories(ball, joints, window):
    if window <= 1:
        return ball, joints
    # Ball
    for axis in range(3):
        col = ball[:, axis]
        ball[:, axis] = smooth_series(col, window)
    # Joints
    for j in range(joints.shape[1]):
        for axis in range(3):
            col = joints[:, j, axis]
            joints[:, j, axis] = smooth_series(col, window)
    return ball, joints


def compute_bone_medians(joints):
    medians = {}
    for s, e in CONNECTIONS:
        seg = joints[:, [s, e], :]
        valid = np.isfinite(seg[:, 0, 0]) & np.isfinite(seg[:, 1, 0])
        if not valid.any():
            medians[(s, e)] = np.nan
            continue
        lengths = np.linalg.norm(seg[valid, 0, :] - seg[valid, 1, :], axis=1)
        medians[(s, e)] = float(np.median(lengths))
    return medians


def bone_is_reasonable(p1, p2, ref_len, min_ratio, max_ratio):
    if not np.isfinite(ref_len):
        return True
    length = np.linalg.norm(p1 - p2)
    return (length >= ref_len * min_ratio) and (length <= ref_len * max_ratio)


def draw_arena(ax, dims, floor_alpha=0.08):
    X, Y, Z = dims["X"], dims["Y"], dims["Z"]
    corners = np.array([
        [0, 0, 0], [X, 0, 0], [X, Y, 0], [0, Y, 0],
        [0, 0, Z], [X, 0, Z], [X, Y, Z], [0, Y, Z]
    ])
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7)
    ]
    floor = Poly3DCollection([[corners[0], corners[1], corners[2], corners[3]]],
                             alpha=floor_alpha, facecolors='#cfd8dc', edgecolors='none')
    ax.add_collection3d(floor)
    for a, b in edges:
        ax.plot(*zip(corners[a], corners[b]), color='#666666', linewidth=1.0, alpha=0.7)


def draw_tags(ax, tags):
    for tag_id, corners in tags.items():
        poly = Poly3DCollection([corners], alpha=0.30, facecolors='#53c4f5', edgecolors='#0c74a8')
        ax.add_collection3d(poly)
        center = corners.mean(axis=0)
        ax.text(center[0], center[1], center[2], str(tag_id), color='#0c74a8', fontsize=6)


def draw_cameras(ax, cams, label_size=9):
    import cv2
    colors = {
        'camNorth': 'red',
        'camEast': 'green',
        'camSouth': 'blue',
        'camWest': 'orange'
    }
    for name, cam in cams.items():
        pos = cam["pos"]
        rvec = cam["rvec"].reshape(3, 1)
        R, _ = cv2.Rodrigues(rvec)
        # Camera forward in world is R.T[:, 2]
        fwd = R.T[:, 2]
        col = colors.get(name, 'black')
        ax.scatter(pos[0], pos[1], pos[2], c=col, s=50, marker='^')
        ax.quiver(pos[0], pos[1], pos[2], fwd[0], fwd[1], fwd[2], length=500, color=col)
        ax.text(pos[0], pos[1], pos[2], name, color=col, fontsize=label_size, fontweight='bold')


def render(args):
    dims, tags = parse_dimensions(args.dimensions)
    cams = load_extrinsics(args.extrinsics)
    ball, joints = load_motion(args.motion)

    if args.smooth_window > 1:
        ball, joints = smooth_trajectories(ball, joints, args.smooth_window)

    if args.auto_center:
        ball, joints = auto_center_xy(ball, joints, dims)
    if args.auto_floor:
        ball, joints = auto_floor_z(ball, joints)

    bone_medians = compute_bone_medians(joints)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.clean_out_dir:
        for p in sorted(out_dir.glob("frame_*.png")):
            p.unlink()

    n = len(ball)
    step = max(1, args.step)
    max_frames = args.max_frames if args.max_frames > 0 else n

    X, Y, Z = dims["X"], dims["Y"], dims["Z"]

    for i in range(0, min(n, max_frames), step):
        fig = plt.figure(figsize=(args.figsize[0], args.figsize[1]), facecolor=args.bg_color)
        ax = fig.add_subplot(111, projection='3d')
        ax.set_facecolor(args.bg_color)
        ax.set_box_aspect([X, Y, Z])
        ax.grid(True, color=args.grid_color, linewidth=0.6, alpha=0.6)

        draw_arena(ax, dims, floor_alpha=args.floor_alpha)
        if args.draw_tags:
            draw_tags(ax, tags)
        if args.draw_cameras:
            draw_cameras(ax, cams, label_size=args.camera_label_size)

        # Ball trajectory (last 1 second)
        start = max(0, i - args.traj_len)
        traj = ball[start:i + 1]
        mask = np.isfinite(traj[:, 0])
        if mask.any():
            vals = traj[mask]
            if args.ball_trail_fade and len(vals) > 1:
                for k in range(1, len(vals)):
                    alpha = 0.15 + 0.85 * (k / max(1, len(vals) - 1))
                    ax.plot(
                        vals[k - 1:k + 1, 0],
                        vals[k - 1:k + 1, 1],
                        vals[k - 1:k + 1, 2],
                        c=args.ball_color,
                        linewidth=2.0,
                        alpha=alpha,
                    )
            else:
                ax.plot(vals[:, 0], vals[:, 1], vals[:, 2], c=args.ball_color, linewidth=2.2)

        # Current ball
        if np.isfinite(ball[i]).all():
            ax.scatter(ball[i, 0], ball[i, 1], ball[i, 2], c=args.ball_color, s=95, edgecolors='white', linewidths=0.9)

        # Skeleton
        sk = joints[i]
        valid = np.isfinite(sk[:, 0])
        for s, e in CONNECTIONS:
            if valid[s] and valid[e]:
                p1, p2 = sk[s], sk[e]
                if bone_is_reasonable(
                    p1,
                    p2,
                    bone_medians.get((s, e), np.nan),
                    min_ratio=args.bone_min_ratio,
                    max_ratio=args.bone_max_ratio,
                ):
                    ax.plot(
                        [p1[0], p2[0]],
                        [p1[1], p2[1]],
                        [p1[2], p2[2]],
                        c=args.skeleton_color,
                        linewidth=2.4,
                        alpha=0.95,
                    )
        for j in range(17):
            if valid[j]:
                ax.scatter(
                    sk[j, 0],
                    sk[j, 1],
                    sk[j, 2],
                    c=args.joint_color,
                    s=22,
                    edgecolors='white',
                    linewidths=0.6,
                    alpha=0.98,
                )

        ax.set_xlim(0, X)
        ax.set_ylim(0, Y)
        ax.set_zlim(0, Z)
        ax.set_xlabel('X (mm)')
        ax.set_ylabel('Y (mm)')
        ax.set_zlabel('Z (mm)')
        ax.set_title(args.title)
        ax.view_init(elev=args.elev, azim=args.azim)
        ax.tick_params(axis='both', which='major', labelsize=10)

        if args.presentation_mode:
            handles = [
                Line2D([0], [0], color=args.skeleton_color, lw=2.4, label="Skeleton"),
                Line2D([0], [0], color=args.ball_color, lw=2.2, label="Ball Trajectory"),
                Line2D([0], [0], marker='o', color='w', markerfacecolor=args.ball_color,
                       markeredgecolor='white', markersize=8, label='Ball'),
            ]
            ax.legend(handles=handles, loc='upper left', framealpha=0.9, fontsize=9)
            ax.text2D(
                0.02,
                0.02,
                f"Frame {i + 1}/{min(n, max_frames)} | t={i / max(1, args.fps):.2f}s",
                transform=ax.transAxes,
                fontsize=10,
                color="#444444",
            )

        out_path = out_dir / f"frame_{i:04d}.png"
        plt.savefig(out_path, dpi=args.dpi)
        plt.close(fig)

        if i % (step * 10) == 0:
            print(f"Rendered frame {i}/{min(n, max_frames)}")

    # Encode video
    if args.encode:
        out_vid = Path(args.out_video)
        if out_vid.exists():
            out_vid.unlink()
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(args.fps),
            "-i",
            str(out_dir / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            args.preset,
            "-crf",
            str(args.crf),
            "-pix_fmt",
            "yuv420p",
            str(out_vid),
        ]
        subprocess.run(cmd, check=True)
        print(f"[SUCCESS] {out_vid}")


def main():
    ap = argparse.ArgumentParser(description="Render arena + ball + skeleton in garage world frame")
    ap.add_argument("--motion", default="data/processed/motion_capture_data.json")
    ap.add_argument("--dimensions", default="arena_fixed/cal/extrinsics/Dimensions_fixed.txt")
    ap.add_argument("--extrinsics", default="arena_fixed/cal/extrinsics/extrinsics_fixed.json")
    ap.add_argument("--out-dir", default="garage_lab_combined/output/frames_arena")
    ap.add_argument("--out-video", default="garage_lab_combined/output/garage_arena_ball_skel.mp4")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--figsize", type=float, nargs=2, default=[12.0, 9.0], help="Figure size in inches (w h)")
    ap.add_argument("--dpi", type=int, default=160, help="Render DPI (higher = better quality, slower)")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--traj-len", type=int, default=15)
    ap.add_argument("--elev", type=int, default=20)
    ap.add_argument("--azim", type=int, default=-60)
    ap.add_argument("--title", default="Garage Arena + 3D Ball + Skeleton")
    ap.add_argument("--skeleton-color", default="#111111", help="Skeleton line color")
    ap.add_argument("--joint-color", default="#222222", help="Joint color")
    ap.add_argument("--ball-color", default="#f4b400", help="Ball color")
    ap.add_argument("--bg-color", default="#f7f7f7", help="Background color")
    ap.add_argument("--grid-color", default="#c0c0c0", help="Grid color")
    ap.add_argument("--floor-alpha", type=float, default=0.08)
    ap.add_argument("--camera-label-size", type=int, default=9)
    ap.add_argument("--bone-min-ratio", type=float, default=0.45, help="Hide bones shorter than this ratio of median length")
    ap.add_argument("--bone-max-ratio", type=float, default=1.75, help="Hide bones longer than this ratio of median length")
    ap.add_argument("--ball-trail-fade", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--smooth-window", type=int, default=3, help="Temporal smoothing window (frames)")
    ap.add_argument("--draw-tags", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--draw-cameras", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--auto-center", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--auto-floor", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--presentation-mode", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--clean-out-dir", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--crf", type=int, default=18, help="Video quality for libx264 (lower is better)")
    ap.add_argument("--preset", default="medium", help="libx264 preset")
    ap.add_argument("--encode", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    Path(Path(args.out_video).parent).mkdir(parents=True, exist_ok=True)

    render(args)


if __name__ == "__main__":
    main()
