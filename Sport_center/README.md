Sport_center dataset

- Place intrinsics images for camera A into `intrinsics_camA/`.
- Place intrinsics images for camera B into `intrinsics_camB/`.
- Place paired captures for extrinsics into `pairs_pairA/` and `pairs_pairB/`.
  - Each pair folder should contain matching filenames for the two cameras, e.g. `000_a.jpg` and `000_b.jpg` (or `_a.png`/_b).
- Outputs will be saved to `outputs/` with unique names so they don't overlap with existing project files.

Script:
- `scripts/auto_sport_calibrate.py` will try a grid search over common Charuco board sizes to find intrinsics with the lowest reprojection error, then estimate extrinsics by averaging pose estimates across valid pairs.

Notes & limitations:
- If true physical square size is unknown, the script searches plausible sizes (20–70 mm). The estimated extrinsic translation scale will be in the same unit (mm) as the chosen square size.
- For absolute real-world scale, you must supply at least one known-distance reference (e.g., ball radius, measured camera baseline) or provide the true square size.
