#!/usr/bin/env bash
# One-time install of the Linux system libraries Tauri 2 needs (Ubuntu 22.04).
# Run this ONCE with sudo:  sudo ./install-system-deps.sh
set -e
# apt-get update may report errors from unrelated third-party repos
# (e.g. a ProtonVPN GPG key issue). The official Ubuntu repos are what we
# need and they update fine, so don't let a third-party repo abort us.
apt-get update || true
apt-get install -y \
  libwebkit2gtk-4.1-dev \
  build-essential \
  curl \
  wget \
  file \
  libxdo-dev \
  libssl-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev
echo
echo "System deps installed. Now launch the app with:  ./run.sh"
