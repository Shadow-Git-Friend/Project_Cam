#!/usr/bin/env bash
# smooth_v2: OpenCV 3D renderer + adaptive EMA + display interpolation
# Key changes vs balanced:
#   - viz-backend cv2 (replaces matplotlib: ~2ms instead of ~300ms → kills 0.5-1s delay)
#   - ema-snap-thresh-mm 80 (jumps/lunges snap instantly, normal movement stays smooth)
#   - display-smooth-alpha 0.45 (fills non-pose frames with interpolation)
#   - ema-alpha 0.45 (responsive triangulation EMA)
#   - pose-every 2, ball-every 1, viz-every 1
#   - mosaic-every 2 (saves ~8ms per skipped frame)
#   - No render-worker-process needed (cv2 backend is fast enough inline)
set -euo pipefail

cd /home/hanush/Desktop/Project_Cam
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
  --width 1280 --height 720 --fps 15 \
  --pose-every 2 \
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
  --perf-log-every 60 \
  --perf-jsonl "Parallel_working/output/perf_smooth_v2_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,nose,body_center \
  --udp-target-conf-min 0.45 \
  --udp-target-cams-min 3 \
  "$@"
