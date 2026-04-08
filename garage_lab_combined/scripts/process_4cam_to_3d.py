import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def load_intrinsics(path):
    with open(path, 'r') as f:
        data = json.load(f)
    K = np.array(data["camera_matrix"], dtype=np.float64)
    D = np.array(data["distortion_coefficients"], dtype=np.float64)
    if D.ndim == 2:
        D = D[0]
    return K, D


def load_extrinsics(path):
    with open(path, 'r') as f:
        data = json.load(f)
    cams = {}
    for name, cam in data.items():
        rvec = np.array(cam["rvec"], dtype=np.float64).reshape(3, 1)
        tvec = np.array(cam["tvec"], dtype=np.float64).reshape(3, 1)
        # extrinsics_main.json is in meters -> convert to mm
        tvec = tvec * 1000.0
        R, _ = cv2.Rodrigues(rvec)
        P = np.hstack([R, tvec])  # world->cam (no K)
        cams[name] = {"R": R, "tvec": tvec, "P": P}
    return cams


def undistort_points(pt, K, D):
    pts = np.array([[pt]], dtype=np.float64)
    und = cv2.undistortPoints(pts, K, D)
    return und[0, 0]


def triangulate_multi(observations, proj_mats):
    # observations: {cam_name: (x,y)} with normalized coords
    if len(observations) < 2:
        return None
    A = []
    for cam, (x, y) in observations.items():
        P = proj_mats[cam]
        A.append(x * P[2] - P[0])
        A.append(y * P[2] - P[1])
    A = np.array(A)
    if A.shape[0] < 4:
        return None
    _, _, Vt = np.linalg.svd(A)
    X = Vt[-1]
    if abs(X[3]) < 1e-9:
        return None
    X = X[:3] / X[3]
    return X


def project_world_to_pixel(point_w, R, tvec, K, D):
    """Project a world 3D point (mm) to distorted image pixel coords."""
    rvec, _ = cv2.Rodrigues(R)
    pt = np.array(point_w, dtype=np.float64).reshape(1, 1, 3)
    uv, _ = cv2.projectPoints(pt, rvec, tvec, K, D)
    return uv.reshape(2)


def robust_triangulate_ball(
    obs_norm,
    obs_px,
    proj_mats,
    extr,
    intr,
    min_cams=2,
    max_reproj_px=20.0,
):
    """
    Triangulate with iterative camera rejection by reprojection error.
    Returns: (point_3d_mm or None, used_cams list, mean_reproj_px or None)
    """
    if len(obs_norm) < min_cams:
        return None, [], None

    active = dict(obs_norm)
    while len(active) >= min_cams:
        X = triangulate_multi(active, proj_mats)
        if X is None:
            return None, [], None

        reproj = {}
        for cam in list(active.keys()):
            uv = project_world_to_pixel(
                point_w=X,
                R=extr[cam]["R"],
                tvec=extr[cam]["tvec"],
                K=intr[cam]["K"],
                D=intr[cam]["D"],
            )
            reproj[cam] = float(np.linalg.norm(uv - obs_px[cam]))

        worst_cam = max(reproj, key=reproj.get)
        worst_err = reproj[worst_cam]
        if worst_err <= max_reproj_px:
            used = sorted(list(active.keys()))
            mean_err = float(np.mean(list(reproj.values())))
            return X, used, mean_err

        # Can't reject further if we already reached minimum camera count.
        if len(active) == min_cams:
            return None, [], worst_err

        del active[worst_cam]

    return None, [], None


def flatten_predictions(preds):
    """Flatten MMPose prediction outputs into a list of person dicts."""
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
    """Extract keypoints/scores and simple geometric stats for a person."""
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
        "valid": valid,
        "area": area,
        "mean_score": mean_score,
    }


def pose_distance(curr, prev, conf_thresh):
    """Mean 2D joint distance on overlapping confident joints."""
    valid_curr = curr["scores"] > conf_thresh
    valid_prev = prev["scores"] > conf_thresh
    common = valid_curr & valid_prev
    if np.count_nonzero(common) < 4:
        return np.inf
    diff = curr["kpts"][common] - prev["kpts"][common]
    d = np.linalg.norm(diff, axis=1)
    return float(np.mean(d))


def select_target_person(candidates, prev_state, conf_thresh, switch_area_ratio):
    """Pick one person per camera while keeping identity stable across frames."""
    if not candidates:
        return None

    if prev_state is None:
        # On first valid frame, favor large + confident person.
        return max(candidates, key=lambda c: c["area"] * max(0.1, c["mean_score"]))

    # Track by nearest pose first.
    tracked = min(candidates, key=lambda c: pose_distance(c, prev_state, conf_thresh))
    tracked_dist = pose_distance(tracked, prev_state, conf_thresh)

    # If tracking is weak, fall back to most dominant person.
    dominant = max(candidates, key=lambda c: c["area"] * max(0.1, c["mean_score"]))
    if np.isinf(tracked_dist):
        return dominant

    # Allow switching when a clearly larger confident person appears
    # (common when target enters after another person is already visible).
    if dominant is not tracked:
        if dominant["mean_score"] >= conf_thresh and dominant["area"] > tracked["area"] * switch_area_ratio:
            return dominant

    return tracked


def main():
    ap = argparse.ArgumentParser(description="Process 4 synchronized videos -> 3D ball + skeleton")
    ap.add_argument("--video-east", required=True)
    ap.add_argument("--video-north", required=True)
    ap.add_argument("--video-south", required=True)
    ap.add_argument("--video-west", required=True)
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--extrinsics", default="garage_lab_combined/cal/extrinsics/extrinsics_main.json")
    ap.add_argument("--out", default="garage_lab_combined/output/motion_capture_data_garage.json")
    ap.add_argument("--ball-model", default="archive/04_garage_backup/garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt")
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--ball-min-cams", type=int, default=2, help="Minimum cameras required for 3D ball triangulation")
    ap.add_argument("--ball-max-reproj-px", type=float, default=20.0, help="Reject ball 3D if reprojection error is above this threshold")
    ap.add_argument("--ball-ema-alpha", type=float, default=0.0, help="EMA smoothing for ball 3D (0=off, typical 0.2-0.4)")
    ap.add_argument("--ball-max-speed-mps", type=float, default=0.0, help="Reject ball jumps faster than this speed in m/s (0=off)")
    ap.add_argument("--pose", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--pose-conf", type=float, default=0.4)
    ap.add_argument("--pose-min-cams", type=int, default=2, help="Minimum cameras required to triangulate each 3D joint")
    ap.add_argument("--pose-start-frame", type=int, default=0, help="Ignore pose before this frame index")
    ap.add_argument("--switch-area-ratio", type=float, default=1.8, help="Allow person switch if new candidate area is larger by this ratio")
    ap.add_argument("--max-frames", type=int, default=0)
    args = ap.parse_args()

    cam_order = [
        ("camEast", args.video_east),
        ("camNorth", args.video_north),
        ("camSouth", args.video_south),
        ("camWest", args.video_west),
    ]

    # Load intrinsics per cam
    intr = {}
    for cam, _ in cam_order:
        path = Path(args.intrinsics_dir) / f"{cam}_intrinsics.json"
        K, D = load_intrinsics(path)
        intr[cam] = {"K": K, "D": D}

    # Load extrinsics (world->cam)
    extr = load_extrinsics(args.extrinsics)
    proj = {cam: extr[cam]["P"] for cam, _ in cam_order if cam in extr}

    # Models
    from ultralytics import YOLO
    ball_model = YOLO(args.ball_model)

    pose_infer = None
    if args.pose:
        try:
            from mmpose.apis import MMPoseInferencer
            try:
                pose_infer = MMPoseInferencer(pose2d='rtmpose-m_8xb256-420e-coco-256x192', det_model='rtmdet-m', device='cpu')
            except Exception:
                pose_infer = MMPoseInferencer(pose2d='human', device='cpu')
        except Exception as e:
            print(f"[WARN] MMPose not available: {e}. Pose disabled.")
            pose_infer = None

    caps = [cv2.VideoCapture(p) for _, p in cam_order]
    for cap, (_, path) in zip(caps, cam_order):
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open {path}")

    fps = caps[0].get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps <= 1.0:
        fps = 15.0
    dt = 1.0 / float(fps)

    frames_out = []
    pose_state = {cam: None for cam, _ in cam_order}
    prev_ball_3d = None
    idx = 0
    while True:
        frames = []
        for cap in caps:
            ret, frame = cap.read()
            if not ret:
                frames = None
                break
            frames.append(frame)
        if frames is None:
            break

        if args.max_frames > 0 and idx >= args.max_frames:
            break

        # Ball detection (batch)
        ball_obs = {}
        ball_obs_px = {}
        ball_results = ball_model(frames, conf=args.conf, verbose=False, stream=False)
        for (cam, _), res in zip(cam_order, ball_results):
            boxes = res.boxes
            if boxes is None or len(boxes) == 0:
                continue
            best = boxes.conf.argmax().item()
            box = boxes[best]
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            # undistort to normalized coords
            K = intr[cam]["K"]
            D = intr[cam]["D"]
            und = undistort_points((cx, cy), K, D)
            ball_obs[cam] = und
            ball_obs_px[cam] = np.array([cx, cy], dtype=np.float64)

        ball_3d = None
        ball_used_cams = []
        ball_reproj_px = None
        if len(ball_obs) >= max(2, int(args.ball_min_cams)):
            tri, used_cams, mean_reproj = robust_triangulate_ball(
                obs_norm=ball_obs,
                obs_px=ball_obs_px,
                proj_mats=proj,
                extr=extr,
                intr=intr,
                min_cams=max(2, int(args.ball_min_cams)),
                max_reproj_px=float(args.ball_max_reproj_px),
            )
            if tri is not None:
                # Optional max-speed gating to suppress physically impossible jumps.
                if prev_ball_3d is not None and args.ball_max_speed_mps > 0:
                    speed_mps = float(np.linalg.norm(tri - prev_ball_3d) / 1000.0 / dt)
                    if speed_mps > args.ball_max_speed_mps:
                        tri = None

                if tri is not None:
                    # Optional light EMA smoothing.
                    if prev_ball_3d is not None and args.ball_ema_alpha > 0:
                        alpha = float(args.ball_ema_alpha)
                        tri = alpha * tri + (1.0 - alpha) * prev_ball_3d
                    prev_ball_3d = tri
                    ball_3d = tri
                    ball_used_cams = used_cams
                    ball_reproj_px = mean_reproj

        # Pose detection
        joints_3d = [None] * 17
        if pose_infer is not None and idx >= args.pose_start_frame:
            # Run pose per frame batch
            try:
                res_list = list(pose_infer(frames, return_vis=False, batch_size=len(frames)))
            except Exception:
                res_list = []

            # Build per-cam keypoints
            per_cam_kpts = {}
            for (cam, _), res in zip(cam_order, res_list):
                preds = res.get('predictions', []) if isinstance(res, dict) else []
                person_dicts = flatten_predictions(preds)
                if not person_dicts:
                    per_cam_kpts[cam] = None
                    pose_state[cam] = None
                    continue

                candidates = []
                for p in person_dicts:
                    cand = extract_person_pose(p)
                    if cand is not None:
                        candidates.append(cand)

                if not candidates:
                    per_cam_kpts[cam] = None
                    pose_state[cam] = None
                    continue

                selected = select_target_person(
                    candidates=candidates,
                    prev_state=pose_state[cam],
                    conf_thresh=args.pose_conf,
                    switch_area_ratio=args.switch_area_ratio,
                )

                if selected is None:
                    per_cam_kpts[cam] = None
                    pose_state[cam] = None
                    continue

                pose_state[cam] = selected
                per_cam_kpts[cam] = (selected["kpts"], selected["scores"])

            # Triangulate per joint
            for j in range(17):
                obs_j = {}
                for cam, _ in cam_order:
                    kdat = per_cam_kpts.get(cam)
                    if kdat is None:
                        continue
                    kpts, scores = kdat
                    if len(kpts) <= j:
                        continue
                    if scores[j] < args.pose_conf:
                        continue
                    x, y = kpts[j]
                    und = undistort_points((x, y), intr[cam]["K"], intr[cam]["D"])
                    obs_j[cam] = und
                if len(obs_j) >= max(2, int(args.pose_min_cams)):
                    pt = triangulate_multi(obs_j, proj)
                    if pt is not None:
                        joints_3d[j] = pt.tolist()

        frame_out = {
            "ball": ball_3d.tolist() if ball_3d is not None else None,
            "ball_cams": ball_used_cams,
            "ball_reproj_px": ball_reproj_px,
            "joints": joints_3d,
        }
        frames_out.append(frame_out)

        if idx % 10 == 0:
            print(f"Processed frame {idx}")
        idx += 1

    for cap in caps:
        cap.release()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(frames_out, f, indent=2)
    print(f"[DONE] Saved {len(frames_out)} frames -> {out_path}")


if __name__ == "__main__":
    main()
