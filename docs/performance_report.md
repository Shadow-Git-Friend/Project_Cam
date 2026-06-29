# Performance Report

This report separates **measured** values from **planned/not-yet-measured** ones.
Regenerate the planned/config rows with `make benchmark-dry`; fill the measured
sections from real runs on the GPU host / live rig.

## Hardware (measured)
- **PC**: HP Z4 G4 — i9-7900X (10C/20T), 32 GB RAM, RTX 2080 Ti 11 GB (inference)
  + Quadro P400 (display), Ubuntu 22.04 / kernel 6.8.
- **Cameras (now)**: USB webcams (C920 + generic 1080P), MJPG, rolling shutter,
  no hardware sync. All 6 on one USB2 controller.
- **Planned upgrade**: 4× global-shutter GigE cameras + hardware trigger + quad
  NIC + NVMe (see the camera-upgrade notes in the repo rules).

## Models / backends (measured, RTX 2080 Ti)
| Component | Latency |
|---|---|
| YOLO ball | 8.7 ms (.pt) / 8.1 ms (TRT FP16) |
| YOLO-Pose | 8.9 ms (.pt) / 6.2 ms (TRT FP16) |
| MMPose | 38.5 ms/image (~80 ms batched 4-cam) |
| cv2 3D renderer | ~2 ms |

## 3D accuracy — 4-camera `arena_fixed` (measured)
| Metric | Ball (static) | Joint (touch) |
|---|---|---|
| Mean | 156.9 mm | 179.0 mm |
| P95 | 288.3 mm | 243.8 mm |
| Precision (std) | 3.1 mm | 4.4 mm |
| Bias (correctable) | X+60, Z−104 mm | X+83, Z−125 mm |

## 3D accuracy — 6-camera (NOT YET MEASURED)
Pending Phase 0 promotion gates (`configs/calibration/usb6_manifest.yaml`):

```text
capture_ok:                       <fill>
max_gap_ms <= 100 (per camera):   <fill>
all 6 intrinsics @ runtime res:   <fill>
all 6 extrinsics solved:          <fill>
mean reprojection error < 25 px:  <fill>
static 3D GT mean error (mm):     <fill>
static 3D GT P95 error (mm):      <fill>
4-camera fallback still runs:     yes
```

Do not state 6-camera production accuracy until these are filled from real runs.

## Latency / FPS benchmark matrix (planned → CSV)
Schema in `benchmarks/_bench_common.py`; rows marked `mode=dry_run, measured=False`
until run on hardware. Matrix:

```text
4-camera vs 6-camera
capture-only vs inference-only vs full pipeline
YOLO ball vs YOLO-Pose
PyTorch .pt vs ONNX Runtime vs TensorRT FP16
batch=4 vs batch=6
1280x720 vs 1920x1080
```

TensorRT `batch=6` requires engines exported with `dynamic=True`.

## Accuracy regression gate (hardware-free CI)
The measured thresholds above are encoded in
[`configs/eval_thresholds.yaml`](../configs/eval_thresholds.yaml). The CI gate is:

```bash
make eval-gate
```

It computes mean / P95 / precision from prediction-vs-GT point pairs and exits
non-zero when a model/calibration change exceeds the configured bounds. This is a
software-quality gate; it does not replace the live Phase 0 hardware promotion
gates for the 6-camera rig.

## Known bottlenecks (measured / observed)
- **USB2 single-controller bandwidth** caps the 6-camera capture rate (~15 fps
  ceiling observed) — the headline reason the GigE upgrade is orthogonal to the
  software work.
- **Rendering** (matplotlib) was the old hot spot; the cv2 renderer (~2 ms) fixed it.
- **Fast/bounce ball** is camera-geometry-limited, not a detector-threshold problem.

## Leg-raise metrics (planned)
To be reported from `data/validation/leg_raise/` once recorded:
`leg_raise_side_accuracy`, `leg_raise_angle_mae_deg`,
`leg_raise_angle_p95_error_deg`, `left_right_swap_count`,
`ankle_/knee_detection_rate`, `mean_contributing_cameras_per_leg_joint`,
`frames_with_inferred_leg_joint`, `frames_rejected_by_segment_prior`.
Initial targets: side accuracy ≥ 95% (slow clips), angle MAE ≤ 10°, ≤ 1 swap per
60 s alternating clip.
