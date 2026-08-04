# MLOps Quality Layer

Project_Cam now treats model artifacts, 3D accuracy, and camera input quality as
versioned signals rather than informal notes. The goal is to catch silent
regressions when a model, calibration, or camera condition changes.

## Model registry

Model metadata lives in [`configs/models.yaml`](../configs/models.yaml). It
records:

- model id, task, version, backend, artifact format, and input size;
- local artifact path and deployment status (`active`, `reference`, `planned`);
- optional SHA-256 checksum for provenance verification;
- measured latency / detection notes when available.

Use it from Python without loading YOLO/TensorRT:

```python
from project_cam.models import load_model_registry

registry = load_model_registry()
ball = registry.default_model("ball_detection")
print(ball.model_id, registry.checksum_status(ball.model_id))
```

The API exposes the same metadata at `GET /v1/models`.

## 3D accuracy regression gate

Ground-truth gates are configured in
[`configs/eval_thresholds.yaml`](../configs/eval_thresholds.yaml). The gate
compares prediction-vs-ground-truth point pairs against documented thresholds:

```bash
make eval-gate

python -m project_cam.evaluation.gate \
  --pairs tests/fixtures/eval_pairs_ball_static.json \
  --suite ball_static
```

The same logic is available through `POST /v1/evaluate`, accepting either inline
`pairs` or precomputed `metrics`. A failed gate returns a structured payload
(`passed=false`) instead of a server error, which makes it suitable for dashboards
and CI summaries.

CI runs this gate after the hardware-free test suite, so a model/calibration
change can fail the build if it silently worsens 3D accuracy.

## Input-quality and drift checks

[`src/project_cam/quality/frame_quality.py`](../src/project_cam/quality/frame_quality.py)
computes camera-quality signals without OpenCV:

- mean brightness (`underexposed`, `overexposed`);
- Laplacian-variance blur metric (`blurry`);
- missing frame/dropout (`missing_frame`).

The metrics can be emitted to Prometheus:

```python
from project_cam.monitoring import get_metrics
from project_cam.quality import analyze_frame, record_frame_quality

result = analyze_frame(frame, camera_id="camUsb01_C920")
record_frame_quality(get_metrics(), result, camera_profile="usb6")
```

Prometheus metric names:

- `project_cam_frame_brightness`
- `project_cam_frame_blur_laplacian_var`
- `project_cam_frame_quality_bad_total`

These are deliberately low-cardinality (`camera_profile`, `camera_id`, and
quality reason only), so they are safe for long-running video analytics.

## What this proves

This layer demonstrates production ML habits around a CV system:

- model provenance is explicit and machine-readable;
- accuracy is guarded by thresholds, not screenshots;
- CI can block regressions without cameras or a GPU;
- camera/data drift is observable before model predictions degrade;
- API and documentation expose the lifecycle state honestly.
