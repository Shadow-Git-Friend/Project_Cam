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
#   --pose-imgsz 960            LOCKED to the pose engine's export size (see
#                               the POSE_IMGSZ block below — off-size calls
#                               produce garbage detections on TRT engines).
#   (parallel-inference REMOVED 2026-07-02: concurrent ball+pose TRT calls
#    from two threads race on the CUDA stream — pose died every frame with
#    'illegal memory access' on torch 2.1 + TensorRT 10.16. Sequential until
#    the ball worker gets its own CUDA stream/process.)
#   --pose-lr-fix (default on)  relabels per-camera left/right keypoints
#                               against the 3D state; fixes "both legs rise"
#                               during push-up leg raises (front/back cameras
#                               mirror YOLO's left/right on prone poses).
#
# Lightweight live avatar is ENABLED by default when SMPL_MODEL_PATH is not
# set. AVATAR_BODY=0 disables it; AVATAR_MARKERS=1 adds joint/body markers.
#
# Ball tracking is ENABLED here (the stock usb6 scripts pass --no-track-ball).
#   TRACK_BALL=0  to disable it for a pose-only session.
#   --ball-conf 0.25 is safe because the KF reprojection gate filters noise;
#   --ball-single-cam-fallback covers moments only one camera sees the ball.
#   --ball-ballistic-fallback uses gravity-aware single-cam depth during
#   airborne/bounce frames; BALL_BALLISTIC_FALLBACK=0 restores KF-Z fallback.
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

# Capture default 1280x720 (2026-07-02): this is the rig's NATIVE calibration
# resolution (garage_lab_combined/cal/intrinsics_usb6_1280x720 — the intrinsics
# scaling becomes a no-op) and doubles the pixels on a prone/floor body, the
# weakest pose case at 640x360. FPS drops to 15 at this size to stay inside
# the shared USB2 bandwidth (6x 1280x720 MJPG @25 oversubscribes the hub and
# starves cameras at startup).
#
# If cameras fail to open / stall at 1280x720, roll back to the fast-small
# mode:   PROJECT_CAM_WIDTH=640 PROJECT_CAM_HEIGHT=360 PROJECT_CAM_FPS=25 \
#         ./Parallel_working/run_live_lowlag.sh
WIDTH="${PROJECT_CAM_WIDTH:-1280}"
HEIGHT="${PROJECT_CAM_HEIGHT:-720}"
if [ -n "${PROJECT_CAM_FPS:-}" ]; then
  FPS="$PROJECT_CAM_FPS"
elif [ "$WIDTH" -ge 960 ]; then
  FPS=15
else
  FPS=25
fi

POSE_MODEL="yolo11m-pose.engine"
[ -f "$POSE_MODEL" ] || POSE_MODEL="yolo11m-pose.pt"

# Inference size is LOCKED to each engine's export size (pose 960, ball 672).
# Proven on real frames 2026-07-02: a TRT engine only decodes correctly at
# its export imgsz — the "dynamic" profile covers batch, NOT the spatial
# decode. Any other size emits ~300 garbage detections/frame, drowns NMS
# ("NMS time limit exceeded") and empties the arena. If you change POSE_IMGSZ
# you must re-export the pose engine at that size (--yolo-imgsz) first.
POSE_IMGSZ="${POSE_IMGSZ:-960}"

# Both engines were re-exported 2026-07-02 with a batch<=6 TRT optimization
# profile (tight shapes: ball imgsz 672/max 1344, pose imgsz 640/max 1280 —
# verified coexisting in one process), so all six cameras run in ONE call per
# model. If you ever roll back to the *.batch4.engine files, set MAX_BATCH=4
# (chunked 4+2, correct but ~15 ms slower). Re-export while the viewer is NOT
# running — the TRT builder needs free GPU.
MAX_BATCH="${MAX_BATCH:-6}"

# Pixel gates scale with capture width (tuned values are for 1280-wide; the
# same angular error covers half the pixels at 640-wide, so gates halve there
# — unscaled loose gates are what let arm fliers and crouch tangles through).
if [ "$WIDTH" -ge 960 ]; then
  POSE_REPROJ=40; BALL_REPROJ=25; BALL_KF_GATE=150; BALL_MAXBOX=220
else
  POSE_REPROJ=20; BALL_REPROJ=15; BALL_KF_GATE=75; BALL_MAXBOX=110
fi
BALL_IMGSZ="${BALL_IMGSZ:-672}"  # locked to the ball engine's export size
BALL_ARGS=(--ball-device cuda:0 --ball-every 1 --ball-conf 0.25 --ball-single-cam-fallback
           --ball-max-reproj-px "$BALL_REPROJ" --ball-kf-gate-px "$BALL_KF_GATE"
           --ball-max-box-side-px "$BALL_MAXBOX" --ball-imgsz "$BALL_IMGSZ")
if [ "${BALL_BALLISTIC_FALLBACK:-1}" != "0" ]; then
  BALL_ARGS+=(--ball-ballistic-fallback)
fi
if [ "${TRACK_BALL:-1}" = "0" ]; then
  BALL_ARGS=(--no-track-ball)
fi

DEFAULT_AVATAR_BODY=1
if [[ -n "${SMPL_MODEL_PATH:-}" ]]; then
  DEFAULT_AVATAR_BODY=0
fi
AVATAR_ARGS=()
if [ "${AVATAR_BODY:-$DEFAULT_AVATAR_BODY}" != "0" ]; then
  AVATAR_ARGS+=(--avatar-body --avatar-alpha "${AVATAR_ALPHA:-0.74}")
  if [ "${AVATAR_MARKERS:-0}" = "1" ]; then
    AVATAR_ARGS+=(--avatar-markers)
  fi
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
  --pose-imgsz "$POSE_IMGSZ" \
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS" --fourcc MJPG \
  --pose-every 1 --viz-every 1 --mosaic-every 4 \
  --no-show-2d --show-3d --viz-backend cv2 --viz-width 1600 --viz-height 900 \
  --render-theme cinematic --show-thumbnails \
  --camera-open-retries 20 --camera-open-retry-delay 5 \
  --display-filter oneeuro \
  --ema-alpha 0.55 \
  --ema-snap-thresh-mm 80 \
  --joint-stale-frames 5 \
  --max-frame-age-ms 350 \
  --kalman-measured-dt \
  --pose-latency-comp-ms 100 \
  --predict-ahead-ms 300 \
  --no-show-ghost-skeleton \
  --kalman-process-noise 500 \
  --kalman-measurement-noise 10 \
  --pose-max-reproj-px "$POSE_REPROJ" \
  --pose-min-cams 2 \
  "${BALL_ARGS[@]}" \
  --perf-log-every 60 \
  --perf-jsonl "Parallel_working/output/perf_lowlag_${TS}.jsonl" \
  --udp-target-host 127.0.0.1 --udp-target-port 5005 \
  --udp-target-joints nose,left_shoulder,right_shoulder,left_elbow,right_elbow,left_wrist,right_wrist,left_hip,right_hip,left_knee,right_knee,left_ankle,right_ankle \
  --udp-target-conf-min 0.45 --udp-target-cams-min 2 \
  "${AVATAR_ARGS[@]}" \
  "${SMPL_ARGS[@]}" \
  "$@"
