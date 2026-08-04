#!/usr/bin/env bash
# =============================================================================
# LIVE 6-USB + BLM: cinematic 3D arena + UDP target broadcast + aim overlay.
# Terminal 1: scripts/uvc_keeper.py --watch
# Terminal 2 (aim-only, SAFE):  garage_lab_combined/scripts/live_aim_test.py
#            --serial-port /dev/ttyUSB0 --no-shoot-enabled ...
# This viewer NEVER actuates the launcher; it only triangulates the skeleton,
# broadcasts the chosen joint over UDP, and draws where the BLM would aim.
# Shooting happens only in live_aim_test.py after the aim is validated.
# =============================================================================
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

# USB2-safe default for the current six-webcam rig. The generic 1080P cameras
# ignore 5 FPS at 1280x720 MJPG and stream at 25 FPS, which can starve the
# deep-hub camera during concurrent startup. Override to 1280x720 after moving
# the cameras to powered USB3 hubs.
WIDTH="${PROJECT_CAM_WIDTH:-640}"
HEIGHT="${PROJECT_CAM_HEIGHT:-360}"
FPS="${PROJECT_CAM_FPS:-5}"

POSE_MODEL="yolo11m-pose.engine"
[ -f "$POSE_MODEL" ] || POSE_MODEL="yolo11m-pose.pt"

# BLM mounting position in the (mirrored, mm) world frame — SET TO YOUR REAL RIG.
BLM_X="${BLM_X_MM:-600}"
BLM_Y="${BLM_Y_MM:-1525}"
BLM_Z="${BLM_Z_MM:-500}"
BLM_JOINT="${BLM_JOINT:-right_shoulder}"

./venv/bin/python Parallel_working/scripts/live_4cam_arena_view_parallel.py \
  --config garage_lab_combined/config/cameras_6usb_test.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics_usb6_1280x720 \
  --extrinsics garage_lab_combined/cal/extrinsics_usb6/extrinsics_usb6.json \
  --dimensions garage_lab_combined/cal/extrinsics_usb6/Dimensions_mirrored_y.txt \
  --no-uvc-controls \
  --no-track-ball \
  --world-y-mirror \
  --no-invert-y-axis-display \
  --draw-global-axes --global-axis-len-mm 900 \
  --pose-device cuda:0 --pose-backend yolopose --yolopose-model "$POSE_MODEL" \
  --pose-max-batch 4 \
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS" --fourcc MJPG \
  --pose-every 1 --viz-every 1 --mosaic-every 4 \
  --no-show-2d --show-3d --viz-backend cv2 --viz-width 1600 --viz-height 900 \
  --camera-open-retries 20 --camera-open-retry-delay 5 \
  --render-theme cinematic --show-thumbnails \
  --display-filter oneeuro \
  --joint-stale-frames 8 --max-frame-age-ms 350 \
  --predict-ahead-ms 300 --kalman-process-noise 500 --kalman-measurement-noise 10 \
  --show-ghost-skeleton \
  --pose-max-reproj-px 40 \
  --udp-target-host 127.0.0.1 --udp-target-port 5005 \
  --udp-target-joints nose,left_shoulder,right_shoulder,left_elbow,right_elbow,left_wrist,right_wrist,left_hip,right_hip,left_knee,right_knee,left_ankle,right_ankle \
  --udp-target-conf-min 0.45 --udp-target-cams-min 2 \
  --demo-blm --demo-blm-joint "$BLM_JOINT" \
  --demo-blm-launcher-x-mm "$BLM_X" --demo-blm-launcher-y-mm "$BLM_Y" --demo-blm-launcher-z-mm "$BLM_Z" \
  --demo-blm-yaw-deg 0 --demo-blm-speed-mps 10 --demo-blm-correction-mode linear \
  --count-reps \
  --perf-log-every 60 \
  "$@"
