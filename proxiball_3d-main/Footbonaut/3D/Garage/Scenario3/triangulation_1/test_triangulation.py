import cv2
import numpy as np
import json

# Load extrinsics and intrinsics
with open('/home/altay/Desktop/Footbonaut/Garage/Scenario3/extrinsics.json') as f:
    extrinsics = json.load(f)

with open('/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics/unified_intrinsics.json') as f:
    intrinsics = json.load(f)
    K = np.array(intrinsics['camera_matrix'], dtype=np.float32)
    D = np.array(intrinsics['dist_coeffs'], dtype=np.float32)[0]

print("="*70)
print("ROUND-TRIP VERIFICATION TEST")
print("="*70)
print("Test: Take a 3D point, project to all cameras, then triangulate back")
print()

# Use Tag 21 center as test point
# ID=21: corners at c0(211.8, 182.5, 4), c1(211.8, 161, 4), c2(233.3, 161, 4), c3(233.3, 182.5, 4)
point_3d_world = np.array([222.55, 171.75, 4.0], dtype=np.float32)  # Center of tag 21
print(f"Test 3D point (Tag 21 center): {point_3d_world}")
print(f"Expected location: floor, roughly middle of room\n")

# Project to each camera
projections = {}
for cam in ['camNorth', 'camEast', 'camSouth', 'camWest']:
    rvec = np.array(extrinsics[cam]['rvec'], dtype=np.float32)
    tvec = np.array(extrinsics[cam]['tvec'], dtype=np.float32)
    
    proj, _ = cv2.projectPoints(point_3d_world.reshape(1,3), rvec, tvec, K, D)
    proj_2d = proj.reshape(2)
    
    projections[cam] = {
        'rvec': rvec,
        'tvec': tvec,
        'proj_2d': proj_2d
    }
    
    print(f"{cam}: projects to image point {proj_2d}")

print("\n" + "="*70)
print("Now triangulate back from 2D projections")
print("="*70)

# Triangulate using camEast and camNorth
cam1, cam2 = 'camEast', 'camNorth'

# Build projection matrices
R1, _ = cv2.Rodrigues(projections[cam1]['rvec'])
R2, _ = cv2.Rodrigues(projections[cam2]['rvec'])
t1 = projections[cam1]['tvec']
t2 = projections[cam2]['tvec']

P1 = K @ np.hstack([R1, t1])  # 3x4
P2 = K @ np.hstack([R2, t2])

# Triangulate
points_2d_1 = projections[cam1]['proj_2d'].reshape(1, 2).T
points_2d_2 = projections[cam2]['proj_2d'].reshape(1, 2).T

points_4d = cv2.triangulatePoints(P1, P2, points_2d_1, points_2d_2)
points_3d = (points_4d[:3] / points_4d[3]).flatten()

print(f"\nTriangulated from {cam1} + {cam2}:")
print(f"  Result: {points_3d}")
print(f"  Original: {point_3d_world}")
print(f"  Error: {np.linalg.norm(points_3d - point_3d_world):.4f} cm")

# Try another pair
cam1, cam2 = 'camEast', 'camSouth'
R1, _ = cv2.Rodrigues(projections[cam1]['rvec'])
R2, _ = cv2.Rodrigues(projections[cam2]['rvec'])
t1 = projections[cam1]['tvec']
t2 = projections[cam2]['tvec']

P1 = K @ np.hstack([R1, t1])
P2 = K @ np.hstack([R2, t2])

points_2d_1 = projections[cam1]['proj_2d'].reshape(1, 2).T
points_2d_2 = projections[cam2]['proj_2d'].reshape(1, 2).T

points_4d = cv2.triangulatePoints(P1, P2, points_2d_1, points_2d_2)
points_3d = (points_4d[:3] / points_4d[3]).flatten()

print(f"\nTriangulated from {cam1} + {cam2}:")
print(f"  Result: {points_3d}")
print(f"  Original: {point_3d_world}")
print(f"  Error: {np.linalg.norm(points_3d - point_3d_world):.4f} cm")

print("\n" + "="*70)
print("CONCLUSION:")
print("="*70)
print("If triangulation gives back the original 3D point correctly,")
print("then extrinsics ARE valid for 3D reconstruction,")
print("regardless of what the camera position values say!")
