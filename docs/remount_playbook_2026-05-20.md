# Lateral Camera Remount — Operator Playbook

**Date drafted:** 2026-05-20
**Rollback tag (local):** `pre-remount-2026-05-20` on commit `8307446f`
**Plan source:** `/home/hanush/.claude/plans/crystalline-stirring-spindle.md`

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

1. **Baseline capture** with the new software, on the current mount:

   ```bash
   ./apps/athlete_assessment/run_live_coach.sh push_up \
       --pushup-ankle-single-cam-fallback \
       --perf-jsonl /tmp/baseline_pre_remount.jsonl
   ```

   Do one push-up set (~5 reps), including the raised-leg test. Save the
   `arena3d_*.mp4` / `mosaic2d_*.mp4` recordings if recording is on. This
   gives you an apples-to-apples comparison tomorrow.

2. **Backup the active calibration files**:

   ```bash
   cp arena_fixed/cal/extrinsics/extrinsics_fixed.json \
      /tmp/extrinsics_fixed.PRE_REMOUNT.json
   cp arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
      /tmp/Dimensions_fixed.PRE_REMOUNT.txt
   ```

3. **Verify rollback tag is present locally**:

   ```bash
   git tag --list 'pre-remount*'
   # expect: pre-remount-2026-05-20
   ```

   If you have a remote, push the tag for off-machine safety:

   ```bash
   git push origin pre-remount-2026-05-20
   ```

4. **Hardware to have ready:** two low brackets for camEast and camWest
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

4. **Intrinsics sanity (only if focus ring was touched).** Intrinsics
   are invariant under a mount-only change, so usually skip. If you ran
   the script, compare new `K, D` against existing JSON and skip
   re-saving if `||deltaK_focal|| < 2 px`.

5. **Extrinsics (mandatory).** Re-run the AprilTag extrinsics solver:

   ```bash
   ./venv/bin/python garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py
   ```

   Acceptance: `reprojection_error_rmse < 2.0` per camera. If higher,
   re-shoot calibration images for that camera and re-run.

6. **Update `Dimensions_fixed.txt`** (lines 12-15) with the new positions
   in cm (e.g. `CamEast = (162, 5, 45)` for `(1620, 50, 450)` mm).

7. **Bump calibration date** in `arena_fixed/config/calibration_manifest.yaml`.

8. **Validate live tracking (before touching the BLM):**

   ```bash
   ./apps/athlete_assessment/run_live_coach.sh push_up \
       --pushup-ankle-single-cam-fallback \
       --perf-jsonl /tmp/baseline_post_remount.jsonl
   ```

   Repeat the same push-up set including the raised-leg test. Compare
   against `/tmp/baseline_pre_remount.jsonl`:

   ```bash
   # Quick heuristic comparison of ankle multi-cam counts:
   grep '"joints_cam"' /tmp/baseline_pre_remount.jsonl  | head
   grep '"joints_cam"' /tmp/baseline_post_remount.jsonl | head
   ```

   Acceptance: `joints_cam[15]` and `[16]` should rise materially across
   a rep (target: average >= 2.5 post-remount vs ~1.5 pre-remount).

9. **Re-run unit tests** to confirm no regressions in pure-Python code:

   ```bash
   PYTHONPATH=src ./venv/bin/python -m unittest discover -s tests
   # expect: 132 tests OK
   ```

10. **BLM re-validation (do NOT skip before `--shoot-enabled`):**
    - **S2** aim-only with `live_aim_test.py --no-shoot-enabled` against
      a static joint. The launcher must track correctly.
    - **GT joint-touch eval** (small, 5 trials, one athlete) to confirm
      accuracy stayed within ~30% of the current 178 mm mean. If worse,
      refit the correction model via the existing `gt_eval` flow before
      shooting.
    - **S4** with a soft target (no human) at low pitch / low RPM before
      shooting at any human subject.

## Rollback (if something goes wrong)

```bash
# Restore the pre-remount calibration files
cp /tmp/extrinsics_fixed.PRE_REMOUNT.json arena_fixed/cal/extrinsics/extrinsics_fixed.json
cp /tmp/Dimensions_fixed.PRE_REMOUNT.txt arena_fixed/cal/extrinsics/Dimensions_fixed.txt

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
