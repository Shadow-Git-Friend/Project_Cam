# Performance Rules

## Scope
- All FPS/perf work is isolated in `Parallel_working/`
- Never modify `garage_lab_combined/scripts/` for performance without approval

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

## Known Issues
- maxfps at 960x540 causes skeleton placement errors
- matplotlib 3D rendering is the main bottleneck — render-worker-process helps
- Threaded capture + staleness gate improves freshness but not raw throughput
- Kalman prediction is ~neutral on jump motion (CV model limitation) — do not tune to it
