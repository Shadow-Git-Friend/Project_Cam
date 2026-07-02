#!/usr/bin/env bash
# lowlag: minimum perceived pose latency + best-validated ball detection flags.
#
# What this profile changes vs run_live_parallel_yolopose.sh and why:
#   --yolopose-model yolo11m-pose.engine  TRT FP16, 6.2 ms (vs 8.9 ms .pt)
#   --kalman-measured-dt                  propagate joint KFs by real elapsed
#                                         time; fixes velocity over-estimation
#                                         when the USB rig runs at 15-18 FPS
#                                         while --fps says 30
#   --pose-latency-comp-ms 130            display-only: render joints from the
#                                         KF prediction ~2 capture intervals
#                                         ahead, cancelling capture+inference+
#                                         smoothing delay. UDP unchanged.
#   --ball-imgsz 960                      bounce detection camNorth 58%->98%
#                                         (offline sweep 2026-04-20), +8 ms
#   --ball-conf 0.25                      safe with the KF gate (2026-04-21)
#   --ball-single-cam-fallback            ray->Z-plane when only 1 cam sees it
#
# Optional live SMPL avatar (async worker thread; never blocks the loop):
#   SMPL_MODEL_PATH=/path/to/smpl ./Parallel_working/run_live_lowlag.sh
#   SMPL_DEVICE=cuda:0 to fit on GPU (default cpu; async makes cpu fine).
#
# A/B: append --no-kalman-measured-dt --pose-latency-comp-ms 0 to reproduce
# the old display behaviour exactly.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p Parallel_working/output
WIDTH="${PROJECT_CAM_WIDTH:-1920}"
HEIGHT="${PROJECT_CAM_HEIGHT:-1080}"
FPS="${PROJECT_CAM_FPS:-30}"

SMPL_ARGS=()
if [[ -n "${SMPL_MODEL_PATH:-}" ]]; then
  SMPL_ARGS+=(
    --smpl-avatar
    --smpl-model-path "$SMPL_MODEL_PATH"
    --smpl-device "${SMPL_DEVICE:-cpu}"
    --smpl-fit-every 2
    --smpl-fit-iters 8
  )
fi

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
  --yolopose-model yolo11m-pose.engine \
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS" \
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
  --kalman-measured-dt \
  --pose-latency-comp-ms 130 \
  --predict-ahead-ms 400 \
  --no-show-ghost-skeleton \
  --kalman-process-noise 500 \
  --kalman-measurement-noise 10 \
  --ball-imgsz 960 \
  --ball-conf 0.25 \
  --ball-single-cam-fallback \
  --perf-log-every 60 \
  --perf-jsonl "Parallel_working/output/perf_lowlag_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,nose,body_center \
  --udp-target-conf-min 0.45 \
  --udp-target-cams-min 3 \
  "${SMPL_ARGS[@]}" \
  "$@"
