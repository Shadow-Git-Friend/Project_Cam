import json
import re
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import os

# Configuration
DIMENSIONS_FILE = 'Dimensions.txt'
EXTRINSICS_FILE = 'extrinsics_main.json'
OUTPUT_FILE = 'arena_3d_view.png'


def parse_dimensions(filepath):
    """Parses Dimensions.txt to extract arena size and tag positions."""
    dimensions = {'X': 0, 'Y': 0, 'Z': 0}
    tags = {}

    with open(filepath, 'r') as f:
        content = f.read()

    # Parse Arena Dimensions
    dim_match = re.search(r'X\s*=\s*(\d+)\s*cm', content)
    if dim_match:
        dimensions['X'] = float(dim_match.group(1)) / \
            100.0  # Convert to meters
    dim_match = re.search(r'Y\s*=\s*(\d+)\s*cm', content)
    if dim_match:
        dimensions['Y'] = float(dim_match.group(1)) / 100.0
    dim_match = re.search(r'Z\s*=\s*(\d+)\s*cm', content)
    if dim_match:
        dimensions['Z'] = float(dim_match.group(1)) / 100.0

    # Parse Tag Positions
    # Looking for patterns like:
    # ID=0:
    # c0(176,3,22)
    # ...

    # Split by ID sections
    id_sections = re.split(r'ID=(\d+):', content)

    # The first element is before the first ID, so start from index 1
    # usage: id_sections[i] is ID, id_sections[i+1] is the content for that ID
    for i in range(1, len(id_sections), 2):
        tag_id = int(id_sections[i])
        section_content = id_sections[i+1]

        corners = []
        # Find all c0, c1, c2, c3 coordinates
        # pattern: c\d\(([\d\.]+),\s*([\d\.]+),\s*([\d\.]+)\)
        # Note: input has mixed spacing, e.g. c0(176,3,22) or c0(623, 71.5, 131.5)

        corner_matches = re.findall(
            r'c\d\s*\(\s*([\d\.]+)\s*,\s*([\d\.]+)\s*,\s*([\d\.]+)\s*\)', section_content)

        if len(corner_matches) == 4:
            # Convert to meters
            corners_m = []
            for cm in corner_matches:
                x = float(cm[0]) / 100.0
                y = float(cm[1]) / 100.0
                z = float(cm[2]) / 100.0
                corners_m.append([x, y, z])
            tags[tag_id] = np.array(corners_m)

    return dimensions, tags


def parse_extrinsics(filepath):
    """Parses extrinsics_main.json to extract camera poses."""
    with open(filepath, 'r') as f:
        data = json.load(f)

    cameras = {}
    for cam_name, cam_data in data.items():
        if 'camera_position' in cam_data and 'rvec' in cam_data:
            pos = np.array(cam_data['camera_position'])
            rvec = np.array(cam_data['rvec'])
            # We also need the rotation matrix to know orientation
            import cv2
            R, _ = cv2.Rodrigues(rvec)
            cameras[cam_name] = {'pos': pos, 'R': R}

    return cameras


def plot_arena(dimensions, tags, cameras, output_path):
    """Visualizes the arena, tags, and cameras in 3D."""
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')

    # 1. Plot Arena Walls (Bounding Box)
    X, Y, Z = dimensions['X'], dimensions['Y'], dimensions['Z']

    # Define corners of the room
    # Origin is North-East (0,0,0) based on text, but let's stick to the coordinates given.
    # X=0..6.23, Y=0..2.98, Z=0..2.95

    # Draw wireframe of the room
    corners = np.array([
        [0, 0, 0], [X, 0, 0], [X, Y, 0], [0, Y, 0],  # Floor
        [0, 0, Z], [X, 0, Z], [X, Y, Z], [0, Y, Z]   # Ceiling
    ])

    # Edges list
    edges = [
        [0, 1], [1, 2], [2, 3], [3, 0],  # Floor
        [4, 5], [5, 6], [6, 7], [7, 4],  # Ceiling
        [0, 4], [1, 5], [2, 6], [3, 7]  # Pillars
    ]

    for edge in edges:
        ax.plot3D(*zip(*corners[edge]), color='gray', alpha=0.3)

    # 2. Plot Tags
    for tag_id, corners in tags.items():
        # corners is 4x3 array
        # Plot a polygon for the tag
        poly = Poly3DCollection([corners], alpha=0.8,
                                facecolors='cyan', edgecolors='blue')
        ax.add_collection3d(poly)

        # Label the tag ID at the center
        center = np.mean(corners, axis=0)
        ax.text(center[0], center[1], center[2], str(
            tag_id), color='black', fontsize=8)

    # 3. Plot Cameras
    colors = {'camNorth': 'red', 'camEast': 'green',
              'camSouth': 'blue', 'camWest': 'orange'}

    for cam_name, cam_data in cameras.items():
        pos = cam_data['pos']
        R = cam_data['R']

        # Plot camera position
        color = colors.get(cam_name, 'black')
        ax.scatter(pos[0], pos[1], pos[2], c=color,
                   s=100, label=cam_name, marker='^')

        # Plot viewing direction (optical axis is usually Z in camera frame)
        # However, we need to check coordinate systems.
        # Assuming standard OpenCV: Z is forward.
        # Transform Z-axis (0,0,1) to world frame via R
        view_dir = R.dot(np.array([0, 0, 1]))
        # Often with rvec/tvec from solvePnP, world_point = R * object_point + tvec.
        # The camera position C = -R^T * tvec.
        # The orientation of the camera in world is R^T (if R maps world to camera).
        # Let's check if 'rvec' in JSON effectively rotates world to camera or camera to world.
        # Usually solvePnP gives R that transforms World -> Camera.
        # So Camera Orientation in World is R_inv = R.T.

        # Let's try plotting the camera's Z axis (look direction)
        # If R is World->Camera, then Camera->World is R.T
        # The camera's Z axis in world coordinates is the 3rd column of R.T (or 3rd row of R).

        view_dir = R.T[:, 2]  # 3rd column of R transpose

        # Scale for visualization
        scale = 1.0
        ax.quiver(pos[0], pos[1], pos[2],
                  view_dir[0], view_dir[1], view_dir[2],
                  length=scale, color=color, alpha=0.6, arrow_length_ratio=0.3)

        # Optional: Plot 'up' vector (Y axis of camera, usually down in image, so -Y is up?)
        # Let's plot the Camera Y axis to see orientation
        up_dir = R.T[:, 1]
        ax.quiver(pos[0], pos[1], pos[2],
                  up_dir[0], up_dir[1], up_dir[2],
                  length=0.5*scale, color=color, linestyle='--', alpha=0.3)

    # formatting
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_zlabel('Z (m)')
    ax.set_title('Arena 3D Reconstruction')

    # Set equal aspect ratio approximate
    max_range = np.array([X, Y, Z]).max()
    mid_x, mid_y, mid_z = X/2, Y/2, Z/2
    ax.set_xlim(mid_x - max_range/2, mid_x + max_range/2)
    ax.set_ylim(mid_y - max_range/2, mid_y + max_range/2)
    ax.invert_yaxis()  # Reverse Y axis as requested
    ax.set_zlim(mid_z - max_range/2, mid_z + max_range/2)

    ax.legend()

    # video generation
    if output_path.endswith('.mp4'):
        import matplotlib.animation as animation

        def update(frame):
            # Rotate camera
            ax.view_init(elev=30, azim=frame)
            return fig,

        print(f"Generating animation to {output_path}...")
        # 360 degrees, 2 degrees per frame = 180 frames. @ 30fps = 6 seconds
        ani = animation.FuncAnimation(
            fig, update, frames=np.arange(0, 360, 2), interval=50, blit=False)
        ani.save(output_path, writer='ffmpeg', fps=30)
    else:
        print(f"Saving visualization to {output_path}")
        plt.savefig(output_path)

    # plt.show() # Uncomment if running locally with display


if __name__ == "__main__":
    if not os.path.exists(DIMENSIONS_FILE):
        print(f"Error: {DIMENSIONS_FILE} not found.")
        exit(1)
    if not os.path.exists(EXTRINSICS_FILE):
        print(f"Error: {EXTRINSICS_FILE} not found.")
        exit(1)

    print("Parsing dimensions...")
    dims, tags = parse_dimensions(DIMENSIONS_FILE)
    print(f"Parsed {len(tags)} tags.")
    print(f"Arena Dimensions: {dims}")

    print("Parsing extrinsics...")
    cameras = parse_extrinsics(EXTRINSICS_FILE)
    print(f"Parsed {len(cameras)} cameras.")

    # Generate Video
    plot_arena(dims, tags, cameras, 'arena_360.mp4')
    print("Done.")
