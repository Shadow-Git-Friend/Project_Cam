#!/usr/bin/env bash
# Thin wrapper around the edge streaming demo. BLM is always disabled.
#
# Usage:
#   apps/edge_stream_demo/run_rtsp_demo.sh <rtsp_url | file | device> [extra args...]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SOURCE="${1:-}"
if [[ -z "$SOURCE" ]]; then
  echo "usage: $0 <rtsp_url | video_file | device_index> [extra args...]" >&2
  exit 2
fi
shift || true

PYTHON="${PYTHON:-./venv/bin/python}"
OUT_JSONL="${OUT_JSONL:-data/events/edge_demo.jsonl}"
mkdir -p "$(dirname "$OUT_JSONL")"

exec env PYTHONPATH=src "$PYTHON" -m project_cam.streaming.rtsp_source \
  --source "$SOURCE" \
  --output-jsonl "$OUT_JSONL" \
  --no-blm \
  "$@"
