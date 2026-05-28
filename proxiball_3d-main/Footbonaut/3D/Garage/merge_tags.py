import cv2
import numpy as np
import os

def merge_images():
    # Define paths
    base_dir = "/home/altay/Desktop/Footbonaut/Garage/Scenario1"
    
    # Note: Using the exact filenames provided by user
    # East (Top Left?) - Let's arrange them geographically or logically?
    # Usually: Top-Left, Top-Right, Bottom-Left, Bottom-Right
    # Let's do: North, East, South, West?
    # User said: East, North, South, West. 
    # Let's arrange them in a standard 2x2 grid.
    # Top Row: North, East
    # Bottom Row: West, South
    # Or just logical order 1,2,3,4. 
    # Let's try North (Top), South (Bottom), West (Left), East (Right).
    # Top-Left: West, Top-Right: North
    # Bot-Left: South, Bot-Right: East ?? 
    # Simplest is just row by row.
    # Let's do:
    # Row 1: North, East
    # Row 2: West, South
    
    img_paths = {
        "North": f"{base_dir}/camNorth/camNorth_1_00.jpg",
        "East":  f"{base_dir}/camEast/camEast_1_00.jpg",
        "South": f"{base_dir}/camSouth/camSouth_1_00.jpg",
        "West":  f"{base_dir}/camWest/camWest_1_00.jpg"
    }
    
    images = {}
    for name, path in img_paths.items():
        if not os.path.exists(path):
            print(f"Error: File not found: {path}")
            return
        
        img = cv2.imread(path)
        if img is None:
            print(f"Error: Could not read image: {path}")
            return
            
        images[name] = img
        print(f"Loaded {name}: {img.shape}")

    # Resize all to match the first one (assuming all should be 1080p)
    ref_h, ref_w = images["North"].shape[:2]
    
    for name in images:
        if images[name].shape[:2] != (ref_h, ref_w):
            print(f"Resizing {name} to match reference...")
            images[name] = cv2.resize(images[name], (ref_w, ref_h))

    # Create 2x2 Grid
    # Top Row: West, North (Left, Up) - Arbitrary choice unless specified
    # Let's do Standard Compass layout if possible?
    #   N
    # W   E
    #   S
    # But for a 2x2 grid:
    # [North, East]
    # [West, South]
    
    top_row = np.hstack([images["North"], images["East"]])
    bot_row = np.hstack([images["West"], images["South"]])
    
    grid = np.vstack([top_row, bot_row])
    
    # Save output
    output_path = f"{base_dir}/merged_grid.jpg"
    cv2.imwrite(output_path, grid)
    print(f"Saved merged grid to: {output_path}")
    
    # Resize for display (too big otherwise)
    display_scale = 0.25
    display_grid = cv2.resize(grid, None, fx=display_scale, fy=display_scale)
    cv2.imshow("Merged Grid", display_grid)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    merge_images()
