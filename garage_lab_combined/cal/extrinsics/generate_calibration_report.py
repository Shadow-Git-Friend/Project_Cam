import json
import numpy as np
import cv2
import os


def rotation_matrix_to_euler_angles(R):
    """
    Calculates rotation matrix to euler angles
    The result is the same as MATLAB except the order
    of the euler angles ( x and z are swapped ).
    """
    sy = np.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6

    if not singular:
        x = np.arctan2(R[2, 1], R[2, 2])
        y = np.arctan2(-R[2, 0], sy)
        z = np.arctan2(R[1, 0], R[0, 0])
    else:
        x = np.arctan2(-R[1, 2], R[1, 1])
        y = np.arctan2(-R[2, 0], sy)
        z = 0

    return np.degrees(np.array([x, y, z]))


def generate_report():
    json_path = "/home/altay/Desktop/Footbonaut/garage/Scenario2/extrinsic_results.json"
    output_path = "/home/altay/Desktop/Footbonaut/garage/Scenario2/calibration_report.md"

    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    # Header
    md_content = "# Calibration Report\n\n"
    md_content += "Generated from `extrinsic_results.json`\n\n"

    # Table Header
    md_content += "| Camera | Reprojection Error | Position (World) X, Y, Z (m) | Rotation (Euler) R, P, Y (deg) |\n"
    md_content += "| :--- | :---: | :--- | :--- |\n"

    for cam_name, metrics in data.items():
        # Reprojection Error
        error = metrics.get("reprojection_error", -1)

        # Position
        pos = metrics.get("camera_position", [0, 0, 0])
        pos_str = f"[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]"

        # Rotation
        rvec = np.array(metrics.get("rvec", [0, 0, 0]))
        R, _ = cv2.Rodrigues(rvec)
        euler = rotation_matrix_to_euler_angles(R)
        rot_str = f"[{euler[0]:.1f}, {euler[1]:.1f}, {euler[2]:.1f}]"

        # Row
        md_content += f"| **{cam_name}** | {error:.4f} | {pos_str} | {rot_str} |\n"

    # Write to file
    with open(output_path, 'w') as f:
        f.write(md_content)

    print(f"Report generated at: {output_path}")
    print("\n" + md_content)


if __name__ == "__main__":
    generate_report()
