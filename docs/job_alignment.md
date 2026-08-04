# Job Alignment

How Project_Cam maps to common CV / Video-Analytics / Edge-AI / ML role
requirements (Astana / Almaty market and similar).

| Requirement area | Where it shows up in this repo |
|---|---|
| **Computer Vision** | YOLO ball detection, YOLO-Pose, OpenCV, SVD/DLT triangulation, robust per-camera reprojection rejection (`src/project_cam/geometry/`) |
| **Multi-view 3D / geometry** | Calibrated intrinsics+extrinsics, normalized-obs ↔ `[R|t]` discipline, single-camera ray→plane fallback, mm world frame |
| **Video Analytics** | Multi-camera capture, RTSP/file/device ingestion + GStreamer pipeline (`src/project_cam/streaming/`, `apps/edge_stream_demo/`), JSONL event stream |
| **Edge AI** | TensorRT FP16 engines (dynamic batch), 4-cam vs 6-cam benchmark matrix, USB bandwidth as an explicit bottleneck, GPU image (`benchmarks/`, `Dockerfile.gpu`) |
| **Inference optimization** | `.pt` vs ONNX vs TensorRT, batch=4/6, 1280×720 vs 1920×1080, latency p50/p95/p99 schema (`benchmarks/_bench_common.py`) |
| **Production ML / backend** | FastAPI service reusing the geometry core, pydantic schemas, typed errors, OpenAPI (`services/api/`, `src/project_cam/api/`) |
| **Docker / Linux / CI-CD** | CPU + GPU Dockerfiles, compose stacks, Makefile, GitHub Actions CI + Docker smoke (`Dockerfile*`, `.github/workflows/`) |
| **MLOps / monitoring** | Model registry/provenance, CI 3D accuracy gate, input-quality drift metrics, Prometheus metrics by name, Grafana dashboard, model/data cards, reproducible benchmarks (`src/project_cam/{models,evaluation,quality,monitoring}/`, `configs/models.yaml`, `deploy/`, `docs/`) |
| **Safety-critical integration** | Architectural safety boundary (API can't fire), safety gates, event audit log (`docs/safety_boundaries.md`) |
| **Real-time systems** | Threaded latest-frame capture, staleness gating, Kalman lead prediction, FPS instrumentation |
| **Testing discipline** | Hardware-free pytest suite (geometry, kalman, API, monitoring, model registry, eval gate, frame quality, leg-raise, streaming, benchmarks) runnable without cameras/GPU |
| **Biomechanics / applied CV** | Athlete assessment reports, C3D export, supine leg-raise mode with left/right identity lock + segment priors |

## One-line positioning

> A 6-camera real-time CV and edge-AI system for markerless 3D pose/ball tracking
> — YOLO/YOLO-Pose, OpenCV, SVD triangulation, Kalman prediction, TensorRT,
> safety-gated robotic control, FastAPI service, Prometheus monitoring, Docker
> deployment, model provenance, CI accuracy gates, input-quality monitoring, and
> reproducible 4-cam vs 6-cam benchmarks.

## Honest caveat (use when asked)

> The 4-camera setup is the validated fallback. The 6-camera setup is the target
> production direction and must pass capture, calibration, and static 3D GT gates
> before production-accuracy claims are made.
