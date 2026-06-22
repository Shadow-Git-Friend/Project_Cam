# Rigid Target GT Pipeline (Garage)

## Goal
Measure true 3D geometric accuracy of the camera setup using a rigid target point with known coordinates.

This removes human-joint uncertainty and answers:
- how accurate triangulation is in world frame,
- whether camera calibration is good enough for control tasks.

## Why This Is Critical
For ball-launching commands, a wrong 3D target causes systematic miss.
Rigid GT separates:
- camera geometry error,
- human pose model error.

Only after rigid GT is stable should joint-specific corrections be trusted.

## Files
- Trials CSV:
  - `garage_lab_combined/gt_eval/rigid_trials_18_mm.csv`
- Evaluator:
  - `garage_lab_combined/scripts/evaluate_ball_static_gt.py`
- Visualizer:
  - `garage_lab_combined/scripts/visualize_ball_tuning_session.py`

## Units
- All coordinates in this protocol are in `mm`.

## Session Setup
```bash
cd /home/hanush/Desktop/Project_Cam

SESSION="garage_lab_combined/gt_eval/rigid_tuning_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SESSION"/{clips,results,reports,visualizations,logs}

CFG="garage_lab_combined/config/cameras.yaml"
INTR="garage_lab_combined/cal/intrinsics"
EXTR="garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json"

cp garage_lab_combined/gt_eval/rigid_trials_18_mm.csv "$SESSION/trials_rigid_18_mm.csv"
```

## Physical Setup
- Use a rigid rod/holder with a small ball at the tip.
- Treat the **ball center** as GT point.
- Measure target point in world frame (same frame as `Dimensions.txt`).
- Keep at least 3 cameras seeing the ball.
- Keep scene static during recording.

## Trial Design
- 15 grid points across 3 heights.
- 3 repeated points (`R016..R018`) to check drift/repeatability.

## Helpful Commands
```bash
show_trial () {
  local T="$1"
  awk -F, -v t="$T" 'NR==1 || $1==t {print}' "$SESSION/trials_rigid_18_mm.csv"
}

record_one () {
  local T="$1"
  ./venv/bin/python garage_lab_combined/scripts/record_short_clips_multi.py \
    --config "$CFG" \
    --out-dir "$SESSION/clips" \
    --prefix "$T" \
    --start-index 1 \
    --clips 1 \
    --duration-sec 4 \
    --start-delay-sec 4 \
    --width 1280 --height 720 --fps 15 \
    --ext avi --out-codec MJPG --show
}

process_one () {
  local T="$1"
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
    --ball-max-speed-mps 0 \
    --ball-ema-alpha 0 \
    --no-pose
}
```

## Record + Process Workflow
For each trial:
```bash
show_trial R001
record_one R001
process_one R001
```

Repeat through:
- `R001..R015` (main grid),
- `R016..R018` (repeat checks).

## Batch Process Already Recorded Clips
```bash
for T in $(awk -F, 'NR>1 {print $1}' "$SESSION/trials_rigid_18_mm.csv"); do
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
      --ball-max-speed-mps 0 \
      --ball-ema-alpha 0 \
      --no-pose
  else
    echo "[SKIP] $T clip not found"
  fi
done
```

## Evaluate Rigid Accuracy
```bash
./venv/bin/python garage_lab_combined/scripts/evaluate_ball_static_gt.py \
  --trials-csv "$SESSION/trials_rigid_18_mm.csv" \
  --results-dir "$SESSION/results" \
  --out-dir "$SESSION/reports" \
  --window-start-frac 0.20 \
  --window-end-frac 0.80
```

## Optional Visualization
`visualize_ball_tuning_session.py` expects a specific session layout (`reports_static_raw`).  
Create symlink-style copy then render:
```bash
mkdir -p "$SESSION/reports_static_raw"
cp "$SESSION/reports/trial_errors.csv" "$SESSION/reports_static_raw/trial_errors.csv"
cp "$SESSION/reports/summary_metrics.json" "$SESSION/reports_static_raw/summary_metrics.json"

./venv/bin/python garage_lab_combined/scripts/visualize_ball_tuning_session.py \
  --session "$SESSION" \
  --dimensions garage_lab_combined/cal/extrinsics/Dimensions.txt
```

## Acceptance Targets For Launcher Stage
- Mean error: `< 60 mm`
- P95 error: `< 90 mm`
- Max error: `< 120 mm`
- Static precision (`std_norm_mean`): `< 8 mm`

If not achieved:
- re-check camera movement / extrinsics,
- improve point visibility (>=3 cameras),
- reduce reflections and blur,
- re-run rigid GT before touching joint corrections.

## Next Step After Passing Rigid GT
Then run joint-touch validation again.
At that point:
- rigid error = camera geometry baseline,
- extra joint error = pose estimation/anatomical mapping error.
