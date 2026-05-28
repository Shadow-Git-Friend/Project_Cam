#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p Parallel_working/output

./venv/bin/python Parallel_working/scripts/live_4cam_arena_view_parallel.py \
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
  --width 960 --height 540 --fps 30 \
  --pose-every 3 \
  --ball-every 3 \
  --viz-every 3 \
  --mosaic-every 3 \
  --no-show-2d --show-3d \
  --render-worker-process \
  --max-frame-age-ms 200 \
  --perf-log-every 60 \
  --perf-jsonl "Parallel_working/output/perf_maxfps_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,nose,body_center \
  --udp-target-conf-min 0.40 \
  --udp-target-cams-min 3 \
  "$@"
