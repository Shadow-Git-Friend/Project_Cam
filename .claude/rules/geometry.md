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

## Robust per-joint pose triangulation (2026-06-19)
- `robust_triangulate_joint(obs_norm, obs_px, proj_mats, extr, intr, min_cams=2, max_reproj_px=40)` in `Parallel_working/scripts/live_4cam_arena_view_parallel.py` — iteratively rejects the worst-reprojection camera ray per joint until all remaining rays agree within `--pose-max-reproj-px` (default 40 px), then triangulates. Mirrors `robust_triangulate_ball`; does NOT modify `triangulate_multi`.
- Why: the pose joint loop previously called bare `triangulate_multi` with no rejection, so ONE bad camera pose (e.g. camUsb02 ~190 px RMSE) or a transient 2D keypoint mis-detection flung that joint to a random 3D point (long spike line + apparent "lag"). Verified: plain triangulation with one bad ray → 708 mm error; robust → rejects the bad cam, 0 mm.
- `--pose-max-reproj-px 0` disables it (old plain behavior). Lower if fliers persist; raise if valid far joints get dropped (a dropped joint holds its previous value via EMA — it never flings).

## Triangulation input pairing (CRITICAL — verified 2026-05-29)
- `triangulate_multi` / `robust_triangulate_ball` expect **normalized undistorted** observations (`cv2.undistortPoints` output) paired with the **bare extrinsic** projection `extr[cam]["P"] = [R|t]` — **NO K**. The canonical viewer does this correctly: `proj = {cam: extr[cam]["P"]}` at `live_4cam_arena_view_parallel.py` + `ball_obs[cam] = undistort_points(...)`.
- **Bug found & to-fix:** `proxiball_3d-main/projector/goal_target_game_multicam.py` builds `proj_mats[cam] = K @ e["P"]` (pixel-space) but feeds normalized obs → DLT scale mismatch → garbage triangulation (~1400 px reproj; one pair ~48,600 px). Proven on the real `Remounted_West_East/` files: correct pairing → 0 px, buggy pairing → 3369 mm error. Fix = `proj_mats[cam] = e["P"]`. If you ever pass pixel obs instead, the matching projection is `K @ [R|t]`. Never mix.
- **The current `Remounted_West_East/` calibration is HEALTHY**, not broken: intrinsics calibrated at runtime res 1920×1080 (RMS 1.0–1.3 px), extrinsics RMSE 2.8–3.4 px, `scale_intrinsics_matrix` correctly applied (no-op since src==dst). The "geometry never agrees" telemetry was the proj_mats bug, NOT bad calibration. The stale `camera_position_error_m` 1.67/1.79 m on camEast/West is just the old high-mount `expected_camera_position` field; recovered positions match the low remount.

## camSouth wall-mapping degeneracy (2026-05-29)
- camSouth (recovered X=6246 mm) is ~coplanar with the south wall plane (X=6230). For per-cam ray→wall-plane projection (`SouthWallMapper.pixel_to_wall`) every pixel collapses to ≈ the camera's own (Y≈1598, Z≈2256) → above the grid → 0% in-grid. This is **degeneracy, not "wall behind camera / t<0"** (the code's `depth_sign` handles sign).
- Fix = **exclude camSouth from wall-zone voting only**. Do NOT move it physically (user decision). camSouth stays VALUABLE for 3D triangulation (strong baseline, sees ball's final approach) — the right goal-scoring method is 3D triangulation + X=6230 plane crossing, not per-cam wall projection.
- Real camera FOV (from K): HFOV ≈ 81–86°, VFOV ≈ 52–56° at 1920×1080. Any frustum/coverage tool must derive FOV from K, not assume ~50°.
