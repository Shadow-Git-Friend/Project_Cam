import cv2
import numpy as np
import json
import glob
import os
import re

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

def detect_tags(image_path, aruco_dict):
    img = cv2.imread(image_path)
    if img is None:
        return [], None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
    corners, ids, _ = detector.detectMarkers(gray)
    return corners, ids

print("="*80)
print("COMPREHENSIVE EXTRINSICS VALIDATION")
print("="*80)

# Load data
base_dir = '/home/altay/Desktop/Footbonaut/Garage/Scenario3'
tag_3d_coords = parse_dimensions(os.path.join(base_dir, 'Dimensions.txt'))
K, D = load_intrinsics('/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json')
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)

# Load existing extrinsics
with open(os.path.join(base_dir, 'extrinsics_1.json')) as f:
    extrinsics = json.load(f)

cameras = ['camNorth', 'camEast', 'camSouth', 'camWest']

print("\n" + "="*80)
print("TEST 1: CHEIRALITY CHECK (points should be in front of camera)")
print("="*80)

for cam_name in cameras:
    cam_dir = os.path.join(base_dir, cam_name)
    image_files = glob.glob(os.path.join(cam_dir, '*.jpg'))
    
    rvec = np.array(extrinsics[cam_name]['rvec'], dtype=np.float32)
    tvec = np.array(extrinsics[cam_name]['tvec'], dtype=np.float32)
    R, _ = cv2.Rodrigues(rvec)
    
    # Sample a few images
    behind_count = 0
    front_count = 0
    
    for img_path in image_files[:10]:
        corners, ids = detect_tags(img_path, aruco_dict)
        if ids is None:
            continue
        
        for i, tag_id in enumerate(ids.flatten()):
            if tag_id not in tag_3d_coords:
                continue
            
            obj_pts = tag_3d_coords[tag_id]
            # Transform to camera frame
            pts_cam = np.dot(R, obj_pts.T).T + tvec.T
            
            # Check Z coordinates (depth)
            z_coords = pts_cam[:, 2]
            if np.any(z_coords < 0):
                behind_count += 1
            else:
                front_count += 1
    
    total = behind_count + front_count
    if total > 0:
        print(f"{cam_name}: {front_count}/{total} tags in front ({100*front_count/total:.1f}%)")
        if behind_count > front_count:
            print(f"  ⚠️  WARNING: More tags behind camera than in front!")
    else:
        print(f"{cam_name}: No tags found in sample")

print("\n" + "="*80)
print("TEST 2: INLIER PLANE ANALYSIS (checking for planar degeneracy)")
print("="*80)

for cam_name in cameras:
    cam_dir = os.path.join(base_dir, cam_name)
    image_files = sorted(glob.glob(os.path.join(cam_dir, '*.jpg')))
    
    all_obj_points = []
    all_img_points = []
    tag_ids_used = []
    
    for img_path in image_files:
        corners, ids = detect_tags(img_path, aruco_dict)
        if ids is None:
            continue
        
        for i, tag_id in enumerate(ids.flatten()):
            if tag_id in tag_3d_coords:
                obj_pts = tag_3d_coords[tag_id]
                img_pts = corners[i].reshape(4, 2)
                all_obj_points.append(obj_pts)
                all_img_points.append(img_pts)
                tag_ids_used.extend([tag_id] * 4)
    
    if not all_obj_points:
        continue
    
    obj_points_np = np.vstack(all_obj_points).astype(np.float32)
    img_points_np = np.vstack(all_img_points).astype(np.float32)
    
    # Re-run RANSAC
    success, rvec, tvec, inliers = cv2.solvePnPRansac(
        obj_points_np, img_points_np, K, D,
        reprojectionError=8.0, flags=cv2.SOLVEPNP_ITERATIVE
    )
    
    if success and inliers is not None:
        inlier_indices = inliers.flatten()
        inlier_points = obj_points_np[inlier_indices]
        
        # Analyze Z-distribution of inlier points
        z_coords = inlier_points[:, 2]
        floor_inliers = np.sum(z_coords < 30)  # Floor tags ~4-20cm
        wall_inliers = np.sum(z_coords >= 30)  # Wall tags ~40-250cm
        
        # Analyze which tags were inliers
        inlier_tags = set([tag_ids_used[i] for i in inlier_indices])
        
        print(f"\n{cam_name}:")
        print(f"  Inliers: {len(inliers)}/{len(obj_points_np)} ({100*len(inliers)/len(obj_points_np):.1f}%)")
        print(f"  Floor tag points: {floor_inliers} ({100*floor_inliers/len(inliers):.1f}%)")
        print(f"  Wall tag points: {wall_inliers} ({100*wall_inliers/len(inliers):.1f}%)")
        print(f"  Unique tags used: {sorted(inlier_tags)}")
        
        if floor_inliers > 0.8 * len(inliers):
            print(f"  ⚠️  WARNING: >80% inliers from floor - potential planar degeneracy!")
        elif wall_inliers > 0.8 * len(inliers):
            print(f"  ⚠️  WARNING: >80% inliers from walls - potential planar degeneracy!")

print("\n" + "="*80)
print("TEST 3: MULTI-CAMERA TRIANGULATION VALIDATION")
print("="*80)

# Test triangulation with different camera pairs
test_points_3d = [
    ("Tag 21 center", np.array([222.55, 171.75, 4.0])),  # Floor
    ("Tag 13 center", np.array([421.375, 167.75, 92.25])),  # Wall
    ("Tag 15 center", np.array([383.6, 168.5, 113.75])),  # Wall
]

camera_pairs = [
    ('camNorth', 'camEast'),
    ('camEast', 'camSouth'),
    ('camSouth', 'camWest'),
    ('camNorth', 'camSouth'),
]

print("\nTriangulating known 3D points from camera pairs:")
print()

for point_name, point_3d in test_points_3d:
    print(f"{point_name}: {point_3d}")
    errors = []
    
    for cam1, cam2 in camera_pairs:
        # Project to both cameras
        rvec1 = np.array(extrinsics[cam1]['rvec'], dtype=np.float32)
        tvec1 = np.array(extrinsics[cam1]['tvec'], dtype=np.float32)
        rvec2 = np.array(extrinsics[cam2]['rvec'], dtype=np.float32)
        tvec2 = np.array(extrinsics[cam2]['tvec'], dtype=np.float32)
        
        proj1, _ = cv2.projectPoints(point_3d.reshape(1,3), rvec1, tvec1, K, D)
        proj2, _ = cv2.projectPoints(point_3d.reshape(1,3), rvec2, tvec2, K, D)
        
        # Triangulate back
        R1, _ = cv2.Rodrigues(rvec1)
        R2, _ = cv2.Rodrigues(rvec2)
        P1 = K @ np.hstack([R1, tvec1])
        P2 = K @ np.hstack([R2, tvec2])
        
        points_4d = cv2.triangulatePoints(P1, P2, 
                                         proj1.reshape(2,1), 
                                         proj2.reshape(2,1))
        result_3d = (points_4d[:3] / points_4d[3]).flatten()
        
        error = np.linalg.norm(result_3d - point_3d)
        errors.append(error)
        print(f"  {cam1}+{cam2}: error = {error:.2f} cm")
    
    avg_error = np.mean(errors)
    max_error = np.max(errors)
    print(f"  Average error: {avg_error:.2f} cm, Max: {max_error:.2f} cm")
    print()

print("="*80)
print("FINAL ASSESSMENT")
print("="*80)

print("""
Based on the validation tests:

1. CHEIRALITY: Checks if tags are in front of cameras (should be >90%)
2. PLANAR DEGENERACY: Checks if inliers are mostly from one plane
3. TRIANGULATION: Measures 3D reconstruction accuracy from camera pairs

CRITERIA FOR USABILITY:
✓ Triangulation error <10 cm → EXCELLENT for ball tracking
✓ Triangulation error 10-30 cm → ACCEPTABLE for ball tracking  
✗ Triangulation error >30 cm → NEEDS IMPROVEMENT

If triangulation is good, extrinsics ARE USABLE regardless of camera
position calculations.
""")
