"""
Simple diagnostic: Check if the coordinate system mapping is consistent
"""
import numpy as np
import json

# Expected camera positions from Dimensions.txt
expected = {
    'camNorth': np.array([5, 110, 226]),
    'camEast': np.array([230, 7, 228]),
    'camWest': np.array([320, 295, 226]),
    'camSouth': np.array([618, 153, 227])
}

# Load computed positions
with open('/home/altay/Desktop/Footbonaut/Garage/Scenario3/extrinsics.json', 'r') as f:
    extrinsics = json.load(f)

computed = {}
for cam in extrinsics:
    computed[cam] = np.array(extrinsics[cam]['camera_position_world']).flatten()

print("="*70)
print("CAMERA POSITION COMPARISON")
print("="*70)
print(f"\n{'Camera':<12} {'Expected (X,Y,Z)':<25} {'Computed (X,Y,Z)':<25} {'Error (cm)'}")
print("-"*70)

for cam in ['camNorth', 'camEast', 'camSouth', 'camWest']:
    exp = expected[cam]
    comp = computed[cam]
    error = np.linalg.norm(exp - comp)
    print(f"{cam:<12} {str(exp):<25} {str(np.round(comp, 1)):<25} {error:.1f}")

print("\n" + "="*70)
print("OBSERVATION:")
print("="*70)

# Check Z coordinates
print("\nZ-coordinate (height) analysis:")
for cam in ['camNorth', 'camEast', 'camSouth', 'camWest']:
    exp_z = expected[cam][2]
    comp_z = computed[cam][2]
    print(f"  {cam}: expected {exp_z:.0f} cm, computed {comp_z:.1f} cm")

print("\n" + "="*70)
print("HYPOTHESIS:")
print("="*70)
print("Two cameras have NEGATIVE Z (below floor) - impossible!")
print("This suggests either:")
print("1. Wrong sign convention in solvePnP output")
print("2. Coordinate system axes are flipped/rotated")
print("3. There's a systematic error in how tag coordinates were measured")
print("\nLet me check the math of C = -R^T * t...")

# Manually verify camEast
print("\n" + "="*70)
print("MANUAL VERIFICATION: camEast")
print("="*70)

rvec = np.array(extrinsics['camEast']['rvec']).flatten()
tvec = np.array(extrinsics['camEast']['tvec']).flatten()

import cv2
R, _ = cv2.Rodrigues(rvec)

print(f"rvec =  {rvec}")
print(f"tvec = {tvec}")
print(f"\nR =")
print(R)
print(f"\nR^T =")
print(R.T)
print(f"\n-R^T * t = {-np.dot(R.T, tvec)}")

# Alternative: Maybe it should be -R * t or R^T * t?
print(f"\nAlternative calculations:")
print(f"  R^T * t (no negation) = {np.dot(R.T, tvec)}")
print(f"  -R * t = {-np.dot(R, tvec)}")
print(f"  R * t = {np.dot(R, tvec)}")

print("\n" + "="*70)
print("Expected camEast position: [230, 7, 228]")
print("="*70)
