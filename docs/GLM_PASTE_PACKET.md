# GLM Paste Packet

Copy/paste this directly to GLM.

## README (Project Summary)

Project_Cam is a multi-camera ball + human pose tracking research workspace for a Master's thesis on pose-guided predictive ballistics.

Core pipeline:
1. Multi-camera synchronized capture.
2. Intrinsic/extrinsic calibration (ChArUco + AprilTag workflows).
3. 2D ball detection (YOLO).
4. 2D human pose estimation (MMPose).
5. Multi-view 3D triangulation (ball + joints).
6. Post-processing + smoothing + 3D rendering.
7. Ground-truth evaluation and thesis/report generation.

Runtime setup:
- 4 fixed cameras (`camNorth`, `camEast`, `camSouth`, `camWest`)
- Resolution: `1280x720`
- Targets: `15 FPS` capture, `5 FPS` inference
- Units: `mm`

Key scripts:
- `garage_lab_combined/scripts/process_4cam_to_3d.py`
- `garage_lab_combined/scripts/render_arena_ball_skeleton.py`
- `garage_lab_combined/scripts/live_4cam_arena_view.py`

## Project Overview

Project title:
Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking

Goal:
Build and evaluate a multi-camera CV system that reconstructs 3D ball trajectory and human pose (near real-time) for analysis, visualization, and predictive ballistics research.

Repository scope:
- Foundational code in `src/`
- Capture tooling in `GARAGE_CAMERAS/`
- Imported baseline in `garage-20260217T113109Z-3-001/`
- Unified current pipeline in `garage_lab_combined/`
- Historical calibration/data/output folders

Technologies:
Python, OpenCV, Ultralytics YOLO, MMPose, NumPy/SciPy, Matplotlib

## Experimental Results Snapshot

Ball static GT (corrected):
- Trials valid: `36/36`
- Mean error: `95.17 mm`
- Median: `84.18 mm`
- RMSE: `102.23 mm`
- P95: `166.51 mm`
- Max: `214.60 mm`
- Mean reprojection error: `6.01 px`
- Mean cameras used: `2.87`

Joint-touch 3D GT:
- Trials valid: `62/81` (19 missing/failed)
- Mean error: `143.38 mm`
- Median: `148.90 mm`
- RMSE: `147.73 mm`
- P95: `198.73 mm`
- Max: `217.34 mm`

Older B02..B10 diagnostic (partial set, 9 trials):
- RMSE: `678.99 mm`
- Mean: `463.57 mm`
- P95: `1284.09 mm`
- Residual RMSE after rigid correction: `599.53 mm`
- Residual RMSE after axis-linear correction: `522.39 mm`

## What I Want You To Write

Please draft:
1. Chapter 3: Methodology (detailed, thesis-ready).
2. Chapter 4: Experimental setup and evaluation protocol.
3. Chapter 5: Results and discussion using the metrics above.

Constraints:
- Academic tone.
- Clear variable definitions and equations where appropriate.
- Separate baseline vs corrected pipeline results.
- Explicitly note assumptions and limitations.

