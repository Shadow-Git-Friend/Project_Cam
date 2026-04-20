#!/usr/bin/env bash
# yolopose: YOLO-Pose backend + Kalman prediction + cv2 renderer
# Uses YOLO11m-Pose instead of MMPose (RTMDet+RTMPose):
#   - 6.2x faster pose inference (25ms vs 154ms for 4 cams with TRT)
#   - Same COCO 17-keypoint output format
#   - Single model replaces both person detector + keypoint estimator
#
# For TensorRT acceleration, use .engine file:
#   ./Parallel_working/run_live_parallel_yolopose.sh --yolopose-model yolo11m-pose.engine
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
  --perf-jsonl "Parallel_working/output/perf_yolopose_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,nose,body_center \
  --udp-target-conf-min 0.45 \
  --udp-target-cams-min 3 \
  "$@"
