#!/usr/bin/env bash
set -euo pipefail

LOG="/home/hanush/Desktop/Project_Cam/.codex_tmp/aic8800/bluetooth_dkms_terminal_install.log"
REPO="/home/hanush/Desktop/Project_Cam/.codex_tmp/aic8800/shenmintao-aic8800d80-bluetooth"

mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

echo "AIC8800D80 BT+AX900 Linux driver install"
echo "Machine: $(hostname)"
echo "Kernel: $(uname -r)"
echo
echo "Enter your Linux sudo password when prompted."
echo

sudo -v

export DEBIAN_FRONTEND=noninteractive
sudo apt-get purge -y ax900-wifi-adapter-linux-driver || true
sudo apt-get install -y \
  usb-modeswitch usb-modeswitch-data \
  dkms build-essential "linux-headers-$(uname -r)" mokutil \
  bluez rfkill wireless-tools iw

cd "$REPO"
sudo bash ./install.sh

echo
echo "Install command finished. Verifying..."
dkms status || true
lsusb | grep -Ei 'aic|368b|a69c' || true
lsmod | grep -Ei 'aic|btusb|bluetooth|cfg80211' || true
iw dev || true
bluetoothctl list || true
nmcli device status || true

echo
echo "Done. You can close this terminal."
