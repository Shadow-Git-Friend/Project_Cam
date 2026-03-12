# Project_Cam

Multi-camera ball + human pose tracking research workspace for a Master's thesis on pose-guided predictive ballistics.

## What This Repository Contains

This repo combines multiple phases of the project:

- `src/`: early and mid-stage pipeline (calibration, capture, triangulation, rendering, goal detection prototypes).
- `garage_lab_combined/`: unified 4-camera garage pipeline used for the latest experiments and thesis outputs.
- `scripts/`: calibration helpers and data utilities.
- `config/`: camera device mapping for local capture.

It is both a development workspace and a thesis production workspace.

## System Components

1. Cameras and synchronized capture.
2. Intrinsic and extrinsic camera calibration (ChArUco/AprilTag workflows).
3. 2D ball detection (YOLO).
4. 2D human pose estimation (MMPose).
5. Multi-view 3D triangulation (ball and body joints).
6. Post-processing, smoothing, and 3D rendering.
7. Ground-truth evaluation and thesis/report generation.

## Core Technologies

- Python
- OpenCV
- Ultralytics YOLO
- MMPose
- NumPy / SciPy
- Matplotlib

## Runtime Environment (Current Setup)

- Arena: garage-style lab
- Cameras: 4 fixed USB cameras (`camNorth`, `camEast`, `camSouth`, `camWest`)
- Runtime resolution: `1280x720`
- Capture target: `15 FPS`
- Inference target: `5 FPS`
- Unit system: `mm`

(See `garage_lab_combined/config/runtime.yaml` and `garage_lab_combined/config/cameras.yaml`.)

## Key Entry Points

- 4-camera processing to 3D:
  - `garage_lab_combined/scripts/process_4cam_to_3d.py`
- Presentation rendering:
  - `garage_lab_combined/scripts/render_arena_ball_skeleton.py`
- Live multi-camera 3D view:
  - `garage_lab_combined/scripts/live_4cam_arena_view.py`
- Intrinsics calibration:
  - `garage_lab_combined/scripts/calibrate_intrinsics_charuco_garage.py`
- Extrinsics calibration:
  - `garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py`

## Documentation For External Analysis

If you want ChatGPT (or any external reviewer) to analyze this project quickly, start with:

- `docs/PROJECT_OVERVIEW_FOR_CHATGPT.md`
- `docs/FOLDER_STRUCTURE.md`
- `docs/REPO_SHARING_CHECKLIST.md`

These files are prepared to match a thesis-assistant workflow.

- `docs/CHATGPT_HANDOFF_PROMPT.md`
