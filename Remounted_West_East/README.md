# Remounted_West_East — Post-Remount Calibration & Validation Bundle

**Created:** 2026-05-25
**Trigger:** camEast and camWest physically remounted from ~2.2 m down to ~450 mm
to fix push-up plank leg occlusion (only camNorth/camSouth see legs in side-profile
from the elevated mount; lateral side-view at body height was missing).
**Camera mode (new):** 1920x1080 MJPG @ 30 FPS on all four cameras
(verified with `v4l2-ctl` after the remount).
**Rollback tag:** `pre-remount-2026-05-20` on commit `8307446f` (local + pushed
to `origin`).

## Why this folder exists

Calibration (intrinsics + extrinsics + dimensions + manifest + GT correction model)
is **bound to physical camera geometry**. The remount invalidates every artifact
that was solved against the old mount. This bundle holds the *new* artifacts and
validation evidence in one place, so the canonical paths
(`garage_lab_combined/cal/`, `arena_fixed/cal/`, `garage_lab_combined/gt_eval/`)
can stay frozen until the new calibration passes both safety gates. Once green,
the new artifacts get promoted into the canonical paths and `calibration_manifest.yaml`
is bumped.

The code itself (live viewer, pose tracker, launcher, BLM scripts) is **not**
duplicated here. The FullHD edits already landed in the canonical scripts under
`garage_lab_combined/`, `Parallel_working/`, `apps/`, and `arena_fixed/`. This
folder only owns artifacts and the validation log.

## Layout

| Path | Owner | Contents |
|------|-------|----------|
| `cal/captures/` | this bundle | New FullHD ChArUco capture batch (`fullhd_remount_20260525/`) |
| `cal/intrinsics/` | this bundle | New FullHD per-cam intrinsics JSONs |
| `cal/extrinsics/` | this bundle | New `extrinsics_fixed.json`, `Dimensions_fixed.txt`, `calibration_manifest.yaml` |
| `gt_eval/` | this bundle | New post-remount GT joint-touch eval + refit `correction_model.json` (if bias drifted) |
| `baselines/` | this bundle | Pose JSONLs (`baseline_post_remount.jsonl`), arena3d MP4s, comparison notes |
| `reference/` | symlinks only | Read-only pointers to the currently-active pre-remount standards |
| `REMOUNT_LOG.md` | this bundle | Chronological log: each step's result, RMSE, decisions, anomalies |

## Reference symlinks (read-only, for "how did we do this before?")

| Symlink | Target | What it gives you |
|---------|--------|--------------------|
| `reference/pre_remount_backup` | `cal_backup/pre_remount_2026-05-25/` | Frozen copy of pre-remount extrinsics, dimensions, manifest, GT correction bundle |
| `reference/intrinsics_active_pre_remount` | `garage_lab_combined/cal/intrinsics/` | Currently-active intrinsics (1280x720, will be superseded) |
| `reference/extrinsics_active_pre_remount` | `arena_fixed/cal/extrinsics/` | Currently-active extrinsics + dimensions (pre-remount geometry) |
| `reference/gt_eval_active_pre_remount` | `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/` | Currently-active GT correction model (refit candidate if bias drifts) |
| `reference/remount_playbook.md` | `docs/remount_playbook_2026-05-20.md` | The operator playbook this bundle implements |

## Workflow (do in order; tick boxes in `REMOUNT_LOG.md` as you go)

The detailed playbook is `reference/remount_playbook.md`. The bundle-aware
output paths are:

1. **Power-on + enumerate cams.** Confirm all four advertise `1920x1080 MJPG @ 30 FPS`.
   - `lsusb`
   - `v4l2-ctl --device=<…> --list-formats-ext` per cam
2. **Live framing check** (eyes-only, no calibration yet). Confirm hip/knee/ankle/foot
   in frame on both lateral cams, ≥80 px headroom, ≥80 px below feet, body axis
   horizontal, BLM + operator outside the cone.
3. **New FullHD ChArUco captures.**
   - `./venv/bin/python garage_lab_combined/scripts/auto_capture_charuco_multi.py \`
     ` --config garage_lab_combined/config/cameras.yaml \`
     ` --out-dir Remounted_West_East/cal/captures/fullhd_remount_20260525 \`
     ` --min-corners 25 --hold-sec 0 --target-count 40`
4. **Solve FullHD intrinsics.**
   - `./venv/bin/python garage_lab_combined/scripts/calibrate_intrinsics_from_images.py \`
     ` --config garage_lab_combined/config/cameras.yaml \`
     ` --captures-dir Remounted_West_East/cal/captures/fullhd_remount_20260525 \`
     ` --out-dir Remounted_West_East/cal/intrinsics`
5. **Solve extrinsics** (AprilTag robust solver). Acceptance: per-cam
   `reprojection_error_rmse < 2.0`. Outputs land in `cal/extrinsics/`.
6. **Update `Dimensions_fixed.txt`** with new East/West mount positions
   (lines 12–15, cm units: e.g. `CamEast = (162, 5, 45)` for `(1620, 50, 450)` mm).
7. **Write a bundle-local `calibration_manifest.yaml`** with `bundle_name:
   arena_fullhd_remount_20260525` and the new intrinsics/extrinsics paths.
   **Do not yet** update the canonical `arena_fixed/config/calibration_manifest.yaml`
   — that happens only after both gates pass.
8. **Pose-gate validation.** Save pose JSONL into `baselines/`.
   - `./apps/athlete_assessment/run_live_coach.sh push_up \`
     ` --pushup-ankle-single-cam-fallback \`
     ` --perf-jsonl Remounted_West_East/baselines/baseline_post_remount.jsonl`
   - Acceptance: `joints_cam[15]` and `[16]` average ≥ 2.5 during plank (vs ~1.5 pre-remount).
9. **Unit tests** — `PYTHONPATH=src ./venv/bin/python -m unittest discover -s tests`.
   Current expected count: 135 OK (was 132 pre-FullHD test additions).
10. **BLM-gate validation, independent of pose gate.**
    - **S2** aim-only with `live_aim_test.py --no-shoot-enabled` against a static joint.
    - **Small GT joint-touch eval** (5 trials, one athlete). If mean drift > ~30%
      vs the 178 mm baseline, refit the correction model into `gt_eval/`
      before any `--shoot-enabled`.
    - **S4** soft-target (no human) at low pitch / low RPM before any human subject.

## Promotion (only after both gates green)

1. Tag the canonical state again: `git tag post-remount-validated-<date>` for rollback.
2. Copy/replace into canonical paths:
   - `cp Remounted_West_East/cal/intrinsics/*.json garage_lab_combined/cal/intrinsics/`
   - `cp Remounted_West_East/cal/extrinsics/extrinsics_fixed.json arena_fixed/cal/extrinsics/`
   - `cp Remounted_West_East/cal/extrinsics/Dimensions_fixed.txt arena_fixed/cal/extrinsics/`
   - If correction model was refit: `cp -r Remounted_West_East/gt_eval/<new-bundle> garage_lab_combined/gt_eval/`
3. Update `arena_fixed/config/calibration_manifest.yaml` (`bundle_name`,
   intrinsics resolution, `created` date).
4. Update `CLAUDE.md` "Current Accuracy" + execution-plan status lines.

## Rollback

If a stage fails and a clean fallback is needed:

```bash
BACKUP=/home/hanush/Desktop/Project_Cam/cal_backup/pre_remount_2026-05-25
cp $BACKUP/extrinsics_fixed.json      arena_fixed/cal/extrinsics/
cp $BACKUP/Dimensions_fixed.txt       arena_fixed/cal/extrinsics/
cp $BACKUP/calibration_manifest.yaml  arena_fixed/config/
```

If the repo also needs to roll back to the tagged state:

```bash
git checkout pre-remount-2026-05-20   # detached HEAD — inspect first
# only if you are sure:
git checkout main && git reset --hard pre-remount-2026-05-20
```

Do **not** run the BLM in `--shoot-enabled` mode while extrinsics on disk and
physical mounts disagree (e.g. mounts low but rolled back to elevated extrinsics).

## What this bundle deliberately does NOT touch

- `triangulate_multi`, `transform_world_point_y`, `ema_update`, UDP axis semantics
  (geometry-protected functions — see `.claude/rules/geometry.md`).
- `arena_fixed/` canonical extrinsics/dimensions (frozen until promotion).
- `garage_lab_combined/cal/intrinsics/` canonical intrinsics (frozen until promotion).
- Live runtime scripts (already FullHD-updated in place).
