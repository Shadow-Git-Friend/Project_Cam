#!/usr/bin/env bash
# Live supine leg-raise diagnostic + tracking launcher.
#
# This wrapper runs the canonical live viewer with leg-raise-friendly gates and
# the LegRaiseTracker post-processor. It is AIM-ONLY: it never passes
# --shoot-enabled. It calls the 6-camera path once the Phase 0 promotion gates
# pass (see configs/calibration/usb6_manifest.yaml); until then it falls back to
# the validated 4-camera viewer.
#
# Usage:
#   apps/athlete_assessment/run_live_leg_raise.sh [--side right|left|alternating]
#
# The leg-raise gating here mirrors configs/exercises/leg_raise.yaml so a quick
# visual diagnosis is one command (see that file's header for what to look for).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SIDE="alternating"
EXTRA_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --side) SIDE="$2"; shift 2 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

# Promotion gate: only use the 6-USB path when its manifest is marked validated.
MANIFEST="configs/calibration/usb6_manifest.yaml"
USE_6CAM=0
if grep -qE '^status:[[:space:]]*validated' "$MANIFEST" 2>/dev/null; then
  USE_6CAM=1
fi

# Leg-raise diagnostic gates (looser conf, no ghost, no prediction lag).
LEG_RAISE_FLAGS=(
  --pose-conf 0.25
  --udp-target-conf-min 0.25
  --pose-max-reproj-px 70
  --no-show-ghost-skeleton
  --predict-ahead-ms 0
  --limb-heat
)

echo "[leg-raise] side=${SIDE}  6cam_validated=${USE_6CAM}"
echo "[leg-raise] AIM-ONLY: this launcher never enables --shoot-enabled."

if [[ "$USE_6CAM" == "1" ]]; then
  echo "[leg-raise] launching 6-USB viewer (validated)"
  exec ./Parallel_working/run_live_usb6_mirrored_skeleton.sh \
    "${LEG_RAISE_FLAGS[@]}" "${EXTRA_ARGS[@]}"
else
  echo "[leg-raise] 6-cam not yet validated -> 4-camera fallback viewer"
  exec ./Parallel_working/run_live_parallel_yolopose.sh \
    "${LEG_RAISE_FLAGS[@]}" "${EXTRA_ARGS[@]}"
fi
