import cv2
import numpy as np
import os

# Load one image from camEast
test_image = '/home/altay/Desktop/Footbonaut/Garage/Scenario3/camEast/image_0001.jpg'

# Check if file exists, otherwise find first available
if not os.path.exists(test_image):
    import glob
    images = glob.glob('/home/altay/Desktop/Footbonaut/Garage/Scenario3/camEast/*.jpg')
    if images:
        test_image = images[0]
    else:
        print("No images found!")
        exit(1)

print(f"Using test image: {test_image}")

img = cv2.imread(test_image)
if img is None:
    print("Failed to load image!")
    exit(1)

# Detect AprilTags
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
corners, ids, rejected = detector.detectMarkers(img)

if ids is None:
    print("No tags detected!")
    exit(1)

print(f"Detected {len(ids)} tags: {ids.flatten()}")

# Draw corners with labels
output_img = img.copy()
for i, tag_id in enumerate(ids.flatten()):
    tag_corners = corners[i][0]  # Shape: (4, 2)
    
    # Draw the tag
    cv2.polylines(output_img, [tag_corners.astype(np.int32)], True, (0, 255, 0), 3)
    
    # Label each corner with its index
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]  # Different color per corner
    labels = ['c0 (TL)', 'c1 (TR)', 'c2 (BR)', 'c3 (BL)']
    
    for j, (corner, color, label) in enumerate(zip(tag_corners, colors, labels)):
        x, y = int(corner[0]), int(corner[1])
        cv2.circle(output_img, (x, y), 10, color, -1)
        cv2.putText(output_img, f"{label}", (x+15, y+15), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    # Tag ID in center
    center = tag_corners.mean(axis=0).astype(int)
    cv2.putText(output_img, f"ID={tag_id}", (center[0]-30, center[1]), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
    
    print(f"\nTag ID={tag_id}:")
    print(f"  Corner 0: {tag_corners[0]}")
    print(f"  Corner 1: {tag_corners[1]}")
    print(f"  Corner 2: {tag_corners[2]}")
    print(f"  Corner 3: {tag_corners[3]}")

# Save annotated image
output_path = '/home/altay/Desktop/Footbonaut/Garage/Scenario3/debug_corners.jpg'
cv2.imwrite(output_path, output_img)
print(f"\nSaved annotated image to: {output_path}")
print("Please review the image to see which corner is labeled as c0, c1, c2, c3 by the detector.")
print("The colors are: c0=Blue, c1=Green, c2=Red, c3=Yellow")
