# Project_Cam — Complete Pipeline, Architecture, and Script Reference

**Author**: Hanush (MSc ECE, Nazarbayev University)
**Title**: Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking
**Date compiled**: 2026-04-13

---

## 1. Pipeline Overview

The system is a closed-loop vision-to-actuation pipeline whose purpose is to detect a person's body joints in real time with four fixed cameras, triangulate each joint to a single 3D world coordinate, predict where that joint will be a few hundred milliseconds into the future, and aim a ball-launching machine (BLM) at that predicted point.

**End-to-end data flow**

```
  [4 USB cameras @1280×720, ~15 fps]
          │
          ▼
  ThreadedCapture   (one thread per camera, drops stale frames)
          │
          ▼
  Detection       → YOLO ball (.pt/.engine) + YOLO-Pose or MMPose
          │        (per-camera 2D keypoints + ball pixels)
          ▼
  Triangulation   → SVD multi-view DLT (needs ≥2 cams, mm output)
          │
          ▼
  EMA smoothing   → adaptive α, snap threshold 80 mm
          │
          ▼
  Kalman predict  → constant-velocity 6-state per joint,
          │        predict-ahead 200–400 ms (UDP ships both
          │        current and predicted payloads)
          ▼
  UDP broadcast   → JSON packet: ball, joints{current}, predicted
          │
          ▼
  Launcher runtime → zone check → confidence/stability gates →
          │         GT correction → world→launcher rotation →
          │         ballistic low-arc solver → angle clamp ±30°
          ▼
  Serial @921600  → "set v h wl wr" / "shoot" / "reload" / "stop"
          │
          ▼
  ESP32 (control_12_full.ino) → steppers + DRV8825 pusher + flywheels
```

Two parallel viewers are provided:

- `garage_lab_combined/scripts/live_4cam_arena_view.py` — production, matplotlib 3D view.
- `Parallel_working/scripts/live_4cam_arena_view_parallel.py` — performance-tuned fork with cv2 renderer, YOLO-Pose backend, Kalman prediction, ghost skeleton, staleness gate.

Only the `garage_lab_combined` scripts touch BLM hardware.

---

## 2. Calibration Pipeline

### 2.1 Intrinsic Calibration — ChArUco Board

**Script**: `calibrate_intrinsics_charuco_garage.py`
**Artifacts**: `garage_lab_combined/cal/intrinsics/cam{North,East,South,West}_intrinsics.json`

**Board**: 10×7 ChArUco, 29.7 mm squares, 22.275 mm markers, DICT_5X5_50.

**Pinhole model**

```
s·[u v 1]ᵀ = K · [R | t] · [X Y Z 1]ᵀ
K = [[fx 0 cx]
     [0 fy cy]
     [0  0  1]]
```

Radial-tangential distortion (Brown-Conrady):

```
x_d = x (1 + k1 r² + k2 r⁴ + k3 r⁶) + 2 p1 x y + p2 (r² + 2 x²)
y_d = y (1 + k1 r² + k2 r⁴ + k3 r⁶) + p1 (r² + 2 y²) + 2 p2 x y
```

**Objective**: minimize the reprojection residual over all detected ChArUco corners across N images:

```
argmin_{K, D, Rᵢ, tᵢ} Σᵢ Σⱼ || π(K, D, Rᵢ, tᵢ, X_j) − u_ij ||²
```

solved by `cv2.aruco.calibrateCameraCharuco` (Levenberg-Marquardt).

**Result for camNorth (example)**: fx=717.88, fy=715.91, cx=634.31, cy=342.79, k1=0.032, k2=-0.121, p1=-0.001, p2=0.0002, k3=0.077, reproj RMS=0.728 px at 1280×720.

All intrinsics MUST be re-scaled if resolution changes: `fx' = fx · W'/W`, and similarly for fy, cx, cy.

### 2.2 Extrinsic Calibration — AprilTag + PnP-RANSAC

**Scripts**: `calibrate_extrinsics_apriltag.py`, `…_oriented.py`, `…_robust.py` (current).
**Artifacts**: `arena_fixed/cal/extrinsics/extrinsics_fixed.json`, `…/Dimensions_fixed.txt`.

`Dimensions_fixed.txt` is a free-text file that defines:
- Arena bounds: X=6230 mm, Y=3050 mm, Z=2950 mm.
- 24 AprilTag corner world positions (mm).
- Ground-truth camera positions (camNorth ≈ (5, 110, 226) cm, etc.).

**Pose estimation**: for each camera, collect ≥4 tag-corner correspondences (2D pixels ↔ 3D world points), then run:

1. `cv2.solvePnPRansac(objectPoints, imagePoints, K, D, flags=SOLVEPNP_EPNP)` to get a robust seed.
2. **Iterative refinement** (`robust_refine_pose`): project all points with the current pose, compute per-point residual, flag outliers using MAD (Median Absolute Deviation):

```
σ_MAD = 1.4826 · median(|r − median(r)|)
reject r_i if |r_i − median(r)| > sigma_scale · σ_MAD   (default 2.5)
```

Also reject if any tag's median residual > `tag_median_thresh_px` (45 px default). Re-solve PnP on the surviving set with `SOLVEPNP_ITERATIVE`. Repeat until the inlier set stabilises.

3. Store `rvec` (Rodrigues 3-vec) and `tvec` (translation, meters) per camera.

**World → pixel projection** (used everywhere):

```
X_cam = R · X_world + t                (R = Rodrigues(rvec))
u = fx · X_cam.x / X_cam.z + cx
v = fy · X_cam.y / X_cam.z + cy
```

Live scripts load extrinsics and multiply `tvec` by 1000 to convert from meters to mm so the whole runtime stack runs in mm.

### 2.3 Supporting Calibration Utilities

- `auto_capture_charuco_multi.py` — simultaneous multi-camera snapshot recorder for intrinsics.
- `calibrate_intrinsics_from_images.py` — re-run intrinsic fit from a folder of stored frames.
- `validate_extrinsics_overlay.py` — projects the known world tag corners back into each camera image to visually audit extrinsics quality.
- `estimate_sync_offsets.py` — estimates camera timestamp offsets by cross-correlating motion; used to compensate asynchronous USB capture.
- `render_apriltag_arena_360.py`, `render_multiviews.py`, `render_arena_ball_skeleton.py` — diagnostic renderers.

---

## 3. 3D Reconstruction Mathematics

### 3.1 Multi-View Triangulation (SVD-DLT)

Given `N ≥ 2` cameras observing the same 3D point X, each 2D observation `(u, v)` gives two linear constraints derived from `s·[u v 1]ᵀ = P · [X 1]ᵀ` where `P = K [R|t]`:

```
(u · P_row3 − P_row1) · X_h = 0
(v · P_row3 − P_row2) · X_h = 0
```

Stacking all 2N rows into matrix A and solving `A · X_h = 0` by SVD, the solution is the right-singular vector of the smallest singular value. Dehomogenise: `X = X_h[0:3] / X_h[3]`. Implemented in `triangulate_multi()` (live_4cam_arena_view_parallel.py and live_4cam_arena_view.py).

### 3.2 EMA Smoothing (adaptive)

```
x̂_t = α · x_t + (1 − α) · x̂_{t−1}
```

`ema_update()` uses α=0.25 by default. **Adaptive variant** (smooth_v2/predictive): if `||x_t − x̂_{t−1}|| > snap_threshold` (80 mm), α is boosted to 0.9 so fast motion is not over-smoothed. Preserves responsiveness for jumps without sacrificing static stability.

### 3.3 Kalman Filter Prediction

Implemented in `JointKalmanFilter` inside `live_4cam_arena_view_parallel.py`. Constant-velocity (CV) model:

**State**: `x = [X, Y, Z, Ẋ, Ẏ, Ż]ᵀ`

**Transition**:
```
F(Δt) = [[I₃   Δt·I₃]
         [0₃   I₃   ]]
```

**Process noise** (acceleration-driven):
```
Q(Δt) = q · [[Δt⁴/4·I₃   Δt³/2·I₃]
             [Δt³/2·I₃   Δt² ·I₃ ]]
```
with `q = process_noise` (default 500 mm²/s⁴).

**Measurement model**: `H = [I₃ 0₃]`, `R = measurement_noise · I₃` (default 10 mm²).

**Predict step**: `x̂⁻ = F·x̂`, `P⁻ = F·P·Fᵀ + Q`.
**Update step**: `K = P⁻·Hᵀ·(H·P⁻·Hᵀ + R)⁻¹`, `x̂ = x̂⁻ + K·(z − H·x̂⁻)`, `P = (I − K·H)·P⁻`.

**Predict-ahead**: a pure `F(Δt_pred)` extrapolation (no measurement) gives the expected position 200–400 ms in the future; ships as `predicted` in the UDP packet.

**Tuned values** (2026-04-07): PN=500, MN=10, predict-ahead 400 ms. Walk: 47 % improvement; jog: 34–39 %; jump: ~neutral (CV limitation).

### 3.4 World → Launcher Frame

The launcher is yaw-mounted in world coordinates. `forward_right_vectors_from_yaw(yaw_deg)` returns two unit vectors in the XY plane:

```
fwd   = ( cos(yaw), sin(yaw) )
right = ( sin(yaw), −cos(yaw) )
```

Then `world_to_launcher_xy_delta(target_world, launcher_world, yaw)`:
```
d_xy = target_xy − launcher_xy
x_lat = d_xy · right            (horizontal offset, sign = yaw direction)
y_fwd = d_xy · fwd              (forward distance)
```

### 3.5 Ballistic Low-Arc Solver

Let `d = y_fwd` (forward), `dz = z_target − z_launcher`, `v = muzzle_speed` (m/s), `g = 9.81`:

```
Δ = v⁴ − g·(g·d² + 2·dz·v²)
if Δ < 0: target out of reach → reject
v_rad_low = atan( (v² − √Δ) / (g·d) )           # low arc (preferred)
v_rad_high = atan( (v² + √Δ) / (g·d) )          # high arc (unused)
pitch_deg = degrees(v_rad_low)
yaw_deg   = degrees(atan2(x_lat, y_fwd))
```

Both are clamped to [0°, 30°] and [−30°, 30°] respectively **in Python** before being sent — the ESP32 reboots on commands beyond ±30°.

### 3.6 GT Correction Model

To close the remaining 150–180 mm systematic bias observed in GT evaluation, `load_correction_model()` supports two modes, per axis:

- **bias mode**: `x_corr = x_est + b_x`, `y_corr = y_est + b_y`, `z_corr = z_est + b_z`.
- **linear mode**: `x_corr = a_x · x_est + b_x`, fit per-axis from GT regression.

Measured systematic bias against arena_fixed extrinsics: X +83 mm, Z −125 mm (joint-touch). Precision (std) is excellent: 4.39 mm, so the residual is correctable.

---

## 4. Runtime Architecture

### 4.1 Live Viewer (parallel, recommended)

`Parallel_working/scripts/live_4cam_arena_view_parallel.py` (2015 lines)

**Core classes**:
- `StageTimer`: timer context manager for the perf-log.
- `ThreadedCapture`: one thread per USB camera, drops frames older than `max_frame_age_ms`. Exposes `get()` → most recent frame + timestamp.
- `JointKalmanFilter`: per-joint filter (see §3.3), methods `_build_F`, `_build_Q`, `predict_step`, `update_step`, `predict_ahead`, `prediction_uncertainty`.

**Core functions**:
- `parse_dimensions(path)` → arena bounds + tag corners.
- `scale_intrinsics_matrix(K, src_wh, dst_wh)` → resolution-safe K scaling.
- `load_extrinsics(path)` → list of (R, t_mm) per camera.
- `triangulate_multi(points_2d, P_matrices)` → SVD-DLT 3D point in mm.
- `transform_world_point_y(p)` → Y-axis display transform (geometry-protected).
- `extract_person_pose(frame, backend)` → dispatches to YOLO-Pose or MMPose.
- `select_target_person(poses)` → picks the nearest person by median Z.
- `ema_update(prev, new, alpha, snap_threshold)` → adaptive smoothing.
- `make_orbit_view(azim, elev)` → camera basis for cv2 3D renderer.
- `_cv2_project(points, view)` → project 3D → 2D for cv2 scene.
- `draw_live_scene_cv2(...)` → ~2 ms renderer replacing matplotlib.
- `_blm_*` helpers — UDP broadcast of current + predicted joints + ball.

**Key CLI flags** (common set):

| Flag | Meaning | Default |
|------|---------|---------|
| `--pose-backend {yolopose,mmpose}` | Pose model | yolopose |
| `--yolopose-model` | `.pt` or `.engine` path | yolo11m-pose.pt |
| `--yolo-model` | Ball detector model | y26s_v1_garage.pt |
| `--renderer {matplotlib,cv2}` | 3D view | cv2 |
| `--render-worker-process` | Offload matplotlib to child | off |
| `--max-frame-age-ms` | Drop stale frames | 200 |
| `--pose-every N` / `--ball-every N` / `--viz-every N` | Frame skip | 1 |
| `--ema-alpha` | Base α | 0.25 |
| `--ema-snap-threshold-mm` | Jump-detect α-boost | 80 |
| `--predict-ahead-ms` | Kalman horizon | 400 |
| `--kalman-process-noise` | q (mm²/s⁴) | 500 |
| `--kalman-measurement-noise` | r (mm²) | 10 |
| `--show-ghost-skeleton` | Translucent predicted pose | on |
| `--predict-max-uncertainty-mm` | Drop predictions above σ | 250 |
| `--udp-host / --udp-port` | Target broadcast addr | 127.0.0.1 / 5005 |
| `--no-world-y-mirror` | Production Y-axis handling | set |
| `--demo-blm` | Draw launcher + aim ray overlay | off |
| `--perf-jsonl` | Per-stage timing log | off |

**COCO-17 joints**: nose, L/R eye, L/R ear, L/R shoulder, L/R elbow, L/R wrist, L/R hip, L/R knee, L/R ankle. The UDP payload uses 13 targetable joints (eyes and ears are excluded for aiming but still drawn).

### 4.2 Launcher Runtime

`garage_lab_combined/scripts/launcher_runtime_from_udp.py` (1441 lines)

**Dataclass `JointSample`**: name, xyz, confidence, n_cams, ts.

**Functions**:
- `load_zone_by_joint(csv_path)` → `{joint: (xmin, xmax, ymin, ymax, zmin, zmax)}` used for zone gate.
- `load_correction_model(path, mode)` → closure `apply(xyz) → xyz'` for bias or linear.
- `apply_correction(xyz, model, mode)` — wrapper.
- `forward_right_vectors_from_yaw(yaw)` — §3.4.
- `world_to_launcher_xy_delta(target, launcher, yaw)` — §3.4.
- `solve_angles_ballistic(d, dz, v)` — §3.5.
- `calculate_kinematics_v1(…)` — legacy angle solver (kept for comparison).
- `stable_target_from_buffer(buf, window, max_std)` — stability gate; rejects noisy samples.
- `parse_joint_samples(packet)` — UDP packet decoder.
- `drain_serial_lines(ser)` — non-blocking line reader.
- `read_rpm_from_lines(lines)` — parses `L:xxx R:xxx` telemetry.

**Key flags**:
- `--serial-port /dev/ttyUSB0` (required)
- `--launcher-yaw-deg` world yaw of the BLM (required)
- `--correction-mode {none,bias,linear}` (default none)
- `--correction-model-path`
- `--target-joint` (default right_shoulder)
- `--udp-target-cams-min` (default 3)
- `--udp-target-conf-min` (default 0.45)
- `--udp-target-stable-window-ms` (default 300)
- `--shoot-enabled / --no-shoot-enabled`
- `--wheel-rpm` (default 0)
- `--dry-run-log-jsonl`

On `shoot`, it enforces the RPM gate (reads telemetry until both wheels ≥ 400 RPM) and then sends `shoot`.

### 4.3 BLM Interactive Tools

- `blm_interactive.py` — raw serial REPL. Uses background `reader_thread`, filters ESP32 boot ROM lines (`ets `, `rst:`, `configsip:`, `clk_drv:`, `mode:`, `load:`, `entry`), baud-garbage (lines ≥20 chars with ≤2 unique chars, e.g. `MMMMMMMM…`), and RPM telemetry. Sends `stop` + `center` on exit.
- `live_aim_test.py` — interactive single-shot aim test. Background `SerialReader` thread. Asks operator to type `yes` to fire. Builds `set v h wl wr` from pose target + correction + ballistic solver, clamps angles, requires successful aim before allowing shoot.
- `blm_follow.py` — continuous follow mode (2026-04-10). Hot-swap target joints by typing their name. Adds `LineEditor` (termios cbreak raw-mode) so status prints never garble the user's typing. `armed` state forces operator to type `reload` before any aim happens when `--shoot-enabled`. Deadband (`--min-delta-deg 0.5`) + rate limit (`--min-interval-s 0.15`) + staleness gate (`--max-staleness-s 1.0`).
- `manual_aim_test.py` — non-interactive aim sweep for mechanical characterisation.
- `launcher_runtime_from_udp.py` — production runtime (see §4.2).

All five scripts: **baud 921600**, background reader thread, `time.sleep(2)` after opening port (ESP32 DTR reset), `reset_input_buffer`, boot/MMMM/RPM filtering.

### 4.4 Firmware (control_12_full.ino)

**Baud**: 921600. **Limits**: `INPUT_PULLUP`, triggered on LOW. Pusher: DRV8825, enable HIGH=rest, LOW=move. Telemetry suppressed during pusher motion.

**Command parser** (exact token match on `cmd.toLowerCase()`):
- `set v h wl wr` — set angles + wheel RPMs (angles clamped ±30° in Python before send).
- `shoot` — requires both wheels ≥ 400 RPM.
- `reload` — RETRACTING → DISPENSING → IDLE (back-limit LOW or 10 s timeout).
- `stop`, `center`, `setzero`, `info`.
- Manual: `jv<n>`, `jh<n>`, `jf<n>`, `js<0-180>`.
- Live tuning: `jsset<v>`, `jfspeedset<v>`, `jfaccelset<v>`.

**State machine**:
```
IDLE ─reload→ RETRACTING ─back_LOW→ DISPENSING ─ball_LOW / 10s→ IDLE
IDLE ─shoot──→ SHOOTING (RPM≥400) ─pusher_fwd→ front_LOW → IDLE
```

---

## 5. Per-Script Reference

### 5.1 Calibration

#### `calibrate_intrinsics_charuco_garage.py`
- **Purpose**: intrinsic calibration via ChArUco.
- **Args**: `--images-dir`, `--out`, `--board-squares 10 7`, `--square-mm 29.7`, `--marker-mm 22.275`, `--dict DICT_5X5_50`, `--width 1280 --height 720`.
- **Flow**: load images → detect ChArUco corners (OpenCV ≥4.7 uses `aruco.CharucoDetector`, else legacy `interpolateCornersCharuco`) → `aruco.calibrateCameraCharuco` → write JSON with `camera_matrix`, `dist_coeffs`, `image_width/height`, `reprojection_error`.

#### `auto_capture_charuco_multi.py`
- Multi-camera synchronous capture GUI. Writes numbered PNG stacks per camera for offline intrinsic calibration.

#### `calibrate_intrinsics_from_images.py`
- Re-run intrinsic fit on pre-captured frames. Same math, no live capture.

#### `calibrate_extrinsics_apriltag_robust.py` (current)
- **Purpose**: per-camera world pose via AprilTag + robust PnP.
- **Dataclass**: `CameraData(name, image, intrinsics, object_points, image_points, tag_ids)`.
- **Functions**: `parse_dimensions`, `load_unified_intrinsics`, `collect_points_for_camera`, `robust_refine_pose(objp, imgp, K, D, sigma_scale=2.5, tag_median_thresh_px=45, max_iter=5)`.
- **Output**: `extrinsics_fixed.json` (per-cam `rvec`, `tvec` in meters, per-cam reproj error, expected vs actual position).

#### `calibrate_extrinsics_apriltag.py`, `…_oriented.py`
- Legacy and intermediate versions. Replaced by `_robust.py`.

#### `validate_extrinsics_overlay.py`
- Projects known tag corners into every camera image; draws residuals. Used to visually audit extrinsics.

#### `estimate_sync_offsets.py`
- Cross-correlates motion signals (ball position across cameras) to estimate per-camera timestamp skew.

### 5.2 Offline 3D Processing

#### `process_4cam_to_3d.py`
- **Purpose**: offline batch pipeline; replays recorded clips, runs detection + triangulation + EMA, writes 3D trajectories.
- **Args**: `--clips-dir`, `--intrinsics`, `--extrinsics`, `--dims`, `--out`, `--pose-backend`, `--ema-alpha`, `--ema-snap-threshold-mm`.
- **Functions**: reuses `triangulate_multi`, `ema_update`, pose backends. Outputs per-joint JSONL time series.

#### `record_short_clips_multi.py`
- 4-cam short clip recorder (pre-YOLO sanity tests).

#### `auto_record_joint_trials.py`
- Scripted joint-touch ground-truth recording (for `evaluate_pose_joint_touch_gt.py`).

### 5.3 Evaluation

#### `evaluate_ball_static_gt.py`
- **Purpose**: measure 3D accuracy at known ball positions.
- **Args**: `--gt-csv`, `--clips-dir`, `--intrinsics`, `--extrinsics`, `--dims`, `--out`.
- **Metrics**: mean, median, P95 Euclidean error per trial, systematic bias per axis, precision (std).
- **Result with arena_fixed**: mean 156.9 mm, P95 288.3 mm, bias X+60/Z-104, σ=3.09 mm.

#### `evaluate_pose_joint_touch_gt.py`
- Joint-touch variant (human touches labelled AprilTag corners).
- **Result**: mean 179.0 mm, P95 243.8 mm, bias X+83/Z-125, σ=4.39 mm.

#### `visualize_ball_tuning_session.py`, `visualize_joint_touch_session.py`
- 3D scatter of estimate vs GT per trial; used when tuning the correction model.

### 5.4 Live Viewers

#### `live_4cam_arena_view.py` (production)
- Matplotlib 3D arena view + 4 camera tiles. Triangulation, EMA, UDP broadcast. No Kalman, no ghost skeleton.

#### `Parallel_working/scripts/live_4cam_arena_view_parallel.py` (current recommended)
- See §4.1. Adds: YOLO-Pose backend, cv2 renderer, `JointKalmanFilter`, ghost skeleton, staleness gate, threaded capture, `--render-worker-process`, `--demo-blm` overlay.

### 5.5 BLM

#### `launcher_runtime_from_udp.py`
- See §4.2. Production launcher runtime.

#### `live_aim_test.py` (586 lines)
- Interactive single-shot tester. Reads UDP pose, prompts `aim <joint>`, then requires typed `yes` to fire.
- Class: `SerialReader` (background thread with filters).
- Flags: `--serial-port`, `--launcher-yaw-deg`, `--correction-mode`, `--shoot-enabled`, `--wheel-rpm`, `--log-jsonl`.

#### `blm_follow.py` (701 lines)
- Continuous follow mode.
- Classes: `SerialReader` (shared), `UDPJointListener`, `LineEditor` (raw-mode cbreak, manages echo + redraw), `CommandHandler` (reload / shoot / pause / resume / `<joint>` / quit).
- State dict: `armed`, `paused`, `busy`, `target_joint`, `last_ts`, `last_cmd_ts`, `last_angles`.
- Gates: deadband (`--min-delta-deg 0.5`), rate (`--min-interval-s 0.15`), staleness (`--max-staleness-s 1.0`), confidence min, cams min.
- Safety: with `--shoot-enabled`, starts `armed=False` — operator must type `reload` before any aim is sent. `shoot` sets `armed=False` after `SHOT FIRED`.

#### `blm_interactive.py`
- Raw serial REPL with filters (see §4.3). Useful for manual `info`, `jv500`, `jsset90`, etc.

#### `manual_aim_test.py`
- Non-interactive aim sweep: iterates pitches/yaws/RPMs for mechanical benchmarking.

#### `bridge_pose_to_launcher_ble.py`
- Legacy BLE bridge (now replaced by USB-serial path).

#### `version1.1.py`
- Legacy combined runtime. Kept for reference.

### 5.6 Performance / Parallel

#### `Parallel_working/scripts/export_models_tensorrt.py` (292 lines)
- Exports YOLO and YOLO-Pose `.pt` → TensorRT `.engine` (FP16).
- Flags: `--yolo-model`, `--yolopose-model`, `--export`, `--benchmark`, `--imgsz 1280`, `--device 0`.
- Benchmark: per-image latency mean/P95 vs `.pt` baseline.

#### `Parallel_working/scripts/record_test_sequence.py` (227 lines)
- Threaded 4-cam recorder for ablation. Saves frames + per-camera timestamps.
- Sequences: walk_01, jog_01, jump_01 (449 frames × 4 cameras each).

#### `Parallel_working/scripts/ablation_ema_adaptive.py` (412 lines)
- 3-phase pipeline: (1) cache poses per clip (backend-switchable), (2) triangulate, (3) sweep EMA variants (fixed α, adaptive snap, no EMA).
- Outputs `Parallel_working/output/ablation_results/` with per-variant jitter metrics.

#### `Parallel_working/scripts/validate_kalman_prediction.py` (430 lines)
- Replays recorded sequences; compares naive (current position held) vs Kalman-predicted at 200/400/600 ms horizons. Tuned PN=500, MN=10 → walk 47 % improvement.

### 5.7 Utilities

- `render_multiviews.py`, `render_arena_ball_skeleton.py`, `render_apriltag_arena_360.py` — offline renderers.
- `optimize_motion_capture.py` — experimental MoCap post-processing.

---

## 6. Safety and Operational Gates (summary)

- **Angle clamp** (Python): pitch [0°, 30°], yaw [−30°, 30°] — firmware reboots outside this.
- **RPM gate** (firmware): shoot rejected unless both wheels ≥ 400 RPM.
- **Zone gate** (Python): target 3D position inside GT-derived joint zone.
- **Confidence gate**: `n_cams ≥ 3` and `confidence ≥ 0.45`.
- **Stability gate**: sliding window std ≤ threshold.
- **Armed state** (blm_follow): must type `reload` before aim is sent when shooting is enabled.
- **ESTOP**: instant `stop`, latched until `clear`; link loss (UDP or serial timeout) → auto stop.
- **Output filtering** (all serial readers): ESP32 boot lines, baud-garbage (`MMMM…`), RPM telemetry, consecutive duplicates.

---

## 7. Current Status (2026-04-13)

- **Calibration**: arena_fixed extrinsics locked; systematic bias X+83/Z-125 mm known, correctable via linear model.
- **3D accuracy**: precision 4.4 mm (excellent), residual bias correctable.
- **Prediction**: Kalman PN=500/MN=10/400 ms horizon — 47 % walk, 34-39 % jog.
- **Inference**: YOLO-Pose TRT 6.2 ms; matches MMPose 3D accuracy within 5 mm jitter.
- **BLM**: S0-S4 + integrated live test PASSED (2026-04-09); controlled fire under operator supervision authorized.
- **Next**: (1) ball-speed calibration RPM→m/s curve, (2) training automation with voice trigger.
