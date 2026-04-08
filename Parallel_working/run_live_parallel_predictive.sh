#!/usr/bin/env bash
# predictive: Kalman-filtered prediction + OpenCV 3D renderer + adaptive EMA
# Built on smooth_v2, adds:
#   - predict-ahead-ms 400 (compensates ~400ms total system + ball flight latency)
#   - Kalman filter per joint (constant-velocity model, process noise 50, measurement noise 80)
#   - Ghost skeleton in 3D view showing predicted future position
#   - UDP packets include both current and predicted joint positions
#
# Usage:
#   ./Parallel_working/run_live_parallel_predictive.sh
#   ./Parallel_working/run_live_parallel_predictive.sh --predict-ahead-ms 300  # override
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
  --predict-ahead-ms 400 \
  --kalman-process-noise 50 \
  --kalman-measurement-noise 80 \
  --show-ghost-skeleton \
  --predict-max-uncertainty-mm 500 \
  --perf-log-every 60 \
  --perf-jsonl "Parallel_working/output/perf_predictive_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,nose,body_center \
  --udp-target-conf-min 0.45 \
  --udp-target-cams-min 3 \
  "$@"
