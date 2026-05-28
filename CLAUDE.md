# Project_Cam — Claude Code Guide

## Project
- **Title**: Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking
- **Author**: Hanush, MSc ECE, Nazarbayev University
- **Stack**: Python, OpenCV, YOLO, YOLO-Pose, MMPose, NumPy/SciPy, Kalman Filter

## Arena & Units
- 4 fixed USB cameras: camNorth, camEast, camSouth, camWest
- All coordinates in **mm**. Runtime resolution: **1920x1080** after the east/west remount recalibration
- Capture target: 30 FPS MJPG. Inference target: 5 FPS

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
- **Never** change resolution without recalibrating intrinsics or verifying intrinsics scaling
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
- [x] Thesis engineering chapter drafted (2026-04-13): `thesis_engineering_chapter.md` — chassis/electronics/firmware FSM/comm stack/safety/integration/ECE-curriculum mapping/BOM rationale
- [x] Defense Q&A pack drafted (2026-04-13): `thesis_defense_qa.md` — ECE panel hardware questions + PhD CV examiner methodology questions + defense tactics
- [x] Pipeline reference doc drafted (2026-04-13): `new_complete.md` — full per-script reference with math/formulas/CLI flags
- [x] Ball detection upgraded (2026-04-13): swapped `y26s_v1_garage.pt` (75 epochs, old garage dataset) → `yolo26m-672.engine` (100 epochs, dataset-main, TRT FP16 @imgsz 1280). Benchmark on recorded sequences: walk_01 99.6%→99.6% with higher conf; jump_01 (hard case) **74.9%→84.2% detection rate**, balanced across all 4 cameras (OLD had camEast drop to 22%). Default device moved CPU→cuda:0. Inference ~13 ms. New weights live in `models/ball/`, selection evaluated in `Parallel_working/scripts/ball_model_sanity_check.py`.
- [x] TRT engines re-exported with `dynamic=True, batch=4` (2026-04-13): previous static-batch engines segfaulted on 4-cam batched inference. `export_models_tensorrt.py` patched. Rebuilt `models/ball/yolo26m-672.engine` and `yolo11m-pose.engine`. Pose skeleton now renders in recordings (was silently failing on batch mismatch).
- [x] Ball tracking robustness (2026-04-13): live viewer now uses `robust_triangulate_ball` (iterative per-cam reprojection rejection, `--ball-max-reproj-px 15`), dedicated ball Kalman filter (CV model, PN=800/MN=25), max-speed gate (`--ball-max-speed-mps 25`), and coast-through-drop (`--ball-coast-frames 6`). Replaces naive EMA — eliminates teleports, false positives across cams, and visual drops on fast motion.
- [x] Recording pipeline (2026-04-13): `run_record_3d.sh` writes `arena3d_<ts>.mp4` + `mosaic2d_<ts>.mp4`. SIGTERM/SIGINT handler added so MP4 moov atom is finalized on any clean interruption (press `q` or single Ctrl+C).
- [x] Ball reproj threshold tuned (2026-04-17): `--ball-max-reproj-px` default raised 15→25 in `live_4cam_arena_view_parallel.py` to let motion-blurred far detections pass triangulation.
- [x] Voice integration (2026-04-17): colleague's Vosk model (`/home/hanush/Desktop/Speech to text/model`) wired into BLM via UDP IPC (127.0.0.1:5006). New scripts: `voice_command_test.py` (standalone tester), `voice_bridge.py` (UDP producer, runs in colleague's venv). `blm_follow.py` added `--voice-port` UDP listener thread + `--auto-reload` flag (training-mode rapid-fire: after shoot, auto-`reload`, target + RPM persist, next "go" fires same joint). Voice grammar: 16 phrases mapping to COCO joint names + shoot/reload/pause/resume/quit. Multi-venv architecture avoids installing Vosk/pyaudio into project venv.
- Next: (1) RPM→m/s calibration (Phase 0 close-out — blocking shot accuracy at 800 RPM), (2) Test voice + auto-reload in live lab, (3) Phase 1.1 `common.py` + `ArenaConfig` before defense.

## Documentation Files (thesis-related, do not modify without approval)
- `new_complete.md` — full pipeline + per-script reference
- `thesis_engineering_chapter.md` — engineering chapter draft for thesis
- `thesis_defense_qa.md` — defense prep Q&A pack
- `thesis_draft.md` — pre-existing thesis draft (do not touch unless asked)
- `thesis_report_bachelors.md`, `yessimkhan_thesis.md` — reference materials (read-only)

## Session Log

### 2026-04-14 — Stack freeze pre-defense
- Done today: ball KF + robust triangulation, dynamic-batch TRT engines (ball + pose), recording SIGTERM fix, README updated, suggestions.md audit + verdicts, plan.md created (Phase 0–5)
- Frozen: tag `v0.9-predefense` — rollback point if anything breaks
- Decision: отложили Pipeline/Strategy, batch SVD, ROS2, HMAC до Phase 5 (post-funding). См. suggestions.md.
- Next: Phase 0 — ball tuning in lab + RPM→m/s calibration. Then Phase 1.1 — `common.py` + `ArenaConfig` before defense if time permits.

### 2026-04-17 — Voice + auto-reload + repo cleanup
- Ball tracking: raised `--ball-max-reproj-px` default 15→25 in `live_4cam_arena_view_parallel.py` (motion-blurred far detections now pass). FPS cap ~15–18 confirmed as hardware ceiling, not code.
- Voice integration: colleague's Vosk model wired via UDP IPC to avoid installing vosk/pyaudio into project venv. Two new scripts in `garage_lab_combined/scripts/`: `voice_command_test.py` (standalone), `voice_bridge.py` (UDP producer on 5006). `blm_follow.py` got `--voice-port` listener + `--auto-reload` for training-mode rapid-fire (wheels keep spinning, target persists, auto-`reload` after each shot).
- Commands for full stack: Terminal 1 `run_live_blm.sh` / Terminal 2 `blm_follow.py --voice-port 5006 [--shoot-enabled --wheel-rpm 800 --auto-reload]` / Terminal 3 `voice_bridge.py` under colleague's venv.
- Cleanup pass: identified `voice_commands/` (old prototype, 48K), `weights-20260413T135335Z-3-001/` (raw download, 340M), legacy `output/frames_*/` dumps (~713M), `sync_frames/` (2.6G), `synchronized_video/` (1.2G) as deletion candidates. Awaiting user confirmation before purge.
- Next: (1) Confirm & purge legacy folders, (2) RPM→m/s calibration (Phase 0 close-out), (3) Test voice + auto-reload in live lab, (4) Phase 1.1 `common.py` refactor if time permits pre-defense.

### 2026-04-21 — Ball selection gates (size + KF) + mosaic render fix
- **Mosaic render bug fixed** (`Parallel_working/scripts/render_ball_detection_mosaic.py`): analyzer JSONL records bboxes in native 1280×720 per-cam pixel space, but the renderer resized tiles to 640×360 default and drew bboxes at original coords → boxes clamped against tile edges, appearing offset from the ball. Now scales by `tile_w/src_w, tile_h/src_h` and draws a center cross. All 16 `detections_{672,960}_mosaic.mp4` regenerated.
- **Visual audit findings** (user): three false-positive modes — (1) ball lost during fast motion (blur streaks below conf=0.40), (2) body curled around ball detected as ball, (3) training cones / AprilTag markers occasionally flagged as balls.
- **New candidate-selection gates in `live_4cam_arena_view_parallel.py`** (applied before triangulation; geometry-safe):
  - `--ball-max-box-side-px 220` (default on) — rejects oversized blobs (body/cone). Primary fix for (2).
  - `--ball-min-box-side-px 0` (default off) — optional micro-box filter.
  - `--ball-kf-gate-px 150` (default on) — when KF locked, prefer candidates within 150 px of KF-predicted reprojection. Falls back to highest-conf if no gated candidate (so re-acquisitions still work). Primary fix for (3) and contributor to (1) (makes lowering `--ball-conf` 0.40→0.25 safe).
- Gates are flag-off with `--ball-*-px 0` for A/B regression against prior behavior.
- New helper: `select_ball_box_for_cam(boxes, kf_pred_uv, kf_gate_px, min_side, max_side)` — unit-tested.
- Next: live arena test with `--ball-imgsz 960 --ball-single-cam-fallback --ball-ballistic-fallback` + defaults on the new gates; compare 3D trajectory stability vs pre-gate runs. If stable, consider lowering `--ball-conf` default 0.40→0.25.

### 2026-04-20 — Ball detection diagnosis + single-cam fallback + Gemini review
- **Tier 0 additions from second-pass review + Gemini/tree review analysis landed.** New `suggestions.md` section (Tier verdicts for gemini3.1pro.md, industrial-tree critique). Safe additions only; pre-defense freeze intact.
- **Ball detection offline analyzer** (`Parallel_working/scripts/ball_detection_analyzer.py`): sweeps conf thresholds + top-K on either per-cam frame directories OR `mosaic2d_*.mp4` 2×2 tiled videos. Reveals how many detections the current conf=0.40 threshold silently discards.
- **Real-recording findings (bounce/fast/slow from 2026-04-15):**
  - `slow`: 64.8% @ conf=0.40 → 67.3% @ 0.15 (small gain, ball confident)
  - `fast`: 46.1% → 51.9% (+5.8 pp) — motion streaks real (aspect 1.6–3.3 at low conf)
  - `bounce`: **23.1% → 27.0% @ conf alone; 23.1% → 33.4% @ imgsz=672→960** — the dominant lever is input resolution, not conf
  - camNorth on bounce: **58.4% → 98.0% at imgsz=960** (+39.6 pp). The other three cams stay 10–17% regardless of model/threshold tuning — bounce visibility is **structurally geometric** (ball outside frustum or occluded), not a detection problem.
- **New flag `--ball-imgsz`** (default 672, try 960 for bounce) in `live_4cam_arena_view_parallel.py`. Engine was exported with `dynamic=True` so no re-export needed. +8 ms latency per 4-cam batch, fits 15 FPS budget easily.
- **New single-camera fallback** (`project_ray_to_z_plane`): when only 1 cam sees the ball, project that cam's ray to the KF-predicted Z plane (or floor on cold start). Geometry-safe; does not touch `triangulate_multi`. Flag-guarded, off by default:
  - `--ball-single-cam-fallback` — enable
  - `--ball-single-cam-max-frames 15` — runaway cap (~1 s at 15 FPS)
  - `--ball-single-cam-floor-mm 0.0` — cold-start Z-plane
- **Recommended runtime flags** (once live-validated): `--ball-imgsz 960 --ball-single-cam-fallback`. Will consider flipping `--ball-conf` default 0.40→0.25 after observing live behavior.
- Next: (1) Live test bounce/fast with new flags, (2) if stable, flip defaults in separate commit, (3) record a `bounce_01` per-cam sequence via `record_test_sequence.py` for regression fixture seed (R1 keystone).
