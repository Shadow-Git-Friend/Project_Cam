#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

INPUT="${1:-data/raw/tpose_check.jsonl}"
OUTPUT="${2:-data/reports/pre_session_calibration.json}"
FPS="${PROJECT_CAM_ASSESSMENT_FPS:-30}"
MAX_STD_MM="${PROJECT_CAM_CAL_MAX_STD_MM:-15}"
MAX_MISSING_RATIO="${PROJECT_CAM_CAL_MAX_MISSING_RATIO:-0.30}"

PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.cal_check \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --fps "$FPS" \
  --max-distance-std-mm "$MAX_STD_MM" \
  --max-missing-frame-ratio "$MAX_MISSING_RATIO"
