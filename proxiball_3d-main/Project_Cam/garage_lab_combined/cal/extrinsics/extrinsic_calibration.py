import cv2
import numpy as np
import os
import glob
import json
import re
import yaml
import sys
import argparse


def parse_dimensions(filepath):
    """
    Parses Dimensions.txt to extract 3D world coordinates for each AprilTag corner.
    Returns a dictionary: {tag_id: {corner_index: np.array([x, y, z])}}
    """
    world_points = {}
    current_id = None

    with open(filepath, 'r') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match ID line, e.g., "ID=16:"
        id_match = re.match(r"ID=(\d+):", line)
        if id_match:
            current_id = int(id_match.group(1))
            world_points[current_id] = {}
            continue

        # Match corner line, e.g., "c0 (376, 122, 4)" or "c0(376, 122, 4)"
        corner_match = re.match(
            r"c(\d+)\s*\(([\d\.]+),\s*([\d\.]+),\s*([\d\.]+)\)", line)

        if corner_match and current_id is not None:
            c_idx = int(corner_match.group(1))
            x = float(corner_match.group(2))
            y = float(corner_match.group(3))
            z = float(corner_match.group(4))

            # Convert to meters
            world_points[current_id][c_idx] = np.array([x, y, z]) / 100.0

    return world_points


def load_intrinsics(filepath):
    """
    Loads camera matrix and distortion coefficients from .npz file (or .json).
    """
    if filepath.endswith('.npz'):
        with np.load(filepath) as data:
            if 'camera_matrix' in data and 'dist_coeffs' in data:
                camera_matrix = data['camera_matrix']
                dist_coeffs = data['dist_coeffs']
            elif 'mtx' in data and 'dist' in data:  # Common opencv save names
                camera_matrix = data['mtx']
                dist_coeffs = data['dist']
            else:
                camera_matrix = data['camera_matrix']
                dist_coeffs = data['dist_coeffs']
    elif filepath.endswith('.json'):
        with open(filepath, 'r') as f:
            data = json.load(f)
        camera_matrix = np.array(data["camera_matrix"])
        dist_coeffs = np.array(data["dist_coeffs"])
    else:
        raise ValueError(f"Unsupported file extension: {filepath}")

    return camera_matrix, dist_coeffs


def compute_reprojection_error(object_points, image_points, rvec, tvec, camera_matrix, dist_coeffs):
    """
    Computes global RMS reprojection error.
    """
    projected_points, _ = cv2.projectPoints(
        object_points, rvec, tvec, camera_matrix, dist_coeffs)
    diff = projected_points.squeeze() - image_points
    sq_dist = np.sum(diff**2, axis=1)
    error = np.sqrt(np.mean(sq_dist))
    return error, projected_points.squeeze()


def process_camera(camera_name, image_dir, intrinsics, world_points_dict, excluded_tags=None, max_reproj_error=8.0, cluster_search=False, loose=False):
    """
    Detects tags in images and computes extrinsic calibration using iterative RANSAC.
    """
    print(f"[{camera_name}] Processing 50 images...")

    # Increase threshold for loose mode
    ransac_thresh = 100.0 if loose else 8.0

    # ... (existing detection code) ...
    # Wait, I need to be careful with the lines I am replacing.
    # I am targeting the function start around line 87.
    pass

# Abort tool call again. I need to replace lines 87 and lines 170-250 separately or in one large block.
# Let's do it in blocks.

# Block 1: Signature
    if excluded_tags is None:
        excluded_tags = set()

    camera_matrix, dist_coeffs = intrinsics

    image_files = sorted(glob.glob(os.path.join(image_dir, "*.jpg")))
    if not image_files:
        print(f"[{camera_name}] No images found in {image_dir}")
        return None

    # Using DICT_APRILTAG_36h11
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    all_object_points = []
    all_image_points = []
    all_tag_ids = []

    # Track which tag ID each point belongs to for later filtering
    point_indices_to_tag_id = []

    print(f"[{camera_name}] Processing {len(image_files)} images...")

    valid_detections_count = 0

    for i, img_path in enumerate(image_files):
        img = cv2.imread(img_path)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray)

        if ids is not None:
            for k, tag_id_arr in enumerate(ids):
                tag_id = int(tag_id_arr[0])

                if tag_id in excluded_tags:
                    continue

                if tag_id in world_points_dict:
                    tag_corners_2d = corners[k][0]  # (4, 2)

                    valid_corners = True
                    for c_idx in range(4):
                        if c_idx not in world_points_dict[tag_id]:
                            valid_corners = False
                            break

                    if valid_corners:
                        for c_idx in range(4):
                            obj_pt = world_points_dict[tag_id][c_idx]
                            all_object_points.append(obj_pt)
                            img_pt = tag_corners_2d[c_idx]
                            all_image_points.append(img_pt)
                            point_indices_to_tag_id.append(tag_id)

                        valid_detections_count += 1
                        all_tag_ids.append(tag_id)

    if not all_object_points:
        print(
            f"[{camera_name}] No valid tokens matched with world coordinates (after exclusions).")
        return None

    all_object_points = np.array(all_object_points, dtype=np.float32)
    all_image_points = np.array(all_image_points, dtype=np.float32)
    point_indices_to_tag_id = np.array(point_indices_to_tag_id)

    print(f"[{camera_name}] Initial points: {len(all_object_points)} from {valid_detections_count} detections.")
    print(
        f"[{camera_name}] Unique tags used for RANSAC: {sorted(list(set(all_tag_ids)))}")

    # --- Step 1: Initial RANSAC ---
    # solvePnPRansac is robust to outliers
    ransac_thresh = 100.0 if loose else 8.0

    ret, rvec, tvec, inliers = cv2.solvePnPRansac(
        all_object_points, all_image_points, camera_matrix, dist_coeffs,
        reprojectionError=ransac_thresh,  # High threshold for loose mode
        flags=cv2.SOLVEPNP_ITERATIVE
    )

    if not ret:
        print(f"[{camera_name}] solvePnPRansac failed.")
        return None

    # In loose mode, we skip cluster search to accept the broad result
    if loose:
        print(
            f"[{camera_name}] Loose mode: Accepting initial RANSAC result regardless of inliers.")

        # Calculate initial error
        initial_error, projected_final = compute_reprojection_error(
            all_object_points, all_image_points, rvec, tvec, camera_matrix, dist_coeffs)
        print(f"[{camera_name}] Loose Reprojection Error: {initial_error:.4f} pixels")

        # Calculate per-tag stats for reporting (crucial for user)
        proj = projected_final
        real = all_image_points
        tag_errors = {}

        diff = proj - real
        dist = np.linalg.norm(diff, axis=1)

        for i, tag_id in enumerate(point_indices_to_tag_id):
            if tag_id not in tag_errors:
                tag_errors[tag_id] = []
            tag_errors[tag_id].append(dist[i])

        sorted_errors = []
        for tag_id, errs in tag_errors.items():
            sorted_errors.append((tag_id, np.mean(errs), len(errs)/4))
        sorted_errors.sort(key=lambda x: x[1], reverse=True)

        print(f"[{camera_name}] Top 5 Worst Tags (Loose Mode):")
        for tag_id, mean_err, count in sorted_errors[:5]:
            print(
                f"  Tag {tag_id}: {mean_err:.4f} px ({int(count)} detections)")

        # Construct result immediately, skipping refinement
        R, _ = cv2.Rodrigues(rvec)
        camera_pos = -np.dot(R.T, tvec)
        print(
            f"[{camera_name}] Estimated Camera Position (World): {camera_pos.flatten()}")

        return {
            "rvec": rvec.flatten().tolist(),
            "tvec": tvec.flatten().tolist(),
            "reprojection_error": float(initial_error),
            "camera_position": camera_pos.flatten().tolist(),
            "per_tag_errors": {int(t): float(e) for t, e, c in sorted_errors},
            "excluded_tags_static": [int(x) for x in excluded_tags],
            "excluded_tags_dynamic": []
        }

    # Check how many unique tags are in the inliers
    if inliers is not None:
        inlier_indices = inliers.flatten()
        inlier_tag_ids = point_indices_to_tag_id[inlier_indices]
        unique_inlier_tags = np.unique(inlier_tag_ids)
        print(f"[{camera_name}] Initial RANSAC inlier tags: {unique_inlier_tags} (Count: {len(unique_inlier_tags)})")

        # --- CLUSTER SEARCH LOGIC (EXPERIMENTAL) ---
        if cluster_search:
            # If RANSAC returns very few tags (e.g. < 4) but we have many more available,
            # it might have locked onto a small, consistent but wrong set (or just one tag).
            if len(unique_inlier_tags) < 4 and len(np.unique(point_indices_to_tag_id)) > 4:
                print(
                    f"[{camera_name}] ⚠️  RANSAC locked on few tags {unique_inlier_tags}. Searching for larger cluster...")

                # 1. Try excluding the "winner" tags to see if a bigger group exists
                mask = np.isin(point_indices_to_tag_id, list(
                    unique_inlier_tags), invert=True)
                if np.sum(mask) > 10:
                    pts_obj_2 = all_object_points[mask]
                    pts_img_2 = all_image_points[mask]

                    ret2, rvec2, tvec2, inliers2 = cv2.solvePnPRansac(
                        pts_obj_2, pts_img_2, camera_matrix, dist_coeffs,
                        reprojectionError=8.0,
                        flags=cv2.SOLVEPNP_ITERATIVE
                    )

                    if ret2 and inliers2 is not None:
                        # Map inliers back to tags
                        # We need to subset the tag map properly
                        subset_tag_ids = point_indices_to_tag_id[mask]
                        inliers_idx_2 = inliers2.flatten()
                        unique_inlier_tags_2 = np.unique(
                            subset_tag_ids[inliers_idx_2])

                        print(
                            f"[{camera_name}] Alternative cluster found: {unique_inlier_tags_2} (Count: {len(unique_inlier_tags_2)})")

                        if len(unique_inlier_tags_2) > len(unique_inlier_tags):
                            print(
                                f"[{camera_name}] ✨ Switching to larger cluster!")
                            rvec, tvec = rvec2, tvec2

            # Special logic for camWest conflict (North vs East)
            if camera_name == "camWest":
                print(
                    f"[{camera_name}] 🧩 Trying forced wall selection (North vs East)...")

                north_tags = [23, 5, 7, 8, 9]
                east_tags = [18, 17, 19, 20, 0, 16]

                def try_tags(tag_list, name):
                    mask = np.isin(point_indices_to_tag_id, tag_list)
                    if np.sum(mask) < 4:
                        return None

                    p_obj = all_object_points[mask]
                    p_img = all_image_points[mask]

                    ret_w, rvec_w, tvec_w, inliers_w = cv2.solvePnPRansac(
                        p_obj, p_img, camera_matrix, dist_coeffs,
                        reprojectionError=8.0, flags=cv2.SOLVEPNP_ITERATIVE
                    )

                    if ret_w and inliers_w is not None:
                        count = len(inliers_w)
                        # Check error
                        proj, _ = cv2.projectPoints(
                            p_obj[inliers_w.flatten()], rvec_w, tvec_w, camera_matrix, dist_coeffs)
                        err = np.linalg.norm(
                            proj.squeeze() - p_img[inliers_w.flatten()], axis=1).mean()
                        return (rvec_w, tvec_w, count, err)
                    return None

                res_north = try_tags(north_tags, "North")
                res_east = try_tags(east_tags, "East")

                best_wall_res = None
                best_wall_name = None

                if res_north:
                    print(
                        f"  North Wall: {res_north[2]} inliers, {res_north[3]:.2f} px error")
                if res_east:
                    print(
                        f"  East Wall: {res_east[2]} inliers, {res_east[3]:.2f} px error")

                # Logic: prefer more inliers, then lower error
                if res_north and res_east:
                    if res_north[2] > res_east[2]:
                        best_wall_res, best_wall_name = res_north, "North"
                    elif res_east[2] > res_north[2]:
                        best_wall_res, best_wall_name = res_east, "East"
                    else:
                        if res_north[3] < res_east[3]:
                            best_wall_res, best_wall_name = res_north, "North"
                        else:
                            best_wall_res, best_wall_name = res_east, "East"
                elif res_north:
                    best_wall_res, best_wall_name = res_north, "North"
                elif res_east:
                    best_wall_res, best_wall_name = res_east, "East"

                if best_wall_res and best_wall_res[2] > len(unique_inlier_tags):
                    print(
                        f"[{camera_name}] ✨ Switching to {best_wall_name} Wall specific solution!")
                    rvec, tvec = best_wall_res[0], best_wall_res[1]

    # Calculate initial error
    initial_error, _ = compute_reprojection_error(
        all_object_points, all_image_points, rvec, tvec, camera_matrix, dist_coeffs)
    print(
        f"[{camera_name}] Initial RANSAC Reprojection Error: {initial_error:.4f} pixels")

    # --- Step 2: Iterative Refinement ---
    # We will loop:
    # 1. Compute per-tag errors
    # 2. Add bad tags to temporary exclusion list
    # 3. Re-solve PnP with remaining points
    # 4. Repeat until all tags are below threshold

    current_object_points = all_object_points
    current_image_points = all_image_points
    current_tag_ids_map = point_indices_to_tag_id

    refined_rvec = rvec
    refined_tvec = tvec

    # Store dynamic exclusions for reporting
    dynamic_exclusions = set()

    max_iterations = 5
    for iteration in range(max_iterations):
        # Compute errors with current pose
        err, projected_pts = compute_reprojection_error(
            current_object_points, current_image_points, refined_rvec, refined_tvec, camera_matrix, dist_coeffs)

        # Calculate per-tag errors
        # Reshape to (N_tags, 4, 2) to average error per tag
        # Note: current_object_points length is always multiple of 4

        n_points = len(current_object_points)
        diffs = projected_pts - current_image_points
        dists = np.linalg.norm(diffs, axis=1)

        # Identify tags to remove
        tags_to_remove = set()

        # Map tag_id -> list of errors
        tag_error_map = {}
        unique_tags = np.unique(current_tag_ids_map)

        for tag_id in unique_tags:
            indices = np.where(current_tag_ids_map == tag_id)[0]
            if len(indices) == 0:
                continue

            tag_mean_err = np.mean(dists[indices])
            tag_error_map[tag_id] = tag_mean_err

            if tag_mean_err > max_reproj_error:
                tags_to_remove.add(tag_id)

        if not tags_to_remove:
            # Convergence: no more tags to remove
            break

        print(
            f"[{camera_name}] Iteration {iteration+1}: Removing high-error tags: {tags_to_remove}")
        dynamic_exclusions.update(tags_to_remove)

        # Filter points
        mask = np.isin(current_tag_ids_map, list(tags_to_remove), invert=True)
        current_object_points = current_object_points[mask]
        current_image_points = current_image_points[mask]
        current_tag_ids_map = current_tag_ids_map[mask]

        if len(current_object_points) < 4:
            print(f"[{camera_name}] Too few points left after filtering!")
            break

        # Re-solve PnP (non-RANSAC, strict iterative) on clean set
        refined_rvec, refined_tvec = cv2.solvePnP(
            current_object_points, current_image_points, camera_matrix, dist_coeffs
        )[1:3]

    if len(current_object_points) < 4:
        print(
            f"[{camera_name}] Failed: Too few points ({len(current_object_points)}) for final solution.")
        return None

    # --- Final Result ---
    final_error, projected_final = compute_reprojection_error(
        current_object_points, current_image_points, refined_rvec, refined_tvec, camera_matrix, dist_coeffs)

    print(f"[{camera_name}] Final Reprojection Error: {final_error:.4f} pixels")
    print(f"[{camera_name}] Dynamically excluded tags: {list(dynamic_exclusions)}")

    # Calculate final per-tag stats for reporting
    proj = projected_final
    real = current_image_points
    tag_errors = {}

    # We need to iterate carefully since points are just a filtered array now
    # Re-map errors to tags
    diff = proj - real
    dist = np.linalg.norm(diff, axis=1)

    for i, tag_id in enumerate(current_tag_ids_map):
        if tag_id not in tag_errors:
            tag_errors[tag_id] = []
        tag_errors[tag_id].append(dist[i])

    sorted_errors = []
    for tag_id, errs in tag_errors.items():
        # count is detections (4 pts per detection)
        sorted_errors.append((tag_id, np.mean(errs), len(errs)/4))

    sorted_errors.sort(key=lambda x: x[1], reverse=True)

    print(f"[{camera_name}] Top 5 Worst Tags (Remaining):")
    for tag_id, mean_err, count in sorted_errors[:5]:
        print(f"  Tag {tag_id}: {mean_err:.4f} px ({int(count)} detections)")

    R, _ = cv2.Rodrigues(refined_rvec)
    camera_pos = -np.dot(R.T, refined_tvec)
    print(f"[{camera_name}] Estimated Camera Position (World): {camera_pos.flatten()}")

    return {
        "rvec": refined_rvec.flatten().tolist(),
        "tvec": refined_tvec.flatten().tolist(),
        "reprojection_error": float(final_error),
        "camera_position": camera_pos.flatten().tolist(),
        "per_tag_errors": {int(t): float(e) for t, e, c in sorted_errors},
        "excluded_tags_static": [int(x) for x in excluded_tags],
        "excluded_tags_dynamic": [int(x) for x in dynamic_exclusions]
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extrinsic Camera Calibration")
    parser.add_argument("--camera", type=str, default=None,
                        help="Process only specific camera (e.g. camEast)")
    parser.add_argument("--output", type=str, default="extrinsic_results.json",
                        help="Output filename (e.g. extrinsic_results.json)")
    parser.add_argument("--cluster-search", action="store_true",
                        help="Enable experimental cluster search to find consistent tag subsets.")
    parser.add_argument("--loose", action="store_true",
                        help="Enable loose mode: high RANSAC threshold, no iterative filtering (reproduces high-error results).")
    args = parser.parse_args()

    root_dir = "/home/altay/Desktop/Footbonaut/garage/Scenario2"
    dimensions_file = os.path.join(root_dir, "Dimensions.txt")
    intrinsics_file = "/home/altay/Desktop/Footbonaut/garage/Intrinsics/unified_intrinsics.npz"

    # ... (Loading world points and intrinsics) ...

    # 1. Parse World Points
    print("Parsing dimensions...")
    world_points = parse_dimensions(dimensions_file)
    print(f"Loaded {len(world_points)} tags.")

    if len(world_points) == 0:
        print("CRITICAL ERROR: No world points parsed.")
        return

    # 2. Load Intrinsics
    print(f"Loading intrinsics from {intrinsics_file}...")
    if not os.path.exists(intrinsics_file):
        print(f"Error: Intrinsics file not found at {intrinsics_file}")
        return
    intrinsics = load_intrinsics(intrinsics_file)

    # 3. Process Cameras
    if args.camera:
        cameras = [args.camera]
    else:
        cameras = ["camNorth", "camEast", "camSouth", "camWest"]

    # Global Exclusion List (from action plan)
    GLOBAL_EXCLUDES = {14, 17, 18, 20, 21, 22}

    # Per-camera extra excludes (optional defaults)
    CAMERA_SPECIFIC_EXCLUDES = {
        "camEast": {13, 6},
        "camWest": {9},
        "camSouth": {19},
        "camNorth": {}
    }

    results = {}

    for cam in cameras:
        cam_dir = os.path.join(root_dir, cam)
        if os.path.isdir(cam_dir):
            excludes = GLOBAL_EXCLUDES.union(
                CAMERA_SPECIFIC_EXCLUDES.get(cam, set()))
            print(f"\n--- Processing {cam} (Excluding: {excludes}) ---")

            if args.cluster_search:
                print(f"[{cam}] ⚡ Cluster Search Mode Enabled")

            # We pass the flag down? Or modify process_camera signature?
            # Let's modify process_camera to accept a 'cluster_search' boolean.

            # Pass flags down
            res = process_camera(cam, cam_dir, intrinsics,
                                 world_points, excluded_tags=excludes,
                                 cluster_search=args.cluster_search,
                                 loose=args.loose)
            if res:
                results[cam] = res
        else:
            print(f"Warning: Directory {cam_dir} not found.")

    # 4. Save Results
    if results:
        # Determine output filename
        output_filename = args.output if args.output else "extrinsic_results.json"
        output_path = os.path.join(root_dir, output_filename)

        # We might want to read existing if we are just updating one camera,
        # but for clean baseline, maybe we just overwrite?
        # The user said "do not overflood... save it like extrinsics_1".
        # Let's trust the argument.

        print(f"\nSaving calibration results to {output_path}")
        with open(output_path, "w") as f:
            json.dump(results, f, indent=4)

        # Also save as YAML for easier reading
        yaml_path = output_path.replace(".json", ".yaml")
        with open(yaml_path, "w") as f:
            yaml.dump(results, f, default_flow_style=False)
    else:
        print("\nNo calibration results produced.")


if __name__ == "__main__":
    main()
