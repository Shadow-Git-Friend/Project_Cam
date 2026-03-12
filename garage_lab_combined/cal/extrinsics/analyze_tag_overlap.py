import cv2
import numpy as np
import os
import glob
import json
import re
import sys


def main():
    root_dir = "/home/altay/Desktop/Footbonaut/garage/Scenario2"
    cameras = ["camNorth", "camEast", "camSouth", "camWest"]

    # Dictionary to store set of unique tags seen by each camera
    # { "camName": {tag_id, tag_id, ...} }
    camera_tags = {}

    # 1. Detect tags in all images
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    print("Scanning all cameras for unique tags...")

    for cam in cameras:
        cam_dir = os.path.join(root_dir, cam)
        if not os.path.isdir(cam_dir):
            print(f"[{cam}] Directory not found.")
            continue

        image_files = sorted(glob.glob(os.path.join(cam_dir, "*.jpg")))
        seen_tags = set()

        # We don't need to process ALL images if we just want to know *what* can be seen.
        # But to be safe, let's process them all or a good subset (e.g. first 20).
        # Let's process all to be sure we catch everything.

        print(f"[{cam}] Processing {len(image_files)} images...")
        for img_path in image_files:
            img = cv2.imread(img_path)
            if img is None:
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            corners, ids, rejected = detector.detectMarkers(gray)

            if ids is not None:
                for tag_id_arr in ids:
                    seen_tags.add(int(tag_id_arr[0]))

        camera_tags[cam] = seen_tags
        print(f"[{cam}] Unique tags seen: {sorted(list(seen_tags))}")

    print("\n" + "="*40)
    print("TAG OVERLAP ANALYSIS")
    print("="*40 + "\n")

    # 2. Compute overlaps pair-wise
    video_chain = [("camNorth", "camWest"), ("camWest", "camSouth"),
                   ("camSouth", "camEast"), ("camEast", "camNorth")]
    extra_pairs = [("camNorth", "camSouth"), ("camEast", "camWest")]

    all_pairs = video_chain + extra_pairs

    for (cam1, cam2) in all_pairs:
        tags1 = camera_tags.get(cam1, set())
        tags2 = camera_tags.get(cam2, set())

        common = tags1.intersection(tags2)

        print(f"{cam1} <--> {cam2}")
        print(f"  Shared Tags ({len(common)}): {sorted(list(common))}")
        if len(common) < 3:
            print(
                "  ⚠️  WARNING: Low overlap (<3 tags). Relative pose estimation difficult.")
        print("-" * 20)

    # 3. Global Reachability
    # Can we get from Cam1 to CamX via shared tags?
    # Simple BFS not needed for 4 nodes, inspection is enough.

    all_seen = set()
    for tags in camera_tags.values():
        all_seen.update(tags)

    print(f"\nTotal unique tags seen across system: {len(all_seen)}")
    print(f"Tags: {sorted(list(all_seen))}")


if __name__ == "__main__":
    main()
