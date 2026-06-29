# Portfolio Case Study — Project_Cam

## Problem
Aim a robotic ball launcher at a moving person in a real arena. That requires
knowing, in real time and in metric 3D, *where a target is now* and *where it will
be* a few hundred milliseconds later — from cheap cameras, on one workstation,
safely.

## Constraints
- Commodity USB webcams (rolling shutter, no hardware sync), one GPU box.
- Indoor garage arena, mm-accurate world frame, 15–30 fps budget.
- A physical launcher: incorrect commands can injure — safety is non-negotiable.
- Research/portfolio scope: must be reproducible and reviewable without the rig.

## System design
Threaded latest-frame capture → per-view YOLO ball + YOLO-Pose → undistort →
multi-view SVD/DLT triangulation with robust per-camera reprojection rejection →
constant-velocity Kalman lead prediction → UDP target broadcast → safety-gated
launcher. A parallel aim-only API + Prometheus monitoring layer makes the same
core observable and integrable. See [architecture.md](architecture.md).

## 6-camera upgrade
The validated baseline is 4 cameras (`arena_fixed`). The target direction is 6
cameras for coverage. Rather than claim it works, the repo gates it: a capture
gate, intrinsics-at-runtime-resolution check, extrinsics solve, and a static 3D
`< 25 px` / GT-mm acceptance, tracked in `configs/calibration/usb6_manifest.yaml`.
Until those pass, 4 cameras stay the runtime fallback.

## Model & inference stack
YOLO26m ball + YOLO11m-Pose, exported to TensorRT FP16 with dynamic batch (static
batch=1 fails on 4/6-cam batches). YOLO-Pose is ≈6× faster than MMPose at matching
3D accuracy. cv2 3D renderer replaced matplotlib (~200 ms → ~2 ms).

## Calibration & geometry
The one rule that makes or breaks DLT: **normalized undistorted observations pair
with the bare extrinsic `[R|t]`, never `K @ [R|t]`**. A real goal-game scoring bug
was root-caused to exactly this mismatch (≈1400 px reprojection → < 25 px once
fixed). Robust triangulation drops a camera whose reprojection disagrees, so a
stale pose can't fling a joint across the room.

## Productionization work
FastAPI service (reusing the geometry core, never copying it), pydantic schemas,
Prometheus metrics with a dependency-free fallback, CPU + GPU Docker images,
GitHub Actions CI + Docker smoke, a reproducible benchmark schema that marks
measured vs planned rows, a model registry/provenance file, a CI 3D-accuracy
regression gate, input-quality drift metrics, and a BLM-disabled
RTSP/GStreamer edge demo.

## Supine leg-raise tracking mode
Lying leg raises were hard to read on a generic skeleton (which leg, how high).
The fix is an exercise-specific post-processor: per-leg elevation angle, left/right
identity lock with swap hysteresis, and segment-length priors that reject
anatomically impossible frames — without touching the squat/push-up paths, and
with single-camera joint *recovery* off unless explicitly enabled.

## Benchmarks
Schema covers FPS, latency p50/p95/p99, per-stage latency, GPU memory, dropped
frames, reprojection error, 3D error, detection/FP rate — across 4 vs 6 cameras,
backends, batch sizes, and resolutions. Dry-run rows are generated without
hardware; real rows come from the GPU host. See [performance_report.md](performance_report.md).

## MLOps quality controls
`configs/models.yaml` records active/reference models without loading their
weights. `make eval-gate` runs a hardware-free 3D accuracy regression gate over
prediction-vs-GT pairs, and CI blocks regressions. Frame-quality metrics expose
brightness, blur, and dropout drift so bad input conditions are visible before
they become model failures. See [mlops.md](mlops.md).

## Safety
The launcher runtime is the *only* component that can fire, behind zone /
confidence / camera-count / stability / angle-clamp / RPM gates plus ESTOP. The
API and edge demo are architecturally incapable of firing — enforced and tested.
See [safety_boundaries.md](safety_boundaries.md).

## Limitations
- 6-camera accuracy not yet measured; all six share one USB2 controller.
- Fast/bounce-ball tracking is camera-geometry-limited (hardware, not threshold).
- Supine pose estimation is weaker than standing; one high oblique view would help.
- Kalman is ~neutral on jumps (constant-velocity model).

## What I'd improve next
Global-shutter GigE cameras + hardware sync; close the RPM→m/s ballistic
calibration; finish the 6-camera promotion gates; record the leg-raise validation
set and report its metrics; extend live metrics emission deeper into the
viewer/launcher.
