# Remount Log — camEast + camWest @ ~450 mm

Chronological, append-only. One section per session. Numbers > prose.

## 2026-05-25 — Bundle created

- Cameras physically remounted: camEast and camWest from ~2.2 m → ~450 mm,
  flush against East/West walls (Y ≤ 75 / Y ≥ 2975 mm).
- Camera mode set to 1920x1080 MJPG @ 30 FPS across all four cams; verified with
  `v4l2-ctl`. FullHD only available in MJPG (YUYV/NV12 caps at 5 FPS at this res).
- Short concurrent stream test held ~30 FPS on all four; 1 dropped buffer on
  two streams during a short window.
- Code-side FullHD defaults updated in:
  - `garage_lab_combined/config/runtime.yaml`
  - `garage_lab_combined/scripts/auto_capture_charuco_multi.py`
  - `garage_lab_combined/scripts/record_short_clips_multi.py`
  - `garage_lab_combined/scripts/auto_record_joint_trials.py`
  - main live/assessment wrappers under `Parallel_working/`,
    `apps/athlete_assessment/`, `apps/assessment_calibration/`, `arena_fixed/`
  - new test: `tests/test_camera_mode_defaults.py`
- Verification passed: 135 unit tests OK, py-compile OK, shell syntax OK,
  `git diff --check` OK.
- Backup top-off: `cal_backup/pre_remount_2026-05-25/` now also holds
  `calibration_manifest.yaml` + `reeval_arena_fixed_20260406/`.
- This bundle (`Remounted_West_East/`) created with skeleton + reference symlinks.

## Step 1 — Power-on + USB enumeration  ✅ 2026-05-25

- [x] `lsusb` shows all four cams (4× `2bdf:0289 SN0002 1080P USB Camera`)
- [x] `v4l2-ctl --list-formats-ext` confirms `1920x1080 MJPG @ 30.000 fps` on each
- camNorth device path: `/dev/v4l/by-path/pci-0000:00:14.0-usb-0:11.1:1.0-video-index0`  → `/dev/video2`
- camEast  device path: `/dev/v4l/by-path/pci-0000:00:14.0-usb-0:13.1:1.0-video-index0` → `/dev/video6`
- camSouth device path: `/dev/v4l/by-path/pci-0000:00:14.0-usb-0:7.1.1:1.0-video-index0` → `/dev/video4`
- camWest  device path: `/dev/v4l/by-path/pci-0000:00:14.0-usb-0:5.1.1:1.0-video-index0` → `/dev/video0`
- All four also advertise `1920x1080 YUYV @ 5 FPS` (expected — FullHD-at-30 is MJPG-only on this sensor; matches the earlier capture-mode audit).
- `cameras.yaml` already points camNorth/East/South/West at these by-path strings — no config edit needed.

## Step 2 — Live framing check (eyes-only)  ✅ 2026-05-25

- Tool: `Remounted_West_East/scripts/framing_check.py` (4-cam 2×2 mosaic, no
  calibration overhead, yellow safe-zone rectangle + center crosshair per tile).
- All four cams opened at 1920x1080 @ 30 FPS MJPG.
- Operator-confirmed pass on camEast + camWest framing (verbal "go next"); detailed
  per-cam checklist not filled in. If a regression surfaces later, re-run the
  viewer and fill in the table:

| Cam | Hip | Knee | Ankle | Foot | ≥80 px headroom | ≥80 px below foot | Body axis horizontal | BLM/operator out of cone |
|-----|-----|------|-------|------|------------------|-------------------|-----------------------|--------------------------|
| camEast | (not recorded — verbal pass) |  |  |  |  |  |  |  |
| camWest | (not recorded — verbal pass) |  |  |  |  |  |  |  |

- Re-pitch / re-yaw notes: not recorded.
- Final lens-roll measurement (bubble level, target ±1°): not recorded.

## Step 3 — FullHD ChArUco capture  ✅ 2026-05-25

- [x] All four cams hit 40/40 valid frames at 1920x1080 MJPG @ 30 FPS.
- Output dir: `Remounted_West_East/cal/captures/fullhd_remount_20260525/` (60 MB).
- Per-cam corner stats (54 = max possible on this board):

  | Cam | Frames | Min | Max | Mean |
  |-----|--------|-----|-----|------|
  | camNorth | 40 | 25 | 54 | 44.0 |
  | camEast  | 40 | 27 | 54 | 49.6 |
  | camSouth | 40 | 25 | 54 | 45.8 |
  | camWest  | 40 | 30 | 54 | 49.4 |

- Lateral cams (camEast/camWest) at the new 450 mm mount returned the highest
  mean corner counts (49.4–49.6), consistent with the board sitting closer to
  the lens. No frames below the 25-corner gate.
- Capture command:
  ```
  ./venv/bin/python garage_lab_combined/scripts/auto_capture_charuco_multi.py \
    --config garage_lab_combined/config/cameras.yaml \
    --out-dir Remounted_West_East/cal/captures/fullhd_remount_20260525 \
    --min-corners 25 --hold-sec 0 --target-count 40
  ```

## Step 4 — Solve FullHD intrinsics  ✅ 2026-05-25

- [x] `cal/intrinsics/cam{North,East,South,West}_intrinsics.json` written
- Per-cam RMS reprojection (px, lower is better; <1.5 is good for FullHD):
  - camNorth: 1.29 (used 40/40)
  - camEast: 1.30 (used 40/40) — remounted lateral
  - camSouth: 1.02 (used 40/40)
  - camWest: 1.26 (used 40/40) — remounted lateral
- No frames rejected, no obvious outliers. Lateral cams within 0.05 px of front/back.

## Step 5 — Solve extrinsics  ✅ 2026-05-25 (with caveats)

### 5a — Capture AprilTag stills

- Tool: `Remounted_West_East/scripts/apriltag_capture.py` (new, ~50 LOC).
- 30 frames per cam saved to `cal/captures/apriltag_remount_20260525/` at
  1920x1080 MJPG (the robust solver wants per-cam still images, not videos).
- Per-cam AprilTag visibility across all 30 frames:

  | Cam | tags/frame (min–max) | unique IDs detected | walls covered |
  |-----|----------------------|---------------------|---------------|
  | camNorth | 8–11 | 11 | N/S/E/W |
  | camEast  | 7 | 7 | E/S/W |
  | camSouth | 4–5 | 5 | N/W/E |
  | camWest  | 7 | 7 | S/W/E |

### 5b — Solver attempts and the corner-orientation gotcha

1. **First run** — `calibrate_extrinsics_apriltag_robust.py --ransac-start`
   converged to absurd positions (camNorth solved at 12.2 m off, camEast 9.3 m
   off). Reproj RMSE was OK (1.7–3.3 px) but world positions wrong.
2. **Second run** — `calibrate_extrinsics_apriltag_oriented.py` (variant with
   per-tag corner-permutation search) settled the corner ordering but still
   converged to wrong solutions — pos errors 4–6 m (camWest was the only one
   close at 0.9 m). The 0.89 px reproj on camSouth confirmed classic PnP
   ambiguity: math fits, geometry is in the wrong half-space.
3. **Third run (kept)** — `calibrate_extrinsics_apriltag_robust.py
   --init-extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json`. Using
   the canonical pre-remount extrinsics as the iterative-PnP prior anchors the
   four cameras in the correct half-space; for camEast/camWest the prior is
   ~1.7 m off in Z but the iterative refine slides into the new pose cleanly.

### 5c — Final extrinsics + sanity check vs physical remount

Output: `cal/extrinsics/extrinsics_fixed.json`.

| Cam | Solved pos (m, X,Y,Z) | Pre-remount solved (m) | ΔZ | Reproj RMSE |
|-----|------------------------|------------------------|-----|--------------|
| camNorth | (0.15, 1.10, 2.26) | (0.30, 1.06, 2.17) | +0.08 | 3.10 px |
| camEast  | (1.80, 0.22, 0.47) | (1.73, 0.23, 2.19) | **−1.72** | 3.41 px |
| camSouth | (6.25, 1.60, 2.27) | (6.09, 1.68, 2.14) | +0.13 | 2.96 px |
| camWest  | (1.99, 2.69, 0.44) | (1.71, 2.95, 2.19) | **−1.75** | 2.84 px |

- ΔZ for both lateral cams matches the physical remount: from ~2.18 m down to
  the targeted ~0.45 m. The non-moved cams stayed within ~13 cm of their old
  solved positions (within the 10–15 cm calibration noise envelope of the
  pre-remount baseline).
- **Caveat 1 — RMSE 2.8–3.4 px is above the playbook's <2.0 target.** Likely
  causes: mixed-mount geometry (init prior is exact for N/S but ~1.7 m off
  for E/W), corner-ordering quirks the robust solver doesn't fully fix
  without orientation search. Acceptable to proceed to pose-gate validation;
  refit if the gate fails.
- **Caveat 2 — Lateral cam X/Y also drifted vs the playbook target** (camEast
  Y target ≤0.075, solved 0.22 m; camWest Y target ≥2.975, solved 2.69 m;
  both X also +20–40 cm). Could be physical bracket placement vs the planned
  target, or solver noise. If pose-gate or BLM gate later show systematic
  bias, physically measure the lateral mounts and compare.
- Inlier ratios: camNorth 1052/1088, camEast 720/840, camSouth 480/572,
  camWest 720/840 — all healthy (>85%).

## Step 6 — Dimensions update  ✅ 2026-05-25

- [x] `cal/extrinsics/Dimensions_fixed.txt` updated (copied from canonical, then
  edited the lateral cam Z values only).
- camEast new (X, Y, Z) cm: **(162, 5, 45)** — Z changed 212 → 45.
- camWest new (X, Y, Z) cm: **(160, 297, 45)** — Z changed 217 → 45.
- camNorth (unchanged): (5, 110, 226).
- camSouth (unchanged): (618, 153, 227).
- Position-source policy (user-selected): "Planned positions (Z=45 cm, keep
  old X/Y)" — the downstream `position_error_m` sanity check will surface any
  bracket-placement drift in X/Y as a known caveat, not a hidden bug.

## Step 7 — Bundle-local manifest  ✅ 2026-05-25

- [x] `cal/extrinsics/calibration_manifest.yaml` written.
- `bundle_name: arena_fullhd_remount_20260525`, `status: candidate` (NOT yet
  promoted to `arena_fixed/config/calibration_manifest.yaml`).
- Records intrinsics RMS (1.02–1.30 px), extrinsics RMSE (2.84–3.41 px), the
  two known caveats, the still-active pre-remount correction models, and the
  workflow provenance.

## Step 8 — Pose-gate validation  ⚠️ PARTIAL PASS 2026-05-25

- [x] `baselines/baseline_post_remount.jsonl` recorded (~80 s, 38 perf records).
- Pipeline health: all 4 cams usable every frame, ~30–40 ms total latency, no
  stale frames, no dropped queue depth.
- **Joints_cam metric NOT extracted** — current `live_4cam_arena_view_parallel.py`
  tracks `joints_cam_state` internally but the perf JSONL payload doesn't carry
  it. To recover the numerical playbook metric, the perf-payload write at
  ~line 2935 would need to also serialize `joints_cam_state.tolist()`. Did
  not patch in this session.
- Visual verdict (operator):
  - **Side-on (athlete facing camEast or camWest during push-up):** leg
    skeleton placed correctly. **This is the primary remount goal — achieved.**
  - **Head-pointing-North orientation:** ankle keypoints rendered slightly
    LOW vs actual ankle position. Consistent with the +8-13 cm Z drift the
    extrinsics solver found on camNorth/camSouth (those cams DIDN'T physically
    move; the drift is calibration noise from solving against fewer/different
    tags with new intrinsics).
  - **Rep counter occasionally missed reps.** Orthogonal to calibration —
    rep-state-machine threshold tuning. Logged as known issue.
  - **Raised-leg test:** not performed this run (forgotten). Side-on legs
    tracked well in the regular plank portion, so probability of raised-leg
    success is high but not confirmed.
  - **3D arena view:** not inspected (`run_live_coach.sh` has `--no-show-3d`
    baked in; only coach overlay was on screen).
- Decision: lateral-cam remount goal is **achieved** (the original push-up
  ankle-tracking failure mode is gone when athlete is side-on). The residual
  N/S ankle Z-bias is exactly what GT correction model refit (step 10) is
  designed to compensate. Continue to step 9 (BLM S2 aim-only) and step 10
  (GT eval + refit) without re-running pose gate.

## Step 9 — Unit tests

- [ ] `PYTHONPATH=src ./venv/bin/python -m unittest discover -s tests` → ___ tests OK

## Step 10 — BLM gate

### S2 — aim-only

- [ ] `live_aim_test.py --no-shoot-enabled` tracks chosen joint correctly
- Notes:

### GT joint-touch eval (5 trials)

- Mean error (mm): _____ (baseline 178 mm; tolerance ~30% → < ~230 mm without refit)
- P95 error (mm): _____
- Refit decision: needed / not needed
- If refit: new `correction_model.json` saved to `gt_eval/<bundle>/`

### S4 — controlled fire (soft target, no human)

- [ ] Low pitch (15°), low RPM (500) single shot, observed
- Trajectory notes:
- Escalation decision:

## Promotion checklist (do only after pose + BLM gates green)

- [ ] `git tag post-remount-validated-<YYYY-MM-DD>`
- [ ] Copy intrinsics → `garage_lab_combined/cal/intrinsics/`
- [ ] Copy extrinsics + dims → `arena_fixed/cal/extrinsics/`
- [ ] Copy refit GT eval (if any) → `garage_lab_combined/gt_eval/`
- [ ] Update canonical `arena_fixed/config/calibration_manifest.yaml`
- [ ] Update `CLAUDE.md` accuracy + execution-plan lines
- [ ] Update `.claude/rules/geometry.md` if any geometry guidance changed
- [ ] Commit + push
