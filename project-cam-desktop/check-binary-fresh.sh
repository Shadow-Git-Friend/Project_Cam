#!/usr/bin/env bash
# Is the compiled binary newer than every source it was built from?
#
# Why this exists: the desktop icon Execs the release binary directly, so a
# forgotten rebuild ships stale behaviour silently. In July 2026 the icon ran a
# 13-day-old build for two weeks, hiding an entire session-evidence layer — the
# app looked fine, it was simply not the app in the repo.
#
# Exit 0 = fresh (or nothing to compare against). Exit 1 = stale, with the list
# of newer sources. Exit 2 = binary missing.
set -u
cd "$(dirname "$0")"

BIN="src-tauri/target/release/project-cam"
# Everything the binary is compiled FROM. target/ and node_modules/ are build
# output, not source, and index.html/config files change behaviour too.
SOURCE_PATHS=(src src-tauri/src src-tauri/Cargo.toml src-tauri/tauri.conf.json
              package.json index.html)

if [ ! -x "$BIN" ]; then
  echo "stale-check: $BIN is missing (never built)" >&2
  exit 2
fi

newer=$(find "${SOURCE_PATHS[@]}" -type f -newer "$BIN" \
        -not -path '*/node_modules/*' -not -path '*/target/*' 2>/dev/null)

if [ -n "$newer" ]; then
  echo "stale-check: the release binary is OLDER than these sources:" >&2
  echo "$newer" | sed 's/^/  /' >&2
  echo >&2
  echo "  The desktop icon runs the BINARY, not this source tree." >&2
  echo "  Rebuild before trusting what you see:  ./project-cam-desktop/rebuild.sh" >&2
  exit 1
fi

exit 0
