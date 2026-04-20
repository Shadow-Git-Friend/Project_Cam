#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash arena_fixed/scripts/run_blm_horizontal_only_cycle.sh [yaw_trim_deg] [aim_only_wheel_rpm] [serial_port] [extra launcher_runtime args...]
# Example:
#   bash arena_fixed/scripts/run_blm_horizontal_only_cycle.sh 0.0 650 /dev/ttyUSB0

YAW_TRIM="${1:-0.0}"
AIM_RPM="${2:-650}"
SERIAL_PORT="${3:-/dev/ttyUSB0}"
EXTRA_ARGS=("${@:4}")

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="garage_lab_combined/output/blm_logs"
mkdir -p "$LOG_DIR"
LOG_PATH="$LOG_DIR/horizontal_only_cycle_${TS}.jsonl"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "[INFO] Horizontal-only cycle"
echo "[INFO] yaw_trim_deg=$YAW_TRIM aim_only_wheel_rpm=$AIM_RPM serial=$SERIAL_PORT"
echo "[INFO] log=$LOG_PATH"
if [ "${#EXTRA_ARGS[@]}" -gt 0 ]; then
  echo "[INFO] extra_args=${EXTRA_ARGS[*]}"
fi
echo "[INFO] In runtime terminal type: start"

./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port "$SERIAL_PORT" \
  --launcher-x-mm 600 --launcher-y-mm 1560 --launcher-z-mm 500 \
  --launcher-yaw-deg 0 \
  --targets right_knee,nose,body_center \
  --yaw-source-map right_knee:body_center \
  --disable-zone-check \
  --pre-aim-delay-sec-map right_knee:10,nose:10,body_center:10 \
  --target-hold-sec-map right_knee:20,nose:20,body_center:20 \
  --home-between-targets \
  --home-wait-sec 0 \
  --run-once-per-start \
  --max-target-events 3 \
  --min-conf 0.40 --min-cams 2 \
  --stable-frames 6 --stable-window-sec 1.8 --stable-std-mm 40 \
  --acquire-timeout-sec 12 \
  --horizontal-only \
  --horizontal-fixed-v-deg 0 \
  --yaw-trim-deg "$YAW_TRIM" \
  --max-abs-angle-deg 40 \
  --no-shoot-enabled \
  --aim-only-wheel-rpm "$AIM_RPM" \
  --no-setzero-on-start \
  --home-on-start \
  --home-on-exit \
  --dry-run-log-jsonl "$LOG_PATH" \
  "${EXTRA_ARGS[@]}"
