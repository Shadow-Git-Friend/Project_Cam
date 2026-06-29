# Data Card

## Context
Data is collected in a domestic garage arena (≈6230 × 3050 × 2950 mm) using
commodity USB webcams. It supports a research/portfolio system for 3D
ball/pose tracking and athlete movement assessment.

## Camera setup
- **4-camera (validated)**: `camNorth`, `camEast`, `camSouth`, `camWest`,
  intrinsics calibrated at 1280×720, extrinsics in `arena_fixed/` (Y-axis fix).
- **6-camera (prototype)**: six USB cameras (`camUsb01..06`), capture-validated;
  full intrinsics/extrinsics/static-GT promotion gates pending
  (`configs/calibration/usb6_manifest.yaml`). All six currently enumerate on one
  USB2 controller → shared-bandwidth ceiling (documented, not hidden).

## Ground-truth datasets
- **Static ball GT** and **joint-touch GT**: measured millimeter targets used for
  3D accuracy evaluation (`garage_lab_combined/gt_eval/`).
- **Recorded sequences** (walk / jog / jump, bounce / fast / slow ball) for EMA,
  Kalman, and detector ablations.
- **Validation set (planned)** for the leg-raise mode:
  `data/validation/leg_raise/{right,left}_leg_{30,60,90}deg/`, `alternating_*`.
  Each clip carries an operator note (intended side + target angle) and a debug
  JSONL with per-joint confidence and camera count.

## Subjects / privacy
Imagery includes identifiable people (the developer and consenting participants).
Raw frames and videos are **local artifacts**, git-ignored (`camUsb*/`,
`*/output/`, `artifacts_local/`, `*.mp4`), and not published. Only derived
numerical results (mm errors, JSONL events, benchmark CSVs) are shared. Obtain
consent before recording new subjects; do not commit raw media.

## Bias / coverage limitations
- Single arena, single lighting/background regime → limited generalization.
- Supine-pose coverage is weaker than standing; one high oblique/top view would
  help leg-raise observation more than additional side views.
- Bounce/fast-ball coverage is structurally camera-geometry-limited.
- Small subject pool → not representative for population-level biomechanics.

## Input-quality monitoring
The runtime can sample frames with
[`project_cam.quality.frame_quality`](../src/project_cam/quality/frame_quality.py)
to record brightness, blur, and missing-frame/dropout reasons. These signals are
not dataset labels; they are operational data-quality checks that help explain
when a model/regression result degraded because the input stream changed.

## Storage policy
Calibration artifacts (intrinsics/extrinsics/manifests) and small GT/report JSON
are tracked. Heavy media, per-camera frame dumps, generated project trees, local
capture outputs, and benchmark/result CSVs are git-ignored under
`artifacts_local/` or the existing output directories and kept locally or in
external storage.
