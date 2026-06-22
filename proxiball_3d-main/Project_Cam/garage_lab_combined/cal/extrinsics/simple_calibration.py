import cv2
import numpy as np
import os
import glob
import re
import yaml
import json


def parse_dimensions(filepath):
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
        elif current_id is not None:
            coord_match = re.match(
                r"c(\d)\(([\d\.]+),\s*([\d\.]+),\s*([\d\.]+)\)", line)
            if coord_match:
                cid = int(coord_match.group(1))
                x, y, z = float(coord_match.group(2)), float(
                    coord_match.group(3)), float(coord_match.group(4))
                # Convert cm to meters
                world_points[current_id][cid] = np.array([x, y, z]) / 100.0
    return world_points


def main():
    root_dir = "/home/altay/Desktop/Footbonaut/garage/Scenario2"
    dimensions_file = os.path.join(root_dir, "Dimensions.txt")
    intrinsics_file = "/home/altay/Desktop/Footbonaut/garage/Intrinsics/unified_intrinsics.npz"

    world_points = parse_dimensions(dimensions_file)
    world_points = parse_dimensions(dimensions_file)
    with np.load(intrinsics_file) as data:
        if 'camera_matrix' in data and 'dist_coeffs' in data:
            cm = data['camera_matrix']
            dc = data['dist_coeffs']
        elif 'mtx' in data and 'dist' in data:
            cm = data['mtx']
            dc = data['dist']
        else:
            # Fallback for some saves where it might be positional or different keys
            # But based on error, it was a KeyError.
            print("Keys found:", list(data.keys()))
            raise KeyError("Could not find camera_matrix/mtx in npz")

    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11)
    detector = cv2.aruco.ArucoDetector(
        dictionary, cv2.aruco.DetectorParameters())

    cameras = ["camNorth", "camEast", "camSouth", "camWest"]
    results = {}

    for cam in cameras:
        cam_dir = os.path.join(root_dir, cam)
        if not os.path.isdir(cam_dir):
            continue

        print(f"\n[{cam}] Processing...")
        all_obj = []
        all_img = []
        img_files = sorted(glob.glob(os.path.join(
            cam_dir, "*.jpg")))[:50]  # Use first 50

        for p in img_files:
            img = cv2.imread(p)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)

            if ids is not None:
                for i, tag_arr in enumerate(ids):
                    tid = int(tag_arr[0])
                    if tid in world_points:
                        for c in range(4):
                            all_obj.append(world_points[tid][c])
                            all_img.append(corners[i][0][c])

        if not all_obj:
            continue

        p_obj = np.array(all_obj, dtype=np.float32)
        p_img = np.array(all_img, dtype=np.float32)

        # SIMPLEST METHOD: NO RANSAC, JUST SOLVEPNP
        # Or basic RANSAC with default parameters if outliers are an issue?
        # User said "simplest method without complexities".
        # Standard solvePnP is simplest.

        try:
            # Use iterative or EPNP. Iterative is standard.
            ret, rvec, tvec = cv2.solvePnP(
                p_obj, p_img, cm, dc, flags=cv2.SOLVEPNP_ITERATIVE)

            # Reproject
            proj, _ = cv2.projectPoints(p_obj, rvec, tvec, cm, dc)
            err = np.linalg.norm(proj.squeeze() - p_img, axis=1).mean()

            # Calculate Position
            R, _ = cv2.Rodrigues(rvec)
            pos = -np.dot(R.T, tvec)

            print(f"  Pos: {pos.flatten()}")
            print(f"  Err: {err:.2f} px")

            results[cam] = {
                "rvec": rvec.flatten().tolist(),
                "tvec": tvec.flatten().tolist(),
                "reprojection_error": float(err),
                "camera_position": pos.flatten().tolist()
            }

        except Exception as e:
            print(f"  Failed: {e}")

    with open(os.path.join(root_dir, "extrinsic_results_simple.json"), "w") as f:
        json.dump(results, f, indent=4)

    print(
        f"\nSaved to {os.path.join(root_dir, 'extrinsic_results_simple.json')}")


if __name__ == "__main__":
    main()
