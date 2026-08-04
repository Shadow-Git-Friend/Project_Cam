#!/usr/bin/env python3
"""Ablation study: Adaptive EMA vs Fixed EMA on recorded test sequences.

Processes a recorded 4-camera sequence through the triangulation pipeline
with both fixed and adaptive EMA, comparing tracking quality metrics.
Supports both MMPose and YOLO-Pose backends for backend comparison.

Usage:
    # EMA ablation with YOLO-Pose (fast):
    python Parallel_working/scripts/ablation_ema_adaptive.py \
        --sequence Parallel_working/output/test_sequences/jump_01 \
        --pose-backend yolopose \
        --output Parallel_working/output/ablation_results/jump_yolopose.json

    # Backend comparison (run once with each, compare output JSONs):
    python Parallel_working/scripts/ablation_ema_adaptive.py \
        --sequence Parallel_working/output/test_sequences/walk_01 \
        --pose-backend mmpose --output .../walk_mmpose.json
    python Parallel_working/scripts/ablation_ema_adaptive.py \
        --sequence Parallel_working/output/test_sequences/walk_01 \
        --pose-backend yolopose --output .../walk_yolopose.json

Metrics computed:
    - Frame-to-frame jitter (mean/P95 displacement between consecutive frames)
    - Smoothness (mean second derivative of position — lower = smoother)
    - Tracking coverage (fraction of frames with valid 3D position per joint)
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np


CAM_ORDER = ["camEast", "camNorth", "camSouth", "camWest"]


def load_intrinsics(path):
    with open(path) as f:
        d = json.load(f)
    K = np.array(d.get("camera_matrix", d.get("K")), dtype=np.float64)
    D_raw = d.get("distortion_coefficients", d.get("dist_coeffs", d.get("D", [0, 0, 0, 0, 0])))
    D = np.array(D_raw, dtype=np.float64).ravel()
    return {"K": K, "D": D}


def load_extrinsics(path):
    with open(path) as f:
        data = json.load(f)
    extr = {}
    for cam, d in data.items():
        rvec = np.array(d["rvec"], dtype=np.float64).reshape(3, 1)
        tvec = np.array(d["tvec"], dtype=np.float64).reshape(3, 1) * 1000.0  # m → mm
        R, _ = cv2.Rodrigues(rvec)
        P = np.hstack([R, tvec])  # 3x4, no K — undistortPoints normalizes
        cam_pos = np.array(d.get("camera_position", [0, 0, 0]), dtype=np.float64) * 1000.0
        extr[cam] = {"R": R, "tvec": tvec, "P": P, "pos": cam_pos}
    return extr


def triangulate_multi(observations, proj_mats):
    cams = list(observations.keys())
    if len(cams) < 2:
        return None
    rows = []
    for cam in cams:
        u, v = observations[cam]
        P = proj_mats[cam]
        rows.append(u * P[2] - P[0])
        rows.append(v * P[2] - P[1])
    A = np.array(rows, dtype=np.float64)
    _, _, Vt = np.linalg.svd(A)
    X = Vt[-1]
    if abs(X[3]) < 1e-12:
        return None
    pt = X[:3] / X[3]
    if not np.isfinite(pt).all():
        return None
    return pt


def ema_update(prev, new, alpha):
    if new is None:
        return prev
    if prev is None:
        return np.array(new, dtype=np.float32)
    return (1.0 - alpha) * prev + alpha * np.array(new, dtype=np.float32)


# ─── Pose backends ────────────────────────────────────────────────


def init_mmpose():
    from mmpose.apis import MMPoseInferencer
    try:
        infer = MMPoseInferencer(
            pose2d="rtmpose-m_8xb256-420e-coco-256x192",
            det_model="rtmdet-m",
            device="cuda:0",
        )
    except Exception:
        infer = MMPoseInferencer(pose2d="human", device="cuda:0")
    return infer


def run_mmpose_frame(infer, frame):
    """Returns (kpts_17x2, scores_17) or None."""
    try:
        results = list(infer(frame, return_vis=False))
        if results and results[0] and "predictions" in results[0]:
            preds = results[0]["predictions"]
            if preds and len(preds) > 0 and len(preds[0]) > 0:
                person = preds[0][0]
                kpts = np.array(person["keypoints"], dtype=np.float32)[:17]
                scores = np.array(person["keypoint_scores"], dtype=np.float32)[:17]
                return kpts, scores
    except Exception:
        pass
    return None


def init_rtmo(size="s", device="cuda:0"):
    """RTMO — one-stage, bottom-up, and the only commercially clean pose option.

    Added 2026-08-04 for roadmap A5. The licence chain was verified from the
    checkpoint's OWN embedded training config (COCO only, YOLOX-COCO backbone
    init, zero CrowdPose), not from the model-zoo metafile — which mislabels
    these COCO checkpoints as CrowdPose-trained.

    The test pipeline is built once here rather than per frame: mmpose's
    `inference_bottomup` rebuilds it on every call, which cost ~7 ms/image.
    """
    from pathlib import Path as _Path

    from mmengine.dataset import Compose, pseudo_collate
    from mmpose.apis import init_model

    repo = _Path(__file__).resolve().parents[2]
    configs = repo / ("venv/lib/python3.10/site-packages/mmpose/.mim/configs/"
                      "body_2d_keypoint/rtmo/coco")
    names = {"s": "rtmo-s_8xb32-600e_coco-640x640.py",
             "m": "rtmo-m_16xb16-600e_coco-640x640.py",
             "l": "rtmo-l_16xb16-600e_coco-640x640.py"}
    model = init_model(str(configs / names[size]),
                       str(repo / f"models/pose/rtmo-{size}_coco.pth"),
                       device=device)
    pipeline = Compose(model.cfg.test_dataloader.dataset.pipeline)
    return {"model": model, "pipeline": pipeline, "collate": pseudo_collate}


def run_rtmo_frame(handle, frame):
    """Returns (kpts_17x2, scores_17) or None — highest-scoring person."""
    import torch

    try:
        info = dict(img=frame)
        info.update(handle["model"].dataset_meta)
        batch = handle["collate"]([handle["pipeline"](info)])
        with torch.no_grad():
            results = handle["model"].test_step(batch)
        if not results:
            return None
        pred = results[0].pred_instances
        kpts = np.asarray(pred.keypoints, dtype=np.float32)
        if kpts.size == 0:
            return None
        person_scores = np.asarray(getattr(pred, "bbox_scores", []),
                                   dtype=np.float32)
        best = int(np.argmax(person_scores)) if person_scores.size else 0
        scores = np.asarray(pred.keypoint_scores, dtype=np.float32)[best, :17]
        return kpts[best, :17, :2], scores
    except Exception:
        return None


def init_yolopose(model_path="yolo11m-pose.pt"):
    from ultralytics import YOLO
    return YOLO(model_path)


def run_yolopose_frame(model, frame):
    """Returns (kpts_17x2, scores_17) or None."""
    try:
        results = model(frame, verbose=False, conf=0.15)
        if results and results[0].keypoints is not None:
            kpts_data = results[0].keypoints.data.cpu().numpy()
            if len(kpts_data) > 0:
                kpts = kpts_data[0, :17, :2].astype(np.float32)
                scores = kpts_data[0, :17, 2].astype(np.float32)
                return kpts, scores
    except Exception:
        pass
    return None


# ─── Core pipeline ────────────────────────────────────────────────


def extract_all_poses(frames_by_cam, pose_fn, cam_order):
    """Run pose inference on all frames, all cameras. Returns per-frame per-cam keypoints.

    Returns: list of dicts, each {cam: (kpts_17x2, scores_17)} or cam missing if no detection.
    """
    n_frames = min(len(frames_by_cam[c]) for c in cam_order)
    all_poses = []
    t0 = time.time()

    for fidx in range(n_frames):
        frame_poses = {}
        for cam in cam_order:
            frame = frames_by_cam[cam][fidx]
            result = pose_fn(frame)
            if result is not None:
                frame_poses[cam] = result
        all_poses.append(frame_poses)

        if (fidx + 1) % 50 == 0 or fidx == n_frames - 1:
            elapsed = time.time() - t0
            fps = (fidx + 1) / elapsed
            print(f"  Pose: {fidx+1}/{n_frames} frames ({fps:.1f} fps)", end="\r")

    print()
    return all_poses


def triangulate_all(all_poses, intr, proj, cam_order, min_score=0.35):
    """Triangulate all joints for all frames from cached pose data.

    Returns: list of dicts, each {joint_idx: np.array(3)} for successfully triangulated joints.
    """
    all_joints_3d = []

    for frame_poses in all_poses:
        joints_3d = {}
        for j in range(17):
            obs = {}
            for cam in cam_order:
                if cam not in frame_poses or cam not in intr:
                    continue
                kpts, scores = frame_poses[cam]
                if j < len(scores) and scores[j] >= min_score:
                    pt = kpts[j].tolist()
                    arr = np.array(pt, dtype=np.float64).reshape(1, 1, 2)
                    und = cv2.undistortPoints(arr, intr[cam]["K"], intr[cam]["D"])
                    obs[cam] = und[0, 0]
            if len(obs) >= 2:
                pt3d = triangulate_multi(obs, proj)
                if pt3d is not None:
                    joints_3d[j] = pt3d
        all_joints_3d.append(joints_3d)

    return all_joints_3d


def apply_ema_variant(all_joints_3d, alpha, snap_thresh):
    """Apply EMA smoothing to triangulated 3D joints.

    Returns: list of (17,3) arrays — smoothed trajectory.
    """
    joints_state = np.full((17, 3), np.nan, dtype=np.float32)
    trajectory = []

    for joints_3d in all_joints_3d:
        for j, pt in joints_3d.items():
            prev = joints_state[j] if np.isfinite(joints_state[j]).all() else None
            alpha_eff = alpha
            if snap_thresh > 0 and prev is not None:
                disp = float(np.linalg.norm(pt - prev))
                if disp > snap_thresh:
                    alpha_eff = min(1.0, alpha * (disp / snap_thresh))
            joints_state[j] = ema_update(prev, pt, alpha=alpha_eff)
        trajectory.append(joints_state.copy())

    return trajectory


def compute_metrics(trajectory):
    """Compute tracking quality metrics from a trajectory."""
    traj = np.array(trajectory)  # (N, 17, 3)
    N = traj.shape[0]

    jitters = []
    accels = []
    valid_per_joint = np.zeros(17)

    for j in range(17):
        for i in range(N):
            if np.isfinite(traj[i, j]).all():
                valid_per_joint[j] += 1
        for i in range(1, N):
            p1, p2 = traj[i-1, j], traj[i, j]
            if np.isfinite(p1).all() and np.isfinite(p2).all():
                jitters.append(float(np.linalg.norm(p2 - p1)))
        for i in range(2, N):
            p0, p1, p2 = traj[i-2, j], traj[i-1, j], traj[i, j]
            if np.isfinite(p0).all() and np.isfinite(p1).all() and np.isfinite(p2).all():
                accels.append(float(np.linalg.norm(p2 - 2*p1 + p0)))

    jitters = np.array(jitters) if jitters else np.array([0.0])
    accels = np.array(accels) if accels else np.array([0.0])
    coverage = float(np.mean(valid_per_joint / max(N, 1)))

    return {
        "jitter_mean_mm": float(np.mean(jitters)),
        "jitter_p95_mm": float(np.percentile(jitters, 95)),
        "jitter_p99_mm": float(np.percentile(jitters, 99)),
        "smoothness_mean_mm": float(np.mean(accels)),
        "smoothness_p95_mm": float(np.percentile(accels, 95)),
        "coverage": coverage,
        "total_frames": N,
        "valid_jitter_samples": len(jitters),
    }


def main():
    ap = argparse.ArgumentParser(description="Ablation: adaptive EMA vs fixed EMA")
    ap.add_argument("--sequence", required=True, help="Recorded test sequence directory")
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--extrinsics", default="arena_fixed/cal/extrinsics/extrinsics_fixed.json")
    ap.add_argument("--output", default="", help="Output JSON path for results")
    ap.add_argument("--max-frames", type=int, default=0, help="Limit frames (0=all)")
    ap.add_argument("--cam-order", default="",
                    help="comma-separated camera roles; default is the 4-camera "
                         "rig. For the 6-USB rig pass the roles from "
                         "cameras_6usb_test.yaml")
    ap.add_argument("--skip-frames", type=int, default=0,
                    help="clips only: drop this many leading frames")
    ap.add_argument("--frame-step", type=int, default=1,
                    help="clips only: keep every Nth frame (30 fps clip -> 2 gives "
                         "the rig's real ~15 fps)")
    ap.add_argument("--alpha", type=float, default=0.45, help="Base EMA alpha")
    ap.add_argument("--snap-thresh", type=float, default=80.0, help="Adaptive snap threshold (mm)")
    ap.add_argument("--pose-backend", choices=["mmpose", "yolopose", "rtmo"],
                    default="yolopose")
    ap.add_argument("--rtmo-size", choices=["s", "m", "l"], default="s",
                    help="RTMO variant; s is the one that fits the rig's budget")
    ap.add_argument("--yolopose-model", default="yolo11m-pose.pt")
    args = ap.parse_args()

    seq_dir = Path(args.sequence)

    # Load frames — a per-camera frame directory OR a per-camera .avi clip.
    # The 6-USB rig records clips (garage_lab_combined/test_clips/altai_*), and a
    # comparison run on the retired 4-camera April sequences would be measuring a
    # calibration the product no longer uses.
    cam_order = ([c.strip() for c in args.cam_order.split(",") if c.strip()]
                 if args.cam_order else CAM_ORDER)
    print(f"Loading sequence from {seq_dir}...")
    frames_by_cam = {}
    active_cams = []
    for cam in cam_order:
        cam_dir = seq_dir / cam
        clip = seq_dir / f"{cam}.avi"
        frames = []
        if cam_dir.is_dir():
            frame_files = sorted(cam_dir.glob("frame_*.jpg"))
            if args.max_frames > 0:
                frame_files = frame_files[:args.max_frames]
            frames = [cv2.imread(str(f)) for f in frame_files]
        elif clip.is_file():
            cap = cv2.VideoCapture(str(clip))
            index = 0
            while True:
                if args.max_frames > 0 and len(frames) >= args.max_frames:
                    break
                ok, frame = cap.read()
                if not ok:
                    break
                if index >= args.skip_frames and index % max(1, args.frame_step) == 0:
                    frames.append(frame)
                index += 1
            cap.release()
        else:
            print(f"  [WARN] {cam} not found (no dir, no .avi), skipping")
            continue
        frames = [f for f in frames if f is not None]
        if not frames:
            print(f"  [WARN] {cam} produced no frames, skipping")
            continue
        frames_by_cam[cam] = frames
        active_cams.append(cam)
        print(f"  {cam}: {len(frames)} frames")

    if len(active_cams) < 2:
        print("[ERROR] Need at least 2 cameras")
        return

    # Load calibration
    intr = {}
    for cam in active_cams:
        for suffix in [f"{cam}_intrinsics.json", f"{cam}.json"]:
            ipath = Path(args.intrinsics_dir) / suffix
            if ipath.exists():
                intr[cam] = load_intrinsics(str(ipath))
                break

    extr = load_extrinsics(args.extrinsics)
    proj = {cam: extr[cam]["P"] for cam in active_cams if cam in extr}

    # Init pose backend
    print(f"Loading {args.pose_backend}...")
    if args.pose_backend == "yolopose":
        model = init_yolopose(args.yolopose_model)
        pose_fn = lambda frame: run_yolopose_frame(model, frame)
    elif args.pose_backend == "rtmo":
        model = init_rtmo(args.rtmo_size)
        pose_fn = lambda frame: run_rtmo_frame(model, frame)
    else:
        model = init_mmpose()
        pose_fn = lambda frame: run_mmpose_frame(model, frame)

    # Phase 1: Extract all poses (run once, cache)
    print(f"\nPhase 1: Pose extraction ({args.pose_backend})...")
    t0 = time.time()
    all_poses = extract_all_poses(frames_by_cam, pose_fn, active_cams)
    pose_time = time.time() - t0
    n_frames = len(all_poses)

    # Compute detection stats
    det_counts = {cam: 0 for cam in active_cams}
    for fp in all_poses:
        for cam in fp:
            det_counts[cam] += 1
    print(f"  Pose extraction: {n_frames} frames in {pose_time:.1f}s ({n_frames/pose_time:.1f} fps)")
    for cam, cnt in det_counts.items():
        print(f"  {cam}: {cnt}/{n_frames} detections ({100*cnt/n_frames:.0f}%)")

    # Phase 2: Triangulate (run once, cache)
    print(f"\nPhase 2: Triangulation...")
    t0 = time.time()
    all_joints_3d = triangulate_all(all_poses, intr, proj, active_cams)
    tri_time = time.time() - t0

    # Triangulation coverage
    tri_counts = np.zeros(17)
    for jd in all_joints_3d:
        for j in jd:
            tri_counts[j] += 1
    mean_coverage = float(np.mean(tri_counts / max(n_frames, 1)))
    print(f"  Triangulated in {tri_time:.1f}s, mean joint coverage: {100*mean_coverage:.0f}%")

    # Phase 3: Apply each EMA variant (fast — just math on cached data)
    print(f"\nPhase 3: EMA ablation variants...")
    variants = {
        "fixed_0.25": {"alpha": 0.25, "snap_thresh": 0},
        "fixed_0.35": {"alpha": 0.35, "snap_thresh": 0},
        "fixed_0.45": {"alpha": 0.45, "snap_thresh": 0},
        "fixed_0.60": {"alpha": 0.60, "snap_thresh": 0},
        f"adaptive_{args.alpha}_snap_{int(args.snap_thresh)}": {
            "alpha": args.alpha, "snap_thresh": args.snap_thresh
        },
        f"adaptive_{args.alpha}_snap_50": {
            "alpha": args.alpha, "snap_thresh": 50.0
        },
        f"adaptive_{args.alpha}_snap_120": {
            "alpha": args.alpha, "snap_thresh": 120.0
        },
        "no_ema": {"alpha": 1.0, "snap_thresh": 0},  # raw triangulation
    }

    results = {"_meta": {
        "sequence": str(seq_dir),
        "pose_backend": (f"rtmo-{args.rtmo_size}" if args.pose_backend == "rtmo"
                         else args.pose_backend),
        "n_frames": n_frames,
        "pose_time_s": pose_time,
        "pose_fps": n_frames / pose_time,
        "cameras": active_cams,
        "detection_rates": {cam: cnt / n_frames for cam, cnt in det_counts.items()},
        "mean_triangulation_coverage": mean_coverage,
    }}

    for name, params in variants.items():
        trajectory = apply_ema_variant(all_joints_3d, params["alpha"], params["snap_thresh"])
        metrics = compute_metrics(trajectory)
        results[name] = {**params, **metrics}
        print(f"  {name:<35} jitter={metrics['jitter_mean_mm']:6.1f}mm  "
              f"P95={metrics['jitter_p95_mm']:6.1f}mm  "
              f"smooth={metrics['smoothness_mean_mm']:6.1f}mm  "
              f"cov={metrics['coverage']:.0%}")

    # Summary table
    print("\n" + "=" * 95)
    print(f"{'Variant':<35} {'Jitter Mean':>12} {'Jitter P95':>12} {'Smooth Mean':>12} {'Coverage':>10}")
    print("-" * 95)
    for name, r in results.items():
        if name == "_meta":
            continue
        print(f"{name:<35} {r['jitter_mean_mm']:>10.1f}mm {r['jitter_p95_mm']:>10.1f}mm "
              f"{r['smoothness_mean_mm']:>10.1f}mm {r['coverage']:>9.0%}")

    # Save
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
