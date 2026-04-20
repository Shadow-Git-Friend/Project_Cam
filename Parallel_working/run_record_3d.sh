#!/usr/bin/env bash
# Record 3D arena + 2D mosaic videos while running the live yolopose pipeline
# with the new yolo26m ball detector. Press 'q' in any cv2 window to stop.
#
# Outputs:
#   Parallel_working/output/recordings/arena3d_<ts>.mp4
#   Parallel_working/output/recordings/mosaic2d_<ts>.mp4
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

TS="$(date +%Y%m%d_%H%M%S)"
REC_DIR="Parallel_working/output/recordings"
mkdir -p "$REC_DIR"

VID_3D="$REC_DIR/arena3d_${TS}.mp4"
VID_2D="$REC_DIR/mosaic2d_${TS}.mp4"

BALL_MODEL="models/ball/yolo26m-672.engine"
if [ ! -f "$BALL_MODEL" ]; then
  BALL_MODEL="models/ball/yolo26m-672.pt"
  echo "[INFO] Ball TRT engine not found, using PyTorch model"
fi

POSE_MODEL="yolo11m-pose.engine"
if [ ! -f "$POSE_MODEL" ]; then
  POSE_MODEL="yolo11m-pose.pt"
fi

echo "[REC] Ball model : $BALL_MODEL"
echo "[REC] Pose model : $POSE_MODEL"
echo "[REC] 3D video   : $VID_3D"
echo "[REC] 2D mosaic  : $VID_2D"
echo "[REC] Press 'q' in any window to stop recording."

./venv/bin/python Parallel_working/scripts/live_4cam_arena_view_parallel.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --no-world-y-mirror \
  --invert-y-axis-display \
  --draw-global-axes \
  --global-axis-len-mm 900 \
  --ball-model "$BALL_MODEL" \
  --ball-device cuda:0 \
  --pose-device cuda:0 \
  --pose-backend yolopose \
  --yolopose-model "$POSE_MODEL" \
  --width 1280 --height 720 --fps 15 \
  --pose-every 1 \
  --ball-every 1 \
  --viz-every 1 \
  --mosaic-every 2 \
  --show-2d --show-3d \
  --viz-backend cv2 \
  --viz-width 960 --viz-height 720 \
  --ema-alpha 0.45 \
  --ema-snap-thresh-mm 80 \
  --display-smooth-alpha 0.45 \
  --joint-stale-frames 8 \
  --max-frame-age-ms 150 \
  --predict-ahead-ms 400 \
  --kalman-process-noise 50 \
  --kalman-measurement-noise 80 \
  --show-ghost-skeleton \
  --perf-log-every 60 \
  --record-video "$VID_3D" \
  --record-mosaic "$VID_2D" \
  --record-fps 15 \
  "$@"
