#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

INPUT="${1:-data/raw/tpose_calibration_check.jsonl}"
OUTPUT="${2:-data/reports/tpose_calibration_check.json}"
FPS="${PROJECT_CAM_ASSESSMENT_FPS:-15}"
MAX_STD_MM="${PROJECT_CAM_CAL_MAX_STD_MM:-15}"

PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.cal_check \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --fps "$FPS" \
  --max-distance-std-mm "$MAX_STD_MM"

