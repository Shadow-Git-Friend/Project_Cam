import argparse
import json
import re
from pathlib import Path

import numpy as np

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


def parse_dimensions(filepath):
    dims = {"X": 0.0, "Y": 0.0, "Z": 0.0}
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
    return dims


def load_motion(path):
    with open(path, "r") as f:
        data = json.load(f)

    n = len(data)
    ball = np.full((n, 3), np.nan, dtype=np.float32)
    joints = np.full((n, 17, 3), np.nan, dtype=np.float32)

    for i, frame in enumerate(data):
        b = frame.get("ball")
        if b is not None:
            ball[i] = np.array(b, dtype=np.float32)
        js = frame.get("joints", [])
        for j, pt in enumerate(js[:17]):
            if pt is not None:
                joints[i, j] = np.array(pt, dtype=np.float32)
    return data, ball, joints


def set_partial_rows_to_nan(track):
    out = track.copy()
    invalid = ~np.isfinite(out).all(axis=1)
    out[invalid] = np.nan
    return out


def clip_to_room_bounds(track, dims, margin_mm):
    out = track.copy()
    valid = np.isfinite(out).all(axis=1)
    if not valid.any():
        return out

    x_ok = (out[:, 0] >= -margin_mm) & (out[:, 0] <= dims["X"] + margin_mm)
    y_ok = (out[:, 1] >= -margin_mm) & (out[:, 1] <= dims["Y"] + margin_mm)
    z_ok = (out[:, 2] >= -margin_mm) & (out[:, 2] <= dims["Z"] + margin_mm)
    keep = x_ok & y_ok & z_ok
    out[~keep] = np.nan
    return out


def interpolate_short_gaps_1d(arr, max_gap):
    out = arr.copy()
    n = len(out)
    i = 0
    while i < n:
        if np.isfinite(out[i]):
            i += 1
            continue

        start = i
        while i < n and not np.isfinite(out[i]):
            i += 1
        end = i - 1
        gap_len = end - start + 1
        left = start - 1
        right = i
        if (
            gap_len <= max_gap
            and left >= 0
            and right < n
            and np.isfinite(out[left])
            and np.isfinite(out[right])
        ):
            out[start:right] = np.linspace(out[left], out[right], gap_len + 2)[1:-1]
    return out


def smooth_1d(arr, window):
    if window <= 1:
        return arr.copy()
    out = arr.copy()
    n = len(arr)
    half = window // 2
    for i in range(n):
        s = max(0, i - half)
        e = min(n, i + half + 1)
        seg = arr[s:e]
        seg = seg[np.isfinite(seg)]
        if len(seg) > 0:
            out[i] = float(np.mean(seg))
    return out


def median_filter_1d(arr, window):
    if window <= 1:
        return arr.copy()
    out = arr.copy()
    n = len(arr)
    half = window // 2
    for i in range(n):
        s = max(0, i - half)
        e = min(n, i + half + 1)
        seg = arr[s:e]
        seg = seg[np.isfinite(seg)]
        if len(seg) > 0:
            out[i] = float(np.median(seg))
    return out


def remove_spikes(track, max_step_mm, spike_mm, passes=2):
    out = track.copy()
    n = len(out)
    for _ in range(passes):
        for i in range(1, n - 1):
            p0 = out[i - 1]
            p1 = out[i]
            p2 = out[i + 1]
            if not (np.isfinite(p0).all() and np.isfinite(p1).all() and np.isfinite(p2).all()):
                continue

            d_prev = np.linalg.norm(p1 - p0)
            d_next = np.linalg.norm(p1 - p2)
            d_bridge = np.linalg.norm(p2 - p0)
            pred = (p0 + p2) * 0.5
            err = np.linalg.norm(p1 - pred)

            is_speed_spike = d_prev > max_step_mm and d_next > max_step_mm and d_bridge < max_step_mm * 0.8
            is_median_spike = err > spike_mm
            if is_speed_spike or is_median_spike:
                out[i] = np.nan
    return out


def remove_accel_spikes(track, max_accel_mm_s2, fps, passes=1):
    if max_accel_mm_s2 <= 0 or fps <= 0:
        return track.copy()
    out = track.copy()
    dt = 1.0 / fps
    n = len(out)
    for _ in range(passes):
        for i in range(1, n - 1):
            p0 = out[i - 1]
            p1 = out[i]
            p2 = out[i + 1]
            if not (np.isfinite(p0).all() and np.isfinite(p1).all() and np.isfinite(p2).all()):
                continue
            v0 = (p1 - p0) / dt
            v1 = (p2 - p1) / dt
            a = (v1 - v0) / dt
            if np.linalg.norm(a) > max_accel_mm_s2:
                out[i] = np.nan
    return out


def clean_track(
    track,
    dims,
    margin_mm,
    max_speed_mm_s,
    spike_mm,
    fps,
    max_gap,
    median_window,
    smooth_window,
    max_accel_mm_s2,
):
    out = set_partial_rows_to_nan(track)
    out = clip_to_room_bounds(out, dims, margin_mm)

    max_step_mm = max_speed_mm_s / max(1.0, fps)
    out = remove_spikes(out, max_step_mm=max_step_mm, spike_mm=spike_mm, passes=2)
    out = remove_accel_spikes(out, max_accel_mm_s2=max_accel_mm_s2, fps=fps, passes=1)

    # Interpolate short gaps axis-wise
    for axis in range(3):
        out[:, axis] = interpolate_short_gaps_1d(out[:, axis], max_gap=max_gap)

    # Median pre-filter for robust denoising (edge-preserving)
    for axis in range(3):
        out[:, axis] = median_filter_1d(out[:, axis], window=median_window)

    # Smoothing axis-wise
    for axis in range(3):
        out[:, axis] = smooth_1d(out[:, axis], window=smooth_window)

    out = set_partial_rows_to_nan(out)
    out = clip_to_room_bounds(out, dims, margin_mm)
    return out


def compute_bone_medians(joints):
    med = {}
    for a, b in CONNECTIONS:
        seg = joints[:, [a, b], :]
        valid = np.isfinite(seg[:, 0, 0]) & np.isfinite(seg[:, 1, 0])
        if not valid.any():
            med[(a, b)] = np.nan
            continue
        lengths = np.linalg.norm(seg[valid, 0, :] - seg[valid, 1, :], axis=1)
        if len(lengths) == 0:
            med[(a, b)] = np.nan
        else:
            med[(a, b)] = float(np.median(lengths))
    return med


def enforce_bone_lengths(joints, bone_medians, iters=2, strength=0.35):
    out = joints.copy()
    n = len(out)
    for i in range(n):
        pts = out[i]
        valid = np.isfinite(pts[:, 0])
        if np.count_nonzero(valid) < 4:
            continue
        for _ in range(iters):
            for a, b in CONNECTIONS:
                target = bone_medians.get((a, b), np.nan)
                if not np.isfinite(target):
                    continue
                if not (valid[a] and valid[b]):
                    continue
                pa = pts[a]
                pb = pts[b]
                vec = pb - pa
                dist = np.linalg.norm(vec)
                if dist < 1e-6:
                    continue
                desired = vec * (target / dist)
                delta = desired - vec
                pts[a] = pa - 0.5 * strength * delta
                pts[b] = pb + 0.5 * strength * delta
        out[i] = pts
    return out


def array_to_motion(ball, joints):
    n = len(ball)
    out = []
    for i in range(n):
        if np.isfinite(ball[i]).all():
            b = ball[i].tolist()
        else:
            b = None

        js = []
        for j in range(17):
            if np.isfinite(joints[i, j]).all():
                js.append(joints[i, j].tolist())
            else:
                js.append(None)
        out.append({"ball": b, "joints": js})
    return out


def summarize(name, ball, joints):
    valid_ball = int(np.isfinite(ball).all(axis=1).sum())
    valid_joint_counts = np.isfinite(joints[:, :, 0]).sum(axis=1)
    median_joints = float(np.median(valid_joint_counts))
    print(f"[{name}] ball valid frames: {valid_ball}/{len(ball)} | median valid joints/frame: {median_joints:.1f}")

    com = np.full((len(joints), 3), np.nan, dtype=np.float32)
    valid_mask = np.isfinite(joints[:, :, 0]).any(axis=1)
    if valid_mask.any():
        com[valid_mask] = np.nanmean(joints[valid_mask], axis=1)
    d = np.linalg.norm(np.diff(com, axis=0), axis=1)
    d = d[np.isfinite(d)]
    if len(d) > 0:
        p50, p90, p95, p99, mx = np.percentile(d, [50, 90, 95, 99, 100])
        print(
            f"[{name}] COM step mm/frame p50={p50:.1f} p90={p90:.1f} p95={p95:.1f} p99={p99:.1f} max={mx:.1f}"
        )


def main():
    ap = argparse.ArgumentParser(description="Post-process garage 3D motion data for cleaner presentation.")
    ap.add_argument("--in-motion", default="garage_lab_combined/output/motion_capture_data_garage_v2.json")
    ap.add_argument("--out-motion", default="garage_lab_combined/output/motion_capture_data_garage_v3_optimized.json")
    ap.add_argument("--dimensions", default="garage_lab_combined/cal/extrinsics/Dimensions.txt")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--margin-mm", type=float, default=800.0, help="Allowed margin outside room before rejecting points")
    ap.add_argument("--ball-max-speed", type=float, default=18000.0, help="Ball max speed (mm/s)")
    ap.add_argument("--joint-max-speed", type=float, default=6000.0, help="Joint max speed (mm/s)")
    ap.add_argument("--ball-max-accel", type=float, default=90000.0, help="Ball max acceleration (mm/s^2)")
    ap.add_argument("--joint-max-accel", type=float, default=45000.0, help="Joint max acceleration (mm/s^2)")
    ap.add_argument("--ball-spike-mm", type=float, default=900.0, help="Single-frame spike threshold for ball")
    ap.add_argument("--joint-spike-mm", type=float, default=500.0, help="Single-frame spike threshold for joints")
    ap.add_argument("--ball-max-gap", type=int, default=4, help="Interpolate ball gaps up to this length")
    ap.add_argument("--joint-max-gap", type=int, default=3, help="Interpolate joint gaps up to this length")
    ap.add_argument("--ball-median", type=int, default=3, help="Median filter window for ball (odd number)")
    ap.add_argument("--joint-median", type=int, default=3, help="Median filter window for joints (odd number)")
    ap.add_argument("--ball-smooth", type=int, default=5)
    ap.add_argument("--joint-smooth", type=int, default=5)
    ap.add_argument("--kinematic-refine", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--kinematic-iters", type=int, default=2)
    ap.add_argument("--kinematic-strength", type=float, default=0.35)
    args = ap.parse_args()

    dims = parse_dimensions(args.dimensions)
    _, ball, joints = load_motion(args.in_motion)
    summarize("input", ball, joints)

    ball_clean = clean_track(
        track=ball,
        dims=dims,
        margin_mm=args.margin_mm,
        max_speed_mm_s=args.ball_max_speed,
        spike_mm=args.ball_spike_mm,
        fps=args.fps,
        max_gap=args.ball_max_gap,
        median_window=args.ball_median,
        smooth_window=args.ball_smooth,
        max_accel_mm_s2=args.ball_max_accel,
    )

    joints_clean = joints.copy()
    for j in range(17):
        joints_clean[:, j, :] = clean_track(
            track=joints[:, j, :],
            dims=dims,
            margin_mm=args.margin_mm,
            max_speed_mm_s=args.joint_max_speed,
            spike_mm=args.joint_spike_mm,
            fps=args.fps,
            max_gap=args.joint_max_gap,
            median_window=args.joint_median,
            smooth_window=args.joint_smooth,
            max_accel_mm_s2=args.joint_max_accel,
        )

    if args.kinematic_refine:
        bone_medians = compute_bone_medians(joints_clean)
        joints_clean = enforce_bone_lengths(
            joints_clean,
            bone_medians,
            iters=args.kinematic_iters,
            strength=args.kinematic_strength,
        )
        joints_clean = clip_to_room_bounds(joints_clean.reshape(-1, 3), dims, args.margin_mm).reshape(joints_clean.shape)

    summarize("output", ball_clean, joints_clean)

    out_data = array_to_motion(ball_clean, joints_clean)
    out_path = Path(args.out_motion)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out_data, f, indent=2)
    print(f"[DONE] {out_path}")


if __name__ == "__main__":
    main()
