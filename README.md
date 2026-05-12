# Project_Cam

**Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking**

MSc Thesis — ECE, Nazarbayev University

## Overview

A vision-guided ball launching system that uses 4 fixed cameras to reconstruct 3D human pose in real-time, predict target motion via Kalman filtering, and aim a robotic ball launcher (BLM) at specific body joints using ballistic trajectory solving.

## Repository Structure

```
Project_Cam/
├── garage_lab_combined/     # Main production pipeline
│   ├── scripts/             # Runtime scripts (live view, launcher, processing)
│   ├── cal/                 # Calibration data (intrinsics, extrinsics)
│   ├── gt_eval/             # Ground-truth evaluation results
│   └── thesis/              # Thesis living worklog
│
├── Parallel_working/        # Performance-optimized pipeline
│   ├── scripts/             # YOLO-Pose, ablation, Kalman, TensorRT export
│   └── run_live_*.sh        # Run profiles (quality, balanced, predictive, etc.)
│
├── arena_fixed/             # Arena extrinsics fix (Y-axis correction)
│   └── cal/extrinsics/      # Fixed rvec/tvec extrinsics
│
├── archive/                 # Historical files (not tracked in git)
│   ├── 01_initial_cameras/  # Early camera captures (Dec 2025)
│   ├── 02_calibration_legacy/  # Original calibration data
│   ├── 03_early_source/     # Initial src/, scripts/, config/, docs/
│   ├── 04_garage_backup/    # Feb 2026 snapshot
│   ├── 05_garage_cameras/   # GARAGE_CAMERAS recordings
│   ├── 06_pitch_demo/       # Presentation videos
│   ├── 07_old_outputs/      # Legacy rendering outputs
│   ├── 08_fps_safe/         # FPS-safe viewer prototype
│   ├── 09_sport_center/     # Sport center experiments
│   └── 10_misc/             # Miscellaneous files
│
└── thesis_draft.md          # Thesis draft document
```

## System Components

1. **4-camera synchronized capture** — USB cameras at 1280x720, 15 FPS
2. **Ball detection** — YOLO26m trained on dataset-main, 100 epochs, TRT FP16 @ imgsz 1280 (`models/ball/yolo26m-672.engine`)
3. **Pose estimation** — YOLO-Pose (6.2x faster than MMPose with TRT) or MMPose (RTMDet-m + RTMPose-m)
4. **Multi-view 3D triangulation** — SVD-based, EMA-smoothed joints; ball uses robust per-cam reprojection rejection + dedicated Kalman filter
5. **Kalman prediction** — 3D motion prediction at 200-400ms horizon (joints: PN=500, MN=10; ball: PN=800, MN=25)
6. **GT correction model** — Compensates systematic extrinsics bias (linear per-axis fit)
7. **Ballistic solver** — Pitch/yaw angles from 3D target position + launch speed
8. **BLM control** — ESP32 serial commands (set, shoot, reload, stop, estop)

## Key Entry Points

| Script | Purpose |
|--------|---------|
| `Parallel_working/scripts/live_4cam_arena_view_parallel.py` | Live 3D viewer (recommended) |
| `garage_lab_combined/scripts/launcher_runtime_from_udp.py` | BLM launcher runtime |
| `garage_lab_combined/scripts/live_aim_test.py` | Interactive live aim test (S2) |
| `garage_lab_combined/scripts/manual_aim_test.py` | Manual aim test on GT positions |
| `garage_lab_combined/scripts/process_4cam_to_3d.py` | Offline 3D processing |
| `Parallel_working/scripts/ablation_ema_adaptive.py` | EMA ablation study |
| `Parallel_working/scripts/validate_kalman_prediction.py` | Kalman prediction validation |
| `Parallel_working/scripts/export_models_tensorrt.py` | TensorRT model export |
| `Parallel_working/scripts/record_test_sequence.py` | Record test sequences |
| `Parallel_working/run_record_3d.sh` | Record 3D arena + 2D mosaic MP4s during live run |

## Quick Start

```bash
# Recommended: YOLO-Pose + Kalman prediction + cv2 renderer
./Parallel_working/run_live_parallel_yolopose.sh

# With TensorRT acceleration
./Parallel_working/run_live_parallel_yolopose.sh --yolopose-model yolo11m-pose.engine

# Launcher aim-only test (no shooting)
./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 \
  --no-shoot-enabled --correction-mode linear \
  --dry-run-log-jsonl garage_lab_combined/output/blm_logs/aim_test.jsonl
```

## Athlete Assessment + Exports

End-to-end recording → report → biomechanics-lab handoff.  Full per-session
protocol lives in [docs/capture_sop.md](docs/capture_sop.md).

```bash
# Generate JSON + HTML + C3D in one call:
PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.offline_assess \
  --input data/raw/athlete_001_squat.jsonl \
  --exercise squat \
  --athlete-id athlete_001 --age 10 --sex male --fps 15 \
  --session-id athlete_001_session_001 \
  --output data/reports/athlete_001_squat_report.json \
  --html-output data/reports/athlete_001_squat_report.html \
  --c3d-output data/reports/athlete_001_squat_report.c3d \
  --calibration-report data/reports/athlete_001_pre_session_calibration.json
```

Outputs:
- `*.json` — full per-rep metrics, flags, confidence tiering, demo verdict.
- `*.html` — coach-facing report with Data Quality / Movement Quality split,
  rep chart, calibration gate.
- `*.c3d` — COCO-17 joints as virtual markers in mm units. Opens in Mokka,
  Visual3D, OpenSim, and `ezc3d` Python pipelines. Includes `META.SESSION_ID`,
  `META.SCHEMA_VERSION`, and `SUBJECTS.NAMES` provenance fields.

## Closed-Loop Event Logging

Live viewer + launcher emit a curated event-narrative JSONL stream for demo
review and post-session analytics. See
[src/project_cam/closed_loop/event_log.py](src/project_cam/closed_loop/event_log.py)
for the schema. Non-blocking writer — never affects render FPS.

```bash
# Live viewer with event log:
./Parallel_working/run_live_blm.sh --session-id demo_001 \
  --event-log-output data/events/demo_001_viewer.jsonl

# Launcher with same session_id + confidence gates:
./venv/bin/python garage_lab_combined/scripts/blm_follow.py \
  --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 \
  --joint right_shoulder --correction-mode linear \
  --min-confidence 0.55 --min-cameras 2
```

In the live-viewer window, press `r` to record `athlete_reacted`, `n` for
`no_reaction`. Join the viewer events with the launcher decision log via
`session_id` to get the full target→aim→fire→outcome trace.

## Arena Setup

- 4 fixed cameras: camNorth, camEast, camSouth, camWest
- Arena dimensions: 6230mm x 3050mm x 2950mm
- Origin: North-East corner (0,0,0)
- All coordinates in mm
- BLM position: (600, 1560, 500) mm, facing South wall (yaw=0)

## Current Accuracy

| Metric | Ball (static) | Joint (touch) |
|--------|--------------|---------------|
| Mean error | 156.9 mm | 179.0 mm |
| P95 error | 288.3 mm | 243.8 mm |
| Precision (std) | 3.1 mm | 4.4 mm |
| Bias (correctable) | X+60, Z-104 mm | X+83, Z-125 mm |

## Latency (RTX 2080 Ti)

| Component | Time |
|-----------|------|
| YOLO ball detection | 8.1 ms (TRT FP16) |
| YOLO-Pose | 6.2 ms (TRT FP16) |
| MMPose | 38.5 ms/image |
| cv2 3D renderer | ~2 ms |

## Tech Stack

Python, OpenCV, Ultralytics YOLO, YOLO-Pose, MMPose, NumPy/SciPy, TensorRT, Kalman Filter, ESP32 (serial)
