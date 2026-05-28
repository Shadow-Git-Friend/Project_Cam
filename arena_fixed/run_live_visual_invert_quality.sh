#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
WIDTH="${PROJECT_CAM_WIDTH:-1920}"
HEIGHT="${PROJECT_CAM_HEIGHT:-1080}"
FPS="${PROJECT_CAM_FPS:-30}"

# Hybrid profile:
# - Uses arena_fixed world frame (the one you validated)
# - Keeps high-quality pose settings from the stable command
./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --no-world-y-mirror \
  --invert-y-axis-display \
  --draw-global-axes \
  --global-axis-len-mm 900 \
  --ball-device cuda:0 \
  --pose-device cuda:0 \
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS" \
  --pose-every 1 \
  --ball-every 1 \
  --viz-every 1 \
  --show-2d --show-3d \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,nose,body_center \
  --udp-target-conf-min 0.50 \
  --udp-target-cams-min 4 \
  "$@"
