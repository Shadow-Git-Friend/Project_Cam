
import json
import numpy as np
import sys
import os

CAL_FILE = "cal/calibration_full.json"
REAL_BASELINE = 2780.0 # mm (2.78m)

def rescale():
    if not os.path.exists(CAL_FILE):
        print(f"File not found: {CAL_FILE}")
        return

    with open(CAL_FILE, 'r') as f:
        data = json.load(f)

    # Get current baseline from Cam 2 (assuming Cam 0 is origin)
    if "cam_2" not in data:
        print("cam_2 not found in JSON")
        return

    T = np.array(data["cam_2"]["T"])
    current_dist = np.linalg.norm(T)
    
    print(f"Current Baseline: {current_dist:.2f} mm")
    print(f"Target Baseline : {REAL_BASELINE:.2f} mm")
    
    scale_factor = REAL_BASELINE / current_dist
    print(f"Scale Factor    : {scale_factor:.5f}")
    
    # Apply Scale
    data["cam_2"]["T"] = (T * scale_factor).tolist()
    
    # Save
    with open(CAL_FILE, 'w') as f:
        json.dump(data, f, indent=4)
        
    print(f"[SUCCESS] Rescaled calibration to match {REAL_BASELINE}mm")

if __name__ == "__main__":
    rescale()
