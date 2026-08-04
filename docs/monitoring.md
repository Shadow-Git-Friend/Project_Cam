# Monitoring

Project_Cam exposes Prometheus metrics so the pipeline and API behave like an
observable production video-analytics system. Metrics are defined once in
[`src/project_cam/monitoring/metrics.py`](../src/project_cam/monitoring/metrics.py)
and surfaced at `GET /metrics`.

## Start the API and scrape

```bash
# local
make api                 # uvicorn services.api.app.main:app on :8000
curl -s http://127.0.0.1:8000/metrics | head

# docker (api + prometheus)
docker compose -f docker-compose.cpu.yml up --build
# Prometheus UI: http://localhost:9090   API: http://localhost:8000
```

A Grafana dashboard is provided at
[`deploy/grafana/project_cam_dashboard.json`](../deploy/grafana/project_cam_dashboard.json)
(import it and point it at the Prometheus datasource).

`prometheus_client` is an **optional** dependency. Without it the metrics module
falls back to a pure-Python store that still renders valid Prometheus text, so
`/metrics` and the metric names are always available; with it installed (the
`api` extra) you get full histogram buckets.

## Metric catalogue

| Metric | Type | Labels | What it tells you |
|---|---|---|---|
| `project_cam_camera_count` | gauge | `camera_profile` | configured cameras (4 vs 6) |
| `project_cam_pose_camera_count` | gauge | `camera_profile` | cameras contributing to the live pose solve |
| `project_cam_frames_total` | counter | `camera_profile`, `camera_id` | per-camera throughput |
| `project_cam_dropped_frames_total` | counter | `camera_profile`, `camera_id` | stale / overflow drops |
| `project_cam_capture_latency_ms` | histogram | `camera_profile`, `camera_id` | capture stage |
| `project_cam_inference_latency_ms` | histogram | `camera_profile`, `stage`, `model_name`, `backend` | model latency |
| `project_cam_triangulation_latency_ms` | histogram | `camera_profile` | triangulation stage |
| `project_cam_pipeline_latency_ms` | histogram | `camera_profile` | end-to-end |
| `project_cam_gpu_memory_mb` | gauge | — | GPU memory in use |
| `project_cam_ball_reprojection_error_px` | histogram | `camera_profile` | ball geometry quality |
| `project_cam_joint_reprojection_error_px` | histogram | `camera_profile` | pose geometry quality |
| `project_cam_safety_gate_blocked_total` | counter | `gate_reason` | targets blocked by a safety gate |
| `project_cam_event_logger_dropped_total` | counter | — | event-log backpressure drops |
| `project_cam_frame_brightness` | gauge | `camera_profile`, `camera_id` | lighting drift / exposure health |
| `project_cam_frame_blur_laplacian_var` | gauge | `camera_profile`, `camera_id` | focus and motion-blur proxy |
| `project_cam_frame_quality_bad_total` | counter | `camera_profile`, `camera_id`, `quality_reason` | underexposed / overexposed / blurry / missing frames |

Label cardinality is kept low on purpose (`ALLOWED_LABELS`): never attach a frame
id, timestamp, file path, or raw session id.

## Reading the signals

- **Camera bandwidth issues** → `dropped_frames_total` climbing and
  `capture_latency_ms` rising, especially with all 6 USB cameras on one
  controller. This is the headline 6-camera bottleneck (see the data card).
- **Model latency issues** → `inference_latency_ms` p95 rising, or
  `pipeline_latency_ms` dominated by the inference stage. Compare `.pt` vs
  TensorRT via the `backend` label.
- **Geometry / calibration quality** → `ball_/joint_reprojection_error_px`
  drifting up means a camera pose or intrinsic has gone stale; the static-ball
  `< 25 px` gate is the calibration health check.
- **Input/data drift** → `frame_brightness` and `frame_blur_laplacian_var`
  drifting out of range, or `frame_quality_bad_total` rising, means lighting,
  focus, motion blur, or camera dropout may be degrading the model input before
  3D accuracy fails.
- **Safety-gate blocking** → `safety_gate_blocked_total{gate_reason=...}` shows
  why targets were rejected (`low_confidence`, `low_camera_count`, `stale`,
  `missing`). A spike means the perception input degraded.

## Wiring metrics into the live pipeline

The metrics registry (`get_metrics()`) is a process singleton. The live viewer
and launcher call `inc`/`set`/`observe` at the relevant stages, e.g.:

```python
from project_cam.monitoring import get_metrics
m = get_metrics()
m.set("project_cam_pose_camera_count", n_cams, camera_profile="usb6")
m.observe("project_cam_pipeline_latency_ms", dt_ms, camera_profile="usb6")
m.inc("project_cam_safety_gate_blocked_total", gate_reason=result.reason)
```

Frame quality can be sampled without OpenCV:

```python
from project_cam.quality import analyze_frame, record_frame_quality

q = analyze_frame(frame, camera_id="camUsb01_C920")
record_frame_quality(m, q, camera_profile="usb6")
```
