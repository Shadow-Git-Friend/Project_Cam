#!/usr/bin/env bash
set -euo pipefail

LOG="/home/hanush/Desktop/Project_Cam/.codex_tmp/aic8800/aic8800_manual_install.log"
REPO="/home/hanush/Desktop/Project_Cam/.codex_tmp/aic8800/shenmintao-aic8800d80-bluetooth"
KVER="$(uname -r)"
MODDIR="/lib/modules/${KVER}/kernel/drivers/net/wireless/aic8800"

mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

echo "AIC8800D80 manual install"
echo "Machine: $(hostname)"
echo "Kernel: ${KVER}"
echo
echo "Enter your Linux sudo password when prompted."
echo

sudo -v

for cmd in make gcc dkms iw nmcli eject; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
done

if [ ! -d "/lib/modules/${KVER}/build" ]; then
  echo "Missing kernel headers: /lib/modules/${KVER}/build"
  echo "Install them with: sudo apt-get install linux-headers-${KVER}"
  exit 1
fi

cd "$REPO"

echo
echo "Stopping old AIC modules if loaded..."
sudo modprobe -r aic_btusb 2>/dev/null || true
sudo modprobe -r aic8800_fdrv 2>/dev/null || true
sudo modprobe -r aic_load_fw 2>/dev/null || true

echo
echo "Installing firmware and udev rules..."
sudo rm -rf /lib/firmware/aic8800*
sudo cp -a fw/aic8800* /lib/firmware/
sudo install -m 0644 aic.rules /etc/udev/rules.d/99-aic8800.rules
sudo install -m 0644 modprobe/aic8800-bt.conf /etc/modprobe.d/aic8800-bt.conf
sudo mkdir -p /etc/usb_modeswitch.d
sudo install -m 0644 usb_modeswitch/1111_1111 /etc/usb_modeswitch.d/1111:1111

echo
echo "Building Wi-Fi modules..."
make -C drivers/aic8800 clean
make -C drivers/aic8800

echo
echo "Building Bluetooth module..."
make -C drivers/aic8800/aic_btusb clean
make -C drivers/aic8800/aic_btusb

echo
echo "Installing kernel modules..."
sudo mkdir -p "$MODDIR"
sudo install -m 0644 drivers/aic8800/aic_load_fw/aic_load_fw.ko "$MODDIR/"
sudo install -m 0644 drivers/aic8800/aic8800_fdrv/aic8800_fdrv.ko "$MODDIR/"
sudo install -m 0644 drivers/aic8800/aic_btusb/aic_btusb.ko "$MODDIR/"
sudo depmod -a "$KVER"

echo
echo "Reloading udev and loading modules..."
sudo udevadm control --reload-rules
sudo udevadm trigger || true
sudo modprobe aic_load_fw
sudo modprobe aic8800_fdrv
sudo modprobe aic_btusb || true

echo
echo "Switching adapter out of fake disk mode if needed..."
AIC_DISK="$(lsblk -dn -o NAME,VENDOR,MODEL,TRAN | awk '$2=="AIC" && $3=="flash" && $4=="usb" {print "/dev/" $1; exit}')"
if [ -n "$AIC_DISK" ]; then
  echo "Ejecting $AIC_DISK"
  sudo eject "$AIC_DISK" || true
  sleep 5
else
  echo "No AIC fake disk found; adapter may already be switched."
fi

echo
echo "Verification:"
lsusb | grep -Ei 'aic|368b|a69c' || true
lsmod | grep -Ei 'aic|btusb|bluetooth|cfg80211' || true
iw dev || true
timeout 5 bluetoothctl list || true
nmcli device status || true

echo
echo "If Wi-Fi is not visible yet, unplug the adapter, plug it back in, wait 10 seconds, then run:"
echo "  nmcli device status"
echo "  nmcli device wifi list"
echo
echo "Done."
