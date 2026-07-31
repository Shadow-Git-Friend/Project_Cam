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

## Display-only layers must stay display-only (2026-07-17)
- The skeletal-rigidity bone clamp (`project_cam.viz.skeleton_stabilize`) and the rigid latency lead (`compute_display_leads`) operate exclusively on the render buffer (`joints_display`). They must NEVER be applied to `joints_state`, the UDP payload, drill scoring, or the firing-line safety snapshot — clamping state would alter safety-corridor inputs (safety.md territory). The BLM demo overlay reads `joints_state` for the same reason: the drawn aim must match what the launcher actually receives.

## Single-camera fallback (2026-04-20, opt-in)
- `project_ray_to_z_plane(obs_norm, R, tvec, target_z)` in `Parallel_working/scripts/live_4cam_arena_view_parallel.py` — intersects one undistorted camera ray with a world Z-plane. Used only for ball tracking when <2 cams see it and `--ball-single-cam-fallback` is set. Pure geometry (`X_w = R^T (X_c − t)` with `X_c = s·[u,v,1]`), no iteration.
- Does NOT replace `triangulate_multi`. Multi-cam path is unchanged.
- Uses KF-predicted Z when available; falls back to `--ball-single-cam-floor-mm` (default 0) on cold start. Capped by `--ball-single-cam-max-frames` (default 15) to prevent depth runaway without geometric constraint.
- Never apply this to pose/joint triangulation — joints have no floor-plane prior.

## Geometric L/R pair split (2026-07-16, single-leg stance fix)
- `split_merged_lr_pair(...)` + `rename_crossed_lr_pair(...)` in `live_4cam_arena_view_parallel.py`. When per-camera left/right labels are MIXED, triangulating each label separately does not necessarily merge the pair in 3D — verified on a synthetic 4-cam rig: a symmetric 2v2 mirror lands BOTH ankles at mid-height with lateral separation intact ("lift one leg → the second rises too"). Therefore the live trigger is **residual-based** (`--pose-lr-split-trigger-px 12`, mean ray residual over pair cams) OR merge-based (`--pose-lr-split-merge-mm 100`), not distance-only.
- The split treats each camera's two detections as an unordered pair: enumerates per-camera label flips (reference cam fixed, ≤6 cams → ≤32 hypotheses, ~5.6 ms worst case, trigger-frames only), scores each by mean normalized-ray residual, re-triangulates the winner through `robust_triangulate_joint`, and names the two clusters by temporal continuity → parent anchors (knees for ankles, hips for knees) → reference-cam labels. Declines when the best split stays under 100 mm separation (feet genuinely together are not an error).
- `rename_crossed_lr_pair` fixes the complementary case: ALL cams consistently label-swapped → clean geometry, exchanged names; swaps back only on a CLEAR (margin 0.5) crossed match vs the previous separated state, so genuine leg crossings (which pass through proximity) are never fought.
- **Anti-churn (2026-07-17):** a non-zero label-flip hypothesis wins only if its residual beats the label-trusting (mask 0) hypothesis by `flip_margin=0.8` — near-tie winners alternated between frames and churned the legs at the update rate. Genuine mixed-label frames beat mask 0 by a wide gap, so recovery is unaffected (all 8 split tests green).
- **Chain relabel guards (2026-07-17, `fix_lr_swaps_for_cam`):** every swap verdict now also needs an ABSOLUTE advantage `(direct - cross) > min_advantage_px (6.0) * n_pairs` — a near-coincident pair (eyes ~10 px apart) could clear the 0.75 ratio on 2-3 px of keypoint noise and mirror its whole chain. The whole-body verdict additionally counts only pairs with reprojected L/R separation ≥ `wholebody_min_sep_px (15.0)` (≥2 required): face noise must never flip well-separated unmeasured limbs. Real mirrored cameras produce advantages of hundreds of px, far above both floors.
- **The chain verdict binds ONLY ambiguous pairs (corrected 2026-07-29).** A pair whose own evidence is conclusive decides for itself; the summed chain verdict applies solely to pairs that cannot tell (coincident reprojections → `direct == cross`). A single summed vote per chain was wrong in both directions and it reached `joints_state`, not just the display: a mirrored wrist pair was outvoted by correct shoulders/elbows and triangulated onto the opposite arm (~1.36 m), and a mirrored elbow+wrist majority dragged the correct shoulders with it. The arms chain has NO `--pose-lr-split` backstop (that guards knees/ankles only), so nothing downstream recovered it. See perf.md "Left/right relabeling" for the numbers.
- Applied to knees first, then ankles (fresh knees anchor the ankles). Calls `triangulate_multi`; does NOT modify it. Flags: `--pose-lr-split` (default on) / `--pose-lr-split-{merge-mm,min-sep-px,trigger-px}`. Tests: `tests/test_pose_lr_split.py` (mid-height artifact control, 2-mirrored and 3-of-6-mirrored recovery, reference-cam-mirrored renaming, anchor naming with merged prev, feet-together decline).

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

## We have no end-to-end pose ground truth (stated plainly, 2026-07-30)
- Every accuracy figure in this project is either reconstruction **repeatability** (ball static precision 3.09 mm, joint-touch precision 4.39 mm) or a **static-target** GT comparison with a known systematic bias (X+83 / Z-125 mm). There is **no ground truth for a moving human skeleton**, so no measured end-to-end joint error exists for the live chain (chain L/R relabel → `--pose-lr-split` → robust per-joint triangulation → EMA → bone clamp → rigid lead).
- Consequence for review work: every test in that chain is a hand-built synthetic rig or a characterisation of our own current output. That is enough to catch regressions, not enough to state an accuracy number. **Never quote 4.4 mm as pose accuracy** — it is precision on a static touch, and it is already a documented misuse to avoid in the pilot design.
- The harness to close this already exists in-repo and needs only a GT motion source: `fix_lr_swaps_for_cam` reprojects 3D joints into every camera, `split_merged_lr_pair` scores mean normalised-ray residuals, and the intrinsics/extrinsics loaders are shared. Feed known 3D joints → synthesise per-camera 2D through the real calibration → inject keypoint noise, mirrored labels and camera dropout → run the production chain → measure mm error against truth.
- Candidate GT motion source assessed 2026-07-30: **ARDY** (`github.com/nv-tlabs/ardy`) emits world-space `posed_joints [T, J, 3]` + rotations + foot contacts, code Apache-2.0 and weights NVIDIA Open Model (commercial-permitting), with no SMPL dependency. Unproven prerequisites: COCO-17 mapping of its Core skeleton (joint count unpublished) and whether it runs in 11 GB with prompt embeddings precomputed. Synthetic motion validates **our pipeline**, never biomechanics.

## Camera-network auto-calibration (AutoMagicCalib, evaluated 2026-07-30 — not adopted)
- NVIDIA **AutoMagicCalib** (DeepStream 9.1 skills) recovers extrinsics from video of people walking, given a layout image and ≥4 manual landmark clicks; pipeline is trajectory extraction → single-view calibration/rectification → multi-view tracklet matching → bundle adjustment. The blog publishes **no accuracy numbers**, so treat every claim as unverified.
- **Not for the garage.** Our charuco calibration is healthy and better-characterised than anything an unquantified pipeline offers: intrinsics RMS 1.0-1.3 px at runtime resolution, extrinsics RMSE 2.8-3.4 px, in a 6.2 m room where a board spans the space easily.
- **Where it matters:** academy-field deployment after the GigE upgrade, where a charuco board cannot span a full pitch and re-calibration must be doable by a coach. Bake-off protocol when that time comes: run it on recorded sequences alongside our charuco bundle and compare against the SAME gate we already use for calibration health — static-ball triangulation reprojection **< 25 px** (workflow.md Phase 0) plus recovered camera positions against measured mount positions. Do not swap calibration on the strength of an easier workflow.
- Any camera-network recalibration, by whatever method, still obeys the existing rule: regenerate intrinsics at runtime resolution → extrinsics → projector homography, then pass the static-ball gate before trusting geometry.
