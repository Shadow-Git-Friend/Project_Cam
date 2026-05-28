import cv2
import numpy as np
import json
import glob
import os
import re

def parse_dimensions_with_z_flip(filepath):
    """Parse with Z-axis flipped"""
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
                # HYPOTHESIS: Flip Z axis
                coords[2] = -coords[2]
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

print("="*70)
print("HYPOTHESIS TEST: Z-AXIS FLIP")
print("="*70)
print("Testing if negating Z coordinates fixes camera positions")
print()

K, D = load_intrinsics('/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json')
tag_coords = parse_dimensions_with_z_flip('/home/altay/Desktop/Footbonaut/Garage/Scenario3/Dimensions.txt')

# Test tag 21 with flipped Z
tag_21 = tag_coords[21]
print(f"Tag ID=21 with Z-FLIPPED:")
print(f"Original: c0(211.8, 182.5, 4) -> With flip: {tag_21[0]}")
print(f"All corners:\n{tag_21}\n")

# Detect in image
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

cam_dir = '/home/altay/Desktop/Footbonaut/Garage/Scenario3/camEast'
images = sorted(glob.glob(os.path.join(cam_dir, '*.jpg')))

for img_path in images:
    img = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    
    if ids is not None and 21 in ids.flatten():
        idx = np.where(ids.flatten() == 21)[0][0]
        img_corners = corners[idx][0]
        
        success, rvec, tvec = cv2.solvePnP(tag_21, img_corners, K, D, flags=cv2.SOLVEPNP_ITERATIVE)
        
        if success:
            R, _ = cv2.Rodrigues(rvec)
            C = -np.dot(R.T, tvec)
            
            print("RESULT WITH Z-FLIP:")
            print(f"  Camera position: {C.flatten()}")
            print(f"  Expected:        [230, 7, 228]")
            print(f"  Error:           {np.linalg.norm(C.flatten() - [230, 7, 228]):.1f} cm")
            
            # Reprojection
            proj, _ = cv2.projectPoints(tag_21, rvec, tvec, K, D)
            proj = proj.reshape(-1, 2)
            error = np.mean([np.linalg.norm(proj[i] - img_corners[i]) for i in range(4)])
            print(f"  Reproj error:    {error:.4f} pixels")
            
        break

print("\n" + "="*70)
print("CONCLUSION:")
print("="*70)
print("If Z-flip reduces position error significantly, we found the issue!")
print("Original error was ~450cm, if now <50cm, Z-axis is inverted.")
