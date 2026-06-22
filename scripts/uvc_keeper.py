#!/usr/bin/env python3
"""
uvc_keeper.py — keep the C920 UVC controls correct during captures.

The Logitech C920 resets gain/exposure to a dark default every time a stream is
opened (cv2.VideoCapture). The capture tools either apply ONE global gain to all
cameras or none at all, so the dark-corner C920 ends up under-exposed and the
intrinsics tool calibrates a dark image.

Run this in the BACKGROUND during any capture / calibration / live run:
    ./venv/bin/python scripts/uvc_keeper.py --watch
It re-asserts the right per-camera controls every ~1.5 s, so whichever tool opens
the camera, it goes bright within ~1.5 s. Ctrl+C to stop. Use --once to apply and
exit, --duration N to auto-stop.

Edit PROFILES if a camera's by-id path or desired values change.
"""
from __future__ import annotations
import argparse, subprocess, time

# device by-id  ->  desired v4l2 controls (order matters: auto_exposure before exposure)
PROFILES = {
    # DARK-corner C920 — needs high gain to be usable
    "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_9718C21F-video-index0": {
        "focus_automatic_continuous": 0, "focus_absolute": 0,
        "auto_exposure": 1, "exposure_time_absolute": 312, "gain": 255,
        "brightness": 180, "backlight_compensation": 1, "power_line_frequency": 1,
    },
    # other C920 — already well lit
    "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_7B879F0F-video-index0": {
        "focus_automatic_continuous": 0, "focus_absolute": 0,
        "auto_exposure": 1, "exposure_time_absolute": 312, "gain": 160,
        "brightness": 128, "backlight_compensation": 1, "power_line_frequency": 1,
    },
}


def apply_once():
    for dev, ctrls in PROFILES.items():
        kv = ",".join(f"{k}={v}" for k, v in ctrls.items())
        subprocess.run(["v4l2-ctl", "-d", dev, f"--set-ctrl={kv}"],
                       capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="re-apply on a loop")
    ap.add_argument("--interval", type=float, default=1.5)
    ap.add_argument("--duration", type=float, default=0.0, help="0 = forever")
    a = ap.parse_args()
    apply_once()
    if not a.watch:
        print("UVC controls applied once.")
        return
    print(f"uvc_keeper: re-applying C920 controls every {a.interval}s "
          f"({'forever' if a.duration<=0 else str(a.duration)+'s'}). Ctrl+C to stop.")
    t0 = time.time()
    try:
        while a.duration <= 0 or (time.time() - t0) < a.duration:
            time.sleep(a.interval)
            apply_once()
    except KeyboardInterrupt:
        print("\nuvc_keeper stopped.")


if __name__ == "__main__":
    main()
