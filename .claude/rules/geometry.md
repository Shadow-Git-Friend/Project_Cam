# Geometry Rules

## Coordinate Frame
- World frame: mm units, origin at arena corner
- X: arena length, Y: arena width, Z: vertical (up)
- East side is Y~0, West side is Y~Ymax (validated in arena_fixed)

## Invariants
- Never silently flip or mirror any axis
- `--no-world-y-mirror` is the production default; `--world-y-mirror` is debug-only
- `--invert-y-axis-display` affects ONLY 3D plot labels, not triangulation or UDP
- Any axis change must be verified against known AprilTag positions

## Intrinsics-Resolution Coupling
- Intrinsics are calibrated at 1280x720
- Running at different resolution REQUIRES scaling K matrix (fx, fy, cx, cy)
- The parallel script has auto-scaling; verify it is active for any new resolution
- 960x540 maxfps profile caused skeleton drift — confirmed issue

## Protected Functions (do not modify without approval)
- `triangulate_multi()` — SVD-based multi-view triangulation
- `transform_world_point_y()` — Y-axis transform for display
- `ema_update()` — exponential moving average for smoothing
- UDP payload construction — axis order must match launcher expectations

## Single-camera fallback (2026-04-20, opt-in)
- `project_ray_to_z_plane(obs_norm, R, tvec, target_z)` in `Parallel_working/scripts/live_4cam_arena_view_parallel.py` — intersects one undistorted camera ray with a world Z-plane. Used only for ball tracking when <2 cams see it and `--ball-single-cam-fallback` is set. Pure geometry (`X_w = R^T (X_c − t)` with `X_c = s·[u,v,1]`), no iteration.
- Does NOT replace `triangulate_multi`. Multi-cam path is unchanged.
- Uses KF-predicted Z when available; falls back to `--ball-single-cam-floor-mm` (default 0) on cold start. Capped by `--ball-single-cam-max-frames` (default 15) to prevent depth runaway without geometric constraint.
- Never apply this to pose/joint triangulation — joints have no floor-plane prior.
