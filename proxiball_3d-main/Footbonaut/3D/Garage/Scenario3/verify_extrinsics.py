import cv2
import numpy as np
import json

# Load calibration results
with open('/home/altay/Desktop/Footbonaut/Garage/Scenario3/extrinsics.json', 'r') as f:
    extrinsics = json.load(f)

# Load intrinsics
with open('/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json', 'r') as f:
    intrinsics = json.load(f)
    K = np.array(intrinsics['camera_matrix'], dtype=np.float32)
    D = np.array(intrinsics['dist_coeffs'], dtype=np.float32)[0]

# Pick a test tag - ID=0 from Dimensions.txt
# ID=0: c0(176,3,22), c1(176, 3, 43.5), c2(197.5, 3, 43.5), c3(197.5, 3, 22)
tag_0_world = np.array([
    [176, 3, 22],
    [176, 3, 43.5],
    [197.5, 3, 43.5],
    [197.5, 3, 22]
], dtype=np.float32)

print("="*60)
print("VERIFICATION: Projecting Tag ID=0 using computed extrinsics")
print("="*60)
print(f"\nTag ID=0 world coordinates (cm):")
print(tag_0_world)
print(f"\nExpected: near East wall (Y≈0-3), middle height (Z≈22-43)")

# Test with camEast (should see this tag clearly)
cam = 'camEast'
print(f"\n{'='*60}")
print(f"Testing camera: {cam}")
print(f"{'='*60}")

rvec = np.array(extrinsics[cam]['rvec'], dtype=np.float32)
tvec = np.array(extrinsics[cam]['tvec'], dtype=np.float32)
cam_pos = np.array(extrinsics[cam]['camera_position_world'])

print(f"Camera position (computed): {cam_pos}")
print(f"Camera position (expected): [230, 7, 228]")
print(f"Rvec: {rvec.flatten()}")
print(f"Tvec: {tvec.flatten()}")

# Convert rvec to rotation matrix
R, _ = cv2.Rodrigues(rvec)
print(f"\nRotation matrix:")
print(R)

# Verify camera position calculation
C_verify = -np.dot(R.T, tvec)
print(f"\nCamera position verify (C = -R^T * t): {C_verify.flatten()}")

# Project the tag corners
projected, _ = cv2.projectPoints(tag_0_world, rvec, tvec, K, D)
projected = projected.reshape(-1, 2)

print(f"\nProjected image coordinates (pixels):")
for i, pt in enumerate(projected):
    print(f"  Corner {i}: {pt}")

# Load an actual image and detect tag 0
import glob
images = sorted(glob.glob(f'/home/altay/Desktop/Footbonaut/Garage/Scenario3/{cam}/*.jpg'))
if images:
    for img_path in images[:10]:  # Check first 10 images
        img = cv2.imread(img_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        parameters = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
        corners, ids, _ = detector.detectMarkers(gray)
        
        if ids is not None and 0 in ids.flatten():
            idx = np.where(ids.flatten() == 0)[0][0]
            detected = corners[idx][0]
            
            print(f"\n*** Found Tag ID=0 in {img_path.split('/')[-1]} ***")
            print(f"Detected image coordinates (pixels):")
            for i, pt in enumerate(detected):
                print(f"  Corner {i}: {pt}")
            
            print(f"\nReprojection error per corner:")
            for i in range(4):
                error = np.linalg.norm(projected[i] - detected[i])
                print(f"  Corner {i}: {error:.2f} pixels")
            
            avg_error = np.mean([np.linalg.norm(projected[i] - detected[i]) for i in range(4)])
            print(f"Average error: {avg_error:.2f} pixels")
            break

print("\n" + "="*60)
print("Analysis:")
print("="*60)
print("If reprojection works well, the calibration math is correct.")
print("If camera position seems wrong, there may be a coordinate system issue.")
