#!/usr/bin/env bash
# Launch the Arena Control Center desktop app (fast — runs the compiled binary).
# The desktop icon "Project Cam Control Center" runs this same binary directly.
#
# If you change the UI (src/) or backend (src-tauri/), run ./rebuild.sh to
# recompile, then launch again.
set -e
cd "$(dirname "$0")"
BIN="src-tauri/target/release/project-cam"
if [ ! -x "$BIN" ]; then
  echo "Release binary missing — building it once (this takes a few minutes)…"
  ./rebuild.sh
fi
exec "$BIN"
