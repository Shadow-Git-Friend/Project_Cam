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
