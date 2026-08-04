#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

INPUT="${1:-data/raw/session_001_joints.jsonl}"
EXERCISE="${2:-squat}"
OUTPUT="${3:-data/reports/session_001_${EXERCISE}_report.json}"
ATHLETE_ID="${4:-athlete_001}"
AGE="${5:-10}"
SEX="${6:-unspecified}"
FPS="${PROJECT_CAM_ASSESSMENT_FPS:-30}"
HTML_OUTPUT="${PROJECT_CAM_ASSESSMENT_HTML_OUTPUT:-${OUTPUT%.json}.html}"
STANDING_HEIGHT_CM="${PROJECT_CAM_STANDING_HEIGHT_CM:-}"
SITTING_HEIGHT_CM="${PROJECT_CAM_SITTING_HEIGHT_CM:-}"
BODY_MASS_KG="${PROJECT_CAM_BODY_MASS_KG:-}"
CALIBRATION_REPORT="${PROJECT_CAM_CALIBRATION_REPORT:-}"

EXTRA_ARGS=()
if [ -n "$HTML_OUTPUT" ]; then
  EXTRA_ARGS+=(--html-output "$HTML_OUTPUT")
fi
if [ -n "$STANDING_HEIGHT_CM" ]; then
  EXTRA_ARGS+=(--standing-height-cm "$STANDING_HEIGHT_CM")
fi
if [ -n "$SITTING_HEIGHT_CM" ]; then
  EXTRA_ARGS+=(--sitting-height-cm "$SITTING_HEIGHT_CM")
fi
if [ -n "$BODY_MASS_KG" ]; then
  EXTRA_ARGS+=(--body-mass-kg "$BODY_MASS_KG")
fi
if [ -n "$CALIBRATION_REPORT" ]; then
  EXTRA_ARGS+=(--calibration-report "$CALIBRATION_REPORT")
fi

PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.offline_assess \
  --input "$INPUT" \
  --exercise "$EXERCISE" \
  --athlete-id "$ATHLETE_ID" \
  --age "$AGE" \
  --sex "$SEX" \
  --fps "$FPS" \
  --output "$OUTPUT" \
  "${EXTRA_ARGS[@]}"
