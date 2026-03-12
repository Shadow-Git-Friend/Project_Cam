import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class CameraData:
    obj: np.ndarray
    img: np.ndarray
    tag_ids: np.ndarray
    num_images: int


def parse_dimensions(dimensions_path: Path):
    """Parse Dimensions.txt tag corners + expected camera positions (meters)."""
    tag_points = {}
    cam_expected = {}
    current_id = None

    with open(dimensions_path, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            tag_match = re.match(r"ID=(\d+):", line)
            if tag_match:
                current_id = int(tag_match.group(1))
                tag_points[current_id] = {}
                continue

            corner_match = re.match(r"c(\d+)\s*\(([^,]+),\s*([^,]+),\s*([^)]+)\)", line)
            if corner_match and current_id is not None:
                c_idx = int(corner_match.group(1))
                x = float(corner_match.group(2)) / 100.0
                y = float(corner_match.group(3)) / 100.0
                z = float(corner_match.group(4)) / 100.0
                tag_points[current_id][c_idx] = np.array([x, y, z], dtype=np.float32)
                continue

            cam_match = re.match(r"Cam([A-Za-z]+)\s*=\s*\(([^,]+),\s*([^,]+),\s*([^)]+)\)", line)
            if cam_match:
                name = f"cam{cam_match.group(1)}"
                x = float(cam_match.group(2)) / 100.0
                y = float(cam_match.group(3)) / 100.0
                z = float(cam_match.group(4)) / 100.0
                cam_expected[name] = np.array([x, y, z], dtype=np.float64)

    tags = {}
    for tag_id, corners in tag_points.items():
        if len(corners) == 4:
            tags[tag_id] = np.stack([corners[i] for i in range(4)], axis=0)

    return tags, cam_expected


def load_unified_intrinsics(path: Path):
    with open(path, "r") as f:
        data = json.load(f)
    K = np.array(data["camera_matrix"], dtype=np.float64)
    if "dist_coeffs" in data:
        D = np.array(data["dist_coeffs"], dtype=np.float64)
    else:
        D = np.array(data["distortion_coefficients"], dtype=np.float64)
    if D.ndim == 2 and D.shape[0] == 1:
        D = D[0]
    width = None
    height = None
    if "resolution" in data and isinstance(data["resolution"], list) and len(data["resolution"]) == 2:
        width, height = int(data["resolution"][0]), int(data["resolution"][1])
    return K, D, width, height


def load_cam_intrinsics(path: Path):
    with open(path, "r") as f:
        data = json.load(f)
    K = np.array(data["camera_matrix"], dtype=np.float64)
    D = np.array(data["distortion_coefficients"], dtype=np.float64)
    if D.ndim == 2 and D.shape[0] == 1:
        D = D[0]
    width = data.get("image_width")
    height = data.get("image_height")
    width = int(width) if width is not None else None
    height = int(height) if height is not None else None
    return K, D, width, height


def collect_points_for_camera(
    cam_name: str,
    images_root: Path,
    world_tags: dict,
    detector: cv2.aruco.ArucoDetector,
    max_images: int,
    target_size=None,
):
    cam_dir = images_root / cam_name
    if not cam_dir.exists():
        return None

    image_files = sorted(list(cam_dir.glob("*.jpg")) + list(cam_dir.glob("*.png")))
    if max_images > 0:
        image_files = image_files[:max_images]

    obj_pts = []
    img_pts = []
    tag_ids = []
    used_images = 0

    for img_path in image_files:
        image = cv2.imread(str(img_path))
        if image is None:
            continue
        if target_size is not None:
            tw, th = target_size
            if image.shape[1] != tw or image.shape[0] != th:
                image = cv2.resize(image, (tw, th))

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)
        if ids is None:
            continue

        had_any = False
        for i, tag_arr in enumerate(ids):
            tag_id = int(tag_arr[0])
            if tag_id not in world_tags:
                continue

            had_any = True
            detected = corners[i][0]  # (4,2)
            world = world_tags[tag_id]  # (4,3)
            for c in range(4):
                obj_pts.append(world[c])
                img_pts.append(detected[c])
                tag_ids.append(tag_id)

        if had_any:
            used_images += 1

    if not obj_pts:
        return None

    return CameraData(
        obj=np.array(obj_pts, dtype=np.float32),
        img=np.array(img_pts, dtype=np.float32),
        tag_ids=np.array(tag_ids, dtype=np.int32),
        num_images=used_images,
    )


def camera_position_from_rt(rvec, tvec):
    R, _ = cv2.Rodrigues(rvec)
    pos = -(R.T @ tvec).reshape(-1)
    return pos


def parse_cam_tags_map(raw: str):
    """
    Parse mapping like:
      camNorth:1,2,3;camEast:4,5
    Returns dict[str, set[int]].
    """
    out = {}
    raw = (raw or "").strip()
    if not raw:
        return out
    for block in raw.split(";"):
        block = block.strip()
        if not block:
            continue
        if ":" not in block:
            continue
        cam, ids_raw = block.split(":", 1)
        cam = cam.strip()
        ids = set()
        for tok in ids_raw.split(","):
            tok = tok.strip()
            if not tok:
                continue
            ids.add(int(tok))
        if cam and ids:
            out[cam] = ids
    return out


def point_errors(obj, img, rvec, tvec, K, D):
    proj, _ = cv2.projectPoints(obj, rvec, tvec, K, D)
    proj = proj.reshape(-1, 2)
    err = np.linalg.norm(proj - img, axis=1)
    return err


def robust_refine_pose(
    obj,
    img,
    tag_ids,
    K,
    D,
    init_rvec=None,
    init_tvec=None,
    max_iters=8,
    min_point_error_px=8.0,
    sigma_scale=2.5,
    tag_median_thresh_px=45.0,
    min_points=120,
    use_ransac_start=True,
):
    mask = np.ones(len(obj), dtype=bool)

    if init_rvec is not None and init_tvec is not None:
        rvec = np.array(init_rvec, dtype=np.float64).reshape(3, 1)
        tvec = np.array(init_tvec, dtype=np.float64).reshape(3, 1)
        ok, rvec, tvec = cv2.solvePnP(
            obj,
            img,
            K,
            D,
            rvec,
            tvec,
            useExtrinsicGuess=True,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return None
    elif use_ransac_start:
        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            obj,
            img,
            K,
            D,
            reprojectionError=max(12.0, min_point_error_px * 2.0),
            iterationsCount=5000,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            ok, rvec, tvec = cv2.solvePnP(obj, img, K, D, flags=cv2.SOLVEPNP_ITERATIVE)
            if not ok:
                return None
        elif inliers is not None and len(inliers) >= min_points:
            mask = np.zeros(len(obj), dtype=bool)
            mask[inliers.flatten()] = True
    else:
        ok, rvec, tvec = cv2.solvePnP(obj, img, K, D, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            return None

    for _ in range(max_iters):
        if int(mask.sum()) < min_points:
            break

        ok, rvec, tvec = cv2.solvePnP(
            obj[mask],
            img[mask],
            K,
            D,
            rvec,
            tvec,
            useExtrinsicGuess=True,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            break

        err = point_errors(obj[mask], img[mask], rvec, tvec, K, D)
        med = float(np.median(err))
        mad = float(np.median(np.abs(err - med)))
        sigma = 1.4826 * mad if mad > 1e-9 else 0.0
        point_thresh = max(min_point_error_px, med + sigma_scale * sigma)

        local_keep = err <= point_thresh

        # Tag-level rejection: remove tags whose median error is too large.
        local_tags = tag_ids[mask]
        if tag_median_thresh_px > 0:
            for tid in np.unique(local_tags):
                idx = local_tags == tid
                if np.count_nonzero(idx) < 8:
                    continue
                if float(np.median(err[idx])) > tag_median_thresh_px:
                    local_keep[idx] = False

        if int(np.count_nonzero(local_keep)) < min_points:
            break

        global_idx = np.where(mask)[0]
        new_mask = np.zeros_like(mask)
        new_mask[global_idx[local_keep]] = True

        if np.array_equal(new_mask, mask):
            break
        mask = new_mask

    if int(mask.sum()) < max(40, min_points // 2):
        return None

    ok, rvec, tvec = cv2.solvePnP(
        obj[mask],
        img[mask],
        K,
        D,
        rvec,
        tvec,
        useExtrinsicGuess=True,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return None

    err = point_errors(obj[mask], img[mask], rvec, tvec, K, D)
    return {
        "rvec": rvec,
        "tvec": tvec,
        "mask": mask,
        "errors": err,
    }


def main():
    ap = argparse.ArgumentParser(description="Robust AprilTag extrinsics calibration with outlier rejection.")
    ap.add_argument("--images-root", default="garage-20260217T113109Z-3-001/garage/Scenario2")
    ap.add_argument("--dimensions", default="garage_lab_combined/cal/extrinsics/Dimensions.txt")
    ap.add_argument("--out", default="garage_lab_combined/cal/extrinsics/extrinsics_robust.json")
    ap.add_argument("--max-images", type=int, default=50)
    ap.add_argument("--cameras", nargs="+", default=["camNorth", "camEast", "camSouth", "camWest"])
    ap.add_argument("--unified-intrinsics", default="garage-20260217T113109Z-3-001/garage/Intrinsics/unified_intrinsics.json")
    ap.add_argument("--intrinsics-dir", default="")
    ap.add_argument("--init-extrinsics", default="garage_lab_combined/cal/extrinsics/extrinsics_main.json")
    ap.add_argument("--max-iters", type=int, default=8)
    ap.add_argument("--min-point-error-px", type=float, default=8.0)
    ap.add_argument("--sigma-scale", type=float, default=2.5)
    ap.add_argument("--tag-median-thresh-px", type=float, default=45.0)
    ap.add_argument("--min-points", type=int, default=120)
    ap.add_argument("--max-position-error-m", type=float, default=0.75)
    ap.add_argument("--ransac-start", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--resize-to-intrinsics", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument(
        "--include-tags-map",
        default="",
        help="Optional per-camera include tags map: camNorth:1,2;camEast:3,4",
    )
    ap.add_argument(
        "--exclude-tags-map",
        default="",
        help="Optional per-camera exclude tags map: camNorth:10,11;camWest:22",
    )
    args = ap.parse_args()

    images_root = Path(args.images_root)
    dimensions_path = Path(args.dimensions)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    world_tags, expected_positions = parse_dimensions(dimensions_path)
    if not world_tags:
        raise RuntimeError(f"No tag corners parsed from {dimensions_path}")

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())

    unified_intrinsics = None
    if args.unified_intrinsics:
        unified_intrinsics = load_unified_intrinsics(Path(args.unified_intrinsics))

    init_extrinsics = {}
    if args.init_extrinsics:
        init_path = Path(args.init_extrinsics)
        if init_path.exists():
            with open(init_path, "r") as f:
                init_extrinsics = json.load(f)
        else:
            print(f"[WARN] init extrinsics file not found: {init_path}")

    out = {}
    include_map = parse_cam_tags_map(args.include_tags_map)
    exclude_map = parse_cam_tags_map(args.exclude_tags_map)
    for cam_name in args.cameras:
        if unified_intrinsics is not None:
            K, D, iw, ih = unified_intrinsics
        else:
            intr_path = Path(args.intrinsics_dir) / f"{cam_name}_intrinsics.json"
            if not intr_path.exists():
                print(f"[WARN] {cam_name}: missing intrinsics {intr_path}")
                continue
            K, D, iw, ih = load_cam_intrinsics(intr_path)

        target_size = None
        if args.resize_to_intrinsics and iw is not None and ih is not None:
            target_size = (int(iw), int(ih))

        cam_data = collect_points_for_camera(
            cam_name=cam_name,
            images_root=images_root,
            world_tags=world_tags,
            detector=detector,
            max_images=args.max_images,
            target_size=target_size,
        )
        if cam_data is None:
            print(f"[WARN] {cam_name}: no detections")
            continue

        # Optional per-camera tag filtering.
        keep_mask = np.ones(len(cam_data.tag_ids), dtype=bool)
        include_tags = include_map.get(cam_name)
        if include_tags:
            keep_mask &= np.isin(cam_data.tag_ids, list(include_tags))
        exclude_tags = exclude_map.get(cam_name)
        if exclude_tags:
            keep_mask &= ~np.isin(cam_data.tag_ids, list(exclude_tags))

        if int(np.count_nonzero(keep_mask)) < 40:
            print(f"[WARN] {cam_name}: too few points after tag filtering")
            continue

        if not np.all(keep_mask):
            cam_data = CameraData(
                obj=cam_data.obj[keep_mask],
                img=cam_data.img[keep_mask],
                tag_ids=cam_data.tag_ids[keep_mask],
                num_images=cam_data.num_images,
            )

        fit = robust_refine_pose(
            obj=cam_data.obj,
            img=cam_data.img,
            tag_ids=cam_data.tag_ids,
            K=K,
            D=D,
            init_rvec=init_extrinsics.get(cam_name, {}).get("rvec"),
            init_tvec=init_extrinsics.get(cam_name, {}).get("tvec"),
            max_iters=args.max_iters,
            min_point_error_px=args.min_point_error_px,
            sigma_scale=args.sigma_scale,
            tag_median_thresh_px=args.tag_median_thresh_px,
            min_points=args.min_points,
            use_ransac_start=args.ransac_start,
        )
        if fit is None:
            print(f"[WARN] {cam_name}: robust fit failed")
            continue

        rvec = fit["rvec"]
        tvec = fit["tvec"]
        inlier_mask = fit["mask"]
        errors = fit["errors"]

        cam_pos = camera_position_from_rt(rvec, tvec)
        exp = expected_positions.get(cam_name)
        pos_err = float(np.linalg.norm(cam_pos - exp)) if exp is not None else None

        local_tags = cam_data.tag_ids[inlier_mask]
        all_tags = cam_data.tag_ids
        inlier_tag_set = set(int(t) for t in np.unique(local_tags))
        all_tag_set = set(int(t) for t in np.unique(all_tags))
        removed_tags = sorted(list(all_tag_set - inlier_tag_set))

        if pos_err is not None and pos_err > args.max_position_error_m:
            print(
                f"[WARN] {cam_name}: position drift {pos_err:.3f}m exceeds "
                f"max {args.max_position_error_m:.3f}m"
            )

        out[cam_name] = {
            "rvec": rvec.reshape(-1).tolist(),
            "tvec": tvec.reshape(-1).tolist(),
            "camera_position": cam_pos.tolist(),
            "reprojection_error": float(np.sqrt(np.mean(errors ** 2))),
            "reprojection_error_rmse": float(np.sqrt(np.mean(errors ** 2))),
            "reprojection_error_mean": float(np.mean(errors)),
            "reprojection_error_median": float(np.median(errors)),
            "reprojection_error_p95": float(np.percentile(errors, 95)),
            "num_points_total": int(len(cam_data.obj)),
            "num_points_inlier": int(np.count_nonzero(inlier_mask)),
            "num_images": int(cam_data.num_images),
            "num_tags_total": int(len(all_tag_set)),
            "num_tags_inlier": int(len(inlier_tag_set)),
            "removed_tag_ids": removed_tags,
            "expected_camera_position": exp.tolist() if exp is not None else None,
            "camera_position_error_m": pos_err,
        }

        msg = (
            f"[OK] {cam_name}: rmse={out[cam_name]['reprojection_error_rmse']:.2f}px, "
            f"inliers={out[cam_name]['num_points_inlier']}/{out[cam_name]['num_points_total']}, "
            f"pos_err={pos_err:.3f}m" if pos_err is not None else
            f"[OK] {cam_name}: rmse={out[cam_name]['reprojection_error_rmse']:.2f}px"
        )
        print(msg)

    with open(out_path, "w") as f:
        json.dump(out, f, indent=4)
    print(f"[DONE] Saved {out_path}")


if __name__ == "__main__":
    main()
