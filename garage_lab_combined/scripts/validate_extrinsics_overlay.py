import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np


def parse_dimensions(filepath, units="mm"):
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
            if units == "mm":
                # Dimensions.txt stores centimeters.
                x *= 10.0
                y *= 10.0
                z *= 10.0
            elif units == "m":
                x /= 100.0
                y /= 100.0
                z /= 100.0
            world_points[current_id][c_idx] = np.array([x, y, z], dtype=np.float32)

    # Convert dict to 4x3 arrays per tag
    tags = {}
    for tag_id, corners in world_points.items():
        if len(corners) != 4:
            continue
        tags[tag_id] = np.stack([corners[i] for i in range(4)], axis=0)
    return tags


def load_intrinsics(path):
    with open(path, 'r') as f:
        data = json.load(f)
    K = np.array(data["camera_matrix"], dtype=np.float64)
    D = np.array(data["distortion_coefficients"], dtype=np.float64)
    width = data.get("image_width")
    height = data.get("image_height")
    return K, D, width, height


def draw_poly(img, pts, color, thickness=2):
    pts = np.array(pts, dtype=np.float64)
    if not np.isfinite(pts).all():
        return
    pts = np.round(pts).astype(np.int32)
    for i in range(len(pts)):
        p1 = tuple(pts[i])
        p2 = tuple(pts[(i + 1) % len(pts)])
        cv2.line(img, p1, p2, color, thickness)


def main():
    ap = argparse.ArgumentParser(description="Validate extrinsics by projecting AprilTag corners onto images")
    ap.add_argument("--images-root", default="garage-20260217T113109Z-3-001/garage/Scenario3")
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--extrinsics", default="garage_lab_combined/cal/extrinsics/extrinsics_garage.json")
    ap.add_argument("--dimensions", default="garage-20260217T113109Z-3-001/garage/extrinsics_1/Dimensions.txt")
    ap.add_argument(
        "--world-units",
        choices=["m", "mm"],
        default="m",
        help="Units expected by extrinsics tvec (default: m for robust calibration outputs).",
    )
    ap.add_argument("--out-dir", default="garage_lab_combined/cal/extrinsics/overlay")
    ap.add_argument("--max-images", type=int, default=1)
    ap.add_argument("--resize", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    images_root = Path(args.images_root)
    intr_dir = Path(args.intrinsics_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tags_3d = parse_dimensions(args.dimensions, units=args.world_units)

    with open(args.extrinsics, 'r') as f:
        extr = json.load(f)

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, params)

    for cam_name, cam_ex in extr.items():
        img_dir = images_root / cam_name
        if not img_dir.exists():
            print(f"[WARN] {cam_name}: missing images dir {img_dir}")
            continue

        intr_path = intr_dir / f"{cam_name}_intrinsics.json"
        if not intr_path.exists():
            print(f"[WARN] {cam_name}: missing intrinsics {intr_path}")
            continue

        K, D, iw, ih = load_intrinsics(intr_path)
        rvec = np.array(cam_ex["rvec"], dtype=np.float64).reshape(3, 1)
        tvec = np.array(cam_ex["tvec"], dtype=np.float64).reshape(3, 1)

        img_files = sorted(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))
        if args.max_images > 0:
            img_files = img_files[: args.max_images]

        for img_path in img_files:
            img = cv2.imread(str(img_path))
            if img is None:
                continue

            if args.resize and iw and ih:
                if img.shape[1] != iw or img.shape[0] != ih:
                    img = cv2.resize(img, (int(iw), int(ih)))

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)

            # Draw detected tags in green
            if ids is not None:
                for i, tag_id_arr in enumerate(ids):
                    tag_id = int(tag_id_arr[0])
                    det = corners[i][0]
                    draw_poly(img, det, (0, 255, 0), 2)
                    c = det.mean(axis=0).astype(int)
                    cv2.putText(img, f"{tag_id}", tuple(c), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Draw projected tags in red (only those detected, to reduce clutter)
            if ids is not None:
                for tag_id_arr in ids:
                    tag_id = int(tag_id_arr[0])
                    if tag_id not in tags_3d:
                        continue
                    obj = tags_3d[tag_id]
                    proj, _ = cv2.projectPoints(obj, rvec, tvec, K, D)
                    proj = proj.reshape(-1, 2)
                    draw_poly(img, proj, (0, 0, 255), 2)
                    if np.isfinite(proj).all():
                        c = proj.mean(axis=0).astype(int)
                        # Slight offset so projected (red) label does not fully overlap detected (green) label.
                        cv2.putText(
                            img,
                            f"{tag_id}",
                            (int(c[0] + 6), int(c[1] - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 0, 255),
                            2,
                        )

            out_path = out_dir / f"{cam_name}_{img_path.name}"
            cv2.imwrite(str(out_path), img)
            print(f"[OK] {cam_name}: {out_path}")


if __name__ == "__main__":
    main()
