#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
WIDTH="${PROJECT_CAM_WIDTH:-1920}"
HEIGHT="${PROJECT_CAM_HEIGHT:-1080}"
FPS="${PROJECT_CAM_FPS:-30}"

# Industrial debug profile:
# - Display uses mirrored Y frame (operator-friendly)
# - UDP stays in native world frame (controller-friendly)
./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --pose-device cuda:0 \
  --ball-device cuda:0 \
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS" \
  --pose-every 3 --viz-every 3 --ball-every 2 \
  --joint-stale-frames 9 \
  --no-world-y-mirror \
  --display-world-y-mirror \
  --no-udp-world-y-mirror \
  --invert-y-axis-display \
  --draw-global-axes \
  --global-axis-len-mm 900 \
  "$@"
