# Project_Cam — Claude Code Guide

## Project
- **Title**: Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking
- **Author**: Hanush, MSc ECE, Nazarbayev University
- **Stack**: Python, OpenCV, YOLO, YOLO-Pose, MMPose, NumPy/SciPy, Kalman Filter

## Arena & Units
- 4 fixed USB cameras: camNorth, camEast, camSouth, camWest
- All coordinates in **mm**. Runtime resolution: **1280x720**
- Capture target: 15 FPS. Inference target: 5 FPS

## Key Entry Points
- Live viewer: `garage_lab_combined/scripts/live_4cam_arena_view.py`
- Launcher runtime: `garage_lab_combined/scripts/launcher_runtime_from_udp.py`
- Offline 3D pipeline: `garage_lab_combined/scripts/process_4cam_to_3d.py`
- Parallel perf viewer: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`
- TensorRT export: `Parallel_working/scripts/export_models_tensorrt.py`
- Test recording: `Parallel_working/scripts/record_test_sequence.py`
- EMA ablation: `Parallel_working/scripts/ablation_ema_adaptive.py`

## BLM Firmware (control_12_full.ino — current)
- **Serial baud: 921600** (was 115200 in control_11)
- **Limit switches: PULLUP, triggered on LOW** (was PULLDOWN+HIGH in control_11)
- BLE name: `RoboLauncher` (USB serial backup also active)
- Pusher uses DRV8825 with active enable management (HIGH=rest/cool, LOW=move)
- Telemetry suppressed during pusher motion to avoid interference

### Commands
- `set v h wl wr` — aim (angles clamped ±30°) + set wheel RPMs
- `shoot` — fire (RPM gate: both wheels ≥400 RPM)
- `reload` — retract → dispense → ball detect (or 10s timeout) → IDLE; also centers + spins down
- `stop` / `center` / `setzero` / `info`
- Manual jog: `jv<steps>`, `jh<steps>`, `jf<steps>` (pusher), `js<0-180>` (servo angle)
- Live tuning (no reflash): `jsset<val>`, `jfspeedset<val>`, `jfaccelset<val>`
- `info` reports: angles, RPMs, feeder state, limit switch states (Front/Back/Ball), live config

### State machine
- IDLE → `reload` → RETRACTING → (back limit LOW) → DISPENSING → (ball limit LOW or 10s timeout) → IDLE
- IDLE → `shoot` → SHOOTING → (RPM ≥ 400) → pusher fwd → (front limit LOW) → IDLE

## Calibration Artifacts
- Intrinsics: `garage_lab_combined/cal/intrinsics/cam{North,East,South,West}_intrinsics.json`
- Extrinsics: `arena_fixed/cal/extrinsics/extrinsics_fixed.json` (rvec/tvec format, meters)
- Dimensions: `arena_fixed/cal/extrinsics/Dimensions_fixed.txt`

## Guardrails
- **Never** modify geometry-critical functions without explicit approval:
  `triangulate_multi`, `transform_world_point_y`, `ema_update`, UDP axis semantics
- **Never** enable `--shoot-enabled` without passing BLM safety tests (S4)
- **Never** change resolution without verifying intrinsics scaling
- `Parallel_working/` is isolated — do not merge into production without approval
- `arena_fixed/` owns the Y-axis fix — do not override its extrinsics/dimensions

## Run Commands (Current Best)
```bash
# YOLO-Pose + prediction (6x faster pose, RECOMMENDED):
./Parallel_working/run_live_parallel_yolopose.sh

# YOLO-Pose with TensorRT (fastest):
./Parallel_working/run_live_parallel_yolopose.sh --yolopose-model yolo11m-pose.engine

# Predictive profile (MMPose backend + Kalman prediction):
./Parallel_working/run_live_parallel_predictive.sh

# Smooth v2 (cv2 renderer, no prediction):
./Parallel_working/run_live_parallel_smooth_v2.sh

# Balanced profile (matplotlib, best skeleton placement):
./Parallel_working/run_live_parallel_balanced.sh

# Quality baseline (no perf opts):
./Parallel_working/run_live_parallel_quality.sh

# Combined live viewer + BLM aim overlay (RECOMMENDED for BLM work):
./Parallel_working/run_live_blm.sh

# Interactive BLM serial terminal (manual testing, raw commands):
./venv/bin/python garage_lab_combined/scripts/blm_interactive.py --port /dev/ttyUSB0

# Live aim test (S2 aim-only, paired with run_live_blm.sh):
./venv/bin/python garage_lab_combined/scripts/live_aim_test.py \
  --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 --correction-mode linear \
  --log-jsonl garage_lab_combined/output/blm_logs/s2_live_aim.jsonl

# Live aim + shoot (S4 only, after RPM gate test):
./venv/bin/python garage_lab_combined/scripts/live_aim_test.py \
  --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 --correction-mode linear \
  --shoot-enabled --wheel-rpm 800

# Continuous follow mode (BLM tracks chosen joint as person moves, aim-only):
./venv/bin/python garage_lab_combined/scripts/blm_follow.py \
  --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 \
  --joint right_shoulder --correction-mode linear

# Continuous follow + shoot (wheels spin at 800 RPM, manual reload/shoot trigger):
./venv/bin/python garage_lab_combined/scripts/blm_follow.py \
  --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 \
  --joint right_shoulder --correction-mode linear \
  --shoot-enabled --wheel-rpm 800
# Commands while running: <joint> / reload / shoot / pause / resume / quit

# Launcher aim-only test (legacy):
./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 --no-shoot-enabled \
  --dry-run-log-jsonl garage_lab_combined/output/blm_logs/aim_decisions.jsonl

# Benchmark / export models:
./venv/bin/python Parallel_working/scripts/export_models_tensorrt.py --benchmark \
  --yolo-model garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt
```

## Pose Backends
- `--pose-backend yolopose` — YOLO11m-Pose, 6.2x faster (6.2ms TRT vs 38.5ms MMPose per image). **VALIDATED on live arena cameras 2026-04-03.**
- `--pose-backend mmpose` — RTMDet-m + RTMPose-m (original, slower but slightly more keypoints)

## Current Accuracy (GT eval)
- Ball static (old extr): mean 95.17mm, P95 166.51mm (36/36 trials)
- Ball static (arena_fixed): mean 156.90mm, P95 288.34mm — systematic bias X+60/Z-104mm, precision 3.09mm
- Joint-touch (old extr): mean 143.38mm, P95 198.73mm (62/81 trials)
- Joint-touch (arena_fixed): mean 178.98mm, P95 243.77mm — systematic bias X+83/Z-125mm, precision 4.39mm
- Bias is correctable via correction model; precision is excellent

## Latency Benchmarks (RTX 2080 Ti, 2026-04-03)
- YOLO ball: 8.7ms (.pt) / 8.1ms (TRT FP16)
- YOLO-Pose: 8.9ms (.pt) / 6.2ms (TRT FP16) — 6.2x faster than MMPose
- MMPose: 38.5ms/image, ~80ms batched 4-cam
- cv2 3D renderer: ~2ms (vs matplotlib 200-500ms)

## EMA Ablation Results (2026-04-06)
- 3 recorded sequences: walk, jog, jump (449 frames × 4 cameras × 15 FPS each)
- YOLO-Pose matches MMPose 3D accuracy (jitter diff <5mm) at 3.6x faster offline speed
- Walk jitter: fixed α=0.25 → 41mm, adaptive snap_80 → 48mm, no_ema → 53mm
- Jump jitter: fixed α=0.25 → 76mm, adaptive snap_80 → 109mm, no_ema → 117mm
- Results: `Parallel_working/output/ablation_results/`
- Test sequences: `Parallel_working/output/test_sequences/{walk_01,jog_01,jump_01}/`

## Kalman Prediction (tuned 2026-04-07)
- Optimal: `--kalman-process-noise 500 --kalman-measurement-noise 10`
- Walk: 47% improvement over naive at 200-400ms horizon
- Jog: 34-39% improvement. Jump: ~neutral (CV model limitation)
- Best BLM horizon: 200-400ms
- Results: `Parallel_working/output/prediction_results/`

## Execution Plan Status (Week 4 in progress)
- [x] TensorRT export, YOLO-Pose integration, Kalman prediction, cv2 renderer
- [x] Test recordings, EMA ablation, backend comparison
- [x] Re-run GT evaluation with arena_fixed extrinsics (systematic bias found, correctable)
- [x] Kalman prediction validation + parameter tuning (PN=500, MN=10)
- [x] GT correction model integrated into launcher runtime (bias + linear modes)
- [x] BLM preflight S0-S1 passed (serial comms + manual commands verified)
- [x] BLM preflight S2 passed (live aim-only with cameras + correction model, 2026-04-09)
- [x] BLM preflight S3+S4 passed (RPM gate + controlled fire, full reload→aim→shoot cycle, 2026-04-09)
- [x] Full integrated live test passed (2026-04-09): pose→aim→fire on multiple joints (left_shoulder, right_knee, nose). First nose shot slightly low. Second nose shot off — ball speed at 800 RPM not yet calibrated.
- Next: (1) Ball speed calibration (RPM→m/s curve), (2) Training automation mode with voice trigger
