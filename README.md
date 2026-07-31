# Project_Cam

**A 6-camera real-time computer-vision & edge-AI system for markerless 3D pose and
ball tracking, with predictive targeting and a safety-gated robotic launcher.**

YOLO / YOLO-Pose · OpenCV · SVD triangulation · Kalman prediction · TensorRT ·
multi-person tracking · local Face ID · 9 training drills · native coach app
(Tauri + React + Rust) · FastAPI service · Prometheus monitoring · Docker ·
reproducible 4-cam vs 6-cam benchmarks · model registry with a three-layer
licence audit · CI accuracy gate · 823 hardware-free tests.

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

On top of that core: cross-view **multi-person** association with stable IDs and
optional **local Face ID** labels, **9 coach-facing training drills** scored from
pose alone, and a native **Control Center** that supervises runs and writes
durable session evidence.

Full architecture + diagram: [docs/architecture.md](docs/architecture.md).
Deep technical walkthrough:
[docs/reports/project_cam_technical_system_report_en.md](docs/reports/project_cam_technical_system_report_en.md).

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

# 6-camera 3D arena with leg-raise identity lock + JSONL diagnostics
# Keep both legs flat for the first ~15 s; that window calibrates leg lengths.
mkdir -p artifacts_local/leg_raise_debug
DISPLAY=:1 PROJECT_CAM_WIDTH=640 PROJECT_CAM_HEIGHT=360 PROJECT_CAM_FPS=5 \
  ./Parallel_working/run_live_usb6_mirrored_skeleton.sh \
  --pose-conf 0.25 --udp-target-conf-min 0.25 --pose-max-reproj-px 70 \
  --no-show-ghost-skeleton --predict-ahead-ms 0 --limb-heat \
  --leg-raise-mode \
  --leg-raise-log-jsonl artifacts_local/leg_raise_debug/leg_raise_$(date +%Y%m%d_%H%M%S).jsonl

# Edge streaming demo (RTSP / file / device; BLM-disabled)
apps/edge_stream_demo/run_rtsp_demo.sh data/benchmark/walk.mp4
```

## Control Center (native coach app)

```bash
./project-cam-desktop/run.sh          # compiled release binary, opens <1 s
./project-cam-desktop/rebuild.sh      # REQUIRED after editing src/ or src-tauri/
```

Tauri 2 + React + Rust supervisor with CONTROL / TRAINING / SESSIONS / SHOTS
views. It launches pipelines and drills, streams their output to a mission log,
and **cannot actuate the launcher** — see [Safety](#safety).

The launch boundary is structural rather than conventional: the frontend names a
`profile_id` and supplies semantic parameters, and Rust resolves program, argv and
cwd. There is no way to express a program path, an argument vector or a working
directory from the UI. Every run gets an opaque session id and an owner-only
directory with an atomically written manifest and lifecycle records; all evidence
is read back through one bounded, typed reader. Supervisor states are
`Idle / Starting / Running / Stopping / Faulted`, and a stop that failed never
reads as stopped.

Readiness reporting is unknown-first: it states local file and device presence
only, and says plainly that presence does not prove camera health, calibration
quality, launcher connectivity, or fire authorization.

Details: [project-cam-desktop/README.md](project-cam-desktop/README.md).

## Training drills (view-only)

```bash
./Parallel_working/run_training_drill.sh balance --athlete Arlen --rounds 4
# if cameras fail to open at the drill default 10 fps:  PROJECT_CAM_FPS=5
```

Nine drills, scored from triangulated pose over UDP.

- **Field player** — `balance`, `shuttle`, `line_hops`, `cmj`, `hop_symmetry`,
  `reaction_zones`, `reactive_cut`
- **Goalkeeper** — `gk_save`, `gk_updown`

`reaction_zones` and `reactive_cut` use the projector as a cue surface; a
projected cue is a light on a wall, not an actuator.

`reactive_cut` fires its cue at the moment of commitment — the one measurement a
timing gate structurally cannot make, since photocells can time a rehearsed
shuttle but cannot decide *when* to ask.

Metric honesty is enforced by tests, not by convention:

- `cmj` reports `pelvis_rise_mm` against the athlete's own standing height —
  never a force-plate "jump height", and no conversion is offered.
- `hop_symmetry` reports the Limb Symmetry Index **together with both absolute
  distances**, and labels itself screening, not clearance: symmetry can be
  satisfied with both limbs weak. There is deliberately no pass/fail badge.
- `reactive_cut` records a wrong-way commit as an `error` (error rate under
  pressure is the measure) and a tracking loss as `void`, which does not consume
  a rep.
- There is no composite athlete score anywhere.

Timing resolution is derived from the observed packet rate (±0.5/Hz at ~15 Hz),
never asserted as a constant.

## Accuracy — 4-camera `arena_fixed` (measured)
| Metric | Ball (static) | Joint (touch) |
|--------|--------------|---------------|
| Mean error | 156.9 mm | 179.0 mm |
| P95 error | 288.3 mm | 243.8 mm |
| Precision (std) | 3.1 mm | 4.4 mm |
| Bias (correctable) | X+60, Z−104 mm | X+83, Z−125 mm |

> **There is no end-to-end ground truth for a moving human skeleton.** Every
> figure above is either reconstruction *repeatability* or a *static*-target
> comparison. The 4.4 mm column is precision on a static joint touch and must not
> be quoted as pose accuracy. No live-chain joint error has been measured.

## Latency (RTX 2080 Ti, measured)
| Component | Time |
|-----------|------|
| YOLO ball | 8.1 ms (TRT FP16) |
| YOLO-Pose | 6.2 ms (TRT FP16) |
| MMPose | 38.5 ms/image |
| cv2 3D renderer | ~2 ms |

More, incl. the 6-camera gate status and benchmark matrix:
[docs/performance_report.md](docs/performance_report.md).

## Model licensing (audited, and currently blocking commercial use)

The model registry records **code, weights and training-data licences as separate
layers**, because they routinely differ and the third is invisible in a
repository badge. `commercial_use` defaults to `undeclared`, so an unaudited
artifact can never read as permission, and declaring a model `clear` while any
layer carries a non-commercial marker raises rather than passes.

**None of the four active models is commercially clear today:**

| Model | Verdict | Blocker |
|-------|---------|---------|
| Ball detector (YOLO) | `blocked` | Ultralytics AGPL — code layer; the imagery is ours |
| Pose (YOLO11m-Pose) | `blocked` | Ultralytics AGPL — data layer (COCO) is fine |
| Face detect (YuNet) | `unverified` | per-model LICENSE not yet read |
| Face recognise (SFace) | `unverified` | per-model LICENSE not yet read |

This audit exists because the escape route we had written down was itself
contaminated: MMPose's code is Apache-2.0, but every published RTMPose checkpoint
is `pt-aic-coco`, pretrained on AI Challenger, which is research-only. That path
is now marked `deprecated` and kept registered so the blocker stays visible.
**RTMO-m** (COCO-only, Apache-2.0 end to end) is the verified clean replacement
candidate; the ball detector is the harder half, with no in-repo alternative.

Query it with `ModelRegistry.commercial_blockers()`, `GET /v1/models`, or
[docs/model_card.md](docs/model_card.md).

## Safety
The launcher runtime is the **only** component that can fire, behind zone /
confidence / camera-count / stability / angle-clamp / RPM gates plus ESTOP. The
API, edge demo, Control Center and all nine drills are architecturally incapable
of firing (tested — the drill wrapper may not reference `--shoot-enabled`,
`live_aim_test`, or a serial device, and no desktop launch profile actuates).
See [docs/safety_boundaries.md](docs/safety_boundaries.md).

Face ID produces identification labels only. It has no liveness or anti-spoofing
and is never a fire-authorization or access signal.

**Open blocker:** RPM→m/s exit-speed calibration. This is not only an accuracy
gap — the trajectory evaluator samples the commanded arc using assumed speed, so
speed uncertainty feeds clearance geometry directly. Until it is measured, the
nominal arc is not commissioned clearance, and multi-person actuation stays
disabled behind fixed low-energy presets and physical exclusion.

**Not yet live-commissioned:** the multi-person firing-line gate, and the drills
themselves, which are unit- and render-tested but have not run against a live
6-camera stream.

## Documentation
- [Current status](docs/current_status.md) · [Improvement plan + status](PROJECT_IMPROVEMENT_PLAN.md)
- [Architecture](docs/architecture.md) · [Case study](docs/portfolio_case_study.md)
- [Technical system report](docs/reports/project_cam_technical_system_report_en.md)
  · [fact-check ledger](docs/reports/project_cam_technical_system_report_fact_check_2026-07-29.md)
- [Control Center](project-cam-desktop/README.md)
- [Garage → academy pilot design](docs/superpowers/specs/2026-07-15-garage-pilot-product-design.md)
- [Job alignment](docs/job_alignment.md) · [Performance report](docs/performance_report.md)
- [Model card](docs/model_card.md) · [Data card](docs/data_card.md)
- [KZ youth data governance](docs/data_governance/kz_youth_academy_pilot.md)
- [KZ academy pricing hypothesis](docs/product/kz_academy_pricing_hypothesis.md)
- [Monitoring](docs/monitoring.md) · [Safety boundaries](docs/safety_boundaries.md)
- [MLOps quality layer](docs/mlops.md)
- [API demo (real responses)](docs/api_demo.md) · [OpenAPI spec](docs/openapi.json)
- [Canonical runtime](CANONICAL.md)
- [Archive manifest](docs/archive_manifest.md)

## Repository layout
```
src/project_cam/        # hardware-free core: geometry, kalman, monitoring, api,
                        #   streaming, assessment (incl. leg-raise mode)
src/project_cam/tracking/  # cross-view multi-person association + Face ID labels
src/project_cam/training/  # drill state machines (pure stdlib, clock-injected)
src/project_cam/viz/       # display-only skeleton stabiliser + unicode text
src/project_cam/models/    # model registry + three-layer licence audit
services/api/           # FastAPI app (aim-only)
project-cam-desktop/    # native Control Center (Tauri 2 + React + Rust)
configs/                # camera profiles (4cam / 6cam), calibration manifest, exercises
configs/models.yaml     # model registry/provenance + licence verdicts
benchmarks/             # reproducible benchmark suite (--dry-run)
deploy/                 # prometheus + grafana
apps/                   # edge_stream_demo, athlete_assessment runners
tests/                  # hardware-free pytest suite (823 tests, 66 files)
docs/                   # architecture, cards, safety, performance, monitoring
docs/reports/           # technical system report + fact-check ledger
docs/thesis_archive/    # thesis / defense history kept out of the root
artifacts_local/        # local generated/heavy artifacts (git-ignored)
Parallel_working/       # perf-optimized live pipeline (isolated)
garage_lab_combined/    # production runtime (live viewer, launcher, BLM scripts)
arena_fixed/            # validated 4-camera extrinsics (Y-axis fix) — do not override
```

## Tech stack
Python · OpenCV · Ultralytics YOLO / YOLO-Pose · MMPose / RTMO · NumPy/SciPy ·
TensorRT · Kalman filter · FastAPI · Prometheus · Docker · CI regression gates ·
Rust + Tauri 2 + React + TypeScript (Control Center) · ESP32 (serial).

See [Model licensing](#model-licensing-audited-and-currently-blocking-commercial-use)
before reusing the detector or pose weights.
