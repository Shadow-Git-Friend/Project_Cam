#!/usr/bin/env bash
# Recompile the desktop app after editing src/ (UI) or src-tauri/ (backend).
# Produces the fast standalone binary that the desktop icon + run.sh launch.
set -e
cd "$(dirname "$0")"
source "$HOME/.cargo/env"
npm run tauri build -- --no-bundle
echo
echo "Done. Launch with ./run.sh or the 'Project Cam Control Center' desktop icon."
