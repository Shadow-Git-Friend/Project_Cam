#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

OUT="${1:-data/raw/session_001_joints.jsonl}"
SESSION_ID="${2:-session_001}"
ATHLETE_ID="${3:-athlete_001}"
EXERCISE="${4:-squat}"
AGE="${5:-10}"
SEX="${6:-unspecified}"
PORT="${PROJECT_CAM_ASSESSMENT_PORT:-5015}"
HOST="${PROJECT_CAM_ASSESSMENT_HOST:-127.0.0.1}"
FPS="${PROJECT_CAM_ASSESSMENT_FPS:-15}"
RECORD_DELAY_SEC="${PROJECT_CAM_RECORD_DELAY_SEC:-10}"
RECORD_DURATION_SEC="${PROJECT_CAM_RECORD_DURATION_SEC:-15}"
RECORD_MAX_FRAMES="${PROJECT_CAM_RECORD_MAX_FRAMES:-0}"

if [ "$RECORD_DELAY_SEC" -gt 0 ]; then
  echo "[WAIT] Recording will start in ${RECORD_DELAY_SEC}s."
  echo "[WAIT] Go to the center of the arena and get ready for: ${EXERCISE}"
  remaining="$RECORD_DELAY_SEC"
  while [ "$remaining" -gt 0 ]; do
    printf '[WAIT] %ss\r' "$remaining"
    sleep 1
    remaining=$((remaining - 1))
  done
  printf '[WAIT] Start recording now.          \n'
fi

PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.udp_record \
  --host "$HOST" \
  --port "$PORT" \
  --output "$OUT" \
  --session-id "$SESSION_ID" \
  --athlete-id "$ATHLETE_ID" \
  --exercise "$EXERCISE" \
  --age "$AGE" \
  --sex "$SEX" \
  --fps "$FPS" \
  --duration-sec "$RECORD_DURATION_SEC" \
  --max-frames "$RECORD_MAX_FRAMES"
