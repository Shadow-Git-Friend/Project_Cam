#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

EXERCISE="${1:-squat}"
if [ "$#" -gt 0 ]; then
  shift
fi

POSE_MODEL="${PROJECT_CAM_POSE_MODEL:-yolo11m-pose.engine}"
if [ ! -f "$POSE_MODEL" ]; then
  POSE_MODEL="yolo11m-pose.pt"
fi
WIDTH="${PROJECT_CAM_ASSESSMENT_WIDTH:-1920}"
HEIGHT="${PROJECT_CAM_ASSESSMENT_HEIGHT:-1080}"
FPS="${PROJECT_CAM_ASSESSMENT_FPS:-30}"

PYTHONPATH=src ./venv/bin/python Parallel_working/scripts/live_4cam_arena_view_parallel.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --no-world-y-mirror \
  --invert-y-axis-display \
  --no-track-ball \
  --pose-device cuda:0 \
  --pose-backend yolopose \
  --yolopose-model "$POSE_MODEL" \
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS" \
  --pose-every 1 \
  --viz-every 1 \
  --mosaic-every 2 \
  --no-show-2d --no-show-3d \
  --viz-backend cv2 \
  --viz-width 1180 --viz-height 720 \
  --ema-alpha 0.45 \
  --ema-snap-thresh-mm 80 \
  --display-smooth-alpha 0.45 \
  --joint-stale-frames 8 \
  --max-frame-age-ms 150 \
  --predict-ahead-ms 0 \
  --perf-log-every 60 \
  --coach-overlay \
  --coach-exercise "$EXERCISE" \
  "$@"
