#!/usr/bin/env python3
"""Validate Kalman filter prediction accuracy on recorded test sequences.

For each frame, predicts future position at multiple horizons (100-600ms)
and compares against actual future ground truth from the sequence.

Usage:
    python Parallel_working/scripts/validate_kalman_prediction.py \
        --sequence Parallel_working/output/test_sequences/walk_01 \
        --pose-backend yolopose \
        --output Parallel_working/output/prediction_results/walk_prediction.json

Metrics computed per horizon:
    - Mean/P95 prediction error (mm)
    - Mean/P95 prediction error per axis
    - Prediction coverage (fraction of frames with valid prediction)
    - Comparison: Kalman prediction vs naive (hold last position) vs linear extrapolation
"""

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np


CAM_ORDER = ["camEast", "camNorth", "camSouth", "camWest"]


# ─── Calibration loaders (same as ablation script) ───────────────

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
        tvec = np.array(d["tvec"], dtype=np.float64).reshape(3, 1) * 1000.0
        R, _ = cv2.Rodrigues(rvec)
        P = np.hstack([R, tvec])
        extr[cam] = {"R": R, "tvec": tvec, "P": P}
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


# ─── Kalman filter (copied from live pipeline) ───────────────────

class JointKalmanFilter:
    def __init__(self, process_noise=50.0, measurement_noise=80.0, dt=1.0 / 15.0):
        self.dt = dt
        self._initialized = False
        self.x = np.zeros(6, dtype=np.float64)
        self.P = np.eye(6, dtype=np.float64) * 1e4
        self.H = np.zeros((3, 6), dtype=np.float64)
        self.H[0, 0] = self.H[1, 1] = self.H[2, 2] = 1.0
        self.R = np.eye(3, dtype=np.float64) * measurement_noise ** 2
        self._q_std = process_noise
        self.Q = self._build_Q(dt, process_noise)

    def _build_F(self, dt):
        F = np.eye(6, dtype=np.float64)
        F[0, 3] = F[1, 4] = F[2, 5] = dt
        return F

    def _build_Q(self, dt, q_std):
        q = q_std ** 2
        dt2, dt3, dt4 = dt**2, dt**3, dt**4
        Q = np.zeros((6, 6), dtype=np.float64)
        for i in range(3):
            Q[i, i] = dt4 / 4 * q
            Q[i, i+3] = Q[i+3, i] = dt3 / 2 * q
            Q[i+3, i+3] = dt2 * q
        return Q

    def predict_step(self, dt=None):
        if dt is None:
            dt = self.dt
        F = self._build_F(dt)
        Q = self._build_Q(dt, self._q_std)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update_step(self, z):
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

    def predict_ahead(self, t_ahead_sec):
        if not self._initialized:
            return self.x[:3].copy()
        F = self._build_F(t_ahead_sec)
        return (F @ self.x)[:3].copy()

    def get_velocity(self):
        return self.x[3:].copy()

    @property
    def initialized(self):
        return self._initialized


# ─── Pose backends ────────────────────────────────────────────────

def init_yolopose(model_path):
    from ultralytics import YOLO
    return YOLO(model_path)

def run_yolopose_frame(model, frame):
    results = model(frame, verbose=False, conf=0.15)
    if results and results[0].keypoints is not None:
        kpts_data = results[0].keypoints.data.cpu().numpy()
        if len(kpts_data) > 0:
            return kpts_data[0, :17, :2].astype(np.float32), kpts_data[0, :17, 2].astype(np.float32)
    return None

def init_mmpose():
    from mmpose.apis import MMPoseInferencer
    try:
        return MMPoseInferencer(pose2d="rtmpose-m_8xb256-420e-coco-256x192", det_model="rtmdet-m", device="cuda:0")
    except Exception:
        return MMPoseInferencer(pose2d="human", device="cuda:0")

def run_mmpose_frame(infer, frame):
    results = list(infer(frame, return_vis=False))
    if results and results[0] and "predictions" in results[0]:
        preds = results[0]["predictions"]
        if preds and len(preds[0]) > 0:
            person = preds[0][0]
            return np.array(person["keypoints"], dtype=np.float32)[:17], np.array(person["keypoint_scores"], dtype=np.float32)[:17]
    return None


# ─── Main pipeline ────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Validate Kalman prediction on recorded sequences")
    ap.add_argument("--sequence", required=True)
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--extrinsics", default="arena_fixed/cal/extrinsics/extrinsics_fixed.json")
    ap.add_argument("--output", default="")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--pose-backend", choices=["mmpose", "yolopose"], default="yolopose")
    ap.add_argument("--yolopose-model", default="yolo11m-pose.pt")
    ap.add_argument("--process-noise", type=float, default=50.0)
    ap.add_argument("--measurement-noise", type=float, default=80.0)
    ap.add_argument("--ema-alpha", type=float, default=0.45, help="EMA alpha before Kalman")
    ap.add_argument("--horizons-ms", type=str, default="67,133,200,400,600",
                    help="Comma-separated prediction horizons in ms")
    args = ap.parse_args()

    horizons_ms = [float(h) for h in args.horizons_ms.split(",")]
    horizons_frames = [h / 1000.0 * args.fps for h in horizons_ms]
    dt = 1.0 / args.fps
    seq_dir = Path(args.sequence)

    # Load frames
    print(f"Loading sequence from {seq_dir}...")
    frames_by_cam = {}
    active_cams = []
    for cam in CAM_ORDER:
        cam_dir = seq_dir / cam
        if not cam_dir.exists():
            continue
        frame_files = sorted(cam_dir.glob("frame_*.jpg"))
        if args.max_frames > 0:
            frame_files = frame_files[:args.max_frames]
        frames = [cv2.imread(str(f)) for f in frame_files]
        frames = [f for f in frames if f is not None]
        frames_by_cam[cam] = frames
        active_cams.append(cam)
        print(f"  {cam}: {len(frames)} frames")

    n_frames = min(len(frames_by_cam[c]) for c in active_cams)

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

    # Init pose
    print(f"Loading {args.pose_backend}...")
    if args.pose_backend == "yolopose":
        model = init_yolopose(args.yolopose_model)
        pose_fn = lambda frame: run_yolopose_frame(model, frame)
    else:
        model = init_mmpose()
        pose_fn = lambda frame: run_mmpose_frame(model, frame)

    # Phase 1: Extract poses
    print(f"\nPhase 1: Pose extraction...")
    t0 = time.time()
    all_poses = []
    for fidx in range(n_frames):
        frame_poses = {}
        for cam in active_cams:
            result = pose_fn(frames_by_cam[cam][fidx])
            if result is not None:
                frame_poses[cam] = result
        all_poses.append(frame_poses)
        if (fidx + 1) % 50 == 0 or fidx == n_frames - 1:
            fps = (fidx + 1) / (time.time() - t0)
            print(f"  {fidx+1}/{n_frames} ({fps:.1f} fps)", end="\r")
    print()

    # Phase 2: Triangulate all frames
    print("Phase 2: Triangulation...")
    all_joints_3d = []
    for frame_poses in all_poses:
        joints_3d = {}
        for j in range(17):
            obs = {}
            for cam in active_cams:
                if cam not in frame_poses or cam not in intr:
                    continue
                kpts, scores = frame_poses[cam]
                if j < len(scores) and scores[j] >= 0.35:
                    arr = np.array(kpts[j].tolist(), dtype=np.float64).reshape(1, 1, 2)
                    und = cv2.undistortPoints(arr, intr[cam]["K"], intr[cam]["D"])
                    obs[cam] = und[0, 0]
            if len(obs) >= 2:
                pt3d = triangulate_multi(obs, proj)
                if pt3d is not None:
                    joints_3d[j] = pt3d
        all_joints_3d.append(joints_3d)

    # Phase 3: Apply EMA + Kalman, evaluate prediction accuracy
    print("Phase 3: Kalman prediction validation...")

    # Build EMA-smoothed trajectory — this is both the Kalman input and the ground truth
    # (matching production pipeline: triangulate → EMA → Kalman → predict)
    alpha = args.ema_alpha
    joints_ema = np.full((n_frames, 17, 3), np.nan, dtype=np.float64)
    joints_state = np.full((17, 3), np.nan, dtype=np.float64)
    for fidx, joints_3d in enumerate(all_joints_3d):
        for j, pt in joints_3d.items():
            prev = joints_state[j] if np.isfinite(joints_state[j]).all() else None
            if prev is None:
                joints_state[j] = pt
            else:
                joints_state[j] = (1.0 - alpha) * prev + alpha * pt
        joints_ema[fidx] = joints_state.copy()

    # Track joints that have good coverage (use torso: nose=0, l_shoulder=5, r_shoulder=6, l_hip=11, r_hip=12)
    eval_joints = [0, 5, 6, 11, 12]
    joint_names = {0: "nose", 5: "l_shoulder", 6: "r_shoulder", 11: "l_hip", 12: "r_hip"}

    # For each prediction horizon, evaluate
    results = {"_meta": {
        "sequence": str(seq_dir),
        "pose_backend": args.pose_backend,
        "n_frames": n_frames,
        "fps": args.fps,
        "ema_alpha": alpha,
        "process_noise": args.process_noise,
        "measurement_noise": args.measurement_noise,
        "horizons_ms": horizons_ms,
        "eval_joints": {str(j): joint_names[j] for j in eval_joints},
    }}

    for horizon_ms in horizons_ms:
        horizon_sec = horizon_ms / 1000.0
        horizon_frames = int(round(horizon_ms / 1000.0 * args.fps))
        label = f"{int(horizon_ms)}ms"

        # Initialize Kalman filters — fed EMA-smoothed positions (matching production)
        kfs = {j: JointKalmanFilter(
            process_noise=args.process_noise,
            measurement_noise=args.measurement_noise,
            dt=dt
        ) for j in eval_joints}

        errors_kalman = []
        errors_naive = []
        errors_linear = []
        errors_per_joint = {j: [] for j in eval_joints}
        errors_per_axis_kalman = {"x": [], "y": [], "z": []}

        for fidx in range(n_frames):
            for j in eval_joints:
                current_ema = joints_ema[fidx, j]
                if not np.isfinite(current_ema).all():
                    continue

                # Feed Kalman with EMA-smoothed position (matches production pipeline)
                kfs[j].predict_step()
                kfs[j].update_step(current_ema)

                # Check if we have a future ground truth
                future_idx = fidx + horizon_frames
                if future_idx >= n_frames or not np.isfinite(joints_ema[future_idx, j]).all():
                    continue
                actual_future = joints_ema[future_idx, j]

                # Kalman prediction
                if kfs[j].initialized:
                    pred_kalman = kfs[j].predict_ahead(horizon_sec)
                    err_k = float(np.linalg.norm(pred_kalman - actual_future))
                    errors_kalman.append(err_k)
                    errors_per_joint[j].append(err_k)
                    diff = pred_kalman - actual_future
                    errors_per_axis_kalman["x"].append(abs(diff[0]))
                    errors_per_axis_kalman["y"].append(abs(diff[1]))
                    errors_per_axis_kalman["z"].append(abs(diff[2]))

                # Naive: hold current EMA position
                err_n = float(np.linalg.norm(current_ema - actual_future))
                errors_naive.append(err_n)

                # Linear extrapolation: use last 2 EMA positions
                if fidx >= 1 and np.isfinite(joints_ema[fidx-1, j]).all():
                    vel = (current_ema - joints_ema[fidx-1, j]) / dt
                    pred_linear = current_ema + vel * horizon_sec
                    err_l = float(np.linalg.norm(pred_linear - actual_future))
                    errors_linear.append(err_l)

        ek = np.array(errors_kalman) if errors_kalman else np.array([0.0])
        en = np.array(errors_naive) if errors_naive else np.array([0.0])
        el = np.array(errors_linear) if errors_linear else np.array([0.0])

        horizon_result = {
            "horizon_ms": horizon_ms,
            "horizon_frames": horizon_frames,
            "kalman": {
                "mean_mm": float(np.mean(ek)),
                "median_mm": float(np.median(ek)),
                "p95_mm": float(np.percentile(ek, 95)),
                "p99_mm": float(np.percentile(ek, 99)),
                "samples": len(errors_kalman),
            },
            "naive_hold": {
                "mean_mm": float(np.mean(en)),
                "median_mm": float(np.median(en)),
                "p95_mm": float(np.percentile(en, 95)),
                "samples": len(errors_naive),
            },
            "linear_extrap": {
                "mean_mm": float(np.mean(el)),
                "median_mm": float(np.median(el)),
                "p95_mm": float(np.percentile(el, 95)),
                "samples": len(errors_linear),
            },
            "per_joint": {
                joint_names[j]: {
                    "mean_mm": float(np.mean(errors_per_joint[j])) if errors_per_joint[j] else 0,
                    "p95_mm": float(np.percentile(errors_per_joint[j], 95)) if errors_per_joint[j] else 0,
                } for j in eval_joints
            },
            "per_axis_kalman": {
                ax: {
                    "mean_mm": float(np.mean(errors_per_axis_kalman[ax])) if errors_per_axis_kalman[ax] else 0,
                    "p95_mm": float(np.percentile(errors_per_axis_kalman[ax], 95)) if errors_per_axis_kalman[ax] else 0,
                } for ax in ["x", "y", "z"]
            },
        }
        results[label] = horizon_result

        # Improvement over naive
        improvement = (1.0 - float(np.mean(ek)) / max(float(np.mean(en)), 0.01)) * 100
        print(f"  {label:>6s}: Kalman={np.mean(ek):6.1f}mm  Naive={np.mean(en):6.1f}mm  "
              f"Linear={np.mean(el):6.1f}mm  Kalman vs Naive: {improvement:+.0f}%")

    # Summary
    print("\n" + "=" * 90)
    print(f"{'Horizon':<10} {'Kalman Mean':>12} {'Kalman P95':>12} {'Naive Mean':>12} {'Linear Mean':>12} {'K vs N':>8}")
    print("-" * 90)
    for horizon_ms in horizons_ms:
        label = f"{int(horizon_ms)}ms"
        r = results[label]
        k, n, l = r["kalman"], r["naive_hold"], r["linear_extrap"]
        imp = (1.0 - k["mean_mm"] / max(n["mean_mm"], 0.01)) * 100
        print(f"{label:<10} {k['mean_mm']:>10.1f}mm {k['p95_mm']:>10.1f}mm "
              f"{n['mean_mm']:>10.1f}mm {l['mean_mm']:>10.1f}mm {imp:>+6.0f}%")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
