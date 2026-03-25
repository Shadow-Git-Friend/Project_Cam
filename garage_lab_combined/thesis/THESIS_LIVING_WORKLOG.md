# Thesis Living Worklog (Project_Cam)

Last updated: 2026-03-20

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
