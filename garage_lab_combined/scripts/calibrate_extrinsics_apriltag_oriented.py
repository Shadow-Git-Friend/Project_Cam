import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml


# 8 possible corner permutations (rotations + mirrored rotations)
PERMUTATIONS = [
    [0, 1, 2, 3],
    [1, 2, 3, 0],
    [2, 3, 0, 1],
    [3, 0, 1, 2],
    [0, 3, 2, 1],
    [3, 2, 1, 0],
    [2, 1, 0, 3],
    [1, 0, 3, 2],
]

CAM_ORDER = ["camNorth", "camEast", "camSouth", "camWest"]


def load_cameras(config_path):
    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}
    cams = data.get("cameras", {})
    if not cams:
        raise ValueError(f"No cameras found in {config_path}")
    return cams


def parse_dimensions(path):
    with open(path, "r") as f:
        content = f.read()

    dims = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    for key in ("X", "Y", "Z"):
        m = re.search(rf"{key}\s*=\s*(\d+(?:\.\d+)?)\s*cm", content)
        if m:
            dims[key] = float(m.group(1)) * 10.0

    expected_cam_pos = {}
    for name in ("North", "East", "South", "West"):
        m = re.search(rf"Cam{name}\s*=\s*\(([^)]+)\)", content)
        if m:
            xyz_cm = [float(x.strip()) for x in m.group(1).split(",")]
            expected_cam_pos[f"cam{name}"] = np.array(xyz_cm, dtype=np.float64) * 10.0

    tags = {}
    parts = re.split(r"ID=(\d+):", content)
    for i in range(1, len(parts), 2):
        tag_id = int(parts[i])
        sec = parts[i + 1]
        hits = re.findall(r"c(\d)\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)", sec)
        if len(hits) != 4:
            continue
        corners = [None] * 4
        for c_idx_s, x_s, y_s, z_s in hits:
            c_idx = int(c_idx_s)
            corners[c_idx] = np.array(
                [float(x_s) * 10.0, float(y_s) * 10.0, float(z_s) * 10.0], dtype=np.float32
            )
        if all(c is not None for c in corners):
            tags[tag_id] = np.stack(corners, axis=0)

    return dims, expected_cam_pos, tags


def load_intrinsics(path):
    with open(path, "r") as f:
        data = json.load(f)
    k = np.array(data["camera_matrix"], dtype=np.float64)
    d = np.array(data["distortion_coefficients"], dtype=np.float64)
    if d.ndim == 2:
        d = d[0]
    width = data.get("image_width")
    height = data.get("image_height")
    return k, d, width, height


def camera_guess_from_position(cam_pos_mm, dims):
    center = np.array([dims["X"] * 0.5, dims["Y"] * 0.5, dims["Z"] * 0.4], dtype=np.float64)
    forward = center - cam_pos_mm
    forward /= np.linalg.norm(forward) + 1e-9

    up_guess = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    if abs(np.dot(forward, up_guess)) > 0.95:
        up_guess = np.array([0.0, 1.0, 0.0], dtype=np.float64)

    x_axis = np.cross(forward, up_guess)
    x_axis /= np.linalg.norm(x_axis) + 1e-9
    y_axis = np.cross(forward, x_axis)
    y_axis /= np.linalg.norm(y_axis) + 1e-9

    # Camera->World rotation columns are camera axes in world
    r_cw = np.stack([x_axis, y_axis, forward], axis=1)
    # World->Camera
    r_wc = r_cw.T
    rvec, _ = cv2.Rodrigues(r_wc)
    tvec = -r_wc @ cam_pos_mm.reshape(3, 1)
    return rvec.reshape(3, 1), tvec.reshape(3, 1)


def reproj_error(obj_pts, img_pts, rvec, tvec, k, d):
    proj, _ = cv2.projectPoints(obj_pts, rvec, tvec, k, d)
    proj = proj.reshape(-1, 2)
    diff = proj - img_pts
    return float(np.sqrt(np.mean(np.sum(diff * diff, axis=1))))


def load_observations(cam_name, images_root, tags_world, detector, resize_to=None, max_images=0):
    img_dir = Path(images_root) / cam_name
    if not img_dir.exists():
        return []
    files = sorted(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))
    if max_images > 0:
        files = files[:max_images]

    obs = []
    for p in files:
        im = cv2.imread(str(p))
        if im is None:
            continue
        if resize_to is not None and (im.shape[1], im.shape[0]) != resize_to:
            im = cv2.resize(im, resize_to)
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)
        if ids is None:
            continue
        for k in range(len(ids)):
            tag_id = int(ids[k][0])
            if tag_id not in tags_world:
                continue
            obs.append({"tag_id": tag_id, "corners_2d": corners[k][0].astype(np.float32)})
    return obs


def choose_perm_for_observation(tag_world, corners_2d, rvec, tvec, k, d):
    best_idx = 0
    best_err = np.inf
    for p_idx, perm in enumerate(PERMUTATIONS):
        obj = tag_world[np.array(perm, dtype=np.int32)]
        err = reproj_error(obj, corners_2d, rvec, tvec, k, d)
        if err < best_err:
            best_err = err
            best_idx = p_idx
    return best_idx, best_err


def solve_camera(cam_obs, tags_world, tag_perm, intr_k, intr_d, rvec_guess=None, tvec_guess=None, ransac_reproj=4.0):
    obj = []
    img = []
    for ob in cam_obs:
        tag_id = ob["tag_id"]
        perm_idx = tag_perm.get(tag_id, 0)
        perm = np.array(PERMUTATIONS[perm_idx], dtype=np.int32)
        obj.append(tags_world[tag_id][perm])
        img.append(ob["corners_2d"])
    if not obj:
        return None

    obj = np.concatenate(obj, axis=0).astype(np.float32)
    img = np.concatenate(img, axis=0).astype(np.float32)
    if len(obj) < 8:
        return None

    ok, rvec, tvec, inliers = cv2.solvePnPRansac(
        obj,
        img,
        intr_k,
        intr_d,
        rvec=rvec_guess,
        tvec=tvec_guess,
        useExtrinsicGuess=(rvec_guess is not None and tvec_guess is not None),
        reprojectionError=ransac_reproj,
        iterationsCount=500,
        confidence=0.999,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return None

    if inliers is not None and len(inliers) >= 12:
        obj_in = obj[inliers.flatten()]
        img_in = img[inliers.flatten()]
        ok2, rvec, tvec = cv2.solvePnP(
            obj_in,
            img_in,
            intr_k,
            intr_d,
            rvec=rvec,
            tvec=tvec,
            useExtrinsicGuess=True,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if ok2:
            err = reproj_error(obj_in, img_in, rvec, tvec, intr_k, intr_d)
            n_in = int(len(obj_in))
        else:
            err = reproj_error(obj, img, rvec, tvec, intr_k, intr_d)
            n_in = int(len(obj))
    else:
        err = reproj_error(obj, img, rvec, tvec, intr_k, intr_d)
        n_in = int(len(obj))

    rmat, _ = cv2.Rodrigues(rvec)
    cam_pos = (-rmat.T @ tvec).reshape(-1)
    return {
        "rvec": rvec.reshape(3, 1),
        "tvec": tvec.reshape(3, 1),
        "reprojection_error": err,
        "num_points": n_in,
        "camera_position": cam_pos,
    }


def main():
    ap = argparse.ArgumentParser(description="Extrinsics calibration with AprilTag corner-orientation recovery.")
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--images-root", default="garage-20260217T113109Z-3-001/garage/Scenario3")
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--dimensions", default="garage_lab_combined/cal/extrinsics/Dimensions.txt")
    ap.add_argument("--out", default="garage_lab_combined/cal/extrinsics/extrinsics_oriented.json")
    ap.add_argument("--iters", type=int, default=6)
    ap.add_argument("--max-images", type=int, default=0)
    ap.add_argument("--ransac-reproj", type=float, default=4.0)
    args = ap.parse_args()

    cams_cfg = load_cameras(args.config)
    dims, expected_pos, tags_world = parse_dimensions(args.dimensions)

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())

    intrinsics = {}
    observations = {}
    extr_state = {}

    active_cams = [c for c in CAM_ORDER if c in cams_cfg]
    for cam in active_cams:
        intr_path = Path(args.intrinsics_dir) / f"{cam}_intrinsics.json"
        if not intr_path.exists():
            print(f"[WARN] {cam}: intrinsics missing at {intr_path}")
            continue
        k, d, w, h = load_intrinsics(intr_path)
        intrinsics[cam] = (k, d, (int(w), int(h)) if w and h else None)

        obs = load_observations(
            cam_name=cam,
            images_root=args.images_root,
            tags_world=tags_world,
            detector=detector,
            resize_to=intrinsics[cam][2],
            max_images=args.max_images,
        )
        observations[cam] = obs
        print(f"[INFO] {cam}: loaded observations = {len(obs)}")

        if cam in expected_pos:
            rvec0, tvec0 = camera_guess_from_position(expected_pos[cam], dims)
            extr_state[cam] = {"rvec": rvec0, "tvec": tvec0}

    if not observations:
        raise RuntimeError("No observations loaded.")

    # Global per-tag permutation map
    tag_perm = {tag_id: 0 for tag_id in tags_world.keys()}

    for it in range(args.iters):
        # 1) Vote best permutations from current camera states
        votes = defaultdict(lambda: np.zeros(len(PERMUTATIONS), dtype=np.float64))
        for cam in active_cams:
            if cam not in extr_state or cam not in intrinsics:
                continue
            k, d, _ = intrinsics[cam]
            rvec = extr_state[cam]["rvec"]
            tvec = extr_state[cam]["tvec"]
            for ob in observations.get(cam, []):
                tag_id = ob["tag_id"]
                p_idx, p_err = choose_perm_for_observation(
                    tags_world[tag_id], ob["corners_2d"], rvec, tvec, k, d
                )
                votes[tag_id][p_idx] += 1.0 / max(0.5, p_err)

        changed = 0
        for tag_id, score_vec in votes.items():
            best = int(np.argmax(score_vec))
            if tag_perm.get(tag_id, 0) != best:
                changed += 1
                tag_perm[tag_id] = best

        # 2) Re-solve each camera using the current global tag permutations
        for cam in active_cams:
            if cam not in intrinsics:
                continue
            k, d, _ = intrinsics[cam]
            guess = extr_state.get(cam)
            rvec_guess = guess["rvec"] if guess is not None else None
            tvec_guess = guess["tvec"] if guess is not None else None
            solved = solve_camera(
                cam_obs=observations.get(cam, []),
                tags_world=tags_world,
                tag_perm=tag_perm,
                intr_k=k,
                intr_d=d,
                rvec_guess=rvec_guess,
                tvec_guess=tvec_guess,
                ransac_reproj=args.ransac_reproj,
            )
            if solved is not None:
                extr_state[cam] = {"rvec": solved["rvec"], "tvec": solved["tvec"]}

        # Report iteration
        report = []
        for cam in active_cams:
            if cam not in intrinsics or cam not in extr_state:
                continue
            k, d, _ = intrinsics[cam]
            solved = solve_camera(
                cam_obs=observations.get(cam, []),
                tags_world=tags_world,
                tag_perm=tag_perm,
                intr_k=k,
                intr_d=d,
                rvec_guess=extr_state[cam]["rvec"],
                tvec_guess=extr_state[cam]["tvec"],
                ransac_reproj=args.ransac_reproj,
            )
            if solved is None:
                continue
            c = solved["camera_position"]
            pos_err = None
            if cam in expected_pos:
                pos_err = float(np.linalg.norm(c - expected_pos[cam]))
            report.append((cam, solved["reprojection_error"], pos_err))
        msg = " | ".join(
            [
                f"{cam}: reproj={err:.2f}px, pos_err={pe:.0f}mm" if pe is not None else f"{cam}: reproj={err:.2f}px"
                for cam, err, pe in report
            ]
        )
        print(f"[ITER {it + 1}] perm_changed={changed} | {msg}")

    # Final solve + save
    out = {}
    for cam in active_cams:
        if cam not in intrinsics or cam not in extr_state:
            continue
        k, d, _ = intrinsics[cam]
        solved = solve_camera(
            cam_obs=observations.get(cam, []),
            tags_world=tags_world,
            tag_perm=tag_perm,
            intr_k=k,
            intr_d=d,
            rvec_guess=extr_state[cam]["rvec"],
            tvec_guess=extr_state[cam]["tvec"],
            ransac_reproj=args.ransac_reproj,
        )
        if solved is None:
            continue
        out[cam] = {
            "rvec": solved["rvec"].flatten().tolist(),
            "tvec": solved["tvec"].flatten().tolist(),
            "reprojection_error": float(solved["reprojection_error"]),
            "camera_position": solved["camera_position"].flatten().tolist(),
            "num_points": int(solved["num_points"]),
        }
        if cam in expected_pos:
            out[cam]["expected_camera_position"] = expected_pos[cam].tolist()
            out[cam]["camera_position_error_mm"] = float(
                np.linalg.norm(solved["camera_position"] - expected_pos[cam])
            )

    out_meta = {
        "tag_corner_permutation_index": {str(k): int(v) for k, v in tag_perm.items()},
        "permutations": PERMUTATIONS,
    }
    out["_meta"] = out_meta

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=4)
    print(f"[DONE] Saved: {out_path}")


if __name__ == "__main__":
    main()
