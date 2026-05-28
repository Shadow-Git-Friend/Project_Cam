#!/usr/bin/env bash
# =============================================================================
# LIVE BLM: Full pipeline + BLM aim overlay (combines yolopose + demo)
# =============================================================================
# Shows: 4 camera feeds + 3D arena view + Kalman prediction + BLM aim panel
# Use with live_aim_test.py in Terminal 2 for interactive aiming via serial.
#
# Usage:
#   ./Parallel_working/run_live_blm.sh                          # default: right_hip
#   ./Parallel_working/run_live_blm.sh --demo-blm-joint left_shoulder
#   ./Parallel_working/run_live_blm.sh --yolopose-model yolo11m-pose.engine  # TRT
# =============================================================================
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
  --pose-backend yolopose \
  --yolopose-model yolo11m-pose.pt \
  --width 1280 --height 720 --fps 15 \
  --pose-every 1 \
  --ball-every 1 \
  --viz-every 1 \
  --mosaic-every 2 \
  --show-2d --show-3d \
  --viz-backend cv2 \
  --viz-width 1280 --viz-height 720 \
  --ema-alpha 0.25 \
  --ema-snap-thresh-mm 80 \
  --display-smooth-alpha 0.45 \
  --joint-stale-frames 8 \
  --max-frame-age-ms 150 \
  --predict-ahead-ms 400 \
  --kalman-process-noise 500 \
  --kalman-measurement-noise 10 \
  --show-ghost-skeleton \
  --perf-log-every 60 \
  --perf-jsonl "Parallel_working/output/perf_blm_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints nose,right_hip,left_hip,right_shoulder,left_shoulder,right_elbow,left_elbow,right_wrist,left_wrist,right_knee,left_knee,right_ankle,left_ankle \
  --udp-target-conf-min 0.45 \
  --udp-target-cams-min 3 \
  --demo-blm \
  --demo-blm-joint right_knee \
  --demo-blm-launcher-x-mm 600 \
  --demo-blm-launcher-y-mm 1560 \
  --demo-blm-launcher-z-mm 500 \
  --demo-blm-yaw-deg 0 \
  --demo-blm-speed-mps 10 \
  --demo-blm-correction-mode linear \
  "$@"
