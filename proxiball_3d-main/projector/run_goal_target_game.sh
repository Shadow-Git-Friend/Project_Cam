#!/usr/bin/env bash
# Launch the Footbonaut-style projector goal game.
#
# Projector is expected on DP-1-2 at +1920+0 (right of HDMI-1-0).
# Run `xrandr --query | grep " connected"` to confirm display layout.
#
# Keys (focus the projector pygame window):
#   N        new active target
#   R        reset score + new target
#   F        toggle fullscreen
#   Q / ESC  quit

set -euo pipefail
cd "$(dirname "$0")/../.."

PROJ_POS="${PROJ_POS:-1920,0}"

exec ./venv/bin/python proxiball_3d-main/projector/goal_target_game.py \
  --proj-pos "$PROJ_POS" \
  --show-debug \
  "$@"
