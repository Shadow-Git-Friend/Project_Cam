# Project_Cam Production Portfolio Improvement Plan

Goal: present Project_Cam as a production ML/video-analytics + edge-AI system that
a Senior/Middle CV / Video Analytics / Edge AI employer can evaluate quickly,
**without overstating unvalidated claims**. 6 cameras are the target direction;
the validated 4-camera `arena_fixed` arena is the fallback until the 6-camera
promotion gates pass.

Conservative around geometry and safety: do not overwrite `arena_fixed`, do not
modify the protected geometry functions, do not enable `--shoot-enabled` on the
6-camera path, and never mix normalized observations with `K @ [R|t]`.

---

## Implementation status — 2026-06-29

Legend: ✅ done (software, tested) · 🟡 partial · ⏳ needs hardware/operator · ⛔ deliberately not done.

| Phase | Status | What landed |
|---|---|---|
| **0 — 6-camera promotion gates** | 🟡 | 2026-06-29 run filled `configs/calibration/usb6_manifest.yaml`: frame-health capture passed (min FPS 16.51, max gap 81.11 ms), intrinsics passed at 1280x720, extrinsics solved for all 6 (mean RMSE 2.97 px, max 6.41 px). Full promotion still blocked by single USB controller topology and missing six-camera static-GT trial data. |
| **1 — Repo cleanup & restructure** | ✅ | `pyproject.toml`, expanded `.gitignore`, camera configs, `docs/archive_manifest.md`, thesis/archive moves under `docs/`, and local generated/heavy material moved to ignored `artifacts_local/`. Active runtime/calibration paths preserved. |
| **2 — Backend & API** | ✅ | `src/project_cam/api/` + `services/api/app/main.py`: `/health`, `/v1/system/info`, `/v1/cameras`, `/v1/triangulate`, `/v1/predict`, `/v1/detect/{ball,pose}` (501), `/v1/session/report`, `/metrics`. Reuses geometry core; aim-only. |
| **3 — Containerization & CI/CD** | ✅ | `Dockerfile` (CPU), `Dockerfile.gpu`, `docker-compose.{cpu,gpu}.yml`, `Makefile`, `.github/workflows/{ci,docker-smoke}.yml`, `requirements-api.txt`. |
| **4 — Optimization & benchmarking** | ✅ | `benchmarks/{benchmark_inference,benchmark_pipeline,benchmark_camera_count}.py` with `--dry-run` + CSV schema (`_bench_common.py`), `benchmarks/results/README.md`. Real numbers need the GPU host. |
| **5 — MLOps & monitoring** | ✅ | `src/project_cam/monitoring/metrics.py` (Prometheus + dependency-free fallback), model registry/provenance (`configs/models.yaml`, `src/project_cam/models/`), 3D accuracy regression gate (`src/project_cam/evaluation/`, `make eval-gate`, CI), input-quality drift checks (`src/project_cam/quality/`), `deploy/prometheus/prometheus.yml`, `deploy/grafana/project_cam_dashboard.json`, `docs/{monitoring,mlops}.md`. |
| **6 — Streaming / edge demo** | ✅ | `src/project_cam/streaming/rtsp_source.py`, `apps/edge_stream_demo/` (README, run script, GStreamer notes). BLM-disabled. |
| **7 — Supine leg-raise mode** | ✅ | `assessment/live_trainer/{leg_raise_mode,limb_identity,limb_constraints,leg_raise_stabilizer}.py`, `configs/exercises/leg_raise.yaml`, `apps/athlete_assessment/run_live_leg_raise.sh`, and opt-in `--leg-raise-mode` in the live 3D arena for lower-body identity lock + JSONL diagnostics. Does not change squat/push-up. |
| **8 — Docs & polish** | ✅ | `docs/{architecture,portfolio_case_study,job_alignment,performance_report,model_card,data_card,safety_boundaries}.md`; README updated. |

**Tests added** (hardware-free): `test_camera_profiles`,
`test_monitoring_metrics`, `test_api_schemas`, `test_api_health`,
`test_api_triangulate`, `test_model_registry`, `test_frame_quality`,
`test_eval_gate_cli`, `test_api_mlops`, `test_leg_raise_mode`,
`test_limb_identity`, `test_limb_constraints`, `test_leg_raise_stabilizer`,
`test_rtsp_source_config`,
`test_benchmark_dry_run`. API/FastAPI tests skip cleanly without the `api` extra
and run in CI/Docker.

**Verification run 2026-06-29**:

```bash
make lint          # ruff: all checks passed
make test          # 269 passed (api extra installed; was 238 passed/3 skipped)
make eval-gate     # ball_static CI regression gate passed
make benchmark-dry # wrote camera-count, inference, and pipeline dry-run CSVs
```

The `api` extra (fastapi/pydantic/prometheus/httpx/uvicorn) is now installed in
the venv, so the API tests run for real and the service was booted end-to-end:
health, system-info, cameras, triangulate (recovers a synthetic point to
sub-micron), predict, and `/metrics` all verified. Captured in
`docs/api_demo.md`; OpenAPI committed at `docs/openapi.json`.

Docker smoke was not run in this local checkout because Docker is not installed
(`docker: command not found`). The Docker smoke workflow is present in
`.github/workflows/docker-smoke.yml` for a runner/host with Docker.

**Not done on purpose:** Phase 0 hardware runs (no cameras here), moving
runtime-linked paths such as `proxiball_3d-main/projector/`,
`yolo11m-pose.engine`, `control_12_full.ino`, `Remounted_West_East/`, and
`cameras.md`, and anything touching `arena_fixed` or the protected geometry
functions or `--shoot-enabled`.

---

## Phase 0 — Six-camera promotion gates (⏳ hardware)
Run `scripts/usb6_capture_gate.py`, validate intrinsics at the live resolution,
solve extrinsics (`scripts/solve_extrinsics_usb6.py`), run static 3D GT, and fill
`configs/calibration/usb6_manifest.yaml` + `docs/performance_report.md`.

2026-06-29 evidence: the frame-health part of the 30 s capture gate passed for
all six cameras, intrinsics at 1280x720 passed, and extrinsics solved for all six
with mean reprojection RMSE 2.97 px. The full capture gate did **not** pass
because all six cameras still enumerate under one USB controller. Static 3D GT
was not run because no six-camera static-GT trial dataset was available.

Acceptance: `capture_ok`, no camera drops in 30 s, `max_gap_ms ≤ 100`/camera, all
6 intrinsics at runtime res, all 6 extrinsics, mean reprojection `< 25 px`, static
3D GT mean + P95 documented, 4-camera fallback still runs.

Do **not**: overwrite `arena_fixed`, rename camera roles before validation, enable
`--shoot-enabled` on the 6-camera path, or claim 6-camera accuracy from overlays.

## Phase 1 — Repo cleanup (✅)
Keep the curated surface in root; archive thesis/defense material under
`docs/thesis_archive/`; move local/generated/heavy material under ignored
`artifacts_local/`; keep runtime-linked assets in place until their references
are updated in a separate pass. See `docs/archive_manifest.md`.

## Phase 2 — API (✅)
Aim-only FastAPI service over the geometry core. The API can never `shoot`.

## Phase 3 — Docker & CI (✅)
CPU image for the service + CI; GPU image for live inference (built on the GPU
host, weights mounted not baked). CI is camera/GPU-free; Docker smoke calls `/health`.

## Phase 4 — Benchmarks (✅)
Reproducible CSV schema; `mode`/`measured` columns separate real numbers from
planned ones. Dry-run works without GPU/cameras.

## Phase 5 — Monitoring (✅)
Prometheus metrics by exact name; Grafana dashboard; model registry; CI 3D
accuracy gate; input-quality/drift monitor; docs.

## Phase 6 — Streaming / edge demo (✅)
RTSP/file/device ingestion + GStreamer pipeline string; JSONL events; BLM disabled.

## Phase 7 — Supine leg-raise mode (✅)
Per-leg elevation angle, left/right identity lock, segment-length priors, rep
counting. Single-camera joint recovery off unless explicitly enabled. The live
3D arena now has an opt-in `--leg-raise-mode` that applies lower-body left/right
identity lock before EMA and writes per-frame JSONL diagnostics. Validation
dataset + measured metrics are the remaining (hardware) step.

## Phase 8 — Docs & portfolio polish (✅)
README + architecture + case study + job alignment + model/data cards + safety +
performance report + monitoring + MLOps quality docs.

---

## Resume positioning
> Built a 6-camera real-time CV and edge-AI system for markerless 3D pose and ball
> tracking, using YOLO/YOLO-Pose, OpenCV, SVD triangulation, Kalman prediction,
> TensorRT acceleration, safety-gated robotic control, FastAPI service packaging,
> Prometheus monitoring, Docker deployment, model registry/provenance, CI
> accuracy gates, input-quality drift monitoring, and reproducible 4-camera vs
> 6-camera benchmarks.

Honest caveat: the 4-camera setup is the validated fallback; the 6-camera setup is
the target production direction and must pass capture, calibration, and static 3D
GT gates before production-accuracy claims are made.
