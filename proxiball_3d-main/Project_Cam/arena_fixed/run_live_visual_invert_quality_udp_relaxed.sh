#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Same geometry/pose baseline as run_live_visual_invert_quality.sh,
# but relaxed UDP gates for horizontal-only BLM aiming stage.
./arena_fixed/run_live_visual_invert_quality.sh \
  --udp-target-conf-min 0.40 \
  --udp-target-cams-min 2 \
  "$@"
