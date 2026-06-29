# Project_Cam

**A 6-camera real-time computer-vision & edge-AI system for markerless 3D pose and
ball tracking, with predictive targeting and a safety-gated robotic launcher.**

YOLO / YOLO-Pose · OpenCV · SVD triangulation · Kalman prediction · TensorRT ·
FastAPI service · Prometheus monitoring · Docker · reproducible 4-cam vs 6-cam
benchmarks · model registry · CI accuracy gate.

> **6 cameras are the target direction. The validated 4-camera `arena_fixed`
> arena is the fallback** until the 6-camera capture/calibration/static-3D gates
> pass (`configs/calibration/usb6_manifest.yaml`). Measured numbers below are
> 4-camera; 6-camera accuracy is not yet measured.

MSc Thesis — ECE, Nazarbayev University.

---

## What it does
Cameras observe a garage arena → per-view YOLO ball + YOLO-Pose → undistort →
multi-view SVD/DLT triangulation (mm world frame) with robust per-camera
reprojection rejection → constant-velocity Kalman lead prediction (200–400 ms) →
UDP target broadcast → **safety-gated** launcher. A parallel **aim-only** API +
Prometheus monitoring layer makes the same core observable and integrable.

Full architecture + diagram: [docs/architecture.md](docs/architecture.md).

## Try it without cameras or a GPU

```bash
# install the aim-only service + dev tooling
pip install -e ".[api,dev]"
pip install opencv-python-headless        # cv2 for the geometry core

# run the API
make api                                  # http://127.0.0.1:8000  (/docs, /metrics)

# run the hardware-free test suite
pytest

# fail CI if a model/calibration swap regresses 3D accuracy
make eval-gate

# benchmark matrix (planned rows, no hardware needed)
make benchmark-dry
```

Docker (CPU service + Prometheus):

```bash
docker compose -f docker-compose.cpu.yml up --build
# API http://localhost:8000  ·  Prometheus http://localhost:9090
```

### API surface (aim-only — never fires the launcher)
`GET /health` · `GET /v1/system/info` · `GET /v1/cameras` ·
`POST /v1/triangulate` · `POST /v1/predict` · `POST /v1/detect/{ball,pose}` (501
until model-backed) · `POST /v1/session/report` · `GET /v1/models` ·
`POST /v1/evaluate` · `GET /metrics`.

## Run the live pipeline (rig required)

```bash
# Recommended: YOLO-Pose + Kalman + cv2 renderer
./Parallel_working/run_live_parallel_yolopose.sh

# Combined viewer + BLM aim overlay (aim-only)
./Parallel_working/run_live_blm.sh

# Supine leg-raise diagnostic/tracking mode (aim-only)
apps/athlete_assessment/run_live_leg_raise.sh --side right

# Edge streaming demo (RTSP / file / device; BLM-disabled)
apps/edge_stream_demo/run_rtsp_demo.sh data/benchmark/walk.mp4
```

## Accuracy — 4-camera `arena_fixed` (measured)
| Metric | Ball (static) | Joint (touch) |
|--------|--------------|---------------|
| Mean error | 156.9 mm | 179.0 mm |
| P95 error | 288.3 mm | 243.8 mm |
| Precision (std) | 3.1 mm | 4.4 mm |
| Bias (correctable) | X+60, Z−104 mm | X+83, Z−125 mm |

## Latency (RTX 2080 Ti, measured)
| Component | Time |
|-----------|------|
| YOLO ball | 8.1 ms (TRT FP16) |
| YOLO-Pose | 6.2 ms (TRT FP16) |
| MMPose | 38.5 ms/image |
| cv2 3D renderer | ~2 ms |

More, incl. the 6-camera gate status and benchmark matrix:
[docs/performance_report.md](docs/performance_report.md).

## Safety
The launcher runtime is the **only** component that can fire, behind zone /
confidence / camera-count / stability / angle-clamp / RPM gates plus ESTOP. The
API and edge demo are architecturally incapable of firing (tested). See
[docs/safety_boundaries.md](docs/safety_boundaries.md).

## Documentation
- [Architecture](docs/architecture.md) · [Case study](docs/portfolio_case_study.md)
- [Job alignment](docs/job_alignment.md) · [Performance report](docs/performance_report.md)
- [Model card](docs/model_card.md) · [Data card](docs/data_card.md)
- [Monitoring](docs/monitoring.md) · [Safety boundaries](docs/safety_boundaries.md)
- [MLOps quality layer](docs/mlops.md)
- [API demo (real responses)](docs/api_demo.md) · [OpenAPI spec](docs/openapi.json)
- [Improvement plan + status](PROJECT_IMPROVEMENT_PLAN.md) · [Canonical runtime](CANONICAL.md)
- [Archive manifest](docs/archive_manifest.md)

## Repository layout
```
src/project_cam/        # hardware-free core: geometry, kalman, monitoring, api,
                        #   streaming, assessment (incl. leg-raise mode)
services/api/           # FastAPI app (aim-only)
configs/                # camera profiles (4cam / 6cam), calibration manifest, exercises
configs/models.yaml     # model registry/provenance
benchmarks/             # reproducible benchmark suite (--dry-run)
deploy/                 # prometheus + grafana
apps/                   # edge_stream_demo, athlete_assessment runners
tests/                  # hardware-free pytest suite
docs/                   # architecture, cards, safety, performance, monitoring
docs/thesis_archive/    # thesis / defense history kept out of the root
artifacts_local/        # local generated/heavy artifacts (git-ignored)
Parallel_working/       # perf-optimized live pipeline (isolated)
garage_lab_combined/    # production runtime (live viewer, launcher, BLM scripts)
arena_fixed/            # validated 4-camera extrinsics (Y-axis fix) — do not override
```

## Tech stack
Python · OpenCV · Ultralytics YOLO / YOLO-Pose · MMPose · NumPy/SciPy · TensorRT ·
Kalman filter · FastAPI · Prometheus · Docker · CI regression gates · ESP32 (serial).
