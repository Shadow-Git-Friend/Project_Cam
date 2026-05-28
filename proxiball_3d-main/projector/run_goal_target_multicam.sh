#!/usr/bin/env bash
# Launch the multi-cam projector goal game.
#
# Layout expected (xrandr --query | grep " connected"):
#   HDMI-1-0  1920x1200+0+0     <- PC monitor (operator window goes here)
#   DP-1-2    1920x1080+1920+0  <- projector (pygame window goes here)
#
# Keys:
#   N        new active target
#   R        reset score + new target
#   Q / ESC  quit

set -euo pipefail
cd "$(dirname "$0")/../.."

PROJ_POS="${PROJ_POS:-1920,0}"
MON_POS="${MON_POS:-50,50}"
PROJECTOR_OUTPUT="${PROJECTOR_OUTPUT:-DP-1-2}"

# Defaults use the post-remount calibration bundle (1920x1080).
# To roll back to pre-remount canonical paths, pass:
#   --intrinsics-dir garage_lab_combined/cal/intrinsics \
#   --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
#   --width 1280 --height 720
echo "[run] calibration: Remounted_West_East/ (post-remount candidate, 1920x1080)"
echo "[run] debug logging ON — per-second stats will print to terminal"

exec ./venv/bin/python proxiball_3d-main/projector/goal_target_game_multicam.py \
  --projector-output "$PROJECTOR_OUTPUT" \
  --proj-pos "$PROJ_POS" \
  --monitor-pos "$MON_POS" \
  --debug \
  "$@"
