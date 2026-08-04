#!/usr/bin/env bash
# Launch the Arena Control Center desktop app (fast — runs the compiled binary).
#
# If you change the UI (src/) or backend (src-tauri/), run ./rebuild.sh to
# recompile, then launch again. This script CHECKS that for you, because the app
# is normally started from a desktop icon and a forgotten rebuild is invisible:
# in July 2026 the icon ran a 13-day-old build for two weeks, hiding a whole
# session-evidence layer behind an app that looked perfectly fine.
set -e
cd "$(dirname "$0")"
BIN="src-tauri/target/release/project-cam"
if [ ! -x "$BIN" ]; then
  echo "Release binary missing — building it once (this takes a few minutes)…"
  ./rebuild.sh
fi

# Warn, then launch anyway. Refusing would trade a stale window for a window
# that never opens, and the icon runs with Terminal=false — so a refusal would
# be a NEW silent failure, worse than the fault being guarded against.
if ! ./check-binary-fresh.sh; then
  if command -v notify-send >/dev/null 2>&1; then
    notify-send -u critical "Project Cam: STALE BUILD" \
      "This window is older than the source tree. Run project-cam-desktop/rebuild.sh."
  fi
fi

exec "$BIN"
