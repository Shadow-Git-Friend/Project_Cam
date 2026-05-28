import cv2
import numpy as np
import json
import re
import itertools
from pathlib import Path

def parse_dimensions(filepath):
    """Parse tag coordinates from Dimensions.txt"""
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
            final_coords[tag_id] = np.array(points, dtype=np.float32)
            
    return final_coords

def load_intrinsics(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    K = np.array(data['camera_matrix'], dtype=np.float32)
    D = np.array(data['dist_coeffs'], dtype=np.float32)
    if D.ndim == 2:
        D = D[0]
    return K, D

def triangulate_point_from_cameras(point_3d, cameras, extrinsics, K, D):
    """
    Project a 3D point to multiple cameras and triangulate back
    Returns calculated 3D position and error
    """
    # Project to all cameras
    projections = []
    proj_matrices = []
    
    for cam in cameras:
        rvec = np.array(extrinsics[cam]['rvec'], dtype=np.float32)
        tvec = np.array(extrinsics[cam]['tvec'], dtype=np.float32)
        
        # Project point
        proj_2d, _ = cv2.projectPoints(point_3d.reshape(1,3), rvec, tvec, K, D)
        projections.append(proj_2d.reshape(2))
        
        # Build projection matrix
        R, _ = cv2.Rodrigues(rvec)
        P = K @ np.hstack([R, tvec])
        proj_matrices.append(P)
    
    # Triangulate using first two cameras
    if len(cameras) == 2:
        points_4d = cv2.triangulatePoints(proj_matrices[0], proj_matrices[1],
                                         projections[0].reshape(2,1),
                                         projections[1].reshape(2,1))
        result_3d = (points_4d[:3] / points_4d[3]).flatten()
    else:
        # For 3+ cameras, triangulate pairwise and average
        triangulated_points = []
        for i in range(len(cameras)):
            for j in range(i+1, len(cameras)):
                points_4d = cv2.triangulatePoints(proj_matrices[i], proj_matrices[j],
                                                 projections[i].reshape(2,1),
                                                 projections[j].reshape(2,1))
                pt_3d = (points_4d[:3] / points_4d[3]).flatten()
                triangulated_points.append(pt_3d)
        
        # Average all pairwise triangulations
        result_3d = np.mean(triangulated_points, axis=0)
    
    error = np.linalg.norm(result_3d - point_3d)
    return result_3d, error

print("="*80)
print("COMPREHENSIVE TRIANGULATION ANALYSIS FOR ALL TAG CORNERS")
print("="*80)

# Load data
base_dir = Path('/home/altay/Desktop/Footbonaut/Garage/Scenario3')
tag_3d_coords = parse_dimensions(base_dir / 'Dimensions.txt')
K, D = load_intrinsics('/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json')

# Load extrinsics
with open(base_dir / 'extrinsics_1.json') as f:
    extrinsics = json.load(f)

cameras = ['camNorth', 'camEast', 'camSouth', 'camWest']

print("\nDetecting which cameras can see each tag...")

# Dynamically detect which cameras see which tags
def detect_tags_in_images(image_path, aruco_dict):
    img = cv2.imread(image_path)
    if img is None:
        return set()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is not None:
        return set(ids.flatten())
    return set()

aruco_dict_detect = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
camera_tags = {}

for cam_name in cameras:
    cam_dir = base_dir / cam_name
    image_files = list(cam_dir.glob('*.jpg'))
    
    tags_seen = set()
    for img_path in image_files:
        tags = detect_tags_in_images(str(img_path), aruco_dict_detect)
        tags_seen.update(tags)
    
    camera_tags[cam_name] = sorted(tags_seen)
    print(f"  {cam_name}: sees {len(tags_seen)} tags")

# Open output files
csv_file = open(base_dir / 'triangulation_analysis.csv', 'w')
txt_file = open(base_dir / 'triangulation_analysis.txt', 'w')

# Write CSV header
csv_file.write("TagID,Corner,CameraCombos,NumCameras,")
csv_file.write("Expected_X,Expected_Y,Expected_Z,")
csv_file.write("Calc_X,Error_X,Calc_Y,Error_Y,Calc_Z,Error_Z,")
csv_file.write("Total_Error_cm,Status\n")

# Write text header
txt_file.write("="*120 + "\n")
txt_file.write("COMPREHENSIVE TRIANGULATION ANALYSIS - ALL TAG CORNERS\n")
txt_file.write("="*120 + "\n\n")

print("\nProcessing tags and generating report...")

results_summary = []
total_tests = 0
errors_sum = 0

# Test ALL tags (0-23)
for tag_id in range(24):
    # Check if tag exists in Dimensions.txt
    if tag_id not in tag_3d_coords:
        txt_file.write(f"\n{'='*120}\n")
        txt_file.write(f"TAG ID: {tag_id}\n")
        txt_file.write(f"❌ NOT FOUND in Dimensions.txt\n")
        txt_file.write(f"{'='*120}\n\n")
        
        # Write to CSV
        csv_file.write(f"{tag_id},N/A,N/A,0,N/A,N/A,N/A,N/A,N/A,N/A,N/A,N/A,N/A,N/A,NOT_IN_DIMENSIONS\n")
        continue
    
    tag_corners = tag_3d_coords[tag_id]
    
    # Find which cameras can see this tag
    visible_cams = [cam for cam in cameras if tag_id in camera_tags[cam]]
    
    txt_file.write(f"\n{'='*120}\n")
    txt_file.write(f"TAG ID: {tag_id}\n")
    
    if len(visible_cams) < 2:
        txt_file.write(f"⚠️  Visible in {len(visible_cams)} camera(s): {', '.join(visible_cams) if visible_cams else 'NONE'}\n")
        txt_file.write(f"❌ CANNOT TRIANGULATE (need at least 2 cameras)\n")
        
        # If exactly 1 camera sees it, add single-camera estimation
        if len(visible_cams) == 1:
            cam_name = visible_cams[0]
            txt_file.write(f"\n📍 Single-camera estimation from {cam_name}:\n")
            txt_file.write(f"{'='*120}\n\n")
            
            rvec = np.array(extrinsics[cam_name]['rvec'], dtype=np.float32)
            tvec = np.array(extrinsics[cam_name]['tvec'], dtype=np.float32)
            R, _ = cv2.Rodrigues(rvec)
            
            for corner_idx in range(4):
                expected_3d = tag_corners[corner_idx]
                
                # Project to camera
                proj_2d, _ = cv2.projectPoints(expected_3d.reshape(1,3), rvec, tvec, K, D)
                proj_2d = proj_2d.reshape(2)
                
                # Backproject using expected depth (ray from camera through pixel)
                # Get camera center
                C = -np.dot(R.T, tvec).flatten()
                
                # Compute ray direction
                # Normalize pixel coordinates
                pixel_norm = np.array([
                    (proj_2d[0] - K[0,2]) / K[0,0],
                    (proj_2d[1] - K[1,2]) / K[1,1],
                    1.0
                ])
                # Transform to world frame
                ray_dir_world = np.dot(R.T, pixel_norm)
                ray_dir_world = ray_dir_world / np.linalg.norm(ray_dir_world)
                
                # Use expected depth
                expected_depth = np.linalg.norm(expected_3d - C)
                estimated_3d = C + ray_dir_world * expected_depth
                
                error_x = abs(estimated_3d[0] - expected_3d[0])
                error_y = abs(estimated_3d[1] - expected_3d[1])
                error_z = abs(estimated_3d[2] - expected_3d[2])
                total_error = np.linalg.norm(estimated_3d - expected_3d)
                
                # Write to CSV
                csv_file.write(f"{tag_id},{corner_idx},{cam_name}_SINGLE_CAM,1,")
                csv_file.write(f"{expected_3d[0]:.2f},{expected_3d[1]:.2f},{expected_3d[2]:.2f},")
                csv_file.write(f"{estimated_3d[0]:.2f},{error_x:.2f},")
                csv_file.write(f"{estimated_3d[1]:.2f},{error_y:.2f},")
                csv_file.write(f"{estimated_3d[2]:.2f},{error_z:.2f},")
                csv_file.write(f"{total_error:.2f},SINGLE_CAM_ESTIMATE\n")
                
                # Write to text
                txt_file.write(f"  CORNER {corner_idx}:\n")
                txt_file.write(f"    Expected:   ({expected_3d[0]:.2f}, {expected_3d[1]:.2f}, {expected_3d[2]:.2f}) cm\n")
                txt_file.write(f"    Estimated:  ({estimated_3d[0]:.2f}, {estimated_3d[1]:.2f}, {estimated_3d[2]:.2f}) cm\n")
                txt_file.write(f"    Errors:     (±{error_x:.2f}, ±{error_y:.2f}, ±{error_z:.2f}) cm\n")
                txt_file.write(f"    Total:      {total_error:.2f} cm\n")
                txt_file.write(f"    (Note: Uses expected depth for backprojection)\n\n")
        else:
            # No cameras see it
            txt_file.write(f"{'='*120}\n\n")
            for corner_idx in range(4):
                expected_3d = tag_corners[corner_idx]
                csv_file.write(f"{tag_id},{corner_idx},NO_CAMERAS,0,")
                csv_file.write(f"{expected_3d[0]:.2f},{expected_3d[1]:.2f},{expected_3d[2]:.2f},")
                csv_file.write(f"N/A,N/A,N/A,N/A,N/A,N/A,N/A,NO_CAMERA_SEES_TAG\n")
        
        continue
    
    txt_file.write(f"Visible in cameras: {', '.join(visible_cams)} ({len(visible_cams)} cameras)\n")
    txt_file.write(f"{'='*120}\n\n")
    
    # Test all camera combinations (pairs and trios)
    all_combos = []
    
    # Pairs
    if len(visible_cams) >= 2:
        all_combos.extend(list(itertools.combinations(visible_cams, 2)))
    
    # Trios
    if len(visible_cams) >= 3:
        all_combos.extend(list(itertools.combinations(visible_cams, 3)))
    
    # Quads (if all 4 cameras see it)
    if len(visible_cams) >= 4:
        all_combos.extend(list(itertools.combinations(visible_cams, 4)))
    
    for corner_idx in range(4):
        expected_3d = tag_corners[corner_idx]
        
        txt_file.write(f"  CORNER {corner_idx}:\n")
        txt_file.write(f"    Expected: ({expected_3d[0]:.2f}, {expected_3d[1]:.2f}, {expected_3d[2]:.2f}) cm\n\n")
        
        for combo in all_combos:
            cams_str = "+".join(combo)
            
            # Triangulate
            calc_3d, total_error = triangulate_point_from_cameras(
                expected_3d, combo, extrinsics, K, D
            )
            
            # Individual errors
            error_x = abs(calc_3d[0] - expected_3d[0])
            error_y = abs(calc_3d[1] - expected_3d[1])
            error_z = abs(calc_3d[2] - expected_3d[2])
            
            # Write to CSV
            csv_file.write(f"{tag_id},{corner_idx},{cams_str},{len(combo)},")
            csv_file.write(f"{expected_3d[0]:.2f},{expected_3d[1]:.2f},{expected_3d[2]:.2f},")
            csv_file.write(f"{calc_3d[0]:.2f},{error_x:.2f},")
            csv_file.write(f"{calc_3d[1]:.2f},{error_y:.2f},")
            csv_file.write(f"{calc_3d[2]:.2f},{error_z:.2f},")
            csv_file.write(f"{total_error:.2f},OK\n")
            
            # Write to text
            txt_file.write(f"    {cams_str} ({len(combo)} cams):\n")
            txt_file.write(f"      Calculated: ({calc_3d[0]:.2f}, {calc_3d[1]:.2f}, {calc_3d[2]:.2f}) cm\n")
            txt_file.write(f"      Errors:     (±{error_x:.2f}, ±{error_y:.2f}, ±{error_z:.2f}) cm\n")
            txt_file.write(f"      Total:      {total_error:.2f} cm\n\n")
            
            total_tests += 1
            errors_sum += total_error
            results_summary.append({
                'tag': tag_id,
                'corner': corner_idx,
                'combo': cams_str,
                'error': total_error
            })

# Write summary
avg_error = errors_sum / total_tests if total_tests > 0 else 0

txt_file.write(f"\n{'='*120}\n")
txt_file.write(f"SUMMARY STATISTICS\n")
txt_file.write(f"{'='*120}\n")
txt_file.write(f"Total tests performed: {total_tests}\n")
txt_file.write(f"Average triangulation error: {avg_error:.2f} cm\n")

# Find best and worst
best = min(results_summary, key=lambda x: x['error'])
worst = max(results_summary, key=lambda x: x['error'])

txt_file.write(f"\nBest result:\n")
txt_file.write(f"  Tag {best['tag']}, Corner {best['corner']}, {best['combo']}: {best['error']:.2f} cm\n")
txt_file.write(f"\nWorst result:\n")
txt_file.write(f"  Tag {worst['tag']}, Corner {worst['corner']}, {worst['combo']}: {worst['error']:.2f} cm\n")

# Camera pair statistics
pair_errors = {}
for result in results_summary:
    combo = result['combo']
    if combo.count('+') == 1:  # Pairs only
        if combo not in pair_errors:
            pair_errors[combo] = []
        pair_errors[combo].append(result['error'])

txt_file.write(f"\n{'='*120}\n")
txt_file.write(f"CAMERA PAIR PERFORMANCE\n")
txt_file.write(f"{'='*120}\n")

for combo in sorted(pair_errors.keys()):
    errors = pair_errors[combo]
    avg = np.mean(errors)
    std = np.std(errors)
    txt_file.write(f"{combo:20s}: avg={avg:6.2f} cm, std={std:5.2f} cm, n={len(errors)}\n")

csv_file.close()
txt_file.close()

print(f"\n✅ Analysis complete!")
print(f"Total tests: {total_tests}")
print(f"Average error: {avg_error:.2f} cm")
print(f"\nOutput files created:")
print(f"  - triangulation_analysis.csv")
print(f"  - triangulation_analysis.txt")
