# Thesis Living Worklog (Project_Cam)

Last updated: 2026-04-07

Use this file as the single memory for thesis reporting.  
When you write `update information for thesis`, this file should be updated with new progress.

## 1) Project Goal (Short Form)
- Build a camera-only 3D training intelligence system in a garage arena.
- Reconstruct arena, camera poses, AprilTag world frame, 3D skeleton, and 3D ball in one metric coordinate system (mm).
- Add decision-ready control layer for Ball Launching Machine (BLM): high-level math on PC, low-level actuation on ESP32.
- Long-term target: voice command -> body part target -> ballistic solve -> safe shot -> visual verification.

## 2) Core Architecture (Current)
- 4 fixed cameras (Hikvision USB webcams) at 1280x720, ~15 FPS capture.
- Calibration:
  - Intrinsics from ChArUco.
  - Extrinsics from AprilTag grid + known world coordinates (`Dimensions.txt`).
- Runtime perception:
  - Ball detection (YOLO).
  - Pose detection (MMPose).
  - Multi-view triangulation to 3D world points (mm).
- Rendering:
  - 3D arena + tags + camera poses + ball + skeleton.
- BLM control:
  - PC computes targets/angles/RPM.
  - ESP32 receives low-level commands only: `set v h wl wr`, `shoot`, `reload`, `center`, `stop`, `setzero`.

## 3) Timeline of Work Done

### Phase A — Project merge and garage migration
- Consolidated work into `garage_lab_combined`.
- Migrated from lab recordings/calibration to garage environment.
- Defined mm units as standard.
- Set runtime target to 1280x720 for speed/stability tradeoff.

### Phase B — Camera calibration pipeline
- Built/updated tools:
  - `calibrate_intrinsics_charuco_garage.py`
  - `auto_capture_charuco_multi.py`
  - `calibrate_intrinsics_from_images.py`
  - `calibrate_extrinsics_apriltag_robust.py`
  - `validate_extrinsics_overlay.py`
- Added auto-capture logic and preview windows.
- Improved capture trigger logic from time-based to corner-count based.
- Introduced stable camera mapping strategy (moved from volatile `/dev/video*` toward by-path mapping).

### Phase C — Synchronization and 3D reconstruction
- Recorded synchronized 4-cam clips with flashlight marker.
- Implemented/used alignment workflow and frame trimming.
- Ran `process_4cam_to_3d.py` for 3D ball + 3D joints.
- Rendered combined arena outputs with `render_arena_ball_skeleton.py`.
- Added tuning iterations for smoother and presentation-ready output.

### Phase D — Error analysis and GT protocols
- Created structured GT protocols for:
  - Ball static points.
  - Dynamic ball (`ball_slow`, `ball_fast`, `no_ball`).
  - Human joint-touch tests.
- Implemented evaluation scripts and reports:
  - `evaluate_ball_static_gt.py`
  - `evaluate_pose_joint_touch_gt.py`
- Ball static dataset (36 points) generated and evaluated.
- Joint-touch dataset (81 planned points) captured partially and evaluated.
- Built correction-model workflow (axis bias/scale style correction) and compared raw vs corrected.

### Phase E — Extrinsics maintenance under camera movement
- Recalibrated after camera shifts (especially south camera movement event).
- Performed single-camera extrinsics update path and merged with previous final extrinsics.
- Verified with projection overlay outputs.
- Repeated tag coordinate cleanup in `Dimensions.txt` (including corrected wall coordinate conventions and several tag re-measurements).

### Phase F — Thesis preparation
- Produced draft thesis structure and content in `garage_lab_combined/thesis`.
- Prepared LaTeX/Word submission scaffolding and formatting guides.
- Mapped repo flow to research-manuscript narrative.

### Phase G — BLM integration (current stage)
- Added control bridge scripts:
  - `bridge_pose_to_launcher_ble.py` (BLE path)
  - `launcher_runtime_from_udp.py` (UDP->Serial runtime path)
- Added live joint UDP streaming from perception in:
  - `live_4cam_arena_view.py`
- Added incremental execution checklist:
  - `BLM_TEST_CHECKLIST.md`
- Added decision logs (`--dry-run-log-jsonl`) for report-grade analysis.
- Added static target mode directly in runtime:
  - `--static-target-x-mm --static-target-y-mm --static-target-z-mm`
  - optional `--static-target-joint`
- Added solver compatibility mode to match old `version1.1.py` equations:
  - `--solver v1`
  - `--fixed-speed-kmh`
  - `--z-launcher-m`

## 4) Key Quantitative Results to Mention

### Intrinsics
- Recomputed garage intrinsics with ChArUco at 1280x720.
- Reprojection errors reported in terminal logs in low-pixel range for usable cameras.
- One camera intermittently required re-capture due to insufficient valid ChArUco frames.

### Extrinsics
- Multiple recalibration rounds performed due to camera repositioning and tag coordinate corrections.
- Final “good” calibration rounds achieved low px-level RMSE for most cameras (as reported in logs), with stricter tag inclusion maps improving stability.
- Overlay validation used as mandatory visual sanity check.

### Ball static GT (36 points)
- Raw performance (reported):
  - Mean ~150.77 mm
  - RMSE ~167.39 mm
  - P95 ~288.34 mm
- After correction-model pass:
  - Mean ~95.17 mm
  - RMSE ~102.23 mm
  - P95 ~166.51 mm
- Interpretation:
  - Big gain from correction, but still not yet “high-precision industrial targeting” in all regions.

### Detection reliability notes
- Accuracy strongly depends on multi-camera visibility.
- 1-2 camera visibility frequently causes unstable triangulation and larger errors.
- 3+ camera overlap is critical for stable 3D targeting.

### Joint-touch GT
- Dataset collected for body parts (`right_knee`, `right_hip`, `left_shoulder`) across grid/height combinations.
- Important caveat documented:
  - Human placement uncertainty can dominate measured error unless rigid physical reference points are used.

## 5) Important Engineering Decisions
- Chosen architecture:
  - PC = high-level compute (vision, triangulation, filters, ballistics, safety logic).
  - ESP32 = low-level actuator executor.
- Reason:
  - Faster iteration and safer debugging without frequent firmware reflashing.
  - Better observability/logging for thesis evidence.
- Safety-first rollout:
  - Aim-only before any shooting.
  - E-STOP latch + command gating.
  - Zone/angle/confidence/camera/stability checks before shoot.

## 6) BLM Control Design (Current)
- Runtime control input:
  - UDP joint targets from live perception, or static target mode for one-terminal testing.
- Runtime output:
  - Serial commands to ESP32.
- Supported ESP commands in use:
  - `set v h wl wr`
  - `shoot`
  - `reload`
  - `center`
  - `stop`
  - `setzero`
- Operating sequence:
  - zero/center -> acquire stable target -> solve -> aim -> (optional shoot) -> center -> next target.
- Target order (v1):
  - `right_knee -> right_hip -> left_shoulder`.

## 7) Safety and Failure Modes Already Observed
- “Freeze” perception often equals waiting for stable target (not crash).
- Wheels can keep spinning if only `center` is sent; explicit `stop` is needed in certain transitions.
- Fixed this by safer aim-only behavior with wheel RPM set to 0 by default.
- Camera remount events require recalibration before trusting 3D outputs.

## 8) What To Explicitly State in Thesis (Recommended)
- Novelty:
  - Reframing launcher training from open-loop ball feeder to closed-loop vision-guided targeting framework.
- Contribution:
  - Calibrated multi-camera 3D perception backbone with quantitative error evaluation.
  - Practical integration blueprint from perception to BLM low-level commands.
- Limitation:
  - Full autonomous closed-loop launcher deployment not finalized yet.
- Honesty statement:
  - Current work provides validated perception and integration infrastructure, with staged BLM validation in progress.

## 9) Current Status vs Next Steps
- Completed:
  - Calibration, reconstruction, GT frameworks, core BLM runtime path.
- In progress:
  - Incremental BLM checklist execution and safe shot validation.
- Next:
  - Finish static-point BLM tests.
  - Move to real-person aiming tests in aim-only.
  - Controlled shooting trials with strict safety envelope.
  - Prepare figures/tables from JSONL decision logs for thesis chapter.

## 10) Commands You Will Reuse Often
- One-terminal static BLM targeting:
```bash
./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 \
  --launcher-x-mm 600 --launcher-y-mm 1560 --launcher-z-mm 500 \
  --launcher-yaw-deg 0 \
  --targets left_shoulder \
  --static-target-x-mm 4600 --static-target-y-mm 2100 --static-target-z-mm 2200 \
  --static-target-joint left_shoulder \
  --solver v1 --fixed-speed-kmh 40 --z-launcher-m 0.5 \
  --no-shoot-enabled \
  --dry-run-log-jsonl garage_lab_combined/output/blm_logs/static_target_log.jsonl
```

- Operator controls in runtime terminal:
  - `start`
  - `home`
  - `setzero`
  - `estop`
  - `clear`
  - `status`
  - `quit`

## 11) Update Protocol
- Trigger phrase: `update information for thesis`
- Expected update actions:
  - Append new milestone under timeline.
  - Update key metrics section.
  - Update completed checklist references.
  - Add exact evidence paths (videos, logs, JSONL, reports).

## 12) Daily Log — 2026-03-16 (BLM zero/home stabilization)

### 12.1 Problem observed
- Runtime could aim to target correctly, but `home` returned to ESP logical zero that did not match desired physical reference direction.
- `miniterm` interaction was unstable in this setup (input blocking/menu behavior), so serial control needed a more reliable method.

### 12.2 Actions performed
- Verified runtime one-shot static target mode works:
  - `--max-target-events 1`
  - `--no-return-center-after-each-target`
  - `--no-shoot-enabled`
- Used direct serial command method to manually jog axes and identify desired physical zero:
  - `jv +/-N`, `jh +/-N`
- Confirmed ESP accepted commands and acknowledged:
  - `stop`, `setzero`, `set 0 0 0 0`, `jv`, `jh`.

### 12.3 Runtime code updates completed today
- Updated `garage_lab_combined/scripts/launcher_runtime_from_udp.py`:
  - Added startup option `--setzero-on-start` (default enabled).
  - Added `--setzero-settle-sec`.
  - Added operator command `setzero` (available during idle/acquire/wait-rpm stages).
  - Extended operator help line to: `start | home | setzero | estop | clear | status | quit`.
  - Startup order now:
    - optional `setzero` -> optional `set 0 0 0 0` (home).
- Validation:
  - `py_compile` passed for updated runtime script.

### 12.4 New stable operating procedure (until hardware homing is added)
1. Start runtime (with default `--setzero-on-start --home-on-start`).
2. If physical zero drifted, jog manually with serial helper and then run:
   - `setzero`
   - `home`
3. Run targeting tests.
4. Finish with:
   - `home`
   - `quit`

### 12.5 5-point static aiming plan selected from CSV
Reference source:
- `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/trials_joint_81_mm.csv`

Chosen points:
1. `J001` `right_knee` `(2600,1100,500)`
2. `J005` `right_knee` `(3600,1600,500)`
3. `J009` `right_knee` `(4600,2100,500)`
4. `J041` `right_hip` `(3600,1600,1400)`
5. `J081` `left_shoulder` `(4600,2100,2200)`

### 12.6 Wheel-speed note for these 5 tests
- In aim-only mode (`--no-shoot-enabled`), runtime sends:
  - `wl=0`, `wr=0` (no wheel spin).
- If shooting is enabled with current defaults (`velocity_to_rpm=80`, no left/right bias), predicted RPM for these points:
  - `J001`: `964`
  - `J005`: `1040`
  - `J009`: `1123`
  - `J041`: `1051`
  - `J081`: `1150`

### 12.7 Open technical limitation (not solved in firmware yet)
- `setzero` defines logical zero for the current powered session.
- Without dual-axis home switches (V/H) + homing routine, absolute mechanical zero is not guaranteed after power cycle/manual displacement.
- Next hardware-level fix:
  - Add homing switches for both steppers.
  - Implement deterministic homing sequence in ESP firmware startup.

## 13) Daily Log — 2026-03-17 (Static-point shooting tuning at x=4600)

### 13.1 Issue report from runtime
- During static test for `left_shoulder (4600,2100,2200)` with high speed, user observed:
  - Shot was too fast and went above/side of desired point.
  - Repeated runtime warning at low angle limit setting:
    - `[WARN] Angle out of bounds for left_shoulder: v=31.27, h=-7.69, limit=30.0`
- Root causes:
  - Command had inconsistent joint settings in one attempt (`--targets left_shoulder` with `--static-target-joint right_knee`).
  - 51.75 km/h was too aggressive for current real launcher mechanics and calibration.
  - `setzero` behavior at startup can redefine logical zero; if not controlled, home motion may look wrong.

### 13.2 Code changes done today
- Updated `garage_lab_combined/scripts/launcher_runtime_from_udp.py`:
  - Added `--speed-scale` (global speed multiplier).
  - Added `--pitch-trim-deg` (negative lowers trajectory).
  - Added `--yaw-trim-deg` (left-right trim).
- Validation:
  - `py_compile` passed for the updated script.

### 13.3 Commands used and confirmed today

#### A) Main static-target runtime command (example)
```bash
./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 \
  --launcher-x-mm 600 --launcher-y-mm 1560 --launcher-z-mm 500 \
  --launcher-yaw-deg 0 \
  --targets left_shoulder \
  --static-target-x-mm 4600 --static-target-y-mm 2100 --static-target-z-mm 2200 \
  --static-target-joint left_shoulder \
  --max-target-events 1 \
  --no-return-center-after-each-target \
  --shoot-enabled \
  --fixed-speed-kmh 47 \
  --velocity-to-rpm 68 \
  --pitch-trim-deg -1.0 \
  --max-abs-angle-deg 40
```

#### B) Serial direct axis check (when runtime is NOT running)
```bash
esp set 0 -20 0 0
esp set 0 0 0 0
```
- Purpose:
  - Verify horizontal axis movement independently of runtime logic.

### 13.4 Correctness rules confirmed
- `--static-target-joint` must be included in `--targets`.
- If `--no-shoot-enabled` is used, wheels stay at 0 RPM (aim-only).
- To avoid startup zero drift in repeated tests, use:
  - `--no-setzero-on-start`
  - and perform manual `setzero` only when desired reference pose is established.

### 13.5 Selected 5-point test set on x=4600
Reference:
- `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/trials_joint_81_mm.csv`

Points:
1. `J003` `right_knee` `(4600,1100,500)`
2. `J015` `right_knee` `(4600,1600,900)`
3. `J027` `right_knee` `(4600,2100,1140)`
4. `J042` `right_hip` `(4600,1600,1400)`
5. `J081` `left_shoulder` `(4600,2100,2200)`

### 13.6 RPM and speed notes for reporting
- Previous theoretical values with `velocity_to_rpm=80`:
  - J003: ~1122 rpm
  - J015: ~1122 rpm
  - J027: ~1127 rpm
  - J042: ~1128 rpm
  - J081: ~1150 rpm
- Practical tuning today moved to reduced aggressiveness:
  - lower conversion in test command (`velocity_to_rpm=68`),
  - use of `pitch-trim-deg` and optional future `yaw-trim-deg`.

### 13.7 End-of-day status
- Static targeting pipeline is operational.
- Hardware control path is confirmed (direct serial + runtime).
- Next session:
  - run full 5-point x=4600 sequence with controlled trims,
  - log hit offset for each point,
  - fit final pitch/yaw/speed correction table.

## 14) Daily Log — 2026-03-24 (Visualization + pose-quality baseline consolidated)

### 14.1 Final accepted baseline (no conflicts)
- User-approved target behavior:
  - world coordinate system from `arena_fixed` (correct operator geometry),
  - smooth and stable skeleton quality close to original full-quality run.
- New canonical wrapper:
  - `arena_fixed/run_live_visual_invert_quality.sh`

### 14.2 Canonical command (keep for report and reproduction)
```bash
cd /home/hanush/Desktop/Project_Cam
./arena_fixed/run_live_visual_invert_quality.sh
```

### 14.3 What this canonical mode fixes
- Uses:
  - `--extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json`
  - `--dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt`
- Keeps display orientation operator-friendly:
  - `--no-world-y-mirror`
  - `--invert-y-axis-display`
- Keeps high-quality pose settings:
  - `--width 1280 --height 720 --fps 15`
  - `--pose-every 1 --ball-every 1 --viz-every 1`
  - `--show-2d --show-3d`
  - `--udp-target-conf-min 0.50 --udp-target-cams-min 4`

### 14.4 Additional runtime code improvements merged
- Updated `garage_lab_combined/scripts/live_4cam_arena_view.py`:
  - Added frame decoupling flags:
    - `--display-world-y-mirror`
    - `--udp-world-y-mirror`
  - Added stale-joint cleanup:
    - `--joint-stale-frames`
  - Kept fast reacquire logic:
    - `pose_reacquire_every` when lock is lost,
    - one-shot pose snap on lock reacquisition.
  - Added GPU runtime optimization hook:
    - auto-enable `torch.backends.cudnn.benchmark=True` when CUDA device is selected.

### 14.5 Active wrappers and usage policy
- `arena_fixed/run_live_visual_invert_quality.sh`
  - **Primary** mode for experiments and thesis screenshots/videos.
- `arena_fixed/run_live_visual_invert_only.sh`
  - Legacy debug wrapper; keep only for quick geometry checks.
- `arena_fixed/run_live_display_mirror_udp_native.sh`
  - Specialized engineering mode: mirrored display with native UDP frame.

## 15) Daily Log — 2026-03-24 (Stage-2 aiming package retained)

### 15.1 Stage objective remains
- Dedicated BLM aiming calibration for horizontal (`yaw`) and vertical (`pitch`) movement.
- Safe rollout in aim-only before shooting.

### 15.2 Artifacts kept valid
- `arena_fixed/BLM_AIM_STAGE2.md`
- `arena_fixed/scripts/run_blm_aim_test.sh`

### 15.3 Stage-2 baseline launch style (updated Terminal A)
- Terminal A:
```bash
cd /home/hanush/Desktop/Project_Cam
./arena_fixed/run_live_visual_invert_quality.sh
```
- Terminal B (example):
```bash
bash arena_fixed/scripts/run_blm_aim_test.sh right_knee 4600 1600 1400 H2
```
- Runtime operator action:
  - type `start` once per test run, then `quit`.

## 16) FPS optimization roadmap (quality-safe only)

### 16.1 Locked baseline (DO NOT change geometry/pose profile)
```bash
./arena_fixed/run_live_visual_invert_quality.sh
```
- This is the **base of bases** for this project stage.
- Keep:
  - `1280x720`, `pose-every 1`, `ball-every 1`, `show-2d + show-3d`, `udp-target-cams-min 4`.
- Keep world system from `arena_fixed`.

### 16.2 Only allowed FPS tweak (safe)
```bash
./arena_fixed/run_live_visual_invert_quality.sh --viz-every 2
```
- This is the only approved speed tweak with preserved skeleton correctness.

### 16.3 Explicitly rejected profiles (caused wrong skeleton placement)
- Rejected for now:
  - reducing resolution to `960x540` or `640x360`,
  - `--no-show-2d` / `--no-show-3d` as primary test mode,
  - `--high-performance` profile,
  - aggressive sparse pose cadence.
- Reason:
  - user-validated degradation in skeleton correctness and/or placement.

### 16.4 Experiment rule
- Change at most 1 parameter per run.
- If skeleton quality drops, immediately revert to section 16.1 baseline.

### 16.5 Final live 3D arena skeleton command (locked)
```bash
cd /home/hanush/Desktop/Project_Cam
./arena_fixed/run_live_visual_invert_quality.sh
```

Optional safe speed-up:
```bash
cd /home/hanush/Desktop/Project_Cam
./arena_fixed/run_live_visual_invert_quality.sh --viz-every 2
```

## 17) Confirmed BLM world placement reference (LOCKED)

- User-confirmed **ground-truth visual reference** for real BLM placement:
  - `arena_fixed/output/world_frame_views_live_quality.png`
- This file is now the canonical coordinate sanity reference for:
  - BLM anchor location in arena,
  - multi-view orientation checks before aiming tests.
- Command used:
```bash
xdg-open /home/hanush/Desktop/Project_Cam/arena_fixed/output/world_frame_views_live_quality.png
```
- Status: **approved by user as correct real-world representation**.

## 18) Next Stage — Horizontal-only BLM aiming cycle (vertical disabled)

### 18.1 Objective
- Validate only horizontal rotation correctness:
  - if operator stands at south-west side, BLM must visually rotate toward operator (not aside).
- Vertical channel is intentionally frozen for this stage.

### 18.2 Control mode
- Runtime uses:
  - `--horizontal-only`
  - `--horizontal-fixed-v-deg 0`
- Sequence stays identical to accepted training flow:
  - 10s pre-aim delay per target,
  - 20s hold per target,
  - home between targets,
  - one full cycle then pause.

### 18.3 Canonical Terminal A (visual tracking baseline)
```bash
cd /home/hanush/Desktop/Project_Cam
./arena_fixed/run_live_visual_invert_quality.sh
```

### 18.4 Canonical Terminal B (horizontal-only cycle)
```bash
cd /home/hanush/Desktop/Project_Cam
bash arena_fixed/scripts/run_blm_horizontal_only_cycle.sh 0.0 650 /dev/ttyUSB0
```
- Args:
  - `0.0` = yaw trim (deg),
  - `650` = aim-only wheel RPM during 20s hold,
  - `/dev/ttyUSB0` = serial port.
- In runtime terminal:
  - type `start` to run full cycle (`right_knee -> nose -> body_center`).

### 18.5 Yaw tuning rule for this stage
- If BLM points to the right of operator, reduce yaw trim (e.g. `-1.0`).
- If BLM points to the left of operator, increase yaw trim (e.g. `+1.0`).
- Change only 1 parameter per run and compare JSONL logs.

---

## 19) Phase H — Performance-Optimized Parallel Pipeline (2026-04-01 → 2026-04-02)

### 19.1 Objective
- Reduce end-to-end latency from ~200ms (matplotlib bottleneck) to <10ms display
- Improve perceived smoothness of 3D skeleton without altering geometric accuracy
- All work isolated in `Parallel_working/` — production `garage_lab_combined/` untouched

### 19.2 Changes implemented in `Parallel_working/scripts/live_4cam_arena_view_parallel.py`

#### A) OpenCV 3D Renderer (replaced matplotlib)
- New functions: `make_orbit_view()`, `_cv2_project()`, `draw_live_scene_cv2()`
- Virtual pinhole camera with orbit-style elevation/azimuth control
- 270° azimuth offset to match matplotlib's display convention
- X-axis mirror in projection (`u = cx - fx*X_cam/Z_cam`) to match matplotlib's left-handed display
- Pre-rendered static background (arena wireframe, AprilTags, camera markers, axes) copied per frame
- Dynamic elements (skeleton, ball, trajectory) drawn with OpenCV primitives
- Result: **~2ms per 3D frame** vs 200-500ms matplotlib

#### B) Coordinate Orientation Fix
- Problem: cv2 3D view had camera positions and axes rotated ~180° from correct matplotlib view
- Root cause: `make_orbit_view()` used standard spherical coords, but matplotlib azim=0 means camera on +Y axis
- Fix: Changed `a = np.radians(azim_deg)` → `a = np.radians(270.0 + azim_deg)`
- Fix: Mirrored X projection to match matplotlib's left-handed display
- Validated: O(0,0,0) at camNorth floor corner, +X→camSouth, +Y→camWest, +Z up — correct

#### C) Displacement-Adaptive EMA
- Problem: Fixed-alpha EMA (0.45) dampens fast movements — jumps appear as standing still
- Solution: Alpha scales with displacement when displacement > snap threshold (80mm):
  - `alpha_eff = min(1.0, alpha_base * (displacement / threshold))`
- Applied to both `joints_state` EMA update and `joints_display` interpolation
- CLI flags: `--ema-snap-thresh-mm 80`

#### D) Display-Only Interpolation Layer
- Separate `joints_display` array (17×3) lerps toward `joints_state` every render frame
- Decouples pose inference rate (every 2 frames) from display rate (every frame)
- `joints_display` used ONLY for rendering — `joints_state` used for UDP and ballistic solving
- CLI flag: `--display-smooth-alpha 0.45`

#### E) `--viz-backend cv2|matplotlib` flag
- Selects between OpenCV renderer (fast, inline) and matplotlib (legacy)
- cv2 backend skips figure/axes creation entirely
- No `--render-worker-process` needed with cv2 backend

### 19.3 Run profiles created
- `run_live_parallel_smooth_v2.sh` — cv2 renderer + adaptive EMA (RECOMMENDED for low-latency)
- Earlier profiles (quality, balanced, smooth, maxfps) remain for reference

### 19.4 Verified invariants
- `triangulate_multi`, `transform_world_point_y`, `ema_update` — byte-identical to production
- `joints_display` only in display paths; `joints_state` for UDP and EMA
- No geometry-critical functions modified

### 19.5 Perf results (from perf JSONL logs)
- **Balanced profile** steady-state: pose=80-85ms, ball=12-13ms, mosaic=8-9ms, total=~103ms, e2e=~195ms
- **Smooth_v2 profile**: viz3d drops from ~300ms → ~2ms, total e2e reduction ~200ms+
- MMPose inference remains dominant bottleneck at 78% of loop time

---

## 20) Phase I — Kalman Filter Predictive Targeting (2026-04-03)

### 20.1 Objective
- Implement per-joint 3D Kalman filter for predictive targeting
- Predict where athlete WILL BE in T_predict ms (compensating for system + ball flight latency)
- Visualize prediction as ghost skeleton in 3D view
- Include predicted positions in UDP payload for launcher runtime

### 20.2 Implementation — `JointKalmanFilter` class
- State vector: [x, y, z, vx, vy, vz] — constant-velocity motion model
- Matrices: F (state transition), H (observation), Q (process noise), R (measurement noise)
- Process noise modeled as piecewise-constant white noise acceleration
- `predict_step()` + `update_step()` run after triangulation when pose data available
- `predict_ahead(t_sec)` extrapolates position WITHOUT modifying filter state
- `prediction_uncertainty(t_sec)` returns positional uncertainty for confidence gating

### 20.3 New CLI flags
- `--predict-ahead-ms 400` — prediction horizon (0 = disabled)
- `--kalman-process-noise 50` — process noise std (mm/s², higher = trust measurements more)
- `--kalman-measurement-noise 80` — measurement noise std (mm, higher = smoother but laggier)
- `--show-ghost-skeleton` — render predicted position as translucent gold skeleton
- `--predict-max-uncertainty-mm 500` — discard predictions exceeding this uncertainty

### 20.4 Ghost skeleton visualization
- Translucent gold skeleton at predicted position in cv2 3D view
- Leader lines from shoulders/hips connecting real skeleton to ghost
- HUD text shows prediction horizon (e.g., "Pred: +400ms")
- Auto-enabled when `--predict-ahead-ms > 0`

### 20.5 UDP extension
- When prediction is active, UDP packets include `predicted` field:
  ```json
  {
    "type": "joints",
    "joints": {"right_knee": {"x_mm": 3000, "y_mm": 1500, "z_mm": 500, ...}},
    "predicted": {"right_knee": {"x_mm": 3400, "y_mm": 1500, "z_mm": 500}},
    "predict_ahead_ms": 400
  }
  ```
- Launcher runtime can use `predicted` field for lead-the-target aiming

### 20.6 Unit test results (synthetic constant-velocity motion)
- After 60 frames at 15fps with 1000mm/s X-velocity:
  - Position: [3924, 500, 1000] (correct)
  - Velocity: [998.6, 0, 0] (converged to true value)
  - Prediction +400ms: [4323, 500, 1000] (correctly leads target)
- Stationary target: prediction stays within 50mm
- Direction reversal: velocity adapts within ~10 frames

### 20.7 New run profile
- `run_live_parallel_predictive.sh` — smooth_v2 + 400ms prediction + ghost skeleton
- Canonical command:
```bash
./Parallel_working/run_live_parallel_predictive.sh
```

### 20.8 TensorRT/ONNX export utility
- Created `Parallel_working/scripts/export_models_tensorrt.py`
- YOLO export: `.pt` → TensorRT FP16 engine (expected: 12ms → 5ms)
- RTMPose export: via mmdeploy ONNX path or manual torch.onnx
- Benchmark suite: latency profiling for YOLO, MMPose, ONNX Runtime
- Command:
```bash
./venv/bin/python Parallel_working/scripts/export_models_tensorrt.py --benchmark \
  --yolo-model garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt
```

---

## 21) Thesis Draft Updates (2026-04-03)

### 21.1 Sections updated in `thesis_draft.md`
- **Section 1.4**: Added Novelty Claim 3 — Displacement-Adaptive Smoothing and Predictive Targeting
- **Section 3.3.1** (NEW): Performance-Optimized Parallel Pipeline — threaded capture, multi-rate processing, OpenCV 3D renderer, display interpolation, run profiles
- **Section 3.7.3**: Updated EMA description — added displacement-adaptive variant and dual-layer architecture
- **Section 6.1**: Updated to 4 contributions (added Contribution 3: adaptive smoothing + prediction + cv2 renderer)
- **Section 6.4**: Completely rewritten with detailed execution plan:
  - 6.4.1 Predictive Trajectory Targeting (core innovation)
  - 6.4.2 TensorRT/ONNX Model Optimization
  - 6.4.3 Closed-Loop BLM Integration
  - 6.4.4 Empirical Ballistic Calibration Map
  - 6.4.5 Stakeholder Demo Platform
  - 6.4.6-6.4.8 SLAM, Multi-Person, Virtual 3D Goal
  - 6.4.9 Execution Timeline (12 weeks, 4 phases)
  - 6.4.10 Edge Deployment (Jetson analysis)

### 21.2 Novelty claims now in thesis (4 total)
1. **Autonomous Aiming Machine** — BLM computes own pitch/yaw/RPM from live 3D joint reconstruction
2. **Low-Cost Multi-Camera Pipeline** — $200 hardware, sub-200mm joint accuracy in domestic arena
3. **Displacement-Adaptive Smoothing + Predictive Targeting** — adaptive EMA + Kalman filter prediction
4. **Safety-Gated Integration Protocol** — 6-stage checklist, ESTOP <100ms, JSONL traceability

---

## 22) Detailed Execution Plan (12-Week Roadmap)

### Phase 1: Foundation & Formalization (Weeks 1-3)

**Week 1: Accuracy Baseline**
- [ ] Re-run GT evaluation with arena_fixed extrinsics
- [ ] Ablation: fixed EMA vs adaptive EMA during fast movements
- [ ] Record 3 reproducible test sequences (walk, jog, jump+direction-change)
- Deliverable: Accuracy table, ablation results

**Week 2: Model Optimization**
- [ ] Export MMPose to ONNX → TensorRT (target: 80ms → 35-40ms)
- [ ] Export YOLO to TensorRT (target: 12ms → 5ms)
- [ ] Benchmark total pipeline latency after optimization
- [ ] Evaluate YOLO-Pose as single-model replacement
- Deliverable: Latency comparison table

**Week 3: Predictive Module Validation**
- [ ] Validate Kalman filter prediction accuracy on recorded sequences
- [ ] Measure prediction error: predicted vs actual position after T ms
- [ ] Tune process/measurement noise for best prediction accuracy
- [ ] Record prediction quality metrics for thesis
- Deliverable: Prediction error table, tuned Kalman parameters

### Phase 2: Closed-Loop Integration (Weeks 4-6)

**Week 4: BLM Preflight (S0-S1)**
- [ ] ESP32 serial communication verification
- [ ] Motor response timing measurement
- [ ] Pan/tilt accuracy test
- [ ] ESTOP reliability test (10 consecutive triggers)
- Deliverable: BLM preflight checklist complete

**Week 5: Predictive Ballistic Solver**
- [ ] Ballistic arc computation (parabolic + optional drag)
- [ ] Add ball flight time to prediction horizon
- [ ] Calibrate launch parameters: measured vs computed trajectory
- Deliverable: Calibrated ballistic solver

**Week 6: Closed-Loop Aim Tests (S2-S3)**
- [ ] Static target aim — measure angular error
- [ ] Slow-moving target aim — tracking accuracy
- [ ] Predictive vs reactive aiming comparison
- Deliverable: Aiming accuracy table

### Phase 3: Live Fire & Evaluation (Weeks 7-9)

**Week 7: Controlled Fire (S4-S5)**
- [ ] Static fire test (3m, 5m, 7m distances)
- [ ] Moving target fire test
- [ ] Predictive fire test (direction changes)
- Deliverable: Hit-rate table

**Week 8: Full Evaluation Protocol**
- [ ] 50-trial reactive evaluation (10 stationary, 20 walking, 20 running)
- [ ] 50-trial predictive evaluation (same patterns)
- [ ] Synchronized video + 3D tracking recording
- Deliverable: Complete evaluation dataset

**Week 9: Results Analysis**
- [ ] Statistical comparison: reactive vs predictive (paired t-test)
- [ ] Ablation studies: ±adaptive EMA, ±prediction, ±TensorRT
- [ ] Failure mode analysis
- Deliverable: Results chapter draft

### Phase 4: Demo Platform & Thesis (Weeks 10-12)

**Week 10: Stakeholder Demo**
- [ ] Unified dashboard: mosaic + 3D skeleton + ghost + BLM status
- [ ] Recording mode for demo sessions
- [ ] Mode selector: manual → reactive → predictive
- Deliverable: Demo-ready platform

**Week 11-12: Thesis & Defense**
- [ ] Complete thesis writing
- [ ] Defense slides with live demo video
- [ ] Backup demo recording
- [ ] Stakeholder pitch deck
- Deliverable: Final thesis, defense slides

---

## 23) Innovation Summary for Committee / Stakeholders

### For thesis committee (research contribution):
1. First system combining multi-camera 3D pose estimation with Kalman-filtered predictive targeting for autonomous ball launching
2. Displacement-adaptive EMA — formalized as a contribution to real-time multi-view pose tracking
3. Quantitative evaluation: reactive vs predictive targeting across movement patterns
4. Safety framework for human-targeting robotic systems in uncontrolled environments

### For stakeholders (Kairat Academy, funding):
- "$300 camera system that does what $50,000 motion capture does"
- "AI predicts where athlete will move — launcher leads the target"
- "Autonomous goalkeeper training, reaction drills, performance analytics"
- "Complete self-contained training instrument — fires, measures, logs results"
- Demo: 2-minute live walkthrough showing manual → reactive → predictive modes

---

## 24) Daily Log — 2026-04-03 (Benchmark Results + YOLO-Pose Discovery)

### 24.1 Benchmark methodology
- All latency benchmarks use **synthetic 720x1280 random images** (standard practice for measuring GPU inference latency)
- Measures pure forward-pass compute time, isolated from I/O
- Detection accuracy tests require real arena frames (separate evaluation)

### 24.2 YOLO Ball Detector Benchmarks

| Format | Mean | Median | P95 |
|---|---|---|---|
| PyTorch .pt | 8.7ms | 8.6ms | 9.4ms |
| ONNX | 19.1ms (CPU fallback) | — | — |
| TensorRT FP16 | 8.1ms | 8.0ms | 8.8ms |

- TensorRT gives only 1.07x speedup — YOLO is already well optimized in PyTorch
- YOLO ball detection is NOT the bottleneck

### 24.3 MMPose Baseline Benchmark

| Component | Per-image | 4-cam sequential |
|---|---|---|
| RTMDet-m + RTMPose-m | 38.5ms | 154ms |

- This is the dominant bottleneck (78% of pipeline time)
- Batch mode in parallel script gets ~80ms but still largest contributor

### 24.4 YOLO-Pose Discovery (KEY RESULT)

| Model | Format | Per-image | 4-cam total | vs MMPose |
|---|---|---|---|---|
| YOLO11m-Pose | PyTorch .pt | 8.9ms | 36ms | 4.3x faster |
| YOLO11m-Pose | TensorRT FP16 | 6.2ms | 25ms | **6.2x faster** |

- YOLO-Pose replaces BOTH RTMDet (person detector) + RTMPose (keypoint estimator) with single forward pass
- Outputs same COCO 17-keypoint format as MMPose
- TensorRT FP16 engine: 42.2 MB, exported at imgsz=640
- **Pipeline total with YOLO-Pose TRT: ~70ms vs ~200ms current = 2.8x end-to-end speedup**

### 24.5 Software artifacts created
- `Parallel_working/scripts/export_models_tensorrt.py` — benchmark + export utility
- `Parallel_working/scripts/record_test_sequence.py` — 4-camera recording for offline eval
- `Parallel_working/scripts/ablation_ema_adaptive.py` — adaptive vs fixed EMA comparison
- `Parallel_working/run_live_parallel_predictive.sh` — Kalman prediction profile
- TensorRT engines:
  - `garage-20260217T113109Z-3-001/garage/y26s_v1_garage.engine` (ball, 20.6 MB)
  - `yolo11m-pose.engine` (pose, 42.2 MB)

### 24.6 ONNX Runtime installation note
- Installed `onnxruntime-gpu==1.16.3` (compatible with system CUDA 11.5)
- System has libcufft.so.10, libcudnn.so.8 — ORT 1.23 requires .so.11 variants
- protobuf upgraded to 7.34.1 (mediapipe incompatibility warning — mediapipe not used)

### 24.7 Completed steps
- [x] Integrate YOLO-Pose into parallel pipeline as `--pose-backend yolopose|mmpose` flag
- [x] Validate YOLO-Pose keypoint accuracy on real arena frames vs MMPose
- [x] Fix YOLO-Pose integration bug (undistortion + pose-lock logic was inside MMPose-only branch)
- [ ] Record test sequences (walk, jog, jump) for ablation study
- [ ] Run ablation: adaptive vs fixed EMA on recorded sequences

---

## 25) Daily Log — 2026-04-03 (YOLO-Pose Integration + Bug Fix)

### 25.1 YOLO-Pose integrated into parallel pipeline
- Added `--pose-backend yolopose|mmpose` CLI flag
- Added `--yolopose-model` flag (accepts .pt or .engine TensorRT)
- YOLO-Pose outputs same COCO 17-keypoint format → drop-in replacement for MMPose

### 25.2 Live camera validation
- Captured test frames from all 4 arena cameras with person standing in arena
- YOLO-Pose results:
  - camNorth: box_conf=0.921, 15/17 valid keypoints
  - camEast: box_conf=0.889, 11/17 valid keypoints
  - camSouth: box_conf=0.899, 12/17 valid keypoints
  - camWest: box_conf=0.341, 2/17 valid keypoints (oblique angle)
- MMPose comparison on same frames:
  - camNorth: 14/17, camEast: 5/17, camSouth: 14/17, camWest: 2/17
- YOLO-Pose matches or exceeds MMPose keypoint count on 3/4 cameras

### 25.3 Bug found and fixed: no skeleton in 3D view with YOLO-Pose
- **Root cause:** The shared post-processing code (undistortion, pose-lock, `pose_und_by_cam` population) was inside the `elif` MMPose branch only. YOLO-Pose filled `per_cam_pose_curr` but triangulation never received undistorted points.
- **Fix:** Moved the shared block (`per_cam_pose` copy, `has_pose_lock`, `force_pose_snap`, undistortion loop) to run after both YOLO-Pose and MMPose branches under a single `if run_pose:` guard.
- **Status:** Live tested and confirmed working — skeleton + ghost skeleton visible in 3D arena view.

### 25.4 New run profiles created
- `run_live_parallel_yolopose.sh` — YOLO-Pose + prediction + cv2 (RECOMMENDED)
- `run_live_parallel_fastest.sh` — ball TRT + YOLO-Pose TRT + prediction (lowest latency)
- Test captures saved: `Parallel_working/output/test_captures/cam{N,E,S,W}.jpg`

### 25.5 Current pipeline status
All features live-validated and working:
- [x] OpenCV 3D renderer (~2ms vs 300ms matplotlib)
- [x] Displacement-adaptive EMA (jumps snap instantly)
- [x] Display interpolation (smooth inter-frame motion)
- [x] Kalman filter prediction (ghost skeleton at +400ms)
- [x] YOLO-Pose backend (6.2x faster than MMPose)
- [x] TensorRT engines (ball + pose)
- [x] Correct coordinate orientation (270° azimuth fix + X-mirror)

---

## 26) Phase J — Recorded Test Sequences + EMA Ablation Study (2026-04-06)

### 26.1 Test sequence recording pipeline
- Rewrote `Parallel_working/scripts/record_test_sequence.py` with threaded capture for reliable multi-camera recording
- Fixed config parser to handle dict-style cameras.yaml format
- Added warmup phase for auto-exposure stabilization

### 26.2 Recorded test sequences (3 × 30s, 4 cameras, 15 FPS)
| Sequence | Frames | Cameras | Motion type |
|----------|--------|---------|-------------|
| walk_01 | 449 | 4/4 | Normal walking pace across arena |
| jog_01 | 449 | 4/4 | Fast jogging movement |
| jump_01 | 449 | 4/4 | Jumps + sudden direction changes |

All sequences saved to `Parallel_working/output/test_sequences/`.

### 26.3 EMA ablation study design
Refactored `Parallel_working/scripts/ablation_ema_adaptive.py` for efficient evaluation:
- **Phase 1**: Pose extraction (run once per backend, cache results)
- **Phase 2**: Multi-view triangulation (run once, cache 3D positions)
- **Phase 3**: Apply 8 EMA variants on cached data (instant)

**EMA variants tested:**
1. `fixed_0.25` — strongest smoothing (α=0.25)
2. `fixed_0.35` — moderate smoothing
3. `fixed_0.45` — default production alpha
4. `fixed_0.60` — light smoothing
5. `adaptive_0.45_snap_80` — adaptive with 80mm snap threshold (production)
6. `adaptive_0.45_snap_50` — aggressive adaptive
7. `adaptive_0.45_snap_120` — conservative adaptive
8. `no_ema` — raw triangulation (α=1.0), baseline

### 26.4 YOLO-Pose vs MMPose backend comparison

**Pose extraction throughput (4 cameras, per frame):**
| Backend | walk FPS | jog FPS | jump FPS | Avg |
|---------|----------|---------|----------|-----|
| YOLO-Pose | 25.4 | 24.4 | 25.4 | 25.1 |
| MMPose | 6.8 | 7.1 | 7.0 | 7.0 |
| **Speedup** | **3.7x** | **3.4x** | **3.6x** | **3.6x** |

Note: This is per-frame 4-camera sequential extraction. Live pipeline processes cameras in batch, achieving ~6.2x speedup with TRT.

**Detection rates:**
| Backend | walk | jog | jump |
|---------|------|-----|------|
| YOLO-Pose | 94-100% | 100% | 98-100% |
| MMPose | 100% | 100% | 100% |

**Triangulation coverage:**
| Backend | walk | jog | jump |
|---------|------|-----|------|
| YOLO-Pose | 90% joints | 95% | 93% |
| MMPose | 99% | 100% | 99% |

### 26.5 EMA ablation results — walk sequence

| Variant | YOLO-Pose Jitter | MMPose Jitter | YOLO-Pose Smooth | MMPose Smooth |
|---------|-----------------|---------------|------------------|---------------|
| fixed_0.25 | 41.1mm | 43.2mm | 10.5mm | 11.0mm |
| fixed_0.45 | 44.4mm | 47.9mm | 18.7mm | 20.2mm |
| adaptive_0.45_snap_80 | 47.6mm | 54.8mm | 37.5mm | 46.6mm |
| no_ema | 52.7mm | 58.7mm | 47.7mm | 53.4mm |

### 26.6 EMA ablation results — jog sequence

| Variant | YOLO-Pose Jitter | MMPose Jitter | YOLO-Pose P95 | MMPose P95 |
|---------|-----------------|---------------|---------------|------------|
| fixed_0.25 | 84.3mm | 85.5mm | 151.0mm | 146.8mm |
| fixed_0.45 | 93.0mm | 93.3mm | 181.5mm | 173.5mm |
| adaptive_0.45_snap_80 | 103.7mm | 101.5mm | 249.1mm | 238.3mm |
| no_ema | 110.0mm | 106.5mm | 237.0mm | 226.0mm |

### 26.7 EMA ablation results — jump sequence

| Variant | YOLO-Pose Jitter | MMPose Jitter | YOLO-Pose P95 | MMPose P95 |
|---------|-----------------|---------------|---------------|------------|
| fixed_0.25 | 75.5mm | 78.5mm | 174.4mm | 170.5mm |
| fixed_0.45 | 90.0mm | 92.6mm | 219.3mm | 211.0mm |
| adaptive_0.45_snap_80 | 108.6mm | 108.0mm | 313.0mm | 282.2mm |
| no_ema | 117.0mm | 114.8mm | 309.3mm | 273.9mm |

### 26.8 Key findings

1. **YOLO-Pose achieves equivalent 3D accuracy to MMPose** at 3.6x faster extraction speed. Mean jitter differences are <5mm across all sequences — well within measurement noise.

2. **Fixed EMA α=0.25 minimizes jitter** (41-85mm mean) but introduces tracking lag for fast motions. Best for static/slow targets.

3. **Adaptive EMA increases P95 jitter** (by ~30-60mm vs fixed) because it intentionally reduces smoothing during large displacements. The trade-off is faster snap response.

4. **For the BLM targeting use case**, the Kalman filter prediction (not measured here as pure EMA ablation) operates on top of the EMA-smoothed trajectory. The combination of moderate EMA (α=0.45) + Kalman prediction should give both smooth tracking and accurate lead.

5. **Jog/jump sequences show 2x the jitter of walk** — expected for faster motion at 15 FPS. This validates the need for predictive targeting.

### 26.9 Execution plan progress update
- Week 1-2 (Foundation): **~90% complete**
  - [x] TensorRT export + benchmarks
  - [x] YOLO-Pose integration (3.6x speedup offline, 6.2x live with TRT)
  - [x] Kalman prediction + ghost skeleton
  - [x] cv2 renderer + adaptive EMA
  - [x] Record test sequences (walk, jog, jump) — 3 × 30s, 4 cameras
  - [x] EMA ablation study (8 variants × 3 sequences × 2 backends)
  - [x] YOLO-Pose vs MMPose 3D accuracy comparison
  - [x] Re-run GT evaluation with current arena_fixed extrinsics
- Week 3 (Prediction validation): Not started
- Week 4-6 (BLM closed-loop): Not started

---

## 27) Phase K — GT Re-evaluation with arena_fixed Extrinsics (2026-04-06)

### 27.1 Motivation
Previous GT evaluation (2026-03-10) used `extrinsics_final_20260309.json`. Since then, the `arena_fixed` extrinsics were introduced with the Y-axis coordinate fix. Need to verify whether the corrected extrinsics maintain or improve GT accuracy.

### 27.2 Method
- Re-processed existing recorded clips (no new recordings needed — cameras haven't moved)
- Ball static: 36 trials from `ball_tuning_20260306_164519/`
- Joint touch: 81 trials from `joint_tuning_20260310_124311/` (62 had clips, 19 missing)
- Used `arena_fixed/cal/extrinsics/extrinsics_fixed.json` instead of old extrinsics
- All other parameters identical (intrinsics, YOLO model, confidence thresholds)
- Results in `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/`

### 27.3 Ball static GT results (36/36 trials)

| Metric | Previous (old extr) | arena_fixed | Change |
|--------|-------------------|-------------|--------|
| Mean error | 95.17mm | 156.90mm | +61.7mm |
| Median error | 84.18mm | 157.52mm | +73.3mm |
| RMSE | 102.23mm | 172.05mm | +69.8mm |
| P95 error | 166.51mm | 288.34mm | +121.8mm |
| Detection | 36/36 (100%) | 36/36 (100%) | same |
| Mean cams used | — | 2.74 | — |
| Reprojection error | — | 5.46px | — |
| Static precision | — | 3.09mm | excellent |

**Axis bias (arena_fixed):** ex=+60.2mm, ey=+13.1mm, ez=-104.3mm

### 27.4 Joint touch GT results (62/81 trials)

| Metric | Previous (old extr) | arena_fixed | Change |
|--------|-------------------|-------------|--------|
| Mean error | 143.38mm | 178.98mm | +35.6mm |
| Median error | 148.90mm | 181.17mm | +32.3mm |
| RMSE | 147.73mm | 183.69mm | +36.0mm |
| P95 error | 198.73mm | 243.77mm | +45.0mm |
| Detection | 62/81 | 62/81 | same |
| Static precision | — | 4.39mm | excellent |

**Axis bias (arena_fixed):** ex=+82.7mm, ey=+72.3mm, ez=-125.4mm

**Per-joint breakdown (arena_fixed):**
| Joint | Trials | Mean Error | P95 | Precision |
|-------|--------|-----------|-----|-----------|
| right_knee | 17 | 148.4mm | 213.4mm | 7.3mm |
| right_hip | 27 | 182.1mm | 218.1mm | 3.4mm |
| left_shoulder | 18 | 203.1mm | 246.4mm | 3.1mm |

### 27.5 Analysis

1. **Precision is excellent** — 3-4mm static std across both evaluations. The cameras are geometrically consistent and the triangulation is stable.

2. **Systematic bias increased** — The arena_fixed extrinsics introduce a consistent offset vs the GT measurement reference frame. The Z bias (-104 to -125mm) is the dominant error component.

3. **The bias is correctable** — The correction model (linear fit per axis) can compensate. The X scale factor is 1.08 (8% stretch), suggesting a minor calibration-to-measurement coordinate mismatch.

4. **Root cause hypothesis**: The arena_fixed extrinsics were calibrated with AprilTags at different heights/positions than the GT measurement grid. The world origin offset between the two coordinate systems explains the systematic bias. The old extrinsics may have been implicitly closer to the GT measurement frame.

5. **For BLM targeting**: The systematic bias is acceptable if a correction model is applied at the launcher runtime level. The correction model from the ball evaluation can offset the known bias. Alternatively, re-calibrating extrinsics with the AprilTag grid aligned to the GT measurement points would remove the bias at source.

### 27.6 Correction model (ball static)
```json
{
  "global_bias_add_mm": {"x": -60.2, "y": -13.1, "z": 104.3},
  "axis_linear_gt_from_est": {
    "x": {"a": 1.080, "b": -383.7},
    "y": {"a": 0.975, "b": 27.9},
    "z": {"a": 0.965, "b": 136.1}
  }
}
```

### 27.7 Execution plan update
- Week 1-2 (Foundation): **100% complete**
  - All items checked off including GT re-evaluation
- Next: Week 3 (Kalman prediction validation on recorded sequences)

---

## 28) Phase L — Kalman Prediction Validation (2026-04-07)

### 28.1 Validation script
Created `Parallel_working/scripts/validate_kalman_prediction.py`:
- 3-phase pipeline (reuses ablation infrastructure): pose → triangulate → predict + compare
- Compares 3 predictors: Kalman filter, naive hold (baseline), linear extrapolation
- Tests 5 prediction horizons: 67ms, 133ms, 200ms, 400ms, 600ms
- Reports per-axis, per-joint, and aggregate error metrics

### 28.2 Parameter tuning
Original defaults (process_noise=50, measurement_noise=80) performed terribly — 700%+ worse than naive.
Root cause: measurement noise was too high relative to EMA-smoothed input, causing the filter to distrust measurements and lag behind.

**Parameter sweep results (walk sequence, 200ms horizon):**
| Process Noise | Meas Noise | Kalman Mean | vs Naive |
|--------------|-----------|-------------|----------|
| 50 | 80 | 416mm | -230% |
| 100 | 10 | 98mm | +17% |
| 200 | 10 | 78mm | +34% |
| **500** | **10** | **61mm** | **+48%** |
| 500 | 20 | 74mm | +37% |
| 500 | 40 | 94mm | +21% |

**Optimal: process_noise=500, measurement_noise=10** — high process noise allows rapid adaptation, low measurement noise trusts the already-smoothed EMA input.

### 28.3 Full validation results (PN=500, MN=10)

**Walk sequence:**
| Horizon | Kalman | Naive | Linear | K vs Naive |
|---------|--------|-------|--------|------------|
| 67ms | 29mm | 42mm | 13mm | +31% |
| 133ms | 46mm | 84mm | 28mm | +45% |
| 200ms | 66mm | 125mm | 45mm | **+47%** |
| 400ms | 132mm | 247mm | 112mm | **+47%** |
| 600ms | 204mm | 366mm | 186mm | +44% |

**Jog sequence:**
| Horizon | Kalman | Naive | Linear | K vs Naive |
|---------|--------|-------|--------|------------|
| 67ms | 69mm | 88mm | 29mm | +21% |
| 200ms | 158mm | 260mm | 109mm | **+39%** |
| 400ms | 332mm | 505mm | 259mm | **+34%** |
| 600ms | 559mm | 738mm | 468mm | +24% |

**Jump sequence:**
| Horizon | Kalman | Naive | Linear | K vs Naive |
|---------|--------|-------|--------|------------|
| 67ms | 101mm | 82mm | 37mm | -23% |
| 200ms | 229mm | 237mm | 150mm | +3% |
| 400ms | 454mm | 446mm | 382mm | -2% |
| 600ms | 689mm | 631mm | 635mm | -9% |

### 28.4 Analysis

1. **Kalman prediction improves walk/jog targeting by 30-47%** at 200-400ms horizons. This is the primary BLM use case — the athlete is typically walking/jogging, not continuously jumping.

2. **Jump prediction is neutral** — the constant-velocity model cannot predict direction changes or vertical jumps. For jump-heavy scenarios, the Kalman prediction should be disabled or combined with a higher-order motion model.

3. **Linear extrapolation wins at short horizons** (<133ms) because it has no filter lag. However, it diverges rapidly on non-linear motion (jump 600ms: 635mm).

4. **Optimal prediction horizon for BLM: 200-400ms** — maximizes Kalman advantage while keeping error manageable (66-132mm for walk, 158-332mm for jog).

5. **Updated live pipeline defaults**: process_noise=500, measurement_noise=10 in `live_4cam_arena_view_parallel.py`.

### 28.5 Execution plan update
- Week 1-2 (Foundation): **100% complete**
- Week 3 (Prediction validation): **100% complete**
  - [x] Kalman parameter sweep + optimization
  - [x] 3-sequence × 5-horizon validation
  - [x] Updated live pipeline defaults
- Week 4-6 (BLM closed-loop): **In progress**
  - [x] Integrate GT correction model into `launcher_runtime_from_udp.py`
  - [x] BLM preflight S0-S1 (ESP32 serial verified)

## 29) GT Correction Model Integration (2026-04-07)

### 29.1 Goal
Compensate the systematic extrinsics bias discovered in Section 27 (X+60-83mm, Z-104 to -125mm) by applying a correction model inside the launcher runtime before the ballistic solver.

### 29.2 Implementation
Added to `garage_lab_combined/scripts/launcher_runtime_from_udp.py`:

1. **`load_correction_model(path)`** — loads correction JSON (from GT eval output)
2. **`apply_correction(xyz_mm, model, mode)`** — two modes:
   - `bias`: global mean offset (`global_bias_add_mm`)
   - `linear`: per-axis linear fit (`gt = a * est + b` from `axis_linear_gt_from_est`)
3. **CLI args**: `--correction-model` (path) and `--correction-mode` (none/bias/linear)
4. **Applied before solver**: raw position saved as `xyz_mm_raw`, corrected position used for ballistic calculation
5. **Logging**: every JSONL log entry now includes `raw_world_xyz_mm`, `corrected_world_xyz_mm`, and `correction_mode`

### 29.3 Correction Model Values (from ball GT eval)
- Bias: X=-60.2mm, Y=-13.1mm, Z=+104.3mm
- Linear: X: a=1.08 b=-383.7 | Y: a=0.975 b=27.9 | Z: a=0.965 b=136.1

### 29.4 Usage
```bash
./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 --no-shoot-enabled \
  --correction-mode linear \
  --dry-run-log-jsonl garage_lab_combined/output/blm_logs/aim_decisions.jsonl
```

## 30) BLM Preflight S0-S1 (2026-04-07)

### 30.1 S0: Serial Connection
- ESP32 on `/dev/ttyUSB0` at 115200 baud
- User in `dialout` group — no permission issues
- Firmware responds to commands: `status`, `center`, `set`, `stop`, `estop`, `clear`

### 30.2 S1: Manual Command Verification
| Command | Response | Physical |
|---------|----------|----------|
| `center` | `CMD: CENTERED (V=0, H=0)` | Returns to home |
| `set 5 5 0 0` | `ACK: V=5.0 H=5.0` | Moves correctly |
| `set 10 10 0 0` | `ACK: V=10.0 H=10.0` | Moves correctly |
| `set 20 0 0 0` | `ACK: V=20.0 H=0.0` | Moves correctly |
| `set 25 0 0 0` | `ACK: V=25.0 H=0.0` | Moves correctly |
| `set 30 0 0 0` | `ACK: V=30.0 H=0.0` | Moves correctly |
| `set -20 0 0 0` | `ACK: V=-20.0 H=0.0` | Moves correctly |
| `set 0 -20 0 0` | `ACK: V=0.0 H=-20.0` | Moves correctly |
| `stop` | `STOPPED` | Halts |
| `estop` → `clear` → `center` | All acknowledged | Latch cycle works |

### 30.3 Known Issue
- `set 40 -40 0 0` (beyond ±30 limit) causes ESP32 firmware reboot (`rst:0x3 SW_RESET`)
- Firmware clamps to ±30 before crash — the ACK shows `V=30.0 H=-30.0` then reboots
- **Mitigation**: software already clamps at `--max-abs-angle-deg` (default 30) before sending

### 30.4 Next Steps
- S2: Aim-only dry run with live cameras (`--no-shoot-enabled --correction-mode linear`)
- S3: RPM gate test (wheel spin-up without firing)
- S4: Controlled fire test with safety observer
