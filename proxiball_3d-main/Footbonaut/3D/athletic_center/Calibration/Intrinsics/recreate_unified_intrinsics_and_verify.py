import numpy as np
import cv2
import json
import os
import glob

# NOTE: Using athletic_center (underscore)
source_file = "/home/altay/Desktop/Footbonaut/Garage/intrinsics/cal/cam0_intrinsics.npz"
target_dir = "/home/altay/Desktop/Footbonaut/athletic_center/Calibration/Intrinsics"
target_npz = os.path.join(target_dir, "unified_intrinsics.npz")
target_json = os.path.join(target_dir, "unified_intrinsics.json")
verif_img_path = os.path.join(target_dir, "verification_undistort.jpg")

def main():
    if not os.path.exists(source_file):
        print(f"Source file missing: {source_file}")
        return

    # Load 720p calibration
    print(f"Loading {source_file}...")
    data = np.load(source_file)
    mtx_720p = data['mtx']
    dist = data['dist']
    error = data['error']
    
    # Scale to 1080p (x1.5)
    scale = 1.5
    mtx_1080p = mtx_720p * scale
    mtx_1080p[2, 2] = 1.0 
    
    # Save artifacts
    np.savez(target_npz, camera_matrix=mtx_1080p, dist_coeffs=dist)
    
    out_data = {
        "camera_matrix": mtx_1080p.tolist(),
        "dist_coeffs": dist.tolist(),
        "reprojection_error": float(error),
        "source": "Scaled from cam0_intrinsics.npz (1.5x)",
        "resolution": [1920, 1080]
    }
    with open(target_json, "w") as f:
        json.dump(out_data, f, indent=4)
        
    print(f"Re-generated unified intrinsics in {target_dir}")
    
    # Verification: Undistort an image
    # Looking in CamA under the new directory
    img_files = glob.glob(os.path.join(target_dir, "CamA/*.jpg"))
    if not img_files:
        print("No images found to verify in CamA.")
        return
        
    print(f"Verifying with {img_files[0]}...")
    img = cv2.imread(img_files[0]) # Should be 1080p
    if img is None:
        print("Failed to read image.")
        return
        
    h, w = img.shape[:2]
    print(f"Image Size: {w}x{h}")
    
    new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(mtx_1080p, dist, (w,h), 1, (w,h))
    undistorted = cv2.undistort(img, mtx_1080p, dist, None, new_camera_matrix)
    
    # Crop based on ROI (optional, but shows valid region)
    x, y, w_roi, h_roi = roi
    cv2.rectangle(undistorted, (x, y), (x+w_roi, y+h_roi), (0, 255, 0), 2)
    
    # Resize for display/saving if huge
    scale_disp = 0.5
    img_s = cv2.resize(img, None, fx=scale_disp, fy=scale_disp)
    undist_s = cv2.resize(undistorted, None, fx=scale_disp, fy=scale_disp)
    
    # Stack side-by-side
    combo = np.hstack((img_s, undist_s))
    cv2.imwrite(verif_img_path, combo)
    print(f"Created verification image: {verif_img_path}")

if __name__ == "__main__":
    main()
