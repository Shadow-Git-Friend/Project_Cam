#!/usr/bin/env bash
set -euo pipefail

cd /home/hanush/Desktop/Project_Cam

# Debug-only: mirror world by Y and also invert Y-axis labels (Ymax..0).
./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --world-y-mirror \
  --invert-y-axis-display \
  --draw-global-axes \
  --global-axis-len-mm 900 \
  "$@"
