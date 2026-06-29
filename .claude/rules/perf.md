# Performance Rules

## Scope
- All FPS/perf work is isolated in `Parallel_working/`
- Never modify `garage_lab_combined/scripts/` for performance without approval

## Latest-frame capture fix (2026-06-23, CRITICAL for multi-cam responsiveness)
- `ThreadedCapture.read_latest()` now returns each camera's MOST RECENT frame every call (returns `(ret, frame, ts, is_new)`); staleness is gated by the caller via `--max-frame-age-ms`. The main loop additionally `continue`s when no camera is new (`any_new_frame`), so pose isn't re-run on identical frames.
- Why: the old version returned a frame only if brand-new+unconsumed, so a multi-cam batch needed >=2 async cameras to deliver within the SAME loop iteration. Rare at low fps -> with 6 USB cameras the 3D skeleton updated ~1 Hz even though the renderer showed 40 FPS. The displayed FPS is now the real skeleton update rate (whenever ANY camera refreshes, ~aggregate fps). At 4 cams/15 fps the old code coincided often, which is why it felt instant before.

## Cinematic 3D renderer (2026-06-23, cv2 backend, display-only)
- `--render-theme cinematic` (DEFAULT) | `classic`. Cinematic = dark gradient stage, 1 m floor grid, dim arena/tag wireframe, floor shadow of the skeleton, glowing depth-shaded skeleton colour-coded by body side (orange=left, cyan=right, mint=head, white=torso), white joint cores sized by camera depth, and a top "● LIVE · MULTI-VIEW 3D POSE · <Hz> · <N> cams" HUD. `classic` = the old flat light-grey look.
- Motion trails for wrists+ankles (joints 9,10,15,16) reuse `--trail-len` (default 20). `--auto-orbit [--auto-orbit-speed deg/s]` slowly rotates the view for demos (off by default).
- All additions are inside `draw_live_scene_cv2` + a trail deque + orbit azimuth in the main loop. They do NOT touch `triangulate_multi`, `transform_world_point_y`, `ema_update`, or UDP. Palette/side constants: `LEFT_JOINTS/RIGHT_JOINTS/COL_* /_bone_color/_shade` near `CONNECTIONS`.

## Demo / startup feature set (2026-06-23, all display-only, cv2 backend)
- **One-Euro display filter** (`--display-filter oneeuro` DEFAULT | `ema`): `OneEuroVec` class, one per joint, applied at the joints_state->joints_display stage. Low lag on fast motion, smooth when still — strictly better than the fixed EMA lerp for live display. Tunables `--oneeuro-mincutoff` (1.2), `--oneeuro-beta` (0.3). Does NOT touch `ema_update` (which still smooths joints_state upstream).
- **Velocity heat-colouring** (`--limb-heat`): bones/joints coloured blue->red by per-joint speed (mm/s) via `_heat_color`; `--heat-vmax-mm-s` (2500) sets the hot end. Speed is computed from joints_state frame-deltas in the display block (`joint_speeds`), independent of the Kalman filters.
- **Live metrics HUD** (`--metrics-hud`, default on): height (joint z-extent), reach (wrist-to-wrist span), peak joint speed. Bottom-left panel in cinematic.
- **Squat + push-up rep counters** (`--count-reps`, on in both usb6 launchers): reuses the coach `make_counter`/`frame_kinematics`/`rep_state` (src/project_cam/assessment) but runs lightweight (no separate coach window), updated each frame from `joints_state`, shown in the ATHLETE panel (Squats / Push-ups). BOTH run simultaneously — do squats and the squat line ticks, push-ups and the push-up line ticks. Press **`c`** in the window to reset. Less rigorous than the full `--coach-overlay` window (no ROI/leg-prior cleanup) but good for live demos.
- **2D camera thumbnails** (`--show-thumbnails`): live per-cam feeds inset down the right edge — shows the multi-view behind the 3D.
- **MP4 record** of the 3D view: press `r` in the window to start/stop; writes `--record-dir/arena_demo_<ts>.mp4` (mp4v). Released cleanly on exit. Separate from `run_record_3d.sh`'s always-on `video_writer_3d`.
- Multi-person is NOT implemented (needs cross-view identity association — a real architectural change, deferred).

## BLM / ball-launcher live connection (2026-06-23)
- `Parallel_working/run_live_usb6_blm.sh` = cinematic 6-USB viewer + UDP target broadcast (127.0.0.1:5005) + `--demo-blm` aim overlay. The VIEWER NEVER actuates the launcher; it only triangulates + broadcasts the chosen joint + draws where the BLM would aim. Actuation is only ever via `garage_lab_combined/scripts/live_aim_test.py` in Terminal 2.
- **Geometry caveat (must validate before firing):** the 6-USB rig triangulates in the Y-MIRRORED frame and the launcher runs `--world-y-mirror` (so UDP is mirrored too). BLM aim was previously validated only on the canonical 4-cam frame. Do an aim-only S2 test first (`live_aim_test.py --no-shoot-enabled`): aim at a joint and confirm the launcher physically points at the person. If it points to the mirrored side, toggle `--udp-y-mirror/--no-udp-y-mirror` on the viewer. Only after aim is correct + RPM gate (S3) re-checked may `--shoot-enabled` be used (S4), per `.claude/rules/safety.md`.
- Set the real BLM mount position via `BLM_X_MM/BLM_Y_MM/BLM_Z_MM` env vars (mirrored-frame mm); the overlay default is a placeholder.

## Robust per-joint pose triangulation (2026-06-23)
- `robust_triangulate_joint(...)` (`--pose-max-reproj-px`, default 40) rejects outlier camera rays per joint, mirroring `robust_triangulate_ball`. Stops a bad camera pose / transient 2D mis-detection from flinging a joint to a random point. See `.claude/rules/geometry.md`.

## Profiles (Parallel_working/)
- quality: baseline behavior, no forced optimizations
- balanced: best current skeleton placement + moderate speedup
- smooth: 30fps capture, EMA 0.40, stale-frames 12, render-worker-process
- smooth_v2: cv2 renderer, adaptive EMA, display interpolation (~2ms 3D render)
- predictive: smooth_v2 + Kalman filter prediction + ghost skeleton (RECOMMENDED)
- maxfps: 960x540 + aggressive skip — KNOWN to cause skeleton drift

## Rules
- Never trade geometric correctness for FPS without explicit approval
- Resolution changes require intrinsics scaling verification
- `--render-worker-process` is safe (offloads matplotlib to child process)
- `--max-frame-age-ms` is safe (drops stale frames, does not alter geometry)
- `--pose-every N` / `--ball-every N` / `--viz-every N` are safe skip params
- Monitor perf with `--perf-log-every` and `--perf-jsonl` flags

## Kalman Prediction
- `--predict-ahead-ms` controls prediction horizon (0 = disabled, 400 = recommended)
- `--kalman-process-noise` and `--kalman-measurement-noise` tune filter responsiveness
- `--show-ghost-skeleton` renders predicted position as translucent skeleton in cv2 view
- `--predict-max-uncertainty-mm` discards predictions with too much uncertainty
- Kalman filter is geometry-safe: operates on post-triangulation 3D points only
- UDP packets include both `joints` (current) and `predicted` (future) when active

## YOLO-Pose Backend
- `--pose-backend yolopose` — YOLO11m-Pose, single-model (no separate detector)
- `--yolopose-model yolo11m-pose.pt` or `.engine` for TRT
- 3.6x faster offline (25 vs 7 fps for 4-cam sequential), 6.2x faster live with TRT
- Matches MMPose 3D accuracy within 5mm jitter — validated 2026-04-06 ablation
- Slightly lower detection rate on oblique views (94% vs 100%) — acceptable trade-off

## Evaluation Tools
- `record_test_sequence.py` — threaded 4-cam recording, saves frames + timestamps
- `ablation_ema_adaptive.py` — 3-phase (cache poses → triangulate → sweep EMA variants)
- Both support `--pose-backend yolopose|mmpose`
- Results in `Parallel_working/output/ablation_results/`

## BLM-Integrated Live Run
- `Parallel_working/run_live_blm.sh` combines live yolopose viewer + Kalman prediction + UDP target broadcast + `--demo-blm` overlay
- Pair with `garage_lab_combined/scripts/live_aim_test.py` in Terminal 2 for interactive aiming
- UDP target joints (13): nose, shoulders, elbows, wrists, hips, knees, ankles
- Default Kalman: PN=500, MN=10, predict-ahead 400ms (best for walk/jog)
- This run script lives in `Parallel_working/` but its serial counterpart in `garage_lab_combined/` is the only path that touches BLM hardware

## TensorRT Export (mandatory)
- Always export YOLO engines with `dynamic=True, batch=4` — `export_models_tensorrt.py` already patched
- Static batch=1 engines segfault (ball) or silently fail (pose) when viewer passes 4-frame batch
- ONNX input `[1, 3, H, W]` = broken; `['batch', 3, 'height', 'width']` = correct
- After any `.pt` swap, rebuild the `.engine` from scratch (delete old `.onnx` + `.engine` first)

## Ball Tracking Robustness (2026-04-13, extended 2026-04-20)
- Live viewer uses `robust_triangulate_ball`: iteratively rejects cameras with reprojection error > `--ball-max-reproj-px` (default 25 px as of 2026-04-17)
- Dedicated ball `JointKalmanFilter` (CV model): defaults `--ball-kalman-process-noise 800 --ball-kalman-measurement-noise 25`
- Max-speed gate: `--ball-max-speed-mps 40` discards physically impossible jumps
- Coast-through-drop: `--ball-coast-frames 6` lets KF predict during brief detection failures (~400 ms at 15 FPS)
- Replaces naive ball EMA. Do not reintroduce `ema_update(ball_state, ...)` — the KF owns ball smoothing now
- Tune reproj threshold down if false positives persist, up if edge-of-frame balls get dropped

### Ball Detection Levers (2026-04-20, measured on real bounce/fast/slow recordings)
- `--ball-imgsz` (default 672) — engine exported with `dynamic=True` so inference-time resize works. **Bumping to 960 moves camNorth bounce detection from 58% → 98%.** +8 ms per 4-cam batch, fits 15 FPS budget.
- `--ball-conf` (default 0.40) — lowering to 0.15 recovers +4–6 pp detection rate on fast/bounce but adds false-positive risk on empty frames. Consider 0.25 as conservative middle ground.
- Motion-blur streak presence: real (aspect > 1.5 seen at low conf on fast/bounce). Fixing via top-K + multi-hypothesis association is Tier 2 (requires regression fixtures).
- **Structural bounce limit:** at bounce moment only camNorth reliably sees the ball (other 3 cams are 10–17% regardless of detector tuning). No threshold/model change fixes it — the ball is genuinely outside East/South/West frustums or occluded. The fix is the single-cam fallback (below) or camera-placement changes (hardware).

### Single-camera fallback (2026-04-20)
- `project_ray_to_z_plane(obs_norm, R, tvec, target_z)` — new helper in `live_4cam_arena_view_parallel.py`. Intersects one camera's undistorted ray with a world Z-plane. Pure geometry, no iteration.
- Flag-guarded, off by default:
  - `--ball-single-cam-fallback` — enable
  - `--ball-single-cam-max-frames 15` — cap before forcing coast-through (prevents KF depth drift without geometric constraint)
  - `--ball-single-cam-floor-mm 0.0` — cold-start Z-plane if KF has no depth yet
- When ≥2 cams: unchanged SVD path (`robust_triangulate_ball`). When exactly 1 cam + flag on + within max-frames: ray→Z-plane; Z taken from `ball_kf.predict_ahead(1/fps)`, else floor. When 0 cams: unchanged coast-through.
- Does **not** modify `triangulate_multi`, `transform_world_point_y`, `ema_update`, or UDP schema.
- Recommended live flags for bounce-heavy sessions: `--ball-imgsz 960 --ball-single-cam-fallback`.

### Candidate selection gates (2026-04-21)
- `--ball-max-box-side-px 220` (default on) — rejects any YOLO candidate whose larger bbox side exceeds 220 px. Primary defense against "person curled around ball" being labelled as a ball. A tennis ball at arena distance is <~120 px; 220 keeps close-range legit detections, rejects body/cone-sized blobs.
- `--ball-min-box-side-px 0` (default off) — lower bound on bbox side; enable (e.g. 6) to filter detector-noise micro-boxes.
- `--ball-kf-gate-px 150` (default on) — when the ball KF is locked, per-cam selection prefers the candidate whose center is within 150 px of the KF-predicted reprojection. Falls back to highest-conf candidate if no candidate is within gate (so re-acquisitions after long drops still work). Primary defense against markers/cones/bodies when the real ball is currently being tracked.
- Both gates operate on raw YOLO candidates *before* `robust_triangulate_ball`. They only filter the per-cam "winner" choice; they do not change triangulation, KF dynamics, or UDP schema.
- Enabling `--ball-kf-gate-px` makes it safe to lower `--ball-conf` 0.40 → 0.25 (the gate filters the extra noise).
- Set either gate to `0` to disable. Use `0 0 0` trio to A/B test old selection behavior: `--ball-max-box-side-px 0 --ball-min-box-side-px 0 --ball-kf-gate-px 0`.

### Offline diagnosis tool
- `Parallel_working/scripts/ball_detection_analyzer.py` — read-only sweep of conf thresholds + top-K over a sequence. Accepts either per-cam frame directories (`--sequence`) or `mosaic2d_*.mp4` 2×2 tiled videos (`--mosaic`). Reports per-cam detection rate, multi-box frequency, bbox aspect ratio histogram, and recovered-vs-0.40 delta.

## Recording (run_record_3d.sh)
- Writes `Parallel_working/output/recordings/arena3d_<ts>.mp4` + `mosaic2d_<ts>.mp4`
- Uses `mp4v` fourcc — MP4s only playable after clean `VideoWriter.release()`
- SIGTERM/SIGINT handler in `live_4cam_arena_view_parallel.py` breaks the loop cleanly so moov atom is written
- Never stop recording with `timeout`/`kill -9` — resulting MP4 is unrecoverable (no moov atom, ffmpeg cannot remux)
- Stop with `q` in the cv2 window or a single Ctrl+C

## Camera hardware upgrade path (2026-05-29)
- **PC (HP Z4 G4, measured):** i9-7900X 10C/20T (44 PCIe3 lanes), 32 GB RAM, RTX 2080 Ti 11 GB (inference) + Quadro P400 2 GB (display), Ubuntu 22.04/k6.8, single 238 GB SATA SSD (60 GB free). The PC is NOT the bottleneck for a 4× global-shutter @ 60 fps upgrade — CPU/RAM/GPU/PCIe all have large headroom (GigE even *drops* CPU vs MJPG decode). Only TWO additions needed: a **NIC** and (for raw recording) an **NVMe SSD**.
- **Plan:** replace all 4 webcams with **4× global-shutter GigE cameras** (HikRobot MV-CS016-10GC IMX296 ~65 fps, or FLIR BFS-PGE-16S2C-CS IMX273 78 fps) + hardware trigger from ESP32. Count stays 4 (1:1; never mix shutter types). Connection = **Intel I350-T4 quad-port GigE NIC** (one dedicated lane/cam), power + trigger via each cam's Hirose I/O cable (12 V + ESP32 opto fan-out), skip PoE. Raw 60 fps record = 373 MB/s → add **2 TB NVMe** (board M.2). Lenses ~3.5–4 mm (NOT 6 mm — too narrow vs current ~81–86° HFOV).
- **Do NOT "just add 4 more DS-E12 webcams" to get 8.** Helps pose coverage only IF split across USB controllers (all 4 current ones share one Bus-001 USB-2 controller → ~15 fps ceiling; 8 on one controller = bandwidth failure). It does NOT fix the goal/fast-ball blocker: rolling shutter stays and **no-sync gets worse** (more unsynced views of a moving ball). Also halves inference fps (8-cam batches) and doubles calibration burden. USB-2 webcams don't scale; GigE does.
- The global-shutter + hardware-sync upgrade is orthogonal to the (free) goal-game software fix — buy fixes fast-ball tracking, software fix makes scoring work. See `.claude/rules/geometry.md` triangulation-pairing + camSouth notes.

## Known Issues
- maxfps at 960x540 causes skeleton placement errors
- matplotlib 3D rendering is the main bottleneck — render-worker-process helps
- Threaded capture + staleness gate improves freshness but not raw throughput
- Kalman prediction is ~neutral on jump motion (CV model limitation) — do not tune to it
