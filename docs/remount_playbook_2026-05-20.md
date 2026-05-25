# Lateral Camera Remount — Operator Playbook

**Date drafted:** 2026-05-20
**Revised:** 2026-05-25 (incorporated operator feedback: durable backup
paths, off-machine push, live framing check before calibration, explicit
two-gate safety model)
**Rollback tag (local):** `pre-remount-2026-05-20` on commit `8307446f`
**Plan source:** `/home/hanush/.claude/plans/crystalline-stirring-spindle.md`

## Two independent safety gates (do NOT conflate)

| Gate | Validates | Tools | Blocks |
|------|-----------|-------|--------|
| **Pose gate** | Coach overlay tracks legs / ankles correctly during plank | `run_live_coach.sh push_up` + `joints_cam` in perf log | Going to the BLM gate |
| **BLM gate** | Launcher geometry, RPM, angle clamp, correction model still produce safe shots | `live_aim_test.py` S2 -> S4 + small GT eval | Using `--shoot-enabled` on a human |

A green pose gate **does not** prove the BLM gate is green. Extrinsics
shifted -> the GT correction model may need a refit before the launcher
is safe to fire. Run both gates independently and in order.

## Off-machine backup (do BEFORE touching cameras)

Remote `origin` is configured at
`https://github.com/Shadow-Git-Friend/Project_Cam.git`. Push everything
that would matter for rollback:

```bash
cd /home/hanush/Desktop/Project_Cam
git push origin main                            # all 5 software commits
git push origin pre-remount-2026-05-20          # the rollback tag
```

If `git push` fails on auth, fix that BEFORE you start remounting — once
extrinsics are overwritten the local repo is your only rollback path.

## Why we are doing this

Push-up leg tracking fails because all four cameras are mounted at ~2.2 m
(elevated corners of a 6230 x 3050 x 2950 mm arena). For a horizontal plank
athlete at ~200-400 mm above the floor, every camera looks steeply
downward and the torso self-occludes the legs. Multi-view triangulation
needs >= 2 cameras per joint; with only one camera reliably seeing the
ankle, the joint either drops to NaN or lands on floor clutter. The
raised-leg test (athlete actively lifts a foot) is the exact failure case.

Software priors and a single-camera ankle fallback (commits `634f9ca6` +
`8307446f`) reduce the visible symptoms but cannot recover an ankle that
no camera sees clearly. The structural fix is to **lower camEast and
camWest** to ~450 mm so they see the athlete in side-profile at body
height. Front and back cameras (camNorth, camSouth) stay where they are.

## Pre-remount checklist (do tonight, before powering down)

1. **Create a durable backup dir** in your home (NOT `/tmp` -- some
   systems clear `/tmp` on reboot):

   ```bash
   mkdir -p ~/Project_Cam_cal_backups/pre_remount_2026-05-25
   ```

2. **Baseline capture** with the new software, on the current mount:

   ```bash
   ./apps/athlete_assessment/run_live_coach.sh push_up \
       --pushup-ankle-single-cam-fallback \
       --perf-jsonl ~/Project_Cam_cal_backups/pre_remount_2026-05-25/baseline_pre_remount.jsonl
   ```

   Do one push-up set (~5 reps), including the raised-leg test. Save the
   `arena3d_*.mp4` / `mosaic2d_*.mp4` recordings if recording is on (copy
   them into the backup dir). This gives you an apples-to-apples
   comparison tomorrow.

3. **Backup the active calibration files into the durable dir**:

   ```bash
   cp arena_fixed/cal/extrinsics/extrinsics_fixed.json \
      ~/Project_Cam_cal_backups/pre_remount_2026-05-25/
   cp arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
      ~/Project_Cam_cal_backups/pre_remount_2026-05-25/
   cp arena_fixed/config/calibration_manifest.yaml \
      ~/Project_Cam_cal_backups/pre_remount_2026-05-25/
   ```

   Also copy any GT-correction artifacts the BLM may need to roll back to:

   ```bash
   cp -r garage_lab_combined/gt_eval/reeval_arena_fixed_20260406 \
      ~/Project_Cam_cal_backups/pre_remount_2026-05-25/
   ```

4. **Verify the rollback tag is present locally AND pushed to origin**:

   ```bash
   git tag --list 'pre-remount*'                      # expect: pre-remount-2026-05-20
   git ls-remote --tags origin pre-remount-2026-05-20 # expect: hash + tag name
   ```

   If the tag is local-only, push it now (see "Off-machine backup" at
   the top of this doc).

5. **Hardware to have ready:** two low brackets for camEast and camWest
   at ~450 mm Z, bubble level (or phone level), and confirmation that
   the existing USB cables reach the new positions (lateral cams now sit
   ~1.7 m closer to the floor).

## Target positions (mm, world frame from `Dimensions_fixed.txt`)

| Cam | X | Y | Z | Pitch | Yaw target | Change |
|-----|---|---|---|-------|-----------|--------|
| camNorth | 50  | 1100 | 2260 | unchanged | unchanged | **none** |
| camSouth | 6180 | 1530 | 2270 | unchanged | unchanged | **none** |
| **camEast** | ~1620 | **<= 75** | **~450** | **~12-18 deg down** | arena center (3115, 1525) | **Z drops 2120 -> 450** |
| **camWest** | ~1600 | **>= 2975** | **~450** | **~12-18 deg down** | arena center (3115, 1525) | **Z drops 2170 -> 450** |

`Y <= 75 mm` on camEast keeps the camera back flush to the East wall at
Y = 0. Symmetrically `Y >= 2975 mm` flushes camWest against the West
wall at Y = 3050. X positions stay at the existing mid-length sweet spot.

## Tomorrow's sequence

1. **Power down the full system.** Do not yank USB while the OS is mid-write.
2. Unmount camEast and camWest. Mount on new low brackets per the table.
   Bubble-level the lens housing; roll within +/- 1 deg.
3. Power up. Verify enumeration:

   ```bash
   lsusb
   ./apps/athlete_assessment/run_live_coach.sh push_up
   # confirm all 4 cameras show up; q to quit
   ```

4. **Live framing check (CRITICAL -- before any calibration).** A camera
   that hits a perfect AprilTag RMS but crops out the athlete's hip is
   useless. Have the athlete go into a steady plank in the centre of the
   mat, then open the 2D mosaic and **eyeball each lateral view**:

   ```bash
   ./apps/athlete_assessment/run_live_parallel_yolopose.sh \
       --show-2d --mosaic-every 1
   ```

   Acceptance, separately for camEast AND camWest:
   - **Hip, knee, ankle, and foot** all visible in the frame.
   - At least ~80 px of headroom above the shoulder line (so the athlete
     coming up from bottom of push-up is not clipped).
   - At least ~80 px below the foot (so a raised-leg test is not clipped).
   - The body axis is roughly horizontal across the frame, not diagonal
     -- adjust yaw to centre the athlete.
   - The cone of view does NOT include the BLM machine, the operator,
     or other moving humans (false-positive pose detections).

   If framing fails on either lateral cam, **re-pitch and re-yaw before
   running the extrinsics solver**. AprilTag RMS does not catch framing
   problems; only a human eye does.

5. **Intrinsics sanity (only if focus ring was touched).** Intrinsics
   are invariant under a mount-only change, so usually skip. If you ran
   the script, compare new `K, D` against existing JSON and skip
   re-saving if `||deltaK_focal|| < 2 px`.

6. **Extrinsics (mandatory).** Re-run the AprilTag extrinsics solver:

   ```bash
   ./venv/bin/python garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py
   ```

   Acceptance: `reprojection_error_rmse < 2.0` per camera. If higher,
   re-shoot calibration images for that camera and re-run.

7. **Update `Dimensions_fixed.txt`** (lines 12-15) with the new positions
   in cm (e.g. `CamEast = (162, 5, 45)` for `(1620, 50, 450)` mm).

8. **Bump calibration date** in `arena_fixed/config/calibration_manifest.yaml`.

9. **Pose-gate validation (do NOT enable BLM yet):**

   ```bash
   ./apps/athlete_assessment/run_live_coach.sh push_up \
       --pushup-ankle-single-cam-fallback \
       --perf-jsonl ~/Project_Cam_cal_backups/pre_remount_2026-05-25/baseline_post_remount.jsonl
   ```

   Repeat the same push-up set including the raised-leg test. Compare
   against the pre-remount baseline saved in the durable dir:

   ```bash
   BACKUP=~/Project_Cam_cal_backups/pre_remount_2026-05-25
   grep '"joints_cam"' $BACKUP/baseline_pre_remount.jsonl  | head
   grep '"joints_cam"' $BACKUP/baseline_post_remount.jsonl | head
   ```

   Acceptance: `joints_cam[15]` and `[16]` should rise materially across
   a rep (target: average >= 2.5 post-remount vs ~1.5 pre-remount). Also
   eyeball the overlay: leg skeleton lines should sit on the athlete's
   legs in BOTH the camEast and camWest views, including during the
   raised-leg test.

   **Pose gate green does NOT mean BLM is safe -- step 11 is mandatory
   before any `--shoot-enabled`.**

10. **Re-run unit tests** to confirm no regressions in pure-Python code:

    ```bash
    PYTHONPATH=src ./venv/bin/python -m unittest discover -s tests
    # expect: 132 tests OK
    ```

11. **BLM-gate validation (independent of the pose gate; do NOT skip
    before `--shoot-enabled`):**
    - **S2** aim-only with `live_aim_test.py --no-shoot-enabled` against
      a static joint. The launcher must track correctly.
    - **GT joint-touch eval** (small, 5 trials, one athlete) to confirm
      accuracy stayed within ~30% of the current 178 mm mean. If worse,
      refit the correction model via the existing `gt_eval` flow before
      shooting. The pre-remount correction model is preserved under
      `~/Project_Cam_cal_backups/pre_remount_2026-05-25/reeval_arena_fixed_20260406/`
      if you need to compare or roll back.
    - **S4** with a soft target (no human) at low pitch / low RPM before
      shooting at any human subject.

## Rollback (if something goes wrong)

```bash
# Restore the pre-remount calibration files from the durable backup
BACKUP=~/Project_Cam_cal_backups/pre_remount_2026-05-25
cp $BACKUP/extrinsics_fixed.json    arena_fixed/cal/extrinsics/
cp $BACKUP/Dimensions_fixed.txt     arena_fixed/cal/extrinsics/
cp $BACKUP/calibration_manifest.yaml arena_fixed/config/

# OR roll the entire repo back to the tagged state
git checkout pre-remount-2026-05-20  # detached HEAD; inspect first
# When happy:
git checkout main
git reset --hard pre-remount-2026-05-20  # destructive -- be sure
```

If the calibration files are restored but cameras are still physically
on the new low mounts, you have an inconsistent state. Either remount
back to elevated positions, or re-run extrinsics. Do not let the BLM run
in `--shoot-enabled` mode while extrinsics and physical mounts disagree.

## Failure modes the remount cannot fix

- YOLO-Pose mis-classifying a floor mark as an ankle from >= 2 cameras
  consistently. The 3D leg-prior validator drops it -> joint goes NaN,
  not a wrong-position render. Prevents corruption, not recovery.
- Pike / decline / single-leg push-up variants. The hip-distance gate
  treats these as out-of-range. Stick to standard plank for now.
- Mat thickness > 0. Use `--pushup-ankle-floor-mm 15` (or whatever the
  mat measures) so the single-cam ankle fallback lands on the mat
  surface, not the concrete floor underneath.
- BLM correction model drift. The model in
  `garage_lab_combined/gt_eval/.../correction_model.json` is calibrated
  against the pre-remount extrinsics. If the post-remount systematic
  bias is materially different, refit before shooting.

## Reference commits

- `4fc59352` — temporal gates: trunk-cue ankle streak, wrists-only floor, elbow velocity clamp
- `4a69292e` — wire PushupFloorAnchor into canonical tracker
- `634f9ca6` — leg priors + single-cam ankle fallback (module + tests)
- `8307446f` — wire leg priors + ankle fallback into canonical tracker
- `pre-remount-2026-05-20` — tag on `8307446f`, rollback target

## Reference files

- `src/project_cam/assessment/live_trainer/leg_priors.py` — priors,
  validator, ankle fallback helper.
- `src/project_cam/assessment/live_trainer/coach_overlay.py` — overlay,
  floor anchor, leg-chain validator.
- `src/project_cam/assessment/live_trainer/rep_state.py` — rep counter,
  trunk-cue streak, elbow velocity clamp.
- `Parallel_working/scripts/live_4cam_arena_view_parallel.py` —
  canonical tracker, all the wiring.
- `arena_fixed/cal/extrinsics/Dimensions_fixed.txt` — physical mount
  truth. Update lines 12-15 post-remount.
- `arena_fixed/cal/extrinsics/extrinsics_fixed.json` — solver output.
  Regenerated by `calibrate_extrinsics_apriltag_robust.py`.
