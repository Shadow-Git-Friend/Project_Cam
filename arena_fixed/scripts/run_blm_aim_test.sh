#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 5 ]; then
  cat <<'EOF'
Usage:
  bash arena_fixed/scripts/run_blm_aim_test.sh <joint> <x_mm> <y_mm> <z_mm> <label> [yaw_trim_deg] [pitch_trim_deg]

Example:
  bash arena_fixed/scripts/run_blm_aim_test.sh right_knee 4600 1600 1400 H2
  bash arena_fixed/scripts/run_blm_aim_test.sh right_knee 4600 2100 1400 H3 -1.0 0.0
EOF
  exit 1
fi

JOINT="$1"
X_MM="$2"
Y_MM="$3"
Z_MM="$4"
LABEL="$5"
YAW_TRIM="${6:-0.0}"
PITCH_TRIM="${7:-0.0}"

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="garage_lab_combined/output/blm_logs"
mkdir -p "$LOG_DIR"
LOG_PATH="$LOG_DIR/aim_stage2_${LABEL}_${TS}.jsonl"

cd /home/hanush/Desktop/Project_Cam

echo "[INFO] joint=$JOINT target=($X_MM,$Y_MM,$Z_MM) yaw_trim=$YAW_TRIM pitch_trim=$PITCH_TRIM"
echo "[INFO] log=$LOG_PATH"
echo "[INFO] In runtime terminal type: start"

./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 \
  --launcher-x-mm 600 --launcher-y-mm 1560 --launcher-z-mm 500 \
  --launcher-yaw-deg 0 \
  --targets "$JOINT" \
  --static-target-x-mm "$X_MM" \
  --static-target-y-mm "$Y_MM" \
  --static-target-z-mm "$Z_MM" \
  --static-target-joint "$JOINT" \
  --min-conf 0.50 \
  --min-cams 3 \
  --stable-frames 10 \
  --stable-window-sec 1.8 \
  --stable-std-mm 15 \
  --max-abs-angle-deg 40 \
  --yaw-trim-deg "$YAW_TRIM" \
  --pitch-trim-deg "$PITCH_TRIM" \
  --max-target-events 1 \
  --run-once-per-start \
  --no-return-center-after-each-target \
  --no-shoot-enabled \
  --aim-only-wheel-rpm 0 \
  --no-setzero-on-start \
  --home-on-start \
  --home-on-exit \
  --dry-run-log-jsonl "$LOG_PATH"
