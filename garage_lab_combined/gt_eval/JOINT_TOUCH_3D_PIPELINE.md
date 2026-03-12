# Joint Touch 3D Validation Pipeline (Garage)

## Goal
Validate 3D localization accuracy of human joints in the same arena/world frame used for ball detection.

This protocol evaluates:
- `right_knee`
- `right_hip` (pelvis proxy)
- `left_shoulder`

All coordinates are in `mm`.

Dataset size:
- `9` XY points in the center area
- `3` platform levels (`0`, `400`, `640` mm)
- `3` joints
- Total: `9 x 3 x 3 = 81` trials

## Files
- Trials template:
  - `garage_lab_combined/gt_eval/joint_trials_template_30_mm.csv`
- Evaluator:
  - `garage_lab_combined/scripts/evaluate_pose_joint_touch_gt.py`
- Visualizer:
  - `garage_lab_combined/scripts/visualize_joint_touch_session.py`

## Session Setup
```bash
cd /home/hanush/Desktop/Project_Cam

SESSION="garage_lab_combined/gt_eval/joint_tuning_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SESSION"/{clips,results,reports,visualizations,logs}

EXTR="garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json"
INTR="garage_lab_combined/cal/intrinsics"
CFG="garage_lab_combined/config/cameras.yaml"

cp garage_lab_combined/gt_eval/joint_trials_template_30_mm.csv "$SESSION/trials_joint_81_mm.csv"
```

## Trial Design
- XY center grid:
  - `(2600,1100)`, `(3200,1100)`, `(3800,1100)`
  - `(2600,1600)`, `(3200,1600)`, `(3800,1600)`
  - `(2600,2100)`, `(3200,2100)`, `(3800,2100)`
- Platform/base `Z` levels:
  - `0 mm` (floor)
  - `400 mm`
  - `640 mm`
- Joint target heights used in template:
  - `right_knee`: base `+500 mm`
  - `right_hip`: base `+1000 mm`
  - `left_shoulder`: base `+1560 mm`

## Capture Rules
- One person in scene.
- For each trial, touch the physical target with the specified joint.
- Hold static pose for `3-4 sec`.
- Keep target visible in at least `3` cameras.
- Start each trial from neutral position, then touch target.

## Auto Recording (Recommended)
This mode does not require pressing `r` for each trial.
It reads `J001..J081` from CSV, shows a countdown, then records automatically.

```bash
./venv/bin/python garage_lab_combined/scripts/auto_record_joint_trials.py \
  --config "$CFG" \
  --trials-csv "$SESSION/trials_joint_81_mm.csv" \
  --out-dir "$SESSION/clips" \
  --duration-sec 4 \
  --settle-sec 8 \
  --width 1280 --height 720 --fps 15 \
  --ext avi --out-codec MJPG --show
```

Useful options:
- Resume from a trial:
  - `--start-trial J041`
- Stop at trial:
  - `--end-trial J054`
- Skip already recorded clips (default on):
  - `--skip-existing`
- Headless run:
  - `--no-show`

## Record One Trial
Example for `J001`:
```bash
./venv/bin/python garage_lab_combined/scripts/record_short_clips_multi.py \
  --config "$CFG" \
  --out-dir "$SESSION/clips" \
  --prefix J001 \
  --start-index 1 \
  --clips 1 \
  --duration-sec 4 \
  --width 1280 --height 720 --fps 15 \
  --ext avi --out-codec MJPG --show
```

## Process One Trial To 3D
```bash
T=J001

./venv/bin/python garage_lab_combined/scripts/process_4cam_to_3d.py \
  --video-east  "$SESSION/clips/${T}_001/camEast.avi" \
  --video-north "$SESSION/clips/${T}_001/camNorth.avi" \
  --video-south "$SESSION/clips/${T}_001/camSouth.avi" \
  --video-west  "$SESSION/clips/${T}_001/camWest.avi" \
  --intrinsics-dir "$INTR" \
  --extrinsics "$EXTR" \
  --out "$SESSION/results/${T}.json" \
  --conf 0.45 \
  --ball-min-cams 2 \
  --ball-max-reproj-px 14 \
  --ball-max-speed-mps 22 \
  --ball-ema-alpha 0.25 \
  --pose-conf 0.35 \
  --pose-min-cams 3
```

## Batch Process All Recorded Trials
```bash
for T in $(awk -F, 'NR>1 {print $1}' "$SESSION/trials_joint_81_mm.csv"); do
  if [ -d "$SESSION/clips/${T}_001" ]; then
    echo "[PROCESS] $T"
    ./venv/bin/python garage_lab_combined/scripts/process_4cam_to_3d.py \
      --video-east  "$SESSION/clips/${T}_001/camEast.avi" \
      --video-north "$SESSION/clips/${T}_001/camNorth.avi" \
      --video-south "$SESSION/clips/${T}_001/camSouth.avi" \
      --video-west  "$SESSION/clips/${T}_001/camWest.avi" \
      --intrinsics-dir "$INTR" \
      --extrinsics "$EXTR" \
      --out "$SESSION/results/${T}.json" \
      --conf 0.45 \
      --ball-min-cams 2 \
      --ball-max-reproj-px 14 \
      --ball-max-speed-mps 22 \
      --ball-ema-alpha 0.25 \
      --pose-conf 0.35 \
      --pose-min-cams 3
  else
    echo "[SKIP] $T clip not found"
  fi
done
```

## Evaluate Joint Accuracy
```bash
./venv/bin/python garage_lab_combined/scripts/evaluate_pose_joint_touch_gt.py \
  --trials-csv "$SESSION/trials_joint_81_mm.csv" \
  --results-dir "$SESSION/results" \
  --out-dir "$SESSION/reports" \
  --window-start-frac 0.20 \
  --window-end-frac 0.80
```

## Visualize Results
```bash
./venv/bin/python garage_lab_combined/scripts/visualize_joint_touch_session.py \
  --trial-errors-csv "$SESSION/reports/trial_errors.csv" \
  --out-dir "$SESSION/visualizations"
```

## Outputs
- Per-trial metrics:
  - `trial_errors.csv`
- Summary metrics:
  - `summary_metrics.json`
- Bias / correction model:
  - `correction_model.json`
- Human-readable report:
  - `error_report.md`
- Figures:
  - `joint_touch_3d_gt_vs_est.png`
  - `joint_touch_error_boxplot.png`

## Acceptance Targets (Initial)
- Global:
  - Mean error `< 180 mm`
  - P95 `< 280 mm`
- Per joint:
  - `right_knee` P95 `< 220 mm`
  - `right_hip` P95 `< 220 mm`
  - `left_shoulder` P95 `< 250 mm`
- Detection ratio in hold window:
  - Mean `>= 0.80`

If any metric is outside target, inspect:
- camera visibility/occlusion at those trials,
- frame window quality,
- false joint identity switches.
