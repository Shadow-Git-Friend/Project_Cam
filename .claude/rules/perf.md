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

## Known Issues
- maxfps at 960x540 causes skeleton placement errors
- matplotlib 3D rendering is the main bottleneck — render-worker-process helps
- Threaded capture + staleness gate improves freshness but not raw throughput
