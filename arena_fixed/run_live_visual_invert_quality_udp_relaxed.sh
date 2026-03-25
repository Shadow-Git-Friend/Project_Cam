#!/usr/bin/env bash
set -euo pipefail

cd /home/hanush/Desktop/Project_Cam

# Same geometry/pose baseline as run_live_visual_invert_quality.sh,
# but relaxed UDP gates for horizontal-only BLM aiming stage.
./arena_fixed/run_live_visual_invert_quality.sh \
  --udp-target-conf-min 0.40 \
  --udp-target-cams-min 2 \
  "$@"
