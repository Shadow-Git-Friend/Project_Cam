#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass

try:
    import serial
except Exception:
    serial = None


ACK_RE = re.compile(r"ACK:\s*V=([\-0-9.]+)\s*H=([\-0-9.]+)")


@dataclass
class Ack:
    v: float
    h: float
    raw: str


def read_lines(ser, duration=0.25):
    t0 = time.time()
    out = []
    while time.time() - t0 < duration:
        try:
            line = ser.readline().decode(errors="ignore").strip()
        except Exception:
            line = ""
        if line:
            out.append(line)
    return out


def send_cmd(ser, cmd: str, read_sec=0.35):
    ser.write((cmd.strip() + "\n").encode("utf-8"))
    ser.flush()
    lines = read_lines(ser, duration=read_sec)
    return lines


def parse_ack(lines):
    for ln in reversed(lines):
        m = ACK_RE.search(ln)
        if m:
            return Ack(v=float(m.group(1)), h=float(m.group(2)), raw=ln)
    return None


def run_sweep(ser):
    tests = []
    vals = [-50, -40, -35, -30, -25, -20, -10, 0, 10, 20, 25, 30, 35, 40, 50]
    for v in vals:
        tests.append((v, 0))
    for h in vals:
        tests.append((0, h))

    got = []
    print("[INFO] Sweep started. Wheels stay OFF (wl=wr=0).")
    for v, h in tests:
        cmd = f"set {v} {h} 0 0"
        lines = send_cmd(ser, cmd, read_sec=0.45)
        ack = parse_ack(lines)
        if ack is None:
            print(f"[WARN] No ACK for {cmd}")
            continue
        print(f"[ACK] cmd=({v:>5.1f},{h:>5.1f}) -> ack=({ack.v:>5.1f},{ack.h:>5.1f})")
        got.append((v, h, ack.v, ack.h))
        time.sleep(0.15)

    if not got:
        print("[ERROR] No ACK parsed. Cannot estimate limits.")
        return

    min_v = min(x[2] for x in got)
    max_v = max(x[2] for x in got)
    min_h = min(x[3] for x in got)
    max_h = max(x[3] for x in got)

    print("\n[RESULT] Estimated firmware limits from ACK:")
    print(f"  Vertical (V): min={min_v:.1f}, max={max_v:.1f}")
    print(f"  Horizontal(H): min={min_h:.1f}, max={max_h:.1f}")
    print("  If max stays at +/-30.0, clamp in ESP firmware is still 30 deg.")


def run_interactive(ser):
    print("Interactive mode. Type raw commands (e.g. 'set 20 -10 0 0', 'setzero', 'stop').")
    print("Type 'quit' to exit.")
    while True:
        try:
            cmd = input("esp> ").strip()
        except EOFError:
            break
        if not cmd:
            continue
        if cmd.lower() in {"quit", "exit", "q"}:
            break
        lines = send_cmd(ser, cmd, read_sec=0.45)
        for ln in lines:
            print("ESP:", ln)


def main():
    ap = argparse.ArgumentParser(description="Probe ESP max V/H angles safely with wl=wr=0.")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--mode", choices=["sweep", "interactive"], default="sweep")
    ap.add_argument("--setzero-first", action="store_true", help="Run setzero before probe.")
    args = ap.parse_args()

    if serial is None:
        print("pyserial is missing. Install: ./venv/bin/pip install pyserial")
        sys.exit(1)

    ser = serial.Serial(args.port, args.baud, timeout=0.05)
    time.sleep(2.0)
    print(f"[OK] Connected: {args.port} @ {args.baud}")

    try:
        send_cmd(ser, "stop", read_sec=0.2)
        if args.setzero_first:
            lines = send_cmd(ser, "setzero", read_sec=0.35)
            for ln in lines:
                print("ESP:", ln)
        lines = send_cmd(ser, "set 0 0 0 0", read_sec=0.35)
        for ln in lines:
            print("ESP:", ln)

        if args.mode == "sweep":
            run_sweep(ser)
        else:
            run_interactive(ser)
    finally:
        send_cmd(ser, "stop", read_sec=0.2)
        send_cmd(ser, "set 0 0 0 0", read_sec=0.25)
        ser.close()
        print("[DONE] Port closed, sent stop + home.")


if __name__ == "__main__":
    main()
