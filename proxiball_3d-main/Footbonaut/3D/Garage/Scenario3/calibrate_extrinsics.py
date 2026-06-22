import cv2
import numpy as np
import json
import glob
import os
import re

def parse_dimensions(filepath):
    """
    Parses Dimensions.txt to extract 3D coordinates of AprilTag corners.
    Returns: dict {tag_id: np.array of shape (4, 3)}
    Ordered as [TL, TR, BR, BL] for OpenCV Aruco.
    """
    tag_coords = {}
    current_id = None
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        id_match = re.match(r'ID=(\d+):', line)
        if id_match:
            current_id = int(id_match.group(1))
            tag_coords[current_id] = []
            continue
            
        coord_match = re.search(r'c\d\((.*?)\)', line)
        if coord_match and current_id is not None:
            content = coord_match.group(1)
            coords = [float(x.strip()) for x in content.split(',')]
            if len(coords) == 3:
                tag_coords[current_id].append(coords)
                
    final_coords = {}
    for tag_id, points in tag_coords.items():
        if len(points) == 4:
            pts = np.array(points, dtype=np.float32)
            # User confirmed: c0, c1, c2, c3 in file MATCH detector order 0, 1, 2, 3.
            # No reordering needed regardless of orientation.
            final_coords[tag_id] = pts
        else:
            print(f"Warning: ID {tag_id} has {len(points)} points, expected 4.")
            
    return final_coords

def load_intrinsics(filepath):
    """
    Loads intrinsics from JSON file.
    Returns: camera_matrix (3x3), dist_coeffs (5,)
    """
    with open(filepath, 'r') as f:
        data = json.load(f)
        
    K = np.array(data['camera_matrix'], dtype=np.float32)
    D = np.array(data['dist_coeffs'], dtype=np.float32)
    # The file has 'dist_coeffs' as a list of lists [[...]], take the first one
    if D.ndim == 2:
        D = D[0]
        
    return K, D

def detect_tags(image_path, aruco_dict):
    """
    Detects AprilTags in an image.
    Returns: corners, ids
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error reading {image_path}")
        return [], None
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
    corners, ids, rejected = detector.detectMarkers(gray)
    
    return corners, ids, img.shape[:2]

def main():
    base_dir = '/home/altay/Desktop/Footbonaut/Garage/Scenario3'
    dimensions_file = os.path.join(base_dir, 'Dimensions.txt')
    intrinsics_file = '/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json'
    
    print(f"Parsing dimensions from {dimensions_file}...")
    tag_3d_coords = parse_dimensions(dimensions_file)
    print(f"Loaded {len(tag_3d_coords)} tags.")
    
    print(f"Loading intrinsics from {intrinsics_file}...")
    K, D = load_intrinsics(intrinsics_file)
    print(f"Camera Matrix:\n{K}")
    print(f"Distortion Coeffs:\n{D}")
    
    # Updated to use DICT_APRILTAG_36h11 as specified in Garage/apriltags.py
    # Note: Dimensions.txt coords seem to be in cm. Output tvec will be in cm.
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    
    cameras = ['camNorth', 'camEast', 'camSouth', 'camWest']
    results = {}
    
    for cam_name in cameras:
        cam_dir = os.path.join(base_dir, cam_name)
        image_files = sorted(glob.glob(os.path.join(cam_dir, '*.jpg')) + glob.glob(os.path.join(cam_dir, '*.png')))
        if not image_files:
            # Try lowercase 'cam' prefix if CamelCase not found, or just list dir to be safe
            # But user said /home/altay/Desktop/Footbonaut/Garage/Scenario3 has these folders.
            # Let's double check if they exist or are empty.
            if not os.path.exists(cam_dir):
                print(f"Directory not found: {cam_dir}")
            else:
                print(f"No images found for {cam_name} in {cam_dir}")
            continue
            
        print(f"\nProcessing {cam_name} ({len(image_files)} images)...")
        
        all_obj_points = []
        all_img_points = []
        
        valid_images = 0
        tag_counts = {}

        for img_path in image_files:
            corners, ids, shape = detect_tags(img_path, aruco_dict)
            if ids is None:
                continue
                
            found_any = False
            for i, tag_id in enumerate(ids.flatten()):
                if tag_id in tag_3d_coords:
                    # 3D points for this tag from Dimensions.txt
                    obj_pts = tag_3d_coords[tag_id]
                    # 2D points detected in image (corners[i] is 1x4x2)
                    img_pts = corners[i].reshape(4, 2)
                    
                    all_obj_points.append(obj_pts)
                    all_img_points.append(img_pts)
                    
                    tag_counts[tag_id] = tag_counts.get(tag_id, 0) + 1
                    found_any = True
            
            if found_any:
                valid_images += 1
                
        if not all_obj_points:
            print(f"No valid tags detected for {cam_name}")
            continue
            
        # Convert to numpy arrays
        # solvePnP expects objectPoints (N, 3) and imagePoints (N, 2)
        # We can concatenate all points from all tags
        obj_points_np = np.vstack(all_obj_points).astype(np.float32)
        img_points_np = np.vstack(all_img_points).astype(np.float32)
        
        print(f"  Used {valid_images} images, {len(all_obj_points)} tags total.")
        print(f"  Tag counts: {tag_counts}")
        
        # Use RANSAC to handle outliers
        try:
            # Use USAC_MAGSAC or ITERATIVE with RANSAC
            success, rvec, tvec, inliers = cv2.solvePnPRansac(
                obj_points_np, 
                img_points_np, 
                K, D, 
                reprojectionError=8.0, 
                flags=cv2.SOLVEPNP_ITERATIVE,
                iterationsCount=1000
            )
        except Exception as e:
            print(f"  solvePnPRansac failed: {e}")
            continue
            
        if success:
            print(f"  RANSAC: {len(inliers)}/{len(obj_points_np)} points used.")
            
            # Refine with inliers only
            if inliers is not None and len(inliers) > 0:
                inliers = inliers.flatten()
                obj_inliers = obj_points_np[inliers]
                img_inliers = img_points_np[inliers]
                
                # Refine
                success, rvec, tvec = cv2.solvePnP(obj_inliers, img_inliers, K, D, rvec, tvec, True, cv2.SOLVEPNP_ITERATIVE)
            
            # Calculate Reprojection Error using all points (or just inliers?)
            # Let's show inlier error
            projected_points, _ = cv2.projectPoints(obj_inliers, rvec, tvec, K, D)
            projected_points = projected_points.reshape(-1, 2)
            error = cv2.norm(img_inliers, projected_points, cv2.NORM_L2) / len(projected_points) # Average error per point
            
            print(f"  Reprojection Error (Inliers): {error:.4f} pixels")
            
            print(f"  Reprojection Error: {error:.4f} pixels")
            print(f"  Tvec (cm): {tvec.flatten()}")
            
            # Rotation Matrix
            R, _ = cv2.Rodrigues(rvec)
            
            # Camera Position in World: C = -R^T * t
            C = -np.dot(R.T, tvec)
            print(f"  Camera Position (World, cm): {C.flatten()}")
            
            results[cam_name] = {
                "rvec": rvec.tolist(),
                "tvec": tvec.tolist(),
                "reprojection_error": float(error),
                "camera_position_world": C.tolist()
            }
        else:
            print(f"  solvePnP failed for {cam_name}")

    # Save output
    output_file = os.path.join(base_dir, 'extrinsics.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=4)
    print(f"\nSaved calibration to {output_file}")

if __name__ == "__main__":
    main()
