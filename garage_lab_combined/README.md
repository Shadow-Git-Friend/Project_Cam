# Garage Lab Combined

This workspace will hold the unified garage pipeline (mm units) at 1280x720.

## Current assumptions
- Units: mm
- Runtime resolution: 1280x720
- Target FPS: 15 (capture), 5 (inference)
- Cameras: Hikvision DS‑E12 (fixed positions)

## Configs
- `config/runtime.yaml`: runtime resolution + FPS targets
- `config/cameras.yaml`: device mapping for camNorth/East/South/West

## Next steps
1. Generate new intrinsics at 1280x720 with a ChArUco board.
2. Validate intrinsics (corner coverage + reprojection error).
3. Define 1x1m goal plane and integrate into 3D visualization.
4. Run garage test capture and build unified visualization.

## Auto-capture ChArUco images (hands-free)
Use this when the PC is far away. It auto-saves a frame if the board is detected
with enough ChArUco corners for 3 seconds.

Example:
```bash
python garage_lab_combined/scripts/auto_capture_charuco_multi.py \
  --config garage_lab_combined/config/cameras.yaml \
  --out-dir garage_lab_combined/cal/captures \
  --min-corners 25 \
  --hold-sec 0 \
  --target-count 30
```

Preview windows are enabled by default. Use `--no-show` to disable.

Each camera saves into its own folder:
- `garage_lab_combined/cal/captures/camNorth/`
- `garage_lab_combined/cal/captures/camEast/`
- `garage_lab_combined/cal/captures/camSouth/`
- `garage_lab_combined/cal/captures/camWest/`

## Record Short 4-Cam Clips (2-3 sec)
Use this for ground-truth tests (ball/body static points).

Example (record 15 clips, each 2.5 sec):
```bash
python garage_lab_combined/scripts/record_short_clips_multi.py \
  --config garage_lab_combined/config/cameras.yaml \
  --out-dir garage_lab_combined/test_clips \
  --prefix gt \
  --duration-sec 2.5 \
  --clips 15
```

Controls:
- Press `r` to record one clip.
- Press `q` to stop.

Each clip is stored as:
- `garage_lab_combined/test_clips/gt_001/camEast.mkv`
- `garage_lab_combined/test_clips/gt_001/camNorth.mkv`
- `garage_lab_combined/test_clips/gt_001/camSouth.mkv`
- `garage_lab_combined/test_clips/gt_001/camWest.mkv`
- `garage_lab_combined/test_clips/gt_001/metadata.json`

## Optimize 3D Motion + Presentation Render
Clean outliers in motion JSON, then render a presentation-grade video.

```bash
python garage_lab_combined/scripts/optimize_motion_capture.py \
  --in-motion garage_lab_combined/output/motion_capture_data_garage_v2.json \
  --out-motion garage_lab_combined/output/motion_capture_data_garage_v3_optimized.json

python garage_lab_combined/scripts/render_arena_ball_skeleton.py \
  --motion garage_lab_combined/output/motion_capture_data_garage_v3_optimized.json \
  --out-dir garage_lab_combined/output/frames_arena_v3 \
  --out-video garage_lab_combined/output/garage_arena_ball_skel_presentation_v3.mp4 \
  --smooth-window 5 \
  --no-auto-center \
  --crf 18
```

For extra-stable stakeholder export (v4):
```bash
python garage_lab_combined/scripts/optimize_motion_capture.py \
  --in-motion garage_lab_combined/output/motion_capture_data_garage_v3_optimized.json \
  --out-motion garage_lab_combined/output/motion_capture_data_garage_v4_ultrastable.json \
  --joint-median 5 --joint-smooth 7 \
  --kinematic-refine --kinematic-iters 3

python garage_lab_combined/scripts/render_arena_ball_skeleton.py \
  --motion garage_lab_combined/output/motion_capture_data_garage_v4_ultrastable.json \
  --out-dir garage_lab_combined/output/frames_arena_v4 \
  --out-video garage_lab_combined/output/garage_arena_ball_skel_presentation_v4.mp4 \
  --smooth-window 7 --no-auto-center --crf 16 --dpi 180
```

## Render AprilTag Arena (Friend-Style 360)
Render a clean 3D arena with AprilTag planes and camera poses (static + orbit video):

```bash
python garage_lab_combined/scripts/render_apriltag_arena_360.py \
  --mode both \
  --out-image garage_lab_combined/output/arena_apriltag_static_v2.png \
  --out-video garage_lab_combined/output/arena_apriltag_360_v2.mp4
```

## Live 4-Cam Arena View (Ball + Skeleton)
Live popup with:
- 3D arena + AprilTags + camera poses + ball + skeleton.
- Optional 2D 4-camera mosaic window.

```bash
./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_main.json \
  --dimensions garage_lab_combined/cal/extrinsics/Dimensions.txt \
  --ball-device cuda:0 \
  --pose-device cpu
```

Performance tips:
- If slow, use `--pose-every 3` or `--no-pose`.
- Recommended split: ball on GPU (`--ball-device cuda:0`), pose on CPU (`--pose-device cpu`).

## Reduce Extrinsics Reprojection Error
Use robust AprilTag recalibration with outlier rejection (keeps camera pose close to current `extrinsics_main.json` and removes inconsistent tags):

```bash
python garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py \
  --images-root garage-20260217T113109Z-3-001/garage/Scenario2 \
  --dimensions garage_lab_combined/cal/extrinsics/Dimensions.txt \
  --out garage_lab_combined/cal/extrinsics/extrinsics_robust_s2.json \
  --max-images 50 \
  --tag-median-thresh-px 50 \
  --min-point-error-px 8 \
  --sigma-scale 2.0
```

For your 1280x720 intrinsics set:
```bash
python garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py \
  --images-root garage-20260217T113109Z-3-001/garage/Scenario2 \
  --dimensions garage_lab_combined/cal/extrinsics/Dimensions.txt \
  --unified-intrinsics '' \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --out garage_lab_combined/cal/extrinsics/extrinsics_robust_s2_1280_strict.json \
  --tag-median-thresh-px 40 \
  --min-point-error-px 6 \
  --sigma-scale 1.2
```
