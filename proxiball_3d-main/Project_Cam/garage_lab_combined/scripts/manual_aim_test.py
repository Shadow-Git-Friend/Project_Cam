#!/usr/bin/env python3
"""
Manual aim test using GT joint positions.
Computes ballistic angles from known 3D coordinates and sends to BLM
only after user confirmation. Safety: pitch clamped to [0, 30], yaw to [-30, 30].

Usage:
    ./venv/bin/python garage_lab_combined/scripts/manual_aim_test.py \
        --serial-port /dev/ttyUSB0 \
        --launcher-yaw-deg <yaw> \
        --correction-mode linear
"""

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, Dict

import numpy as np

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: ./venv/bin/pip install pyserial")
    sys.exit(1)


# --------------- ballistic math (copied from launcher_runtime_from_udp.py) ---------------

def forward_right_vectors_from_yaw(yaw_deg: float):
    yaw = math.radians(yaw_deg)
    fwd = np.array([math.cos(yaw), math.sin(yaw), 0.0], dtype=np.float64)
    right = np.array([fwd[1], -fwd[0], 0.0], dtype=np.float64)
    return fwd, right


def world_to_launcher_xy_delta(target_xyz_mm, launcher_xyz_mm, launcher_yaw_deg):
    d = np.asarray(target_xyz_mm, dtype=np.float64) - np.asarray(launcher_xyz_mm, dtype=np.float64)
    fwd, right = forward_right_vectors_from_yaw(launcher_yaw_deg)
    x_lat_mm = float(np.dot(d[:2], right[:2]))
    y_fwd_mm = float(np.dot(d[:2], fwd[:2]))
    dz_mm = float(d[2])
    return x_lat_mm / 1000.0, y_fwd_mm / 1000.0, dz_mm / 1000.0


def solve_angles_ballistic(x_lat_m, y_fwd_m, dz_m, v_ms, g=9.81):
    if y_fwd_m <= 0.15:
        return None
    d = math.sqrt(x_lat_m**2 + y_fwd_m**2)
    if d <= 1e-6:
        return None
    h_deg = math.degrees(math.atan2(x_lat_m, y_fwd_m))
    disc = v_ms**4 - g * (g * d**2 + 2.0 * dz_m * v_ms**2)
    if disc < 0.0:
        return None
    v_rad = math.atan((v_ms**2 - math.sqrt(disc)) / (g * d))
    v_deg = math.degrees(v_rad)
    return v_deg, h_deg


# --------------- correction model ---------------

def load_correction_model(path: str) -> Optional[Dict]:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Could not load correction model {path}: {e}")
        return None


def apply_correction(xyz_mm: np.ndarray, model: Optional[Dict], mode: str = "linear") -> np.ndarray:
    if mode == "none" or model is None:
        return xyz_mm.copy()
    xyz = np.array(xyz_mm, dtype=np.float64)
    if mode == "bias":
        bias = model.get("global_bias_add_mm", {})
        xyz[0] += bias.get("x", 0.0)
        xyz[1] += bias.get("y", 0.0)
        xyz[2] += bias.get("z", 0.0)
    elif mode == "linear":
        linear = model.get("axis_linear_gt_from_est", {})
        for i, ax in enumerate(["x", "y", "z"]):
            if ax in linear:
                xyz[i] = linear[ax]["a"] * xyz[i] + linear[ax]["b"]
    return xyz


# --------------- main ---------------

def main():
    ap = argparse.ArgumentParser(description="Manual BLM aim test on GT joint positions")
    ap.add_argument("--serial-port", required=True, help="ESP32 serial port")
    ap.add_argument("--baud-rate", type=int, default=921600)
    ap.add_argument("--gt-csv", default="garage_lab_combined/gt_eval/joint_tuning_20260310_124311/trials_joint_81_mm.csv")
    ap.add_argument("--launcher-x-mm", type=float, default=600.0)
    ap.add_argument("--launcher-y-mm", type=float, default=1560.0)
    ap.add_argument("--launcher-z-mm", type=float, default=500.0)
    ap.add_argument("--launcher-yaw-deg", type=float, required=True)
    ap.add_argument("--v-base-mps", type=float, default=10.0,
                    help="Launch speed (m/s) for ballistic solver")
    ap.add_argument("--correction-model", default="garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/correction_model.json")
    ap.add_argument("--correction-mode", choices=["none", "bias", "linear"], default="none")
    ap.add_argument("--pitch-trim-deg", type=float, default=0.0)
    ap.add_argument("--yaw-trim-deg", type=float, default=0.0)
    args = ap.parse_args()

    # Load GT trials
    trials = []
    with open(args.gt_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            trials.append({
                "id": row["trial_id"],
                "joint": row["joint_name"],
                "x": float(row["x_mm"]),
                "y": float(row["y_mm"]),
                "z": float(row["z_mm"]),
                "notes": row.get("notes", ""),
            })
    print(f"Loaded {len(trials)} GT trials from {args.gt_csv}")

    # Load correction model
    correction_model = None
    if args.correction_mode != "none":
        correction_model = load_correction_model(args.correction_model)
        if correction_model:
            print(f"Correction model loaded ({args.correction_mode} mode)")

    launcher_xyz = np.array([args.launcher_x_mm, args.launcher_y_mm, args.launcher_z_mm])

    # Connect serial
    ser = serial.Serial(args.serial_port, args.baud_rate, timeout=0.1)
    time.sleep(2)
    # Drain boot messages
    while ser.readline():
        pass
    print(f"Serial connected: {args.serial_port}")

    # Center on startup
    ser.write(b"center\n")
    time.sleep(0.5)
    while ser.readline():
        pass
    print("BLM centered.")

    # Print available trials summary
    print("\n--- Available GT Trials ---")
    print(f"{'ID':>5}  {'Joint':<16}  {'X':>6}  {'Y':>6}  {'Z':>6}  Notes")
    print("-" * 70)
    for t in trials:
        print(f"{t['id']:>5}  {t['joint']:<16}  {t['x']:6.0f}  {t['y']:6.0f}  {t['z']:6.0f}  {t['notes']}")

    print("\n--- Commands ---")
    print("  <trial_id>  — compute & aim (e.g. J005, J032, J059)")
    print("  center      — return to home")
    print("  stop        — stop motors")
    print("  status      — show current state")
    print("  quit        — exit")
    print()

    last_v = 0.0
    last_h = 0.0

    while True:
        try:
            cmd = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not cmd:
            continue

        if cmd.lower() == "quit":
            break
        elif cmd.lower() in ("center", "stop", "status"):
            ser.write((cmd.lower() + "\n").encode())
            time.sleep(0.3)
            while True:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    break
                if not line.startswith("ets ") and not line.startswith("rst:"):
                    print(f"  <- {line}")
            if cmd.lower() == "center":
                last_v, last_h = 0.0, 0.0
            continue

        # Find trial
        trial = None
        for t in trials:
            if t["id"].upper() == cmd.upper():
                trial = t
                break
        if trial is None:
            print(f"  Unknown trial '{cmd}'. Try J001-J081, center, stop, quit.")
            continue

        # Compute aim
        raw_xyz = np.array([trial["x"], trial["y"], trial["z"]], dtype=np.float64)
        corrected_xyz = apply_correction(raw_xyz, correction_model, mode=args.correction_mode)

        x_lat_m, y_fwd_m, dz_m = world_to_launcher_xy_delta(
            corrected_xyz, launcher_xyz, args.launcher_yaw_deg
        )
        d_m = math.sqrt(x_lat_m**2 + y_fwd_m**2)

        sol = solve_angles_ballistic(x_lat_m, y_fwd_m, dz_m, v_ms=args.v_base_mps)
        if sol is None:
            print(f"  UNREACHABLE: {trial['id']} {trial['joint']} at ({trial['x']}, {trial['y']}, {trial['z']}) mm")
            print(f"  Launcher frame: lat={x_lat_m:.3f}m fwd={y_fwd_m:.3f}m dz={dz_m:.3f}m dist={d_m:.2f}m")
            continue

        v_deg, h_deg = sol
        v_deg += args.pitch_trim_deg
        h_deg += args.yaw_trim_deg

        # SAFETY: clamp pitch to [0, 30], yaw to [-30, 30]
        v_clamped = max(0.0, min(30.0, v_deg))
        h_clamped = max(-30.0, min(30.0, h_deg))

        was_clamped = (v_clamped != v_deg) or (h_clamped != h_deg)

        print(f"\n  Trial:     {trial['id']} — {trial['joint']} ({trial['notes']})")
        print(f"  GT pos:    X={trial['x']:.0f}  Y={trial['y']:.0f}  Z={trial['z']:.0f} mm")
        if args.correction_mode != "none":
            print(f"  Corrected: X={corrected_xyz[0]:.1f}  Y={corrected_xyz[1]:.1f}  Z={corrected_xyz[2]:.1f} mm")
        print(f"  Launcher:  lat={x_lat_m:.3f}m  fwd={y_fwd_m:.3f}m  dz={dz_m:.3f}m  dist={d_m:.2f}m")
        print(f"  Angles:    pitch={v_deg:.2f}°  yaw={h_deg:.2f}°")
        if was_clamped:
            print(f"  CLAMPED:   pitch={v_clamped:.2f}°  yaw={h_clamped:.2f}°")
            if v_deg < 0:
                print(f"  ⚠ PITCH WAS NEGATIVE ({v_deg:.2f}°) — clamped to 0°")
        print(f"  Command:   set {v_clamped:.1f} {h_clamped:.1f} 0 0")

        confirm = input("  Send? [y/N] ").strip().lower()
        if confirm != "y":
            print("  Skipped.")
            continue

        cmd_str = f"set {v_clamped:.1f} {h_clamped:.1f} 0 0"
        ser.write((cmd_str + "\n").encode())
        time.sleep(0.5)
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                break
            if not line.startswith("ets ") and not line.startswith("rst:"):
                print(f"  <- {line}")

        last_v, last_h = v_clamped, h_clamped
        print()

    # Cleanup: center and close
    print("Returning to center...")
    ser.write(b"center\n")
    time.sleep(1)
    ser.close()
    print("Done.")


if __name__ == "__main__":
    main()
