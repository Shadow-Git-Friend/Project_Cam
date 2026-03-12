# Project Overview For ChatGPT

Copy this file into ChatGPT when you want thesis-writing and system-analysis help.

## Project Title

Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking

## Goal

Build and evaluate a multi-camera computer vision system that reconstructs 3D ball trajectory and human pose in real time (or near-real-time), then uses that data for analysis, visualization, and predictive ballistics research.

## Repository Scope

This handoff is for the full `Project_Cam` repository, including:

- foundational code in `src/`,
- capture tooling in `GARAGE_CAMERAS/`,
- imported baseline in `garage-20260217T113109Z-3-001/`,
- unified current pipeline in `garage_lab_combined/`,
- historical calibration/data/output folders used for experiments.

## System Components

1. Camera capture and synchronization (`GARAGE_CAMERAS/`, `garage_lab_combined/scripts/record_*`).
2. Camera calibration (intrinsics + extrinsics via ChArUco and AprilTag pipelines).
3. Ball detection (YOLO models).
4. Human pose estimation (MMPose / COCO keypoints).
5. 3D triangulation (ball + joints from multiple camera views).
6. 3D rendering and post-processing.
7. Ground-truth evaluation protocols (static and dynamic trials).
8. Thesis document generation assets.

## Technologies

- Python
- OpenCV
- Ultralytics YOLO
- MMPose
- NumPy / SciPy
- Matplotlib

## Environment

- Arena: garage lab setup.
- Cameras: 4 fixed cameras (`camNorth`, `camEast`, `camSouth`, `camWest`).
- Runtime resolution: `1280x720`.
- Target FPS: `15` capture, `5` inference.
- Coordinate units: `mm`.

## Dataset / Data Sources

- Multi-camera synchronized recordings (garage sessions).
- Calibration image sets (ChArUco/AprilTag).
- Ground-truth protocol datasets under `garage_lab_combined/gt_eval/`.
- Optional Roboflow dataset utilities under `data/footbonaut_yolo11/`.

## Current Results Snapshot

- Ball/static and pose/joint-touch evaluation workflows are documented in:
  - `garage_lab_combined/gt_eval/BALL_DETECTION_PIPELINE.md`
  - `garage_lab_combined/gt_eval/JOINT_TOUCH_3D_PIPELINE.md`
- Thesis drafts and selected figures are under `garage_lab_combined/thesis/`.

Fill in exact numbers before sharing:

- Ball 3D mean error: `TODO`
- Ball 3D P95 error: `TODO`
- Joint-touch mean error: `TODO`
- Throughput/FPS on target machine: `TODO`

## Main Folders To Read First

- `README.md`
- `docs/FOLDER_STRUCTURE.md`
- `src/`
- `GARAGE_CAMERAS/README.md`
- `garage-20260217T113109Z-3-001/garage/environment/README.md`
- `garage_lab_combined/README.md`
- `garage_lab_combined/thesis/PROJECT_CAM_REPO_FLOW_MAP.md`
- `garage_lab_combined/scripts/`

## What I Need Help With

1. Thesis structure and chapter writing.
2. Methodology clarity (calibration + triangulation + evaluation).
3. Result interpretation and discussion framing.
4. Figure/table selection and captions.
5. Academic formatting (IEEE/APA/ASME as required).

## University Requirements (Fill Before Sharing)

- Degree / program: `TODO`
- Required page count: `TODO`
- Template format: `TODO`
- Citation style: `TODO`
- Submission deadline: `TODO`
