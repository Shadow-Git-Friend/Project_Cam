# API Demo (real responses)

Captured from the running service (no GPU, no cameras). Reproduce with:

```bash
pip install -e ".[api,dev]"
make api                     # uvicorn on :8000 — open http://127.0.0.1:8000/docs
```

The OpenAPI spec is committed at [openapi.json](openapi.json). The
service is **aim-only**: `shooting_enabled` is always `false` and no `shoot`/`fire`
route exists.

## Health
```http
GET /health  ->  200
{ "status": "ok", "service": "project-cam-api", "version": "0.1.0" }
```

## System info
```http
GET /v1/system/info  ->  200
{
  "camera_profile": "usb6", "camera_count": 6,
  "fallback_profile": "arena_fixed_4cam", "units": "mm",
  "shooting_enabled": false,
  "available_profiles": ["usb6", "arena_fixed_4cam"]
}
```

## Triangulation (reuses the geometry core)
Four synthetic cameras observing one world point; the endpoint recovers it to
sub-micron precision and reports latency.
```http
POST /v1/triangulate  ->  200
{
  "point_mm": [1500.0, 800.0, 900.0],
  "contributing_cameras": ["a", "b", "c", "d"],
  "camera_count": 4,
  "calibration_profile": "usb6",
  "latency_ms": 0.56
}
```
Guards: `< 2` observations → `422`; pixel-space observations → `422`; no
projection matrices → `501` (server-side calibration not configured).

## Prediction (constant-velocity Kalman lead)
8-sample track at ~1500 mm/s in +x, led 400 ms ahead:
```http
POST /v1/predict  ->  200
{
  "filtered_position_mm": [689.6, 0.0, 1000.0],
  "velocity_mm_s": [1496.8, 0.0, 0.0],
  "predicted_position_mm": [1288.3, 0.0, 1000.0],
  "prediction_uncertainty_mm": 83.3,
  "predict_ahead_ms": 400.0, "samples": 8
}
```

## Metrics
```http
GET /metrics  ->  200   (Prometheus text exposition)
# HELP project_cam_triangulation_latency_ms Multi-view triangulation latency in milliseconds.
# TYPE project_cam_triangulation_latency_ms histogram
project_cam_camera_count{camera_profile="usb6"} 6.0
...
```
See [monitoring.md](monitoring.md) for the full metric catalogue.

## Model registry
```http
GET /v1/models  ->  200
{
  "registry_version": 1,
  "default_models": {
    "ball_detection": "ball_yolo26m_672_trt",
    "pose_estimation": "pose_yolo11m_trt"
  },
  "models": [
    {
      "model_id": "ball_yolo26m_672_trt",
      "task": "ball_detection",
      "backend": "tensorrt",
      "status": "active",
      "checksum_status": { "status": "unregistered", "sha256": null }
    }
  ]
}
```

## Evaluation gate
```http
POST /v1/evaluate  ->  200
{
  "passed": true,
  "suite": "ball_static",
  "failures": [],
  "metrics": { "n": 5, "mean_mm": 3.92, "p95_mm": 5.8 },
  "thresholds": { "min_n": 5, "max_mean_mm": 180.0 }
}
```

The endpoint accepts inline `pairs` or precomputed `metrics`. A regression is
reported as `passed: false`, not a 500 error.
