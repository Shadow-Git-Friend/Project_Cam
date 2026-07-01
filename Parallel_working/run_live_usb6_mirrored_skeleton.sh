#!/usr/bin/env bash
# Live 6-USB mirrored-Y arena skeleton view.
# Keep scripts/uvc_keeper.py --watch running in another terminal for the C920s.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

# USB2-safe default for the current six-webcam rig. The generic 1080P cameras
# ignore 5 FPS at 1280x720 MJPG and stream at 25 FPS, which can starve the
# deep-hub camera during concurrent startup. Override to 1280x720 after moving
# the cameras to powered USB3 hubs.
WIDTH="${PROJECT_CAM_WIDTH:-640}"
HEIGHT="${PROJECT_CAM_HEIGHT:-360}"
FPS="${PROJECT_CAM_FPS:-5}"

POSE_MODEL="yolo11m-pose.engine"
if [ ! -f "$POSE_MODEL" ]; then
  POSE_MODEL="yolo11m-pose.pt"
fi

./venv/bin/python Parallel_working/scripts/live_4cam_arena_view_parallel.py \
  --config garage_lab_combined/config/cameras_6usb_test.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics_usb6_1280x720 \
  --extrinsics garage_lab_combined/cal/extrinsics_usb6/extrinsics_usb6.json \
  --dimensions garage_lab_combined/cal/extrinsics_usb6/Dimensions_mirrored_y.txt \
  --no-uvc-controls \
  --no-track-ball \
  --world-y-mirror \
  --no-invert-y-axis-display \
  --draw-global-axes \
  --global-axis-len-mm 900 \
  --pose-device cuda:0 \
  --pose-backend yolopose \
  --yolopose-model "$POSE_MODEL" \
  --pose-max-batch 4 \
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS" --fourcc MJPG \
  --pose-every 2 \
  --viz-every 1 \
  --mosaic-every 4 \
  --no-show-2d --show-3d \
  --viz-backend cv2 \
  --viz-width 1600 --viz-height 900 \
  --avatar-body --avatar-markers \
  --camera-open-retries 20 --camera-open-retry-delay 5 \
  --ema-alpha 0.55 \
  --ema-snap-thresh-mm 80 \
  --display-smooth-alpha 0.75 \
  --joint-stale-frames 8 \
  --max-frame-age-ms 350 \
  --predict-ahead-ms 0 \
  --kalman-process-noise 500 \
  --kalman-measurement-noise 10 \
  --no-show-ghost-skeleton \
  --count-reps \
  --perf-log-every 60 \
  "$@"
