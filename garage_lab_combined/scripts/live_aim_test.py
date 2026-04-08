#!/usr/bin/env python3
"""
Interactive live aim test — S2 preflight.

Listens to UDP pose packets from the live viewer, lets you manually
select a joint to aim at, shows computed angles, and sends to BLM
only after confirmation.

Procedure:
  1. Start live viewer in Terminal 1 (sends UDP on port 5005)
  2. Start this script in Terminal 2
  3. Person stands at a position in the arena
  4. Type a joint name (e.g. right_hip) → script grabs latest reading
  5. Review angles → confirm → BLM aims
  6. Visually verify → person moves → repeat

Usage:
    # Terminal 1:
    ./Parallel_working/run_live_parallel_yolopose.sh

    # Terminal 2:
    ./venv/bin/python garage_lab_combined/scripts/live_aim_test.py \
        --serial-port /dev/ttyUSB0 \
        --launcher-yaw-deg 0 \
        --correction-mode linear
"""

import argparse
import json
import math
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: ./venv/bin/pip install pyserial")
    sys.exit(1)


# --------------- ballistic math ---------------

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
            data = json.load(f)
        model = {
            "bias": np.array([
                data["global_bias_add_mm"]["x"],
                data["global_bias_add_mm"]["y"],
                data["global_bias_add_mm"]["z"],
            ], dtype=np.float64),
        }
        if "axis_linear_gt_from_est" in data:
            model["linear"] = data["axis_linear_gt_from_est"]
        return model
    except Exception as e:
        print(f"[WARN] Could not load correction model {path}: {e}")
        return None


def apply_correction(xyz_mm: np.ndarray, model: Optional[Dict], mode: str = "linear") -> np.ndarray:
    if model is None or mode == "none":
        return xyz_mm.copy()
    xyz = np.array(xyz_mm, dtype=np.float64)
    if mode == "bias":
        return xyz + model["bias"]
    if mode == "linear" and "linear" in model:
        lin = model["linear"]
        for i, ax in enumerate(["x", "y", "z"]):
            if ax in lin:
                xyz[i] = lin[ax]["a"] * xyz[i] + lin[ax]["b"]
        return xyz
    return xyz + model["bias"]


# --------------- UDP listener ---------------

class UDPJointListener:
    """Background thread that listens for UDP pose packets and stores latest joint positions."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.lock = threading.Lock()
        self.joints: Dict[str, dict] = {}  # joint_name -> {x_mm, y_mm, z_mm, conf, cams, ts}
        self.last_packet_ts = 0.0
        self.packet_count = 0
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.settimeout(1.0)
        while self._running:
            try:
                data, _ = sock.recvfrom(65535)
                pkt = json.loads(data.decode("utf-8", errors="ignore"))
                now = time.time()
                with self.lock:
                    self.last_packet_ts = now
                    self.packet_count += 1
                    # Parse multi-joint format
                    joints_obj = pkt.get("joints", {})
                    if isinstance(joints_obj, dict):
                        for j, val in joints_obj.items():
                            if not isinstance(val, dict):
                                continue
                            if not all(k in val for k in ("x_mm", "y_mm", "z_mm")):
                                continue
                            self.joints[j] = {
                                "x_mm": float(val["x_mm"]),
                                "y_mm": float(val["y_mm"]),
                                "z_mm": float(val["z_mm"]),
                                "conf": float(val.get("conf", 1.0)),
                                "cams": int(val.get("cams", 0)),
                                "ts": now,
                            }
                    # Parse single-joint format
                    elif "joint" in pkt and "x_mm" in pkt:
                        j = str(pkt["joint"])
                        self.joints[j] = {
                            "x_mm": float(pkt["x_mm"]),
                            "y_mm": float(pkt["y_mm"]),
                            "z_mm": float(pkt["z_mm"]),
                            "conf": float(pkt.get("conf", 1.0)),
                            "cams": int(pkt.get("cams", 0)),
                            "ts": now,
                        }
            except socket.timeout:
                pass
            except Exception:
                pass
        sock.close()

    def get_joint(self, name: str) -> Optional[dict]:
        with self.lock:
            return self.joints.get(name)

    def get_all_joints(self) -> Dict[str, dict]:
        with self.lock:
            return dict(self.joints)

    def get_status(self) -> Tuple[int, float]:
        with self.lock:
            return self.packet_count, self.last_packet_ts

    def stop(self):
        self._running = False


# --------------- COCO joint names ---------------

COCO_JOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

# Joints that make sense as BLM targets (body, not face)
TARGETABLE_JOINTS = [
    "left_shoulder", "right_shoulder",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
]


def main():
    ap = argparse.ArgumentParser(description="Interactive live BLM aim test (S2 preflight)")
    ap.add_argument("--serial-port", required=True)
    ap.add_argument("--baud-rate", type=int, default=115200)
    ap.add_argument("--udp-host", default="0.0.0.0")
    ap.add_argument("--udp-port", type=int, default=5005)
    ap.add_argument("--launcher-x-mm", type=float, default=600.0)
    ap.add_argument("--launcher-y-mm", type=float, default=1560.0)
    ap.add_argument("--launcher-z-mm", type=float, default=500.0)
    ap.add_argument("--launcher-yaw-deg", type=float, required=True)
    ap.add_argument("--v-base-mps", type=float, default=10.0)
    ap.add_argument("--correction-model",
                    default="garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/correction_model.json")
    ap.add_argument("--correction-mode", choices=["none", "bias", "linear"], default="none")
    ap.add_argument("--pitch-trim-deg", type=float, default=0.0)
    ap.add_argument("--yaw-trim-deg", type=float, default=0.0)
    ap.add_argument("--log-jsonl", default="", help="Log aim decisions to JSONL file")
    args = ap.parse_args()

    launcher_xyz = np.array([args.launcher_x_mm, args.launcher_y_mm, args.launcher_z_mm])

    # Load correction model
    correction_model = None
    if args.correction_mode != "none":
        correction_model = load_correction_model(args.correction_model)
        if correction_model:
            print(f"[OK] Correction model loaded ({args.correction_mode} mode)")
        else:
            print(f"[WARN] Correction model failed to load, falling back to mode=none")
            args.correction_mode = "none"

    # Start UDP listener
    udp = UDPJointListener(args.udp_host, args.udp_port)
    print(f"[OK] UDP listener started on {args.udp_host}:{args.udp_port}")

    # Connect serial
    ser = serial.Serial(args.serial_port, args.baud_rate, timeout=0.1)
    time.sleep(2)
    while ser.readline():
        pass
    ser.write(b"center\n")
    time.sleep(0.5)
    while ser.readline():
        pass
    print(f"[OK] Serial connected: {args.serial_port}, BLM centered")

    # Open log file
    log_fp = None
    if args.log_jsonl:
        Path(args.log_jsonl).parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(args.log_jsonl, "a")
        print(f"[OK] Logging to {args.log_jsonl}")

    print("\n--- Interactive Live Aim Test (S2) ---")
    print("Commands:")
    print("  <joint_name>  — aim at joint (e.g. right_hip, left_shoulder, right_knee)")
    print("  joints        — show currently detected joints")
    print("  status        — UDP + serial status")
    print("  center        — return BLM to home")
    print("  stop          — stop BLM")
    print("  quit          — exit")
    print(f"\nTargetable joints: {', '.join(TARGETABLE_JOINTS)}")
    print()

    test_number = 0

    while True:
        try:
            cmd = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not cmd:
            continue

        if cmd.lower() == "quit":
            break

        if cmd.lower() in ("center", "stop"):
            ser.write((cmd.lower() + "\n").encode())
            time.sleep(0.3)
            while True:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    break
                if not line.startswith("ets ") and not line.startswith("rst:"):
                    print(f"  <- {line}")
            continue

        if cmd.lower() == "status":
            pkt_count, last_ts = udp.get_status()
            age = time.time() - last_ts if last_ts > 0 else float("inf")
            print(f"  UDP: {pkt_count} packets, last {age:.1f}s ago")
            print(f"  Joints tracked: {list(udp.get_all_joints().keys())}")
            continue

        if cmd.lower() == "joints":
            all_joints = udp.get_all_joints()
            if not all_joints:
                print("  No joints detected. Is the live viewer running?")
                continue
            now = time.time()
            print(f"  {'Joint':<18}  {'X':>7}  {'Y':>7}  {'Z':>7}  {'Conf':>5}  {'Cams':>4}  {'Age':>5}")
            print("  " + "-" * 70)
            for j in COCO_JOINTS:
                if j in all_joints:
                    d = all_joints[j]
                    age = now - d["ts"]
                    marker = " *" if j in TARGETABLE_JOINTS else ""
                    print(f"  {j:<18}  {d['x_mm']:7.0f}  {d['y_mm']:7.0f}  {d['z_mm']:7.0f}"
                          f"  {d['conf']:5.2f}  {d['cams']:4d}  {age:4.1f}s{marker}")
            continue

        # Try as joint name
        joint_name = cmd.lower().replace("-", "_")
        joint_data = udp.get_joint(joint_name)

        if joint_data is None:
            # Check if it's a known joint that just isn't detected
            if joint_name in COCO_JOINTS:
                print(f"  Joint '{joint_name}' is known but not currently detected.")
                print(f"  Detected joints: {list(udp.get_all_joints().keys())}")
            else:
                print(f"  Unknown command/joint '{cmd}'.")
                print(f"  Available: {', '.join(TARGETABLE_JOINTS)}")
            continue

        # Check staleness
        age = time.time() - joint_data["ts"]
        if age > 2.0:
            print(f"  WARNING: Joint '{joint_name}' data is {age:.1f}s old (stale).")
            proceed = input("  Use anyway? [y/N] ").strip().lower()
            if proceed != "y":
                print("  Skipped.")
                continue

        # Compute aim
        raw_xyz = np.array([joint_data["x_mm"], joint_data["y_mm"], joint_data["z_mm"]])
        corrected_xyz = apply_correction(raw_xyz, correction_model, mode=args.correction_mode)

        x_lat_m, y_fwd_m, dz_m = world_to_launcher_xy_delta(
            corrected_xyz, launcher_xyz, args.launcher_yaw_deg
        )
        d_m = math.sqrt(x_lat_m**2 + y_fwd_m**2)

        sol = solve_angles_ballistic(x_lat_m, y_fwd_m, dz_m, v_ms=args.v_base_mps)
        if sol is None:
            print(f"  UNREACHABLE: {joint_name} at ({raw_xyz[0]:.0f}, {raw_xyz[1]:.0f}, {raw_xyz[2]:.0f}) mm")
            print(f"  Launcher frame: lat={x_lat_m:.3f}m fwd={y_fwd_m:.3f}m dz={dz_m:.3f}m dist={d_m:.2f}m")
            continue

        v_deg, h_deg = sol
        v_deg += args.pitch_trim_deg
        h_deg += args.yaw_trim_deg

        # Raw (unclamped) for display
        v_raw, h_raw = v_deg, h_deg

        # SAFETY: clamp pitch to [0, 30], yaw to [-30, 30]
        v_deg = max(0.0, min(30.0, v_deg))
        h_deg = max(-30.0, min(30.0, h_deg))
        was_clamped = (v_deg != v_raw) or (h_deg != h_raw)

        test_number += 1
        print(f"\n  Test #{test_number}")
        print(f"  Joint:     {joint_name} (conf={joint_data['conf']:.2f}, cams={joint_data['cams']}, age={age:.1f}s)")
        print(f"  Raw pos:   X={raw_xyz[0]:.0f}  Y={raw_xyz[1]:.0f}  Z={raw_xyz[2]:.0f} mm")
        if args.correction_mode != "none":
            print(f"  Corrected: X={corrected_xyz[0]:.1f}  Y={corrected_xyz[1]:.1f}  Z={corrected_xyz[2]:.1f} mm")
        print(f"  Launcher:  lat={x_lat_m:.3f}m  fwd={y_fwd_m:.3f}m  dz={dz_m:.3f}m  dist={d_m:.2f}m")
        print(f"  Angles:    pitch={v_raw:.2f} deg  yaw={h_raw:.2f} deg")
        if was_clamped:
            print(f"  CLAMPED:   pitch={v_deg:.2f} deg  yaw={h_deg:.2f} deg")
            if v_raw < 0:
                print(f"  WARNING: PITCH WAS NEGATIVE ({v_raw:.2f} deg) — clamped to 0 deg")
        print(f"  Command:   set {v_deg:.1f} {h_deg:.1f} 0 0")

        confirm = input("  Send? [y/N] ").strip().lower()
        if confirm != "y":
            print("  Skipped.")
            continue

        # Send
        cmd_str = f"set {v_deg:.1f} {h_deg:.1f} 0 0"
        ser.write((cmd_str + "\n").encode())
        time.sleep(0.5)
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                break
            if not line.startswith("ets ") and not line.startswith("rst:"):
                print(f"  <- {line}")

        # Visual check
        visual = input("  Aim looks correct? [y/n/skip] ").strip().lower()

        # Log
        if log_fp:
            log_rec = {
                "test_number": test_number,
                "timestamp": time.time(),
                "joint": joint_name,
                "raw_xyz_mm": raw_xyz.tolist(),
                "corrected_xyz_mm": corrected_xyz.tolist(),
                "correction_mode": args.correction_mode,
                "launcher_frame": {
                    "x_lateral_m": x_lat_m,
                    "y_forward_m": y_fwd_m,
                    "dz_m": dz_m,
                    "distance_m": d_m,
                },
                "angles_raw": {"pitch_deg": v_raw, "yaw_deg": h_raw},
                "angles_clamped": {"pitch_deg": v_deg, "yaw_deg": h_deg},
                "was_clamped": was_clamped,
                "sent_command": cmd_str,
                "visual_check": visual,
                "conf": joint_data["conf"],
                "cams": joint_data["cams"],
                "data_age_sec": age,
            }
            log_fp.write(json.dumps(log_rec, ensure_ascii=False) + "\n")
            log_fp.flush()

        print()

    # Cleanup
    print("Returning to center...")
    ser.write(b"center\n")
    time.sleep(1)
    udp.stop()
    ser.close()
    if log_fp:
        log_fp.close()
    print("Done.")


if __name__ == "__main__":
    main()
