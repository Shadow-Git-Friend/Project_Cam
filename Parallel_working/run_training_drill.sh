#!/usr/bin/env bash
# =============================================================================
# TRAINING DRILL: live 6-USB viewer (background, UDP joint broadcast) + the
# athlete-facing drill scoreboard (foreground).
#
#   run_training_drill.sh <drill> [--athlete NAME] [--face-id] [--people N]
#                         [--rounds N] [--duration S] [--flip] [--seed N]
#                         [--fullscreen] [--layout split|swap|none]
#
#   drill: balance | shuttle | line_hops | gk_save | gk_updown | reaction_zones
#          | cmj | hop_symmetry | reactive_cut
#
# Both windows are tiled side by side on the desktop work area and OPEN
# TOGETHER: the board waits for the viewer's first UDP packet, so the athlete
# does not stare at an empty board through model load and camera open.
#   --layout split  board left,  3D arena right  (default)
#   --layout swap   board right, 3D arena left
#   --layout none   no placement — drag the windows yourself
# --fullscreen (projector) takes the whole screen for the board and therefore
# ignores the board's pane.
#
# VIEW-ONLY: neither process actuates the BLM — the viewer only triangulates
# and broadcasts joints; the drill board only listens and draws. The desktop
# Control Center spawns this script in its own process group, so STOP
# (SIGINT on the group) shuts down both windows cleanly.
# =============================================================================
set -uo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

DRILL="${1:?usage: run_training_drill.sh <drill> [--athlete NAME] [--face-id] [--people N] [--rounds N] [--duration S] [--flip] [--seed N] [--fullscreen] [--layout split|swap|none]}"
shift

ATHLETE=""
FACE_ID=0
PEOPLE=1
LAYOUT="split"
DRILL_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --athlete)  ATHLETE="${2:?--athlete needs a value}"; DRILL_ARGS+=(--athlete "$2"); shift 2 ;;
    --face-id)  FACE_ID=1; shift ;;
    --people)   PEOPLE="${2:?--people needs a value}"; shift 2 ;;
    --rounds|--duration|--seed) DRILL_ARGS+=("$1" "${2:?$1 needs a value}"); shift 2 ;;
    --flip)     DRILL_ARGS+=(--flip); shift ;;
    --fullscreen) DRILL_ARGS+=(--fullscreen); shift ;;
    --layout)   LAYOUT="${2:?--layout needs a value}"; shift 2 ;;
    *) echo "[drill] unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$LAYOUT" in
  split) BOARD_PANE=left;  VIEWER_PANE=right ;;
  swap)  BOARD_PANE=right; VIEWER_PANE=left ;;
  none)  BOARD_PANE=none;  VIEWER_PANE=none ;;
  *) echo "[drill] unknown --layout: $LAYOUT (split|swap|none)" >&2; exit 2 ;;
esac

# Ceiling on how long the board waits for the viewer before opening anyway.
# Generous on purpose: TensorRT engine load plus six USB cameras with
# --camera-open-retries can legitimately take over a minute, and the watchdog
# below ends the wait immediately if the viewer dies instead.
ARENA_WAIT_S="${PROJECT_CAM_ARENA_WAIT_S:-240}"

# Drills need lower latency than the demo default of 5 fps/cam. 10 fps halves
# the worst-case frame age at 640x360 (still USB2-conservative). If cameras
# fail to open or starve on your hub, run with PROJECT_CAM_FPS=5.
export PROJECT_CAM_FPS="${PROJECT_CAM_FPS:-10}"

# The plain mirrored-skeleton viewer, with the UDP target broadcast enabled
# (same 13 joints / gates as run_live_usb6_blm.sh, but no BLM aim overlay)
# and a smaller 3D window so the drill board is the hero display.
# Drill-specific profile (all geometry-safe, appended AFTER the launcher's own
# args so argparse last-wins):
#   --no-avatar-body/-markers  raw skeleton — the SMPL capsule mangles on
#                              one-leg/floor poses and hides what tracking sees
#   --max-frame-age-ms 250     less cross-camera temporal smear per triangulation
#   --ema-alpha 0.65           snappier 3D state for mm-scale balance motion
#   --kalman-measured-dt       correct KF velocity on this async-refresh rig
#   --pose-latency-comp-ms 120 display-only lead cancelling capture+inference
#                              lag. Since 2026-07-17 this is a RIGID whole-
#                              skeleton lead (median of shoulder/hip KF leads)
#                              — per-joint prediction made bones breathe
#                              ("liquid skeleton"). To A/B the per-joint lead:
#                              --pose-latency-comp-joint-frac 1.0 (diagnostic
#                              only — NOT a byte-exact restoration of the
#                              pre-2026-07-17 path; see the flag's help)
# Also active via viewer defaults (2026-07-17): display bone-length
# consistency (--pose-bone-consistency, learned-median soft clamp) and the
# mm-scaled One-Euro display filter (--oneeuro-beta 0.015). Disable for A/B
# with --no-pose-bone-consistency / --oneeuro-beta 0.3.
VIEWER_ARGS=(
  --udp-target-host 127.0.0.1 --udp-target-port 5005
  --udp-target-joints nose,left_shoulder,right_shoulder,left_elbow,right_elbow,left_wrist,right_wrist,left_hip,right_hip,left_knee,right_knee,left_ankle,right_ankle
  --udp-target-conf-min 0.45 --udp-target-cams-min 2
  # Comparability evidence for the session record: opened camera ROLES +
  # calibration fingerprint, plus a heartbeat when nothing is tracked so the
  # valid-frame ratio is honest. View-only consumer, so the heartbeat cannot
  # reach fire control (a packet without `safety` disarms the launcher).
  --udp-capture-context
  --pose-every 1
  --viz-width 960 --viz-height 540
  # Display-only: tile the 3D window onto its half of the desktop work area so
  # the board and the arena never overlap and neither needs dragging.
  --window-pane "$VIEWER_PANE"
  --no-avatar-body --no-avatar-markers
  --max-frame-age-ms 250
  --ema-alpha 0.65
  --kalman-measured-dt
  --pose-latency-comp-ms 120
)
# A SERVED drill scores the real delivery, so it is the one profile that needs
# ball tracking. Every other drill keeps the base launcher's --no-track-ball,
# which leaves the ball engine off the GPU entirely.
#
# Still VIEW-ONLY: --udp-ball only ADDS the tracked ball to the outgoing
# broadcast. Nothing here opens serial, and the launcher is served by the
# operator through the gated desktop console — the drill measures whatever was
# delivered and can neither request nor authorize a shot.
#
# --ball-imgsz stays at the engine's export size: inference imgsz is LOCKED to
# it (see .claude/rules/perf.md), and an off-size run produces ~300 garbage
# detections per frame rather than an error.
case "$DRILL" in
  gk_save_served)
    VIEWER_ARGS+=(--track-ball --udp-ball --ball-imgsz 672 --ball-every 1)
    echo "[drill] served drill: ball tracking ON (view-only broadcast)"
    ;;
esac

if [ "$PEOPLE" -gt 1 ] 2>/dev/null; then
  VIEWER_ARGS+=(--multi-person "$PEOPLE")
fi
if [ "$FACE_ID" = "1" ] && [ -n "$ATHLETE" ]; then
  VIEWER_ARGS+=(--face-id --primary-person "$ATHLETE")
fi

echo "[drill] starting live viewer (UDP :5005) ..."
./Parallel_working/run_live_usb6_mirrored_skeleton.sh "${VIEWER_ARGS[@]}" &
VIEWER_PID=$!

echo "[drill] starting drill board: $DRILL (layout: $LAYOUT)"
./venv/bin/python garage_lab_combined/scripts/training_drill.py \
  --drill "$DRILL" "${DRILL_ARGS[@]}" \
  --window-pane "$BOARD_PANE" --wait-for-arena "$ARENA_WAIT_S" &
BOARD_PID=$!

cleanup() {
  kill -INT "$BOARD_PID" "$VIEWER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# One session, two processes: whichever ends first ends the other. Without this
# a viewer that dies during startup would leave the board waiting out its whole
# --wait-for-arena window with nothing on screen.
while kill -0 "$BOARD_PID" 2>/dev/null; do
  if ! kill -0 "$VIEWER_PID" 2>/dev/null; then
    echo "[drill] live viewer exited — stopping the drill board" >&2
    kill -INT "$BOARD_PID" 2>/dev/null || true
    break
  fi
  sleep 0.3
done
wait "$BOARD_PID"
RC=$?

# Let the viewer shut down cleanly (it already got SIGINT from cleanup/group).
cleanup
for _ in $(seq 1 40); do
  kill -0 "$VIEWER_PID" 2>/dev/null || break
  sleep 0.25
done
kill -TERM "$VIEWER_PID" 2>/dev/null || true
exit "$RC"
