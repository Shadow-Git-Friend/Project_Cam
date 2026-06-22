import cv2
import numpy as np
import json
import glob
import os

def load_intrinsics(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    K = np.array(data['camera_matrix'], dtype=np.float32)
    D = np.array(data['dist_coeffs'], dtype=np.float32)
    if D.ndim == 2:
        D = D[0]
    return K, D

# Load intrinsics
K, D = load_intrinsics('/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json')

# Define one simple test tag - ID=10 on West Wall
# ID=10: c0(463.7, 298, 85), c1(463.7, 298, 106.5), c2(442.2, 298, 106.5), c3(442.2, 298, 85)
tag_10_world = np.array([
    [463.7, 298, 85],
    [463.7, 298, 106.5],
    [442.2, 298, 106.5],
    [442.2, 298, 85]
], dtype=np.float32)

print("Testing with Tag ID=10 (West Wall)")
print(f"3D coordinates:\n{tag_10_world}\n")

# camWest should see this tag clearly
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

cam_dir = '/home/altay/Desktop/Footbonaut/Garage/Scenario3/camWest'
images = sorted(glob.glob(os.path.join(cam_dir, '*.jpg')))

print(f"Searching for Tag ID=10 in camWest images...")

for img_path in images[:20]:  # Check first 20 images
    img = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    
    if ids is not None and 10 in ids.flatten():
        idx = np.where(ids.flatten() == 10)[0][0]
        img_corners = corners[idx][0]
        
        print(f"\n✓ Found in: {os.path.basename(img_path)}")
        print(f"2D image coords:\n{img_corners}\n")
        
        # Method 1: solvePnP directly
        success, rvec, tvec = cv2.solvePnP(tag_10_world, img_corners, K, D, flags=cv2.SOLVEPNP_ITERATIVE)
        
        if success:
            R, _ = cv2.Rodrigues(rvec)
            C = -np.dot(R.T, tvec)
            
            print("="*60)
            print("SINGLE TAG CALIBRATION (Tag ID=10)")
            print("="*60)
            print(f"rvec: {rvec.flatten()}")
            print(f"tvec: {tvec.flatten()}")
            print(f"\nCamera position C = -R^T * t: {C.flatten()}")
            print(f"Expected camWest position: [320, 295, 226]")
            
            # Reprojection check
            proj, _ = cv2.projectPoints(tag_10_world, rvec, tvec, K, D)
            proj = proj.reshape(-1, 2)
            error = np.mean([np.linalg.norm(proj[i] - img_corners[i]) for i in range(4)])
            print(f"Reprojection error: {error:.4f} pixels")
            
            # Try alternative interpretations
            print("\n" + "="*60)
            print("Alternative camera position calculations:")
            print("="*60)
            C_alt1 = np.dot(R.T, tvec)  # No negation
            C_alt2 = -np.dot(R, tvec)   # -R*t instead
            C_alt3 = np.dot(R, tvec)    # R*t
            
            print(f"  R^T * t (no neg):  {C_alt1.flatten()}")
            print(f"  -R * t:            {C_alt2.flatten()}")
            print(f"  R * t:             {C_alt3.flatten()}")
            
            # Compute camera optical axis (camera looks along +Z in camera frame)
            # Camera Z-axis in world = 3rd column of R
            camera_z_world = R[:, 2]
            print(f"\nCamera optical axis (Z-axis) in world frame: {camera_z_world}")
            print(f"  (Should point INTO room from wall)")
            
        break

print("\n" + "="*60)
print("Conclusion: Compare single-tag result with multi-tag RANSAC")
print("="*60)
