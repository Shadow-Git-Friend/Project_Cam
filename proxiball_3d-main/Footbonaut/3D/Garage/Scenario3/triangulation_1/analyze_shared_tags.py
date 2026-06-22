import cv2
import numpy as np
import json
import glob
import os
import re

def parse_dimensions(filepath):
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

# Load data
base_dir = '/home/altay/Desktop/Footbonaut/Garage/Scenario3'
tag_3d_coords = parse_dimensions(os.path.join(base_dir, 'Dimensions.txt'))
K, D = load_intrinsics('/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json')
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)

cameras = ['camNorth', 'camEast', 'camSouth', 'camWest']

# Find which tags each camera sees
camera_tags = {}
for cam_name in cameras:
    cam_dir = os.path.join(base_dir, cam_name)
    image_files = glob.glob(os.path.join(cam_dir, '*.jpg'))
    
    tags_seen = set()
    for img_path in image_files:
        corners, ids = detect_tags(img_path, aruco_dict)
        if ids is not None:
            tags_seen.update(ids.flatten())
    
    camera_tags[cam_name] = tags_seen
    print(f"{cam_name}: sees {len(tags_seen)} unique tags: {sorted(tags_seen)}")

# Find shared tags between camera pairs
print("\n" + "="*70)
print("SHARED TAGS BETWEEN CAMERA PAIRS")
print("="*70)

shared_tags = {}
for i, cam1 in enumerate(cameras):
    for cam2 in cameras[i+1:]:
        shared = camera_tags[cam1] & camera_tags[cam2]
        shared_tags[(cam1, cam2)] = shared
        print(f"{cam1} ∩ {cam2}: {len(shared)} tags - {sorted(shared)}")

print("\n" + "="*70)
print("THREE-CAMERA SHARED TAGS")
print("="*70)

# Find tags visible in 3 or more cameras
tag_visibility = {}
for cam in cameras:
    for tag in camera_tags[cam]:
        if tag not in tag_visibility:
            tag_visibility[tag] = []
        tag_visibility[tag].append(cam)

multi_cam_tags = {tag: cams for tag, cams in tag_visibility.items() if len(cams) >= 3}
for tag, cams in sorted(multi_cam_tags.items()):
    print(f"Tag {tag:2d}: visible in {len(cams)} cameras: {cams}")

print("\n" + "="*70)
print("TESTING: Calibrate camEast using ONLY floor tags (21, 22)")
print("="*70)

# Calibrate camEast using only floor tags 21 and 22
cam_dir = os.path.join(base_dir, 'camEast')
image_files = sorted(glob.glob(os.path.join(cam_dir, '*.jpg')))

all_obj_points = []
all_img_points = []

floor_tags = [21, 22]
for img_path in image_files:
    corners, ids = detect_tags(img_path, aruco_dict)
    if ids is None:
        continue
    
    for i, tag_id in enumerate(ids.flatten()):
        if tag_id in floor_tags and tag_id in tag_3d_coords:
            obj_pts = tag_3d_coords[tag_id]
            img_pts = corners[i].reshape(4, 2)
            all_obj_points.append(obj_pts)
            all_img_points.append(img_pts)

if all_obj_points:
    obj_points_np = np.vstack(all_obj_points).astype(np.float32)
    img_points_np = np.vstack(all_img_points).astype(np.float32)
    
    print(f"Using {len(all_obj_points)} tag instances from floor tags only")
    
    # Calibrate with RANSAC
    success, rvec, tvec, inliers = cv2.solvePnPRansac(
        obj_points_np, img_points_np, K, D,
        reprojectionError=8.0, flags=cv2.SOLVEPNP_ITERATIVE
    )
    
    if success:
        R, _ = cv2.Rodrigues(rvec)
        C = -np.dot(R.T, tvec)
        
        print(f"RANSAC: {len(inliers)}/{len(obj_points_np)} points used")
        print(f"Camera position (floor tags only): {C.flatten()}")
        print(f"Expected camEast: [230, 7, 228]")
        print(f"Error: {np.linalg.norm(C.flatten() - [230, 7, 228]):.1f} cm")

print("\n" + "="*70)
print("Now trying with ALL wall tags (excluding floor)")
print("="*70)

all_obj_points = []
all_img_points = []

for img_path in image_files:
    corners, ids = detect_tags(img_path, aruco_dict)
    if ids is None:
        continue
    
    for i, tag_id in enumerate(ids.flatten()):
        # Exclude floor tags
        if tag_id not in [21, 22] and tag_id in tag_3d_coords:
            obj_pts = tag_3d_coords[tag_id]
            img_pts = corners[i].reshape(4, 2)
            all_obj_points.append(obj_pts)
            all_img_points.append(img_pts)

if all_obj_points:
    obj_points_np = np.vstack(all_obj_points).astype(np.float32)
    img_points_np = np.vstack(all_img_points).astype(np.float32)
    
    print(f"Using {len(all_obj_points)} tag instances from wall tags only")
    
    success, rvec, tvec, inliers = cv2.solvePnPRansac(
        obj_points_np, img_points_np, K, D,
        reprojectionError=8.0, flags=cv2.SOLVEPNP_ITERATIVE
    )
    
    if success:
        R, _ = cv2.Rodrigues(rvec)
        C = -np.dot(R.T, tvec)
        
        print(f"RANSAC: {len(inliers)}/{len(obj_points_np)} points used")
        print(f"Camera position (wall tags only): {C.flatten()}")
        print(f"Expected camEast: [230, 7, 228]")
        print(f"Error: {np.linalg.norm(C.flatten() - [230, 7, 228]):.1f} cm")
