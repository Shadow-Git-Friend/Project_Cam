# Ball Detection Improvement Pipeline (Garage)

## Goal
Improve 3D ball detection stability and accuracy in the garage arena, using fixed known ground-truth positions plus dynamic stress tests.

This protocol is for:
- `garage_lab_combined/cal/intrinsics/*`
- `garage_lab_combined/cal/extrinsics/extrinsics_final.json`
- `garage_lab_combined/cal/extrinsics/Dimensions.txt`

Use the same camera setup during the whole session.

## Units And Frame
- All coordinates in this document are in `mm`.
- Processing output is in `mm`.
- Ball position for GT is the **ball center**.

## Session Setup
```bash
SESSION="garage_lab_combined/gt_eval/ball_tuning_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SESSION"/{clips,results,renders,logs}
EXTR="garage_lab_combined/cal/extrinsics/extrinsics_final.json"
INTR="garage_lab_combined/cal/intrinsics"
CFG="garage_lab_combined/config/cameras.yaml"
```

## Static GT Dataset: 36 Fixed Points
Grid definition:
- `X = 3000, 4000, 5000 mm`
- `Y = 2300, 1600, 1000 mm`
- `Z = 200, 750, 1300, 1800 mm`

Total: `3 x 3 x 4 = 36` trials (`B001..B036`).

| Trial | X (mm) | Y (mm) | Z (mm) |
|---|---:|---:|---:|
| B001 | 3000 | 2300 | 200 |
| B002 | 4000 | 2300 | 200 |
| B003 | 5000 | 2300 | 200 |
| B004 | 3000 | 1600 | 200 |
| B005 | 4000 | 1600 | 200 |
| B006 | 5000 | 1600 | 200 |
| B007 | 3000 | 1000 | 200 |
| B008 | 4000 | 1000 | 200 |
| B009 | 5000 | 1000 | 200 |
| B010 | 3000 | 2300 | 700 |
| B011 | 4000 | 2300 | 700 |
| B012 | 5000 | 2300 | 700 |
| B013 | 3000 | 1600 | 700 |
| B014 | 4000 | 1600 | 700 |
| B015 | 5000 | 1600 | 700 |
| B016 | 3000 | 1000 | 700 |
| B017 | 4000 | 1000 | 700 |
| B018 | 5000 | 1000 | 700 |
| B019 | 3000 | 2300 | 1200 |
| B020 | 4000 | 2300 | 1200 |
| B021 | 5000 | 2300 | 1200 |
| B022 | 3000 | 1600 | 1200 |
| B023 | 4000 | 1600 | 1200 |
| B024 | 5000 | 1600 | 1200 |
| B025 | 3000 | 1000 | 1200 |
| B026 | 4000 | 1000 | 1200 |
| B027 | 5000 | 1000 | 1200 |
| B028 | 3000 | 2300 | 1800 |
| B029 | 4000 | 2300 | 1800 |
| B030 | 5000 | 2300 | 1800 |
| B031 | 3000 | 1600 | 1800 |
| B032 | 4000 | 1600 | 1800 |
| B033 | 5000 | 1600 | 1800 |
| B034 | 3000 | 1000 | 1800 |
| B035 | 4000 | 1000 | 1800 |
| B036 | 5000 | 1000 | 1800 |

## Static Capture Order (By Fixed X,Y Then Sweep Z)
Use this recording order so each `(X,Y)` is tested at all 4 heights before moving to next `(X,Y)`:

1. `B001 -> B010 -> B019 -> B028`  (`X=3000, Y=2300`, `Z=200,700,1200,1800`)
2. `B002 -> B011 -> B020 -> B029`  (`X=4000, Y=2300`, `Z=200,700,1200,1800`)
3. `B003 -> B012 -> B021 -> B030`  (`X=5000, Y=2300`, `Z=200,700,1200,1800`)
4. `B004 -> B013 -> B022 -> B031`  (`X=3000, Y=1600`, `Z=200,700,1200,1800`)
5. `B005 -> B014 -> B023 -> B032`  (`X=4000, Y=1600`, `Z=200,700,1200,1800`)
6. `B006 -> B015 -> B024 -> B033`  (`X=5000, Y=1600`, `Z=200,700,1200,1800`)
7. `B007 -> B016 -> B025 -> B034`  (`X=3000, Y=1000`, `Z=200,700,1200,1800`)
8. `B008 -> B017 -> B026 -> B035`  (`X=4000, Y=1000`, `Z=200,700,1200,1800`)
9. `B009 -> B018 -> B027 -> B036`  (`X=5000, Y=1000`, `Z=200,700,1200,1800`)

## Capture Protocol For Each Static Trial
1. Place a rigid holder at the target coordinate.
2. Place ball center exactly at the coordinate.
3. Keep scene static 3-4 seconds.
4. Record one synchronized 4-camera clip.
5. Log trial id and notes in `"$SESSION/logs/trials_notes.csv"`.

Recommended clip command pattern:
```bash
./venv/bin/python garage_lab_combined/scripts/record_short_clips_multi.py \
  --config "$CFG" \
  --out-dir "$SESSION/clips" \
  --prefix "B001" \
  --start-index 1 \
  --clips 1 \
  --duration-sec 4 \
  --width 1280 --height 720 --fps 15 \
  --ext avi --out-codec MJPG --show
```

## Dynamic Validation Clips

### 1) `ball_slow` (20s): gentle movement
Purpose:
- Check temporal stability.
- Check that 3D track stays continuous and does not jitter at low speed.

How to perform:
- Move ball smoothly by hand in arcs/lines.
- Keep speed low (`~0.2-0.8 m/s`).
- Avoid sudden stops and sharp direction changes.
- Keep ball visible in at least 2 cameras at all times.

What to look for:
- No large 3D jumps.
- Stable trajectory with low frame-to-frame noise.
- Small reprojection error.

### 2) `ball_fast` (20s): real throws
Purpose:
- Stress test detection under motion blur and acceleration.
- Measure dropouts and outlier rejection behavior.

How to perform:
- Real throws through center and near walls.
- Include forward/back and diagonal throws.
- Include a few bounce-like motions near floor.
- Avoid full occlusion by body for long segments.

What to look for:
- Acceptable detection coverage during high speed.
- Outlier spikes are rejected.
- 3D points remain inside arena bounds.

### 3) `no_ball` (15s): background-only false positive check
Purpose:
- Measure false positives when no ball exists in scene.

How to perform:
- Remove ball from arena.
- Keep normal lighting.
- Include person motion and static periods.
- Include reflective/background clutter normally present in garage.

What to look for:
- Ideally zero ball detections.
- If detections appear, inspect camera and frame causing them.

## Dynamic Clip Recording Commands
```bash
./venv/bin/python garage_lab_combined/scripts/record_short_clips_multi.py \
  --config "$CFG" \
  --out-dir "$SESSION/clips" \
  --prefix ball_slow \
  --start-index 1 \
  --clips 1 \
  --duration-sec 20 \
  --width 1280 --height 720 --fps 15 \
  --ext avi --out-codec MJPG --show

./venv/bin/python garage_lab_combined/scripts/record_short_clips_multi.py \
  --config "$CFG" \
  --out-dir "$SESSION/clips" \
  --prefix ball_fast \
  --start-index 1 \
  --clips 1 \
  --duration-sec 20 \
  --width 1280 --height 720 --fps 15 \
  --ext avi --out-codec MJPG --show

./venv/bin/python garage_lab_combined/scripts/record_short_clips_multi.py \
  --config "$CFG" \
  --out-dir "$SESSION/clips" \
  --prefix no_ball \
  --start-index 1 \
  --clips 1 \
  --duration-sec 15 \
  --width 1280 --height 720 --fps 15 \
  --ext avi --out-codec MJPG --show
```

## Processing Baseline (No Pose)
Use this for ball-only analysis first:
```bash
./venv/bin/python garage_lab_combined/scripts/process_4cam_to_3d.py \
  --video-east  "$SESSION/clips/ball_fast_001/camEast.avi" \
  --video-north "$SESSION/clips/ball_fast_001/camNorth.avi" \
  --video-south "$SESSION/clips/ball_fast_001/camSouth.avi" \
  --video-west  "$SESSION/clips/ball_fast_001/camWest.avi" \
  --intrinsics-dir "$INTR" \
  --extrinsics "$EXTR" \
  --out "$SESSION/results/ball_fast_raw.json" \
  --conf 0.25 \
  --ball-min-cams 2 \
  --ball-max-reproj-px 18 \
  --ball-max-speed-mps 0 \
  --ball-ema-alpha 0 \
  --no-pose
```

## Minimal Acceptance Targets
- Static points:
  - Mean 3D error under `120 mm`
  - P95 error under `200 mm`
- Dynamic:
  - `ball_slow`: no major spikes (`>800 mm` frame jump ideally 0)
  - `ball_fast`: robust detection with controlled outliers
- `no_ball`:
  - false positives close to 0

## Output Checklist Before Moving On
- 36 static clips recorded (`B001..B036`)
- 3 dynamic clips recorded (`ball_slow`, `ball_fast`, `no_ball`)
- Raw JSON outputs generated for all clips
- Quick metric report generated (coverage, jumps, reprojection, false positives)

After this dataset is complete, proceed to parameter sweep and final model/config lock.
