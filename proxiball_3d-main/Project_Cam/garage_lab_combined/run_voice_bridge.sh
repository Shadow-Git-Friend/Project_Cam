#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

VOICE_PYTHON="${PROJECT_CAM_VOICE_PYTHON:-$HOME/Desktop/Speech to text/.venv/bin/python}"
VOSK_MODEL="${PROJECT_CAM_VOSK_MODEL:-$HOME/Desktop/Speech to text/model}"

if [ ! -x "$VOICE_PYTHON" ]; then
  echo "[ERR] Voice Python not found or not executable: $VOICE_PYTHON" >&2
  echo "Set PROJECT_CAM_VOICE_PYTHON to your Vosk venv python." >&2
  exit 1
fi

if [ ! -d "$VOSK_MODEL" ]; then
  echo "[ERR] Vosk model directory not found: $VOSK_MODEL" >&2
  echo "Set PROJECT_CAM_VOSK_MODEL to your model directory." >&2
  exit 1
fi

export PROJECT_CAM_VOSK_MODEL="$VOSK_MODEL"

"$VOICE_PYTHON" garage_lab_combined/scripts/voice_bridge.py \
  --port 5006 \
  "$@"
