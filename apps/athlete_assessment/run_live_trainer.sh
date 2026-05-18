#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

EXERCISE="${1:-squat}"
HOST="${PROJECT_CAM_ASSESSMENT_HOST:-127.0.0.1}"
PORT="${PROJECT_CAM_ASSESSMENT_PORT:-5015}"

PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.live_trainer \
  --host "$HOST" \
  --port "$PORT" \
  --exercise "$EXERCISE" \
  "${@:2}"
