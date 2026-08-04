#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_ROOT/desktop/project-cam.desktop.in"
PYTHON_BIN="$(command -v python3)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
APP_DEST="$APP_DIR/project-cam.desktop"

DESKTOP_DIR="$HOME/Desktop"
if command -v xdg-user-dir >/dev/null 2>&1; then
  RESOLVED_DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
  if [[ -n "$RESOLVED_DESKTOP" ]]; then
    DESKTOP_DIR="$RESOLVED_DESKTOP"
  fi
fi
DESKTOP_DEST="$DESKTOP_DIR/Project Cam.desktop"

DRY_RUN=0
NO_DESKTOP=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-desktop) NO_DESKTOP=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

escape_sed() {
  printf '%s' "$1" | sed 's/[&|]/\\&/g'
}

ROOT_ESC="$(escape_sed "$REPO_ROOT")"
PYTHON_ESC="$(escape_sed "$PYTHON_BIN")"
RENDERED="$(sed -e "s|@REPO_ROOT@|$ROOT_ESC|g" -e "s|@PYTHON@|$PYTHON_ESC|g" "$TEMPLATE")"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Would install application entry: $APP_DEST"
  if [[ "$NO_DESKTOP" -eq 0 ]]; then
    echo "Would install desktop icon: $DESKTOP_DEST"
  fi
  echo
  printf '%s\n' "$RENDERED"
  exit 0
fi

mkdir -p "$APP_DIR"
printf '%s\n' "$RENDERED" > "$APP_DEST"
chmod 0755 "$APP_DEST"

if [[ "$NO_DESKTOP" -eq 0 ]]; then
  mkdir -p "$DESKTOP_DIR"
  cp "$APP_DEST" "$DESKTOP_DEST"
  chmod 0755 "$DESKTOP_DEST"
  if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DEST" metadata::trusted true >/dev/null 2>&1 || true
  fi
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "Installed Project Cam application entry: $APP_DEST"
if [[ "$NO_DESKTOP" -eq 0 ]]; then
  echo "Installed Project Cam desktop icon: $DESKTOP_DEST"
fi
