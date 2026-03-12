import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np
import yaml


def load_cameras(config_path):
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    cams = data.get('cameras', {}) if data else {}
    if not cams:
        raise ValueError(f"No cameras found in {config_path}")
    return cams


def parse_dimensions(filepath, to_mm=True):
    world_points = {}
    current_id = None
    with open(filepath, 'r') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        id_match = re.match(r"ID=(\d+):", line)
        if id_match:
            current_id = int(id_match.group(1))
            world_points[current_id] = {}
            continue

        corner_match = re.match(r"c(\d+)\s*\(([^,]+),\s*([^,]+),\s*([^\)]+)\)", line)
        if corner_match and current_id is not None:
            c_idx = int(corner_match.group(1))
            x = float(corner_match.group(2))
            y = float(corner_match.group(3))
            z = float(corner_match.group(4))
            if to_mm:
                x *= 10.0
                y *= 10.0
                z *= 10.0
            world_points[current_id][c_idx] = np.array([x, y, z], dtype=np.float32)

    return world_points


def load_intrinsics(path):
    with open(path, 'r') as f:
        data = json.load(f)
    K = np.array(data["camera_matrix"], dtype=np.float64)
    D = np.array(data["distortion_coefficients"], dtype=np.float64)
    width = data.get("image_width")
    height = data.get("image_height")
    return K, D, width, height


def compute_reproj_error(obj_points, img_points, rvec, tvec, K, D):
    proj, _ = cv2.projectPoints(obj_points, rvec, tvec, K, D)
    proj = proj.reshape(-1, 2)
    diff = proj - img_points
    err = np.sqrt(np.mean(np.sum(diff ** 2, axis=1)))
    return float(err)


def main():
    ap = argparse.ArgumentParser(description="Calibrate camera extrinsics using AprilTag grid and Dimensions.txt")
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--images-root", default="garage-20260217T113109Z-3-001/garage/Scenario3")
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--dimensions", default="garage-20260217T113109Z-3-001/garage/extrinsics_1/Dimensions.txt")
    ap.add_argument("--out", default="garage_lab_combined/cal/extrinsics/extrinsics_garage.json")
    ap.add_argument("--resize", action=argparse.BooleanOptionalAction, default=True,
                    help="Resize images to intrinsics resolution (default: on). Use --no-resize to disable.")
    ap.add_argument("--max-images", type=int, default=0)
    ap.add_argument("--ransac-reproj", type=float, default=8.0)
    args = ap.parse_args()

    cams = load_cameras(args.config)
    world_points = parse_dimensions(args.dimensions, to_mm=True)

    out = {}
    images_root = Path(args.images_root)
    intr_dir = Path(args.intrinsics_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, params)

    for cam_name in cams.keys():
        img_dir = images_root / cam_name
        if not img_dir.exists():
            print(f"[WARN] {cam_name}: missing images at {img_dir}")
            continue

        intr_path = intr_dir / f"{cam_name}_intrinsics.json"
        if not intr_path.exists():
            print(f"[WARN] {cam_name}: missing intrinsics {intr_path}")
            continue

        K, D, iw, ih = load_intrinsics(intr_path)

        img_files = sorted(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))
        if args.max_images > 0:
            img_files = img_files[: args.max_images]

        all_obj = []
        all_img = []
        used_imgs = 0
        used_tags = set()

        for img_path in img_files:
            img = cv2.imread(str(img_path))
            if img is None:
                continue

            if args.resize and iw and ih:
                if img.shape[1] != iw or img.shape[0] != ih:
                    img = cv2.resize(img, (int(iw), int(ih)))

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)
            if ids is None:
                continue

            for k, tag_id_arr in enumerate(ids):
                tag_id = int(tag_id_arr[0])
                if tag_id not in world_points:
                    continue

                tag_corners_2d = corners[k][0]  # (4,2)
                valid = True
                for c_idx in range(4):
                    if c_idx not in world_points[tag_id]:
                        valid = False
                        break
                if not valid:
                    continue

                for c_idx in range(4):
                    all_obj.append(world_points[tag_id][c_idx])
                    all_img.append(tag_corners_2d[c_idx])
                used_tags.add(tag_id)

            if len(used_tags) > 0:
                used_imgs += 1

        if len(all_obj) < 8:
            print(f"[WARN] {cam_name}: not enough points ({len(all_obj)})")
            continue

        all_obj = np.array(all_obj, dtype=np.float32)
        all_img = np.array(all_img, dtype=np.float32)

        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            all_obj,
            all_img,
            K,
            D,
            reprojectionError=args.ransac_reproj,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not ok:
            print(f"[WARN] {cam_name}: solvePnPRansac failed")
            continue

        # Refine with inliers if available
        if inliers is not None and len(inliers) >= 6:
            obj_in = all_obj[inliers.flatten()]
            img_in = all_img[inliers.flatten()]
            ok2, rvec, tvec = cv2.solvePnP(obj_in, img_in, K, D, rvec, tvec, useExtrinsicGuess=True)
            if not ok2:
                print(f"[WARN] {cam_name}: refine solvePnP failed, using RANSAC result")
                obj_in = all_obj
                img_in = all_img
        else:
            obj_in = all_obj
            img_in = all_img

        reproj = compute_reproj_error(obj_in, img_in, rvec, tvec, K, D)

        R, _ = cv2.Rodrigues(rvec)
        cam_pos = -R.T @ tvec

        out[cam_name] = {
            "rvec": rvec.flatten().tolist(),
            "tvec": tvec.flatten().tolist(),
            "reprojection_error": reproj,
            "camera_position": cam_pos.flatten().tolist(),
            "num_points": int(len(obj_in)),
            "num_images": int(used_imgs),
            "num_tags": int(len(used_tags)),
        }

        print(f"[OK] {cam_name}: reproj={reproj:.2f}px, tags={len(used_tags)}, imgs={used_imgs}")

    with open(out_path, 'w') as f:
        json.dump(out, f, indent=4)

    print(f"[DONE] Saved extrinsics -> {out_path}")


if __name__ == "__main__":
    main()
