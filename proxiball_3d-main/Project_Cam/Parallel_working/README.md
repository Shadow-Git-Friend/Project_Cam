# Parallel_working

Isolated workspace for FPS/performance experiments on the live 4-cam viewer.

## Safety constraints
- This folder is intentionally separate from `garage_lab_combined/` and `arena_fixed/` runtime code.
- Only files under `Parallel_working/` are modified for this track.
- Geometry-critical math must stay unchanged:
  - `triangulate_multi`
  - `transform_world_point_y`
  - `ema_update`
  - UDP payload axis semantics

## Main script
- `Parallel_working/scripts/live_4cam_arena_view_parallel.py`

This script is a parallel copy with performance-focused additions:
- Perf instrumentation
  - `--perf-log-every`
  - `--perf-jsonl`
  - Stage timings: `capture, ball, pose, triang, udp, viz3d, mosaic, total`
  - Extra metrics: `end_to_end_ms`, `frame_age_ms_per_cam`, `dropped_frames_per_cam`, `queue_depth`
- Threaded capture + staleness gate
  - latest-frame policy per camera
  - `--max-frame-age-ms` to drop stale frames before triangulation
- Optional 3D render worker process
  - `--render-worker-process`
  - Matplotlib runs in child process (Queue maxsize=1, drop-old snapshots)
- Scoped hot-path cleanup
  - batched undistortion helper for joint keypoints
  - reduced avoidable copies in mosaic rendering
- Intrinsics scaling fix for non-1280x720 runtime
  - camera intrinsics are automatically scaled when `--width/--height` differs from calibration size
  - this prevents 3D placement drift in lower-resolution modes

## Run helpers
- Quality baseline (keeps baseline behavior, no forced worker):
  - `Parallel_working/run_live_parallel_quality.sh`
- Balanced profile (safer speedup):
  - `Parallel_working/run_live_parallel_balanced.sh`
- Smooth profile (best current compromise for skeleton + ball):
  - `Parallel_working/run_live_parallel_smooth.sh`
  - keeps geometry-safe runtime resolution (`1280x720`) to avoid 3D placement drift
- Max-FPS profile (aggressive):
  - `Parallel_working/run_live_parallel_maxfps.sh`

All wrappers accept extra flags via `"$@"`.

## Example
```bash
cd /home/hanush/Desktop/Project_Cam
./Parallel_working/run_live_parallel_balanced.sh
```

If needed, add overrides, e.g.:
```bash
./Parallel_working/run_live_parallel_balanced.sh --no-render-worker-process --perf-log-every 30
```
