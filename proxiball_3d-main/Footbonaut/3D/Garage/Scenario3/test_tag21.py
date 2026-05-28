import cv2
import numpy as np
import json

def load_intrinsics(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    K = np.array(data['camera_matrix'], dtype=np.float32)
    D = np.array(data['dist_coeffs'], dtype=np.float32)
    if D.ndim == 2:
        D = D[0]
    return K, D

K, D = load_intrinsics('/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json')

# Use Tag ID=21 (floor tag) - simpler geometry
# ID=21: c0(211.8, 182.5, 4), c1(211.8, 161, 4), c2(233.3, 161, 4), c3(233.3, 182.5, 4)
tag_21_world = np.array([
    [211.8, 182.5, 4],
    [211.8, 161, 4],
    [233.3, 161, 4],
    [233.3, 182.5, 4]
], dtype=np.float32)

print("Testing with Tag ID=21 (Floor Tag)")
print(f"3D coordinates (X, Y, Z in cm):\n{tag_21_world}")
print(f"\nNote: Z=4cm (floor level), Y range 161-182.5, X range 211.8-233.3\n")

# Test with camEast (from the debug image, we saw tag 21 there)
import glob, os
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
        
        print(f"Found in: {os.path.basename(img_path)}")
        print(f"2D image coords:\n{img_corners}\n")
        
        # Calibrate using this single tag
        success, rvec, tvec = cv2.solvePnP(tag_21_world, img_corners, K, D, flags=cv2.SOLVEPNP_ITERATIVE)
        
        if success:
            R, _ = cv2.Rodrigues(rvec)
            C = -np.dot(R.T, tvec)
            
            print("="*70)
            print("SINGLE TAG CALIBRATION RESULT")
            print("="*70)
            print(f"rvec: {rvec.flatten()}")
            print(f"tvec: {tvec.flatten()}")
            print(f"\nCamera position C = -R^T * t: {C.flatten()}")
            print(f"Expected camEast: [230, 7, 228]")
            
            # Check reprojection
            proj, _ = cv2.projectPoints(tag_21_world, rvec, tvec, K, D)
            proj = proj.reshape(-1, 2)
            errors = [np.linalg.norm(proj[i] - img_corners[i]) for i in range(4)]
            print(f"Reprojection errors: {[f'{e:.3f}' for e in errors]} pixels")
            print(f"Average: {np.mean(errors):.4f} pixels")
            
            print("\n" + "="*70)
            print("DETAILED ANALYSIS")
            print("="*70)
            print(f"\nRotation matrix R:")
            print(R)
            print(f"\nR^T:")
            print(R.T)
            
            # Camera optical axis
            cam_z = R[:, 2]
            print(f"\nCamera Z-axis in world (optical axis): {cam_z}")
            print("  (Camera looks along +Z in its own frame)")
            print(f"  Expected: camEast at (230,7,228) should look INTO room (positive X direction)")
            
            # Alternative calculations
            print("\n" + "="*70)
            print("TESTING DIFFERENT CAMERA POSITION FORMULAS")
            print("="*70)
            formulas = {
                "C = -R^T * t": -np.dot(R.T, tvec),
                "C = R^T * t (no neg)": np.dot(R.T, tvec),
                "C = -R * t": -np.dot(R, tvec),
                "C = R * t": np.dot(R, tvec),
                "C = -t": -tvec,
                "C = t": tvec
            }
            
            for name, result in formulas.items():
                dist_to_expected = np.linalg.norm(result.flatten() - np.array([230, 7, 228]))
                print(f"{name:25} = {np.round(result.flatten(), 1):30}  dist={dist_to_expected:.1f}")
            
            print("\n" + "="*70)
            print("Which formula gives closest to expected [230, 7, 228]?")
            print("="*70)
            
        break
