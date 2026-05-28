# Project_Cam Repository Flow Map

## Purpose
This map links all major folders in `Project_Cam` into one end-to-end research workflow for the thesis.

## A) Foundational Algorithm Layer (`src/`)
- `src/calibration`: early intrinsics/extrinsics, board generation, scaling tools.
- `src/core`: triangulation, renderers, goal detection prototypes.
- `src/legacy`: first 3D tracker and recording prototypes.
- `src/capture`, `src/tools`, `scripts/`: capture helpers and automation utilities.

Role in thesis flow:
- historical baseline and method origin.

## B) Capture Hardening Layer (`GARAGE_CAMERAS/`)
- Multi-camera recording scripts (`record_cams.py`, `sync_record_2.py`).
- Device probing and preview tools.

Role in thesis flow:
- practical reliability for synchronized acquisition.

## C) Imported Garage Baseline (`garage-20260217T113109Z-3-001/`)
- `garage/extrinsics_1`: friend baseline arena calibration and visualization.
- `garage/environment`: dual-camera high-speed inference references.
- `garage/Intrinsics`: calibration assets and board references.

Role in thesis flow:
- inherited baseline logic and tag/arena methodology.

## D) Unified Research Layer (`garage_lab_combined/`)
- `config/`: stable camera mapping by physical roles.
- `cal/`: active intrinsics/extrinsics and arena dimensions.
- `scripts/`: full integrated capture/process/render/eval pipeline.
- `gt_eval/`: static/dynamic ball and joint-touch protocol sessions.
- `output/`: session outputs and presentation videos.
- `thesis/`: manuscript and submission packages.

Role in thesis flow:
- final integrated experimental and reporting system.

## E) Data/Output Archives
- `data/`, `output/`, `cal/`, `Intrinsicsdec17/`, `runs/`.

Role in thesis flow:
- archived evidence and historical outputs used for comparison.

## End-to-End Dependency Chain
1. Record clips (`GARAGE_CAMERAS` or `garage_lab_combined/scripts/record_*`).
2. Calibrate intrinsics/extrinsics (`garage_lab_combined/cal` + scripts).
3. Process 4-camera clips to 3D (`process_4cam_to_3d.py`).
4. Render 3D arena + ball + skeleton (`render_arena_ball_skeleton.py`).
5. Evaluate GT trials (`evaluate_ball_static_gt.py`, `evaluate_pose_joint_touch_gt.py`).
6. Feed findings into thesis and next-stage launcher integration roadmap.
