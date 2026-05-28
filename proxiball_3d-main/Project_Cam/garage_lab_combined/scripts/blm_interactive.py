#!/usr/bin/env python3
"""
Simple interactive BLM serial terminal.
Type commands directly (set, center, stop, info, shoot, reload, setzero, jv, jh).
Filters ESP32 boot noise and deduplicates repeated messages.

Usage:
    ./venv/bin/python garage_lab_combined/scripts/blm_interactive.py --port /dev/ttyUSB0
"""

import argparse
import sys
import threading
import time

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: ./venv/bin/pip install pyserial")
    sys.exit(1)


def reader_thread(ser, stop_event):
    """Background thread that prints serial output, filtering noise."""
    last_msg = ""
    while not stop_event.is_set():
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            # Filter boot ROM noise
            if line.startswith("ets ") or line.startswith("rst:") or line.startswith("configsip:"):
                continue
            # Filter long runs of repeated chars (line noise / garbled bytes from baud transitions)
            if len(line) > 20 and len(set(line)) <= 2:
                continue
            # Filter wheel RPM telemetry (L:xxx R:xxx) — too chatty for interactive use
            if line.startswith("L:") and " R:" in line:
                continue
            # Deduplicate repeated messages
            if line == last_msg:
                continue
            last_msg = line
            print(f"  <- {line}")
        except serial.SerialException:
            print("[ERROR] Serial disconnected")
            break
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="Interactive BLM serial terminal")
    ap.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    ap.add_argument("--baud", type=int, default=921600)
    args = ap.parse_args()

    print(f"Connecting to {args.port} @ {args.baud}...")
    ser = serial.Serial(args.port, args.baud, timeout=0.1)
    time.sleep(2)
    ser.reset_input_buffer()

    stop_event = threading.Event()
    t = threading.Thread(target=reader_thread, args=(ser, stop_event), daemon=True)
    t.start()

    print(f"[OK] Connected to {args.port}")
    print("Commands: set V H WL WR | center | stop | info | shoot | reload | setzero | jv<steps> | jh<steps> | quit")
    print()

    while True:
        try:
            cmd = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not cmd:
            continue
        if cmd.lower() == "quit":
            break

        ser.write((cmd + "\n").encode())
        time.sleep(0.3)  # Give ESP32 time to respond

    print("\nSending stop + center...")
    ser.write(b"stop\n")
    time.sleep(0.3)
    ser.write(b"center\n")
    time.sleep(0.5)
    stop_event.set()
    ser.close()
    print("Done.")


if __name__ == "__main__":
    main()
