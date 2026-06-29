# Model Card

## Models in the pipeline

Machine-readable provenance is tracked in
[`configs/models.yaml`](../configs/models.yaml) and exposed by `GET /v1/models`.

| Role | Model | Backend | Notes |
|---|---|---|---|
| Ball detection | YOLO26m (`models/ball/yolo26m-672.engine`) | TensorRT FP16, dynamic batch | trained on dataset-main, 100 epochs |
| Pose (primary) | YOLO11m-Pose | TensorRT FP16 / `.pt` | COCO-17, ≈6× faster than MMPose |
| Pose (fallback) | RTMDet-m + RTMPose-m (MMPose) | PyTorch | slightly more keypoints, slower |
| Prediction | Constant-velocity 3D Kalman filter | NumPy | not learned; tuned PN/MN |

## Intended use
Markerless 3D ball/pose tracking in a calibrated indoor arena for predictive
targeting research and athlete movement assessment. **Not** for medical diagnosis
and **not** for autonomous unsafe actuation — firing is human-supervised and
safety-gated.

## Training / evaluation data
Garage-arena imagery and a project ball dataset (see [data_card.md](data_card.md)).
3D accuracy is evaluated against measured millimeter ground-truth points (static
ball and joint-touch protocols).

## Metrics (measured, 4-camera `arena_fixed`)
| Metric | Ball (static) | Joint (touch) |
|---|---|---|
| Mean error | 156.9 mm | 179.0 mm |
| P95 error | 288.3 mm | 243.8 mm |
| Precision (std) | 3.1 mm | 4.4 mm |
| Systematic bias | X+60, Z−104 mm | X+83, Z−125 mm |

Bias is a correctable systematic (linear correction model); precision is
excellent. 6-camera accuracy is **not yet measured** — see
[performance_report.md](performance_report.md).

## Latency (measured, RTX 2080 Ti)
YOLO ball 8.1 ms (TRT FP16) · YOLO-Pose 6.2 ms (TRT FP16) · MMPose 38.5 ms/image ·
cv2 3D renderer ≈2 ms.

## Known failure modes
- **Fast / bouncing ball**: motion blur and frustum geometry — at the bounce
  moment often only one camera sees the ball; resolution (`--ball-imgsz 960`) and
  the single-camera fallback help, camera placement is the real fix.
- **Supine poses**: generic RGB pose models are weaker lying down; left/right leg
  labels can swap (mitigated by the leg-raise identity lock + segment priors).
- **Oblique pose views**: YOLO-Pose detection ~94% vs MMPose ~100%.
- **Kalman on jumps**: constant-velocity model is ~neutral on jump motion.

## Runtime backends / export
Export TensorRT engines with `dynamic=True, batch=N`; static batch=1 engines fail
on batched multi-cam inference. After any `.pt` swap, rebuild the `.engine` from
scratch.

## Regression control
Model or calibration changes must pass the 3D accuracy gate:

```bash
make eval-gate
```

Thresholds live in [`configs/eval_thresholds.yaml`](../configs/eval_thresholds.yaml).
The gate is hardware-free and runs in CI; it is a guard against silently shipping
a worse model/calibration pair.

## Ethical / safety notes
See [safety_boundaries.md](safety_boundaries.md). The API and edge demo cannot
fire the launcher.
