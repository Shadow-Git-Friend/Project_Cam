#!/usr/bin/env bash
# fastest: Both YOLO ball + YOLO-Pose on TensorRT FP16 + Kalman prediction
# Expected total pipeline: ~50ms per frame (vs ~200ms baseline)
#   - Ball detection: 8.1ms (TRT) instead of 8.7ms (PyTorch)
#   - Pose estimation: 6.2ms/cam (TRT) instead of 38.5ms/cam (MMPose)
#   - 3D render: ~2ms (cv2) instead of ~300ms (matplotlib)
#   - Kalman prediction: <0.1ms overhead
#   - pose-every 1 (can afford it now that pose is 6ms not 80ms)
#
# Prerequisites:
#   - TensorRT engines must be built first:
#     python Parallel_working/scripts/export_models_tensorrt.py \
#       --yolo-model garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt \
#       --yolo-format engine --yolo-half
#   - yolo11m-pose.engine must exist (auto-built on first run of yolopose profile)
set -euo pipefail

cd /home/hanush/Desktop/Project_Cam
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p Parallel_working/output

# Use TRT engines if available, fall back to .pt
BALL_MODEL="garage-20260217T113109Z-3-001/garage/y26s_v1_garage.engine"
if [ ! -f "$BALL_MODEL" ]; then
  BALL_MODEL="garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt"
  echo "[INFO] Ball TRT engine not found, using PyTorch model"
fi

POSE_MODEL="yolo11m-pose.engine"
if [ ! -f "$POSE_MODEL" ]; then
  POSE_MODEL="yolo11m-pose.pt"
  echo "[INFO] Pose TRT engine not found, using PyTorch model"
fi

./venv/bin/python Parallel_working/scripts/live_4cam_arena_view_parallel.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --ball-model "$BALL_MODEL" \
  --no-world-y-mirror \
  --invert-y-axis-display \
  --draw-global-axes \
  --global-axis-len-mm 900 \
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
  --perf-jsonl "Parallel_working/output/perf_fastest_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,nose,body_center \
  --udp-target-conf-min 0.45 \
  --udp-target-cams-min 3 \
  "$@"
