#!/usr/bin/env python3
"""
Interactive live BLM aim + shoot test.

Full cycle: reload → aim at joint → spin wheels → shoot → repeat.

Listens to UDP pose packets from the live viewer. Also runs a background
serial reader so firmware state messages (RELOAD DONE, SHOT FIRED, etc.)
are printed in real time.

Procedure:
  1. Start live viewer in Terminal 1 (sends UDP on port 5005)
  2. Start this script in Terminal 2
  3. Type 'reload' to load a ball
  4. Type a joint name (e.g. right_hip) → computes angles + sends aim + spins wheels
  5. Type 'shoot' to fire
  6. Repeat from step 3

Usage:
    # Terminal 1:
    ./Parallel_working/run_live_blm.sh

    # Terminal 2 (aim-only, no shooting):
    ./venv/bin/python garage_lab_combined/scripts/live_aim_test.py \
        --serial-port /dev/ttyUSB0 \
        --launcher-yaw-deg 0 \
        --correction-mode linear

    # Terminal 2 (with shooting enabled):
    ./venv/bin/python garage_lab_combined/scripts/live_aim_test.py \
        --serial-port /dev/ttyUSB0 \
        --launcher-yaw-deg 0 \
        --correction-mode linear \
        --shoot-enabled \
        --wheel-rpm 800
"""

import argparse
import json
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from launcher_common import apply_correction, load_correction_model, solve_angles_ballistic, world_to_launcher_xy_delta

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: ./venv/bin/pip install pyserial")
    sys.exit(1)


# --------------- Serial reader thread ---------------

class SerialReader:
    """Background thread that reads serial output and prints it."""

    def __init__(self, ser: serial.Serial):
        self.ser = ser
        self._running = True
        self._last_msg = ""
        self.last_state_msg = ""  # last firmware state message
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        while self._running:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                # Filter boot ROM noise
                if line.startswith("ets ") or line.startswith("rst:") or line.startswith("configsip:"):
                    continue
                if line.startswith("clk_drv:") or line.startswith("mode:DIO") or line.startswith("load:"):
                    continue
                if line.startswith("entry "):
                    continue
                # Filter long runs of repeated chars (line noise from baud transitions)
                if len(line) > 20 and len(set(line)) <= 2:
                    continue
                # Filter wheel RPM telemetry (L:xxx R:xxx) — too chatty for interactive use
                if line.startswith("L:") and " R:" in line:
                    continue
                # Deduplicate
                if line == self._last_msg:
                    continue
                self._last_msg = line
                # Track state messages
                if "RELOAD DONE" in line or "SHOT FIRED" in line or "RETRACT" in line or "DISPENS" in line:
                    self.last_state_msg = line
                print(f"  <- {line}")
            except serial.SerialException:
                break
            except Exception:
                pass

    def stop(self):
        self._running = False


# --------------- UDP listener ---------------

class UDPJointListener:
    """Background thread that listens for UDP pose packets and stores latest joint positions."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.lock = threading.Lock()
        self.joints: Dict[str, dict] = {}
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

TARGETABLE_JOINTS = [
    "nose",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
]


def send_serial(ser, cmd_str):
    """Send a command to the BLM via serial."""
    ser.write((cmd_str + "\n").encode())


def main():
    ap = argparse.ArgumentParser(description="Interactive live BLM aim + shoot test")
    ap.add_argument("--serial-port", required=True)
    ap.add_argument("--baud-rate", type=int, default=921600)
    ap.add_argument("--udp-host", default="0.0.0.0")
    ap.add_argument("--udp-port", type=int, default=5005)
    ap.add_argument("--launcher-x-mm", type=float, default=600.0)
    ap.add_argument("--launcher-y-mm", type=float, default=1560.0)
    ap.add_argument("--launcher-z-mm", type=float, default=500.0)
    ap.add_argument("--launcher-yaw-deg", type=float, required=True)
    ap.add_argument("--v-base-mps", type=float, default=10.0,
                    help="Assumed ball exit speed (m/s) for ballistic calculation")
    ap.add_argument("--wheel-rpm", type=float, default=800.0,
                    help="Flywheel RPM to set when aiming (both wheels)")
    ap.add_argument("--correction-model",
                    default="garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/correction_model.json")
    ap.add_argument("--correction-mode", choices=["none", "bias", "linear"], default="none")
    ap.add_argument("--pitch-trim-deg", type=float, default=0.0)
    ap.add_argument("--yaw-trim-deg", type=float, default=0.0)
    ap.add_argument("--shoot-enabled", action="store_true",
                    help="Enable shoot command. Without this flag, 'shoot' is blocked.")
    ap.add_argument("--log-jsonl", default="", help="Log decisions to JSONL file")
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
    ser.reset_input_buffer()

    # Start serial reader thread
    serial_reader = SerialReader(ser)

    send_serial(ser, "center")
    time.sleep(0.5)
    print(f"[OK] Serial connected: {args.serial_port}, BLM centered")

    if args.shoot_enabled:
        print(f"[!!] SHOOT ENABLED — wheel RPM: {args.wheel_rpm:.0f}")
    else:
        print(f"[OK] Shoot DISABLED (aim-only mode). Use --shoot-enabled to allow firing.")

    # Open log file
    log_fp = None
    if args.log_jsonl:
        Path(args.log_jsonl).parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(args.log_jsonl, "a")
        print(f"[OK] Logging to {args.log_jsonl}")

    print("\n" + "=" * 60)
    print("  Interactive BLM Aim + Shoot Test")
    print("=" * 60)
    print("\nFull cycle:  reload → <joint> → shoot → reload → ...")
    print("\nCommands:")
    print("  <joint_name>  — aim at joint + spin wheels")
    print("  reload        — retract pusher, load ball, center aim")
    print("  shoot         — fire (only if --shoot-enabled)")
    print("  joints        — show detected joints")
    print("  status        — UDP + serial status")
    print("  info          — query BLM angles/RPM/state")
    print("  center        — return BLM to home")
    print("  stop          — emergency stop")
    print("  quit          — exit safely")
    print(f"\nTargetable: {', '.join(TARGETABLE_JOINTS)}")
    print()

    test_number = 0
    last_aim_cmd = None  # track last aim command for logging

    while True:
        try:
            cmd = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not cmd:
            continue

        cmd_low = cmd.lower()

        # --- Direct BLM commands ---
        if cmd_low == "quit":
            break

        if cmd_low == "stop":
            send_serial(ser, "stop")
            time.sleep(0.3)
            print("  [STOPPED]")
            continue

        if cmd_low == "center":
            send_serial(ser, "center")
            time.sleep(0.3)
            continue

        if cmd_low == "info":
            send_serial(ser, "info")
            time.sleep(0.5)  # wait for 3 info lines
            continue

        if cmd_low == "reload":
            print("  Reloading: retract pusher → dispense ball → center aim...")
            send_serial(ser, "reload")
            # Wait for reload completion (ball detect or timeout)
            t0 = time.time()
            while time.time() - t0 < 15:  # max 15s wait
                if "RELOAD DONE" in serial_reader.last_state_msg:
                    break
                time.sleep(0.2)
            serial_reader.last_state_msg = ""
            print("  [RELOAD COMPLETE] Ready for next aim.")
            continue

        if cmd_low == "shoot":
            if not args.shoot_enabled:
                print("  [BLOCKED] Shoot is disabled. Use --shoot-enabled flag.")
                continue
            if last_aim_cmd is None:
                print("  [BLOCKED] Aim at a joint first before shooting.")
                continue
            confirm = input("  FIRE? This will launch a ball. [yes/N] ").strip().lower()
            if confirm != "yes":
                print("  Aborted.")
                continue
            print("  Firing...")
            send_serial(ser, "shoot")
            # Wait for shot fired
            t0 = time.time()
            while time.time() - t0 < 10:
                if "SHOT FIRED" in serial_reader.last_state_msg:
                    break
                time.sleep(0.2)
            serial_reader.last_state_msg = ""

            # Log
            if log_fp and last_aim_cmd:
                log_rec = {**last_aim_cmd, "action": "shoot", "shoot_timestamp": time.time()}
                log_fp.write(json.dumps(log_rec, ensure_ascii=False) + "\n")
                log_fp.flush()
            last_aim_cmd = None
            print("  [SHOT COMPLETE] Type 'reload' to load next ball.")
            continue

        if cmd_low == "status":
            pkt_count, last_ts = udp.get_status()
            age = time.time() - last_ts if last_ts > 0 else float("inf")
            print(f"  UDP: {pkt_count} packets, last {age:.1f}s ago")
            print(f"  Joints tracked: {list(udp.get_all_joints().keys())}")
            continue

        if cmd_low == "joints":
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

        # --- Joint aim ---
        joint_name = cmd_low.replace("-", "_")
        joint_data = udp.get_joint(joint_name)

        if joint_data is None:
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

        v_raw, h_raw = v_deg, h_deg

        # SAFETY: clamp pitch to [0, 30], yaw to [-30, 30]
        v_deg = max(0.0, min(30.0, v_deg))
        h_deg = max(-30.0, min(30.0, h_deg))
        was_clamped = (v_deg != v_raw) or (h_deg != h_raw)

        test_number += 1
        wl = int(args.wheel_rpm) if args.shoot_enabled else 0
        wr = int(args.wheel_rpm) if args.shoot_enabled else 0

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
        print(f"  Command:   set {v_deg:.1f} {h_deg:.1f} {wl} {wr}")

        confirm = input("  Send? [y/N] ").strip().lower()
        if confirm != "y":
            print("  Skipped.")
            continue

        # Send aim + wheels
        cmd_str = f"set {v_deg:.1f} {h_deg:.1f} {wl} {wr}"
        send_serial(ser, cmd_str)
        time.sleep(0.5)

        # Visual check
        visual = input("  Aim looks correct? [y/n/skip] ").strip().lower()

        # Store for shoot logging
        last_aim_cmd = {
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
            "wheel_rpm": args.wheel_rpm,
            "visual_check": visual,
            "conf": joint_data["conf"],
            "cams": joint_data["cams"],
            "data_age_sec": age,
        }

        # Log aim
        if log_fp:
            log_rec = {**last_aim_cmd, "action": "aim"}
            log_fp.write(json.dumps(log_rec, ensure_ascii=False) + "\n")
            log_fp.flush()

        if args.shoot_enabled:
            print(f"  Wheels spinning to {wl} RPM. Type 'shoot' when ready.")
        print()

    # Cleanup
    print("\nShutting down safely...")
    send_serial(ser, "stop")
    time.sleep(0.3)
    send_serial(ser, "center")
    time.sleep(1)
    serial_reader.stop()
    udp.stop()
    ser.close()
    if log_fp:
        log_fp.close()
    print("Done.")


if __name__ == "__main__":
    main()
