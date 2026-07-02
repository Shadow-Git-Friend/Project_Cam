#!/usr/bin/env bash
# lowlag (6-USB rig): minimum perceived pose latency + ball tracking on the
# CURRENT six-webcam mirrored-Y setup (cameras_6usb_test.yaml, intrinsics
# calibrated at 1280x720, extrinsics_usb6, world-y-mirror).
#
# Keep `scripts/uvc_keeper.py --watch` running in another terminal for the C920s.
#
# Lag levers (vs the stock usb6 scripts):
#   --kalman-measured-dt        propagate joint KFs by real elapsed time. On
#                               this rig the effective skeleton update rate is
#                               "any camera refreshed" (~aggregate fps), not
#                               --fps, so the fixed 1/fps step badly skews KF
#                               velocities and predict-ahead.
#   --pose-latency-comp-ms 100  display-only: render joints from the KF
#                               prediction ~capture+inference delay ahead. UDP
#                               and joints_state unchanged.
#   --pose-every 1              TRT pose is cheap; no reason to skip frames.
#   --pose-imgsz 640            infer pose at 640 instead of the engine default
#                               1280 — 640x360 frames gain nothing from 1280
#                               letterboxing, and 640 is ~3-4x less compute.
#
# Ball tracking is ENABLED here (the stock usb6 scripts pass --no-track-ball).
#   TRACK_BALL=0  to disable it for a pose-only session.
#   --ball-conf 0.25 is safe because the KF reprojection gate filters noise;
#   --ball-single-cam-fallback covers moments only one camera sees the ball.
#   ball-imgsz is auto: 672 at the USB2-safe 640x360, 960 when you override
#   PROJECT_CAM_WIDTH=1280 (upsampling 360p frames to 960 buys nothing).
#
# Optional live SMPL avatar (async worker; never blocks the loop):
#   SMPL_MODEL_PATH=/path/to/smpl [SMPL_DEVICE=cuda:0] ./Parallel_working/run_live_lowlag.sh
#
# A/B against old display behaviour:
#   ./Parallel_working/run_live_lowlag.sh --no-kalman-measured-dt --pose-latency-comp-ms 0
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p Parallel_working/output

# 640x360 keeps six cameras inside the USB2 budget; 1280x720 only after the
# cameras move to powered USB3 hubs.
#
# FPS 25 (was 5): the stock usb6 scripts pinned 5 to ride out concurrent-
# startup starvation on the deep hub, but the generic 1080P cams ignore 5 and
# stream 25 anyway, so steady-state bandwidth already carries ~25 fps. Higher
# capture rate = fresher frames (max_age ~200 ms -> ~40 ms) even when the
# processing loop runs slower. If cameras fail to open after the retries,
# fall back: PROJECT_CAM_FPS=5 ./Parallel_working/run_live_lowlag.sh
WIDTH="${PROJECT_CAM_WIDTH:-640}"
HEIGHT="${PROJECT_CAM_HEIGHT:-360}"
FPS="${PROJECT_CAM_FPS:-25}"

POSE_MODEL="yolo11m-pose.engine"
[ -f "$POSE_MODEL" ] || POSE_MODEL="yolo11m-pose.pt"

# Current engines carry a batch<=4 TRT optimization profile, so 6 cameras run
# chunked 4+2 per model (correct, ~15 ms slower than one call). After
# re-exporting BOTH engines with `export_models_tensorrt.py --yolo-batch 6`
# (do it while the viewer is NOT running — the build needs the GPU), set
# MAX_BATCH=6 here or in the environment for single-call inference.
MAX_BATCH="${MAX_BATCH:-4}"

BALL_ARGS=(--ball-device cuda:0 --ball-every 1 --ball-conf 0.25 --ball-single-cam-fallback)
if [ "$WIDTH" -ge 960 ]; then
  BALL_ARGS+=(--ball-imgsz 960)
else
  BALL_ARGS+=(--ball-imgsz 672)
fi
if [ "${TRACK_BALL:-1}" = "0" ]; then
  BALL_ARGS=(--no-track-ball)
fi

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
  --config garage_lab_combined/config/cameras_6usb_test.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics_usb6_1280x720 \
  --extrinsics garage_lab_combined/cal/extrinsics_usb6/extrinsics_usb6.json \
  --dimensions garage_lab_combined/cal/extrinsics_usb6/Dimensions_mirrored_y.txt \
  --no-uvc-controls \
  --world-y-mirror \
  --no-invert-y-axis-display \
  --draw-global-axes --global-axis-len-mm 900 \
  --pose-device cuda:0 --pose-backend yolopose --yolopose-model "$POSE_MODEL" \
  --pose-max-batch "$MAX_BATCH" \
  --ball-max-batch "$MAX_BATCH" \
  --pose-imgsz 640 \
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS" --fourcc MJPG \
  --pose-every 1 --viz-every 1 --mosaic-every 4 \
  --no-show-2d --show-3d --viz-backend cv2 --viz-width 1600 --viz-height 900 \
  --render-theme cinematic --show-thumbnails \
  --camera-open-retries 20 --camera-open-retry-delay 5 \
  --display-filter oneeuro \
  --ema-alpha 0.55 \
  --ema-snap-thresh-mm 80 \
  --joint-stale-frames 8 \
  --max-frame-age-ms 350 \
  --kalman-measured-dt \
  --pose-latency-comp-ms 100 \
  --predict-ahead-ms 300 \
  --no-show-ghost-skeleton \
  --kalman-process-noise 500 \
  --kalman-measurement-noise 10 \
  --pose-max-reproj-px 40 \
  "${BALL_ARGS[@]}" \
  --perf-log-every 60 \
  --perf-jsonl "Parallel_working/output/perf_lowlag_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 --udp-target-port 5005 \
  --udp-target-joints nose,left_shoulder,right_shoulder,left_elbow,right_elbow,left_wrist,right_wrist,left_hip,right_hip,left_knee,right_knee,left_ankle,right_ankle \
  --udp-target-conf-min 0.45 --udp-target-cams-min 2 \
  "${SMPL_ARGS[@]}" \
  "$@"
