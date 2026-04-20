#!/usr/bin/env python3
"""
Launcher runtime controller:
- Receives live 3D body targets over UDP (JSON, world frame, mm)
- Solves aim + velocity using ballistic model
- Sends commands to ESP32 launcher over serial ("set", "shoot", "center", "stop")
- Enforces safety gates (zone, angle limits, confidence/camera/stability)

This is an operational bridge for:
right_knee -> right_hip -> left_shoulder sequence.
"""

import argparse
import csv
import json
import math
import queue
import signal
import socket
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from launcher_common import apply_correction, load_correction_model, solve_angles_ballistic, world_to_launcher_xy_delta

try:
    import serial
except Exception:  # pragma: no cover
    serial = None


@dataclass
class JointSample:
    ts: float
    x_mm: float
    y_mm: float
    z_mm: float
    conf: float
    cams: int


def load_zone_by_joint(
    csv_path: str,
    joints: List[str],
    allow_missing: bool = False,
) -> Dict[str, Optional[Dict[str, float]]]:
    if not csv_path:
        if allow_missing:
            return {j: None for j in joints}
        raise RuntimeError("Empty --zone-csv. Use --disable-zone-check or provide a CSV.")

    zones = {
        j: {
            "x_min": float("inf"),
            "x_max": float("-inf"),
            "y_min": float("inf"),
            "y_max": float("-inf"),
            "z_min": float("inf"),
            "z_max": float("-inf"),
        }
        for j in joints
    }
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jn = row.get("joint_name", "").strip()
            if jn not in zones:
                continue
            x = float(row["x_mm"])
            y = float(row["y_mm"])
            z = float(row["z_mm"])
            zc = zones[jn]
            zc["x_min"] = min(zc["x_min"], x)
            zc["x_max"] = max(zc["x_max"], x)
            zc["y_min"] = min(zc["y_min"], y)
            zc["y_max"] = max(zc["y_max"], y)
            zc["z_min"] = min(zc["z_min"], z)
            zc["z_max"] = max(zc["z_max"], z)

    out: Dict[str, Optional[Dict[str, float]]] = {}
    for jn, z in zones.items():
        has_values = np.isfinite([z["x_min"], z["x_max"], z["y_min"], z["y_max"], z["z_min"], z["z_max"]]).all()
        if has_values:
            out[jn] = z
        elif allow_missing:
            out[jn] = None
            print(f"[WARN] Zone for joint '{jn}' missing in {csv_path}; zone check disabled for this joint")
        else:
            raise RuntimeError(f"Joint '{jn}' not found in CSV zone file: {csv_path}")
    return out


def point_in_zone(x_mm: float, y_mm: float, z_mm: float, zone: Dict[str, float], margin_mm: float = 0.0) -> bool:
    return (
        zone["x_min"] - margin_mm <= x_mm <= zone["x_max"] + margin_mm
        and zone["y_min"] - margin_mm <= y_mm <= zone["y_max"] + margin_mm
        and zone["z_min"] - margin_mm <= z_mm <= zone["z_max"] + margin_mm
    )


def calculate_kinematics_v1(
    x_lat_m: float,
    y_fwd_m: float,
    z_target_m: float,
    v_ms: float,
    z_launcher_m: float,
    g: float = 9.81,
) -> Optional[Tuple[float, float]]:
    """
    Same math style as version1.1.py:
      h = atan2(x, y)
      d = sqrt(x^2 + y^2)
      delta_z = z_target - z_launcher
      low-arc solution for v
    """
    d = math.sqrt(x_lat_m * x_lat_m + y_fwd_m * y_fwd_m)
    if d <= 1e-6:
        return None
    h_deg = math.degrees(math.atan2(x_lat_m, y_fwd_m))
    delta_z = z_target_m - z_launcher_m
    discriminant = v_ms**4 - g * (g * d**2 + 2.0 * delta_z * v_ms**2)
    if discriminant < 0.0:
        return None
    v_rad = math.atan((v_ms**2 - math.sqrt(discriminant)) / (g * d))
    v_deg = math.degrees(v_rad)
    return v_deg, h_deg


def speed_from_distance(
    distance_m: float,
    base_mps: float,
    slope_mps_per_m: float,
    min_mps: float,
    max_mps: float,
) -> float:
    v = base_mps + slope_mps_per_m * distance_m
    return max(min_mps, min(max_mps, v))


def parse_joint_float_map(spec: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    s = (spec or "").strip()
    if not s:
        return out
    chunks = [x.strip() for x in s.replace(";", ",").split(",") if x.strip()]
    for c in chunks:
        if ":" not in c:
            raise RuntimeError(f"Invalid map item '{c}', expected joint:value")
        k, v = c.split(":", 1)
        out[k.strip()] = float(v.strip())
    return out


def parse_joint_name_map(spec: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    s = (spec or "").strip()
    if not s:
        return out
    chunks = [x.strip() for x in s.replace(";", ",").split(",") if x.strip()]
    for c in chunks:
        if ":" not in c:
            raise RuntimeError(f"Invalid map item '{c}', expected target_joint:source_joint")
        k, v = c.split(":", 1)
        target_joint = k.strip()
        source_joint = v.strip()
        if not target_joint or not source_joint:
            raise RuntimeError(f"Invalid map item '{c}', expected target_joint:source_joint")
        out[target_joint] = source_joint
    return out


def parse_joint_samples(pkt: dict, now_ts: float) -> List[Tuple[str, JointSample]]:
    out = []
    pkt_ts = float(pkt.get("ts", now_ts))

    # single-joint format
    if "joint" in pkt and "x_mm" in pkt and "y_mm" in pkt and "z_mm" in pkt:
        j = str(pkt["joint"])
        s = JointSample(
            ts=pkt_ts,
            x_mm=float(pkt["x_mm"]),
            y_mm=float(pkt["y_mm"]),
            z_mm=float(pkt["z_mm"]),
            conf=float(pkt.get("conf", 1.0)),
            cams=int(pkt.get("cams", 0)),
        )
        out.append((j, s))
        return out

    # multi-joint format
    joints_obj = pkt.get("joints", {})
    if isinstance(joints_obj, dict):
        parsed: Dict[str, JointSample] = {}
        for j, val in joints_obj.items():
            if not isinstance(val, dict):
                continue
            if not all(k in val for k in ("x_mm", "y_mm", "z_mm")):
                continue
            s = JointSample(
                ts=pkt_ts,
                x_mm=float(val["x_mm"]),
                y_mm=float(val["y_mm"]),
                z_mm=float(val["z_mm"]),
                conf=float(val.get("conf", 1.0)),
                cams=int(val.get("cams", 0)),
            )
            out.append((j, s))
            parsed[j] = s
        # Derived target used in stage-2 protocol.
        if "left_hip" in parsed and "right_hip" in parsed:
            lh = parsed["left_hip"]
            rh = parsed["right_hip"]
            bc = JointSample(
                ts=pkt_ts,
                x_mm=0.5 * (lh.x_mm + rh.x_mm),
                y_mm=0.5 * (lh.y_mm + rh.y_mm),
                z_mm=0.5 * (lh.z_mm + rh.z_mm),
                conf=min(lh.conf, rh.conf),
                cams=min(lh.cams, rh.cams),
            )
            out.append(("body_center", bc))
    return out


def cmd_input_loop(cmd_q: queue.Queue, stop_ev: threading.Event):
    while not stop_ev.is_set():
        try:
            line = input().strip().lower()
        except EOFError:
            break
        except KeyboardInterrupt:
            cmd_q.put("quit")
            break
        if line:
            cmd_q.put(line)


def drain_serial_lines(ser, max_lines: int = 50):
    lines = []
    if ser is None:
        return lines
    try:
        n = 0
        while getattr(ser, "in_waiting", 0) > 0 and n < max_lines:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line:
                lines.append(line)
            n += 1
    except Exception:
        pass
    return lines


def read_rpm_from_lines(lines: List[str]) -> Optional[Tuple[float, float]]:
    for ln in reversed(lines):
        if ln.startswith("L:") and "R:" in ln:
            try:
                left_part, right_part = ln.split("R:")
                l = float(left_part.replace("L:", "").strip())
                r = float(right_part.strip())
                return l, r
            except Exception:
                continue
    return None


def stable_target_from_buffer(
    buf: deque,
    now_ts: float,
    stable_frames: int,
    stable_window_sec: float,
    min_conf: float,
    min_cams: int,
    stable_std_mm: float,
    zone: Optional[Dict[str, float]],
    zone_margin_mm: float,
) -> Optional[Tuple[np.ndarray, float, int, float]]:
    if len(buf) < stable_frames:
        return None
    recent = []
    for s in reversed(buf):
        if now_ts - s.ts > stable_window_sec:
            break
        recent.append(s)
        if len(recent) >= stable_frames:
            break
    if len(recent) < stable_frames:
        return None
    recent.reverse()

    for s in recent:
        if s.conf < min_conf or s.cams < min_cams:
            return None
        if zone is not None and not point_in_zone(s.x_mm, s.y_mm, s.z_mm, zone, margin_mm=zone_margin_mm):
            return None

    arr = np.array([[s.x_mm, s.y_mm, s.z_mm] for s in recent], dtype=np.float64)
    std_norm = float(np.linalg.norm(np.std(arr, axis=0)))
    if std_norm > stable_std_mm:
        return None
    mean_xyz = np.mean(arr, axis=0)
    conf_mean = float(np.mean([s.conf for s in recent]))
    cams_min = int(min(s.cams for s in recent))
    return mean_xyz, conf_mean, cams_min, std_norm


def main():
    ap = argparse.ArgumentParser(description="Run BLM sequence from live UDP joint targets.")
    ap.add_argument("--serial-port", required=True, help="ESP32 serial port, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud-rate", type=int, default=921600)
    ap.add_argument("--udp-host", default="0.0.0.0")
    ap.add_argument("--udp-port", type=int, default=5005)
    ap.add_argument("--static-target-x-mm", type=float, default=None, help="Enable one-terminal mode with static target X")
    ap.add_argument("--static-target-y-mm", type=float, default=None, help="Enable one-terminal mode with static target Y")
    ap.add_argument("--static-target-z-mm", type=float, default=None, help="Enable one-terminal mode with static target Z")
    ap.add_argument(
        "--static-target-joint",
        default="",
        help="Joint name for static mode. If empty, same point is fed to all joints in --targets.",
    )
    ap.add_argument("--static-target-conf", type=float, default=0.99)
    ap.add_argument("--static-target-cams", type=int, default=4)
    ap.add_argument(
        "--targets",
        default="right_knee,right_hip,left_shoulder",
        help="Comma-separated sequence of joints",
    )
    ap.add_argument(
        "--zone-csv",
        default="garage_lab_combined/gt_eval/joint_tuning_20260310_124311/trials_joint_81_mm.csv",
    )
    ap.add_argument(
        "--disable-zone-check",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Disable workspace-zone check for all targets",
    )
    ap.add_argument(
        "--allow-missing-zone-joints",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If a target joint is missing in zone CSV, keep running with zone check disabled for that joint",
    )
    ap.add_argument("--zone-margin-mm", type=float, default=0.0)

    ap.add_argument(
        "--correction-model",
        default="",
        help="Path to GT correction model JSON (from evaluate_ball_static_gt.py). "
             "Corrects systematic bias in 3D triangulation.",
    )
    ap.add_argument(
        "--correction-mode",
        choices=["none", "bias", "linear"],
        default="linear",
        help="Correction mode: 'none'=disabled, 'bias'=additive offset, 'linear'=per-axis linear fit (default)",
    )

    ap.add_argument("--launcher-x-mm", type=float, default=600.0)
    ap.add_argument("--launcher-y-mm", type=float, default=1560.0)
    ap.add_argument("--launcher-z-mm", type=float, default=500.0)
    ap.add_argument("--launcher-yaw-deg", type=float, required=True)

    ap.add_argument("--min-conf", type=float, default=0.35)
    ap.add_argument("--min-cams", type=int, default=3)
    ap.add_argument("--stable-frames", type=int, default=10)
    ap.add_argument("--stable-window-sec", type=float, default=1.2)
    ap.add_argument("--stable-std-mm", type=float, default=40.0)
    ap.add_argument("--acquire-timeout-sec", type=float, default=8.0)

    ap.add_argument("--max-abs-angle-deg", type=float, default=30.0)
    ap.add_argument(
        "--horizontal-only",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Disable vertical aiming dynamics and keep pitch fixed (yaw-only aiming).",
    )
    ap.add_argument(
        "--horizontal-fixed-v-deg",
        type=float,
        default=0.0,
        help="Pitch angle used when --horizontal-only is enabled.",
    )
    ap.add_argument("--g", type=float, default=9.81)
    ap.add_argument(
        "--solver",
        choices=["v1", "current"],
        default="v1",
        help="Ballistic solver: 'v1' matches version1.1.py equations",
    )
    ap.add_argument(
        "--fixed-speed-kmh",
        type=float,
        default=0.0,
        help="If >0, use this constant launch speed (km/h) like version1.1.py",
    )
    ap.add_argument(
        "--z-launcher-m",
        type=float,
        default=None,
        help="Launcher height for v1 solver; default uses --launcher-z-mm/1000",
    )
    ap.add_argument("--v-base-mps", type=float, default=10.0)
    ap.add_argument("--v-slope-mps-per-m", type=float, default=1.0)
    ap.add_argument("--v-min-mps", type=float, default=8.0)
    ap.add_argument("--v-max-mps", type=float, default=16.0)
    ap.add_argument(
        "--speed-scale",
        type=float,
        default=1.0,
        help="Global multiplier for solved launch speed (1.0 = unchanged)",
    )
    ap.add_argument("--velocity-to-rpm", type=float, default=80.0)
    ap.add_argument("--rpm-left-bias", type=float, default=0.0)
    ap.add_argument("--rpm-right-bias", type=float, default=0.0)
    ap.add_argument(
        "--pitch-trim-deg",
        type=float,
        default=0.0,
        help="Manual trim added to solved pitch angle (deg). Negative = lower shot",
    )
    ap.add_argument(
        "--yaw-trim-deg",
        type=float,
        default=0.0,
        help="Manual trim added to solved yaw angle (deg). Positive = more right",
    )
    ap.add_argument(
        "--yaw-source-map",
        default="",
        help="Optional target->yaw source map, e.g. right_knee:body_center",
    )

    ap.add_argument("--aim-settle-sec", type=float, default=0.45)
    ap.add_argument("--pre-aim-delay-sec", type=float, default=0.0, help="Wait before acquiring each target")
    ap.add_argument(
        "--pre-aim-delay-sec-map",
        default="",
        help="Optional per-target pre-aim delay, e.g. right_knee:10,nose:10,body_center:10",
    )
    ap.add_argument("--target-hold-sec", type=float, default=0.0, help="Seconds to keep aimed (and wheels spinning if enabled)")
    ap.add_argument(
        "--target-hold-sec-map",
        default="",
        help="Optional per-target hold override, e.g. right_knee:30,nose:30,body_center:30",
    )
    ap.add_argument(
        "--home-between-targets",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Send home command between targets",
    )
    ap.add_argument("--home-wait-sec", type=float, default=0.0, help="Wait after home-between-targets")
    ap.add_argument(
        "--run-once-per-start",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run one full target list then pause (requires typing 'start' again)",
    )
    ap.add_argument("--wait-rpm-sec", type=float, default=1.2)
    ap.add_argument(
        "--ignore-rpm-gate",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If enabled, continue hold/shoot sequence even when telemetry RPM gate is not reached",
    )
    ap.add_argument("--min-feed-rpm", type=float, default=400.0)
    ap.add_argument("--center-settle-sec", type=float, default=0.35)
    ap.add_argument(
        "--home-on-start",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Send 'set 0 0 0 0' when runtime starts",
    )
    ap.add_argument(
        "--home-on-exit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Send 'set 0 0 0 0' during graceful shutdown",
    )
    ap.add_argument(
        "--home-settle-sec",
        type=float,
        default=0.8,
        help="Wait after 'set 0 0 0 0' command",
    )
    ap.add_argument(
        "--setzero-on-start",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Send 'setzero' when runtime starts to lock current pose as logical zero",
    )
    ap.add_argument(
        "--setzero-settle-sec",
        type=float,
        default=0.25,
        help="Wait after 'setzero' command",
    )
    ap.add_argument(
        "--return-center-after-each-target",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If false, keep last aimed position instead of sending center after each target",
    )
    ap.add_argument(
        "--max-target-events",
        type=int,
        default=0,
        help="Stop auto-loop after N completed target events (0 = infinite)",
    )
    ap.add_argument("--shoot-enabled", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--shoot-pulse-sec", type=float, default=0.25)
    ap.add_argument(
        "--center-on-exit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Send center command on graceful exit (Ctrl+C/quit/SIGTERM)",
    )
    ap.add_argument(
        "--stop-on-exit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Send stop command on graceful exit (Ctrl+C/quit/SIGTERM)",
    )
    ap.add_argument(
        "--exit-center-wait-sec",
        type=float,
        default=0.6,
        help="Wait after center command before closing serial",
    )
    ap.add_argument(
        "--aim-only-wheel-rpm",
        type=int,
        default=0,
        help="Wheel RPM used in --no-shoot-enabled mode (default: 0 for safe aiming)",
    )
    ap.add_argument(
        "--dry-run-log-jsonl",
        default="",
        help="If set, write one JSON line per target decision for reporting",
    )
    ap.add_argument(
        "--correction-model",
        default="",
        help="Path to GT correction model JSON (from evaluate_ball_static_gt.py). "
             "Default: garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/correction_model.json",
    )
    ap.add_argument(
        "--correction-mode",
        choices=["none", "bias", "linear"],
        default="none",
        help="Correction mode: 'none' = no correction, 'bias' = global mean offset, "
             "'linear' = per-axis linear fit (most accurate)",
    )

    args = ap.parse_args()

    if serial is None:
        raise RuntimeError("pyserial is not installed. Install: ./venv/bin/pip install pyserial")

    # Load correction model if specified
    correction_model = load_correction_model(args.correction_model) if args.correction_model else None
    if correction_model is not None:
        print(f"[OK] Correction model loaded ({args.correction_mode}): bias={correction_model['bias']}")
    elif args.correction_mode != "none":
        print("[INFO] No correction model — using raw triangulated positions")

    target_order = [x.strip() for x in args.targets.split(",") if x.strip()]
    if not target_order:
        raise RuntimeError("Empty --targets list")
    yaw_source_map = parse_joint_name_map(args.yaw_source_map)
    valid_joint_names = set(target_order)
    valid_joint_names.add("body_center")
    for target_joint, source_joint in yaw_source_map.items():
        if target_joint not in valid_joint_names:
            raise RuntimeError(
                f"--yaw-source-map target '{target_joint}' must be one of: {', '.join(sorted(valid_joint_names))}"
            )
        if source_joint not in valid_joint_names:
            raise RuntimeError(
                f"--yaw-source-map source '{source_joint}' must be one of: {', '.join(sorted(valid_joint_names))}"
            )
    tracked_joints = set(target_order)
    tracked_joints.update(yaw_source_map.values())
    if args.disable_zone_check:
        zones: Dict[str, Optional[Dict[str, float]]] = {j: None for j in target_order}
    else:
        zones = load_zone_by_joint(
            args.zone_csv,
            target_order,
            allow_missing=args.allow_missing_zone_joints,
        )
    hold_sec_map = parse_joint_float_map(args.target_hold_sec_map)
    pre_aim_sec_map = parse_joint_float_map(args.pre_aim_delay_sec_map)

    static_xyz = [args.static_target_x_mm, args.static_target_y_mm, args.static_target_z_mm]
    static_mode = all(v is not None for v in static_xyz)
    if any(v is not None for v in static_xyz) and not static_mode:
        raise RuntimeError("Use all three static coords: --static-target-x-mm --static-target-y-mm --static-target-z-mm")
    if args.static_target_joint and args.static_target_joint not in target_order:
        raise RuntimeError(f"--static-target-joint '{args.static_target_joint}' must be in --targets")

    ser = serial.Serial(args.serial_port, args.baud_rate, timeout=0.05)
    time.sleep(1.5)
    print(f"[OK] Serial connected: {args.serial_port} @ {args.baud_rate}")

    sock = None
    if not static_mode:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((args.udp_host, args.udp_port))
        sock.settimeout(0.10)
        print(f"[OK] UDP listening: {args.udp_host}:{args.udp_port}")
    else:
        print(
            "[OK] Static target mode enabled:"
            f" xyz=({args.static_target_x_mm},{args.static_target_y_mm},{args.static_target_z_mm}) "
            f"joint={args.static_target_joint or 'ALL'}"
        )

    cmd_q = queue.Queue()
    stop_ev = threading.Event()
    th = threading.Thread(target=cmd_input_loop, args=(cmd_q, stop_ev), daemon=True)
    th.start()

    print("Operator commands: start | home | setzero | shoot | reload | estop | clear | status | quit")

    buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
    launcher_xyz = np.array([args.launcher_x_mm, args.launcher_y_mm, args.launcher_z_mm], dtype=np.float64)

    # Load correction model
    correction_model = None
    if args.correction_mode != "none":
        model_path = args.correction_model or \
            "garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/correction_model.json"
        correction_model = load_correction_model(model_path)
        if correction_model is not None:
            print(f"[OK] Correction model loaded: {model_path} (mode={args.correction_mode})")
            bias = correction_model.get("global_bias_add_mm", {})
            print(f"     Bias: X={bias.get('x',0):.1f} Y={bias.get('y',0):.1f} Z={bias.get('z',0):.1f} mm")
        else:
            print(f"[WARN] Correction model not found at {model_path}, running uncorrected")

    started = False
    estop = False
    target_idx = 0
    last_stop_sent = False
    current_joint = None
    completed_target_events = 0

    log_fp = None
    if args.dry_run_log_jsonl:
        log_path = Path(args.dry_run_log_jsonl)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(log_path, "a", encoding="utf-8")
        print(f"[OK] Decision log enabled: {log_path}")
    if args.horizontal_only:
        print(
            "[INFO] Horizontal-only mode enabled: "
            f"pitch fixed at {args.horizontal_fixed_v_deg:.2f} deg, yaw from target."
        )

    def send_cmd(cmd: str):
        ser.write((cmd.strip() + "\n").encode("utf-8"))
        ser.flush()
        print(f"[TX] {cmd.strip()}")

    def send_home_set():
        send_cmd("set 0 0 0 0")
        time.sleep(max(0.0, args.home_settle_sec))

    def send_setzero():
        send_cmd("setzero")
        time.sleep(max(0.0, args.setzero_settle_sec))

    def graceful_shutdown(reason: str = ""):
        if reason:
            print(f"[INFO] Graceful shutdown: {reason}")
        try:
            if args.stop_on_exit:
                send_cmd("stop")
            if args.home_on_exit:
                send_home_set()
            elif args.center_on_exit:
                send_cmd("center")
                time.sleep(max(0.0, args.exit_center_wait_sec))
        except Exception:
            pass

    def _sig_handler(signum, _frame):
        name = signal.Signals(signum).name
        raise KeyboardInterrupt(f"signal:{name}")

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    def ingest_targets_once():
        now_ts = time.time()
        if static_mode:
            if args.static_target_joint:
                target_joints = [args.static_target_joint]
                src_joint = yaw_source_map.get(args.static_target_joint)
                if src_joint and src_joint != args.static_target_joint:
                    target_joints.append(src_joint)
            else:
                target_joints = list(target_order)
                for src_joint in yaw_source_map.values():
                    if src_joint not in target_joints:
                        target_joints.append(src_joint)
            for j in target_joints:
                buffers[j].append(
                    JointSample(
                        ts=now_ts,
                        x_mm=float(args.static_target_x_mm),
                        y_mm=float(args.static_target_y_mm),
                        z_mm=float(args.static_target_z_mm),
                        conf=float(args.static_target_conf),
                        cams=int(args.static_target_cams),
                    )
                )
            return
        try:
            data, _ = sock.recvfrom(65535)
            pkt = json.loads(data.decode("utf-8", errors="ignore"))
            for j, s in parse_joint_samples(pkt, now_ts):
                if j in tracked_joints:
                    buffers[j].append(s)
        except socket.timeout:
            pass
        except Exception:
            pass

    def log_decision(
        *,
        decision: str,
        joint_name: Optional[str] = None,
        raw_world_xyz_mm: Optional[np.ndarray] = None,
        corrected_world_xyz_mm: Optional[np.ndarray] = None,
        transformed_launcher_xyz: Optional[dict] = None,
        calculated_pitch_yaw_v: Optional[dict] = None,
        execution_time_ms: Optional[float] = None,
        extra: Optional[dict] = None,
    ):
        if log_fp is None:
            return
        rec = {
            "timestamp": time.time(),
            "input_joint_name": joint_name,
            "raw_world_xyz_mm": raw_world_xyz_mm.tolist() if isinstance(raw_world_xyz_mm, np.ndarray) else raw_world_xyz_mm,
            "corrected_world_xyz_mm": corrected_world_xyz_mm.tolist() if isinstance(corrected_world_xyz_mm, np.ndarray) else corrected_world_xyz_mm,
            "correction_mode": args.correction_mode,
            "transformed_launcher_xyz": transformed_launcher_xyz,
            "calculated_pitch_yaw_v": calculated_pitch_yaw_v,
            "decision": decision,
            "execution_time_ms": execution_time_ms,
        }
        if extra:
            rec["extra"] = extra
        log_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log_fp.flush()

    def handle_operator_command(op: str, *, stage: str, joint_name: Optional[str] = None):
        nonlocal started, estop, last_stop_sent, current_joint
        active_joint = joint_name if joint_name is not None else current_joint
        if op == "start":
            started = True
            print("[INFO] Sequence started")
            return
        if op == "home":
            send_home_set()
            print("[INFO] Home command executed (set 0 0 0 0)")
            return
        if op == "setzero":
            send_setzero()
            print("[INFO] setzero executed (current pose is now logical zero)")
            return
        if op == "shoot":
            send_cmd("shoot")
            print("[INFO] Manual SHOOT command sent")
            return
        if op == "reload":
            send_cmd("reload")
            print("[INFO] Manual RELOAD command sent")
            return
        if op == "estop":
            estop = True
            print("[INFO] E-STOP latched")
            log_decision(
                decision="ESTOP",
                joint_name=active_joint,
                extra={"source": "operator_command", "stage": stage},
            )
            return
        if op == "clear":
            estop = False
            last_stop_sent = False
            print("[INFO] E-STOP cleared")
            return
        if op == "status":
            if stage == "main":
                print(
                    f"[STATUS] started={started} estop={estop} "
                    f"target={target_order[target_idx]} shoot_enabled={args.shoot_enabled} "
                    f"mode={'static' if static_mode else 'udp'}"
                )
            else:
                print(
                    f"[STATUS] stage={stage} joint={active_joint} "
                    f"started={started} estop={estop}"
                )
            return
        if op == "quit":
            raise KeyboardInterrupt

    def drain_operator_commands(*, stage: str, joint_name: Optional[str] = None):
        while True:
            try:
                op = cmd_q.get_nowait()
            except queue.Empty:
                break
            handle_operator_command(op, stage=stage, joint_name=joint_name)

    def wait_with_background(duration_sec: float, *, stage: str, joint_name: Optional[str] = None):
        end_ts = time.time() + max(0.0, duration_sec)
        while time.time() < end_ts:
            drain_operator_commands(stage=stage, joint_name=joint_name)
            if estop:
                break
            ingest_targets_once()
            _ = drain_serial_lines(ser)
            time.sleep(0.03)

    # Initial safe state:
    # 1) optionally latch current pose as logical zero
    # 2) optionally move to 0/0 home command
    if args.setzero_on_start:
        send_setzero()
    if args.home_on_start:
        send_home_set()
    elif not args.setzero_on_start:
        send_cmd("center")
        time.sleep(args.center_settle_sec)

    try:
        while True:
            # Operator commands
            drain_operator_commands(stage="main", joint_name=current_joint)

            # Emergency stop latch
            if estop:
                if not last_stop_sent:
                    send_cmd("stop")
                    last_stop_sent = True
                # keep draining UDP + serial but no actions
                ingest_targets_once()
                _ = drain_serial_lines(ser)
                continue

            if not started:
                # drain incoming target stream while waiting
                ingest_targets_once()
                _ = drain_serial_lines(ser)
                continue

            joint = target_order[target_idx]
            current_joint = joint
            zone = zones[joint]
            pre_aim_sec = max(0.0, args.pre_aim_delay_sec + pre_aim_sec_map.get(joint, 0.0))
            buffers[joint].clear()
            if pre_aim_sec > 0.0:
                print(f"[INFO] Pre-aim delay for {joint}: {pre_aim_sec:.2f}s")
                wait_with_background(pre_aim_sec, stage="pre_aim_delay", joint_name=joint)
                if estop:
                    log_decision(decision="ESTOP", joint_name=joint, extra={"stage": "pre_aim_delay"})
                    continue

            print(f"[INFO] Waiting stable target: {joint}")

            acquire_start = time.time()
            stable = None
            while (time.time() - acquire_start) < args.acquire_timeout_sec:
                # Commands during acquisition
                drain_operator_commands(stage="acquire", joint_name=joint)
                if estop:
                    break

                ingest_targets_once()

                _ = drain_serial_lines(ser)
                stable = stable_target_from_buffer(
                    buf=buffers[joint],
                    now_ts=time.time(),
                    stable_frames=args.stable_frames,
                    stable_window_sec=args.stable_window_sec,
                    min_conf=args.min_conf,
                    min_cams=args.min_cams,
                    stable_std_mm=args.stable_std_mm,
                    zone=zone,
                    zone_margin_mm=args.zone_margin_mm,
                )
                if stable is not None:
                    break

            if estop:
                log_decision(decision="ESTOP", joint_name=joint, extra={"stage": "acquire_or_wait"})
                continue

            acquire_elapsed_sec = max(0.0, time.time() - acquire_start)

            if stable is None:
                print(f"[WARN] No stable target for {joint}, skipping")
                latest = buffers[joint][-1] if buffers[joint] else None
                raw_xyz = None
                extra = {"stage": "acquire_timeout"}
                if latest is not None:
                    raw_xyz = np.array([latest.x_mm, latest.y_mm, latest.z_mm], dtype=np.float64)
                    extra["latest_conf"] = float(latest.conf)
                    extra["latest_cams"] = int(latest.cams)
                log_decision(
                    decision="LOW_CONFIDENCE",
                    joint_name=joint,
                    raw_world_xyz_mm=raw_xyz,
                    execution_time_ms=0.0,
                    extra={**extra, "acquire_elapsed_sec": acquire_elapsed_sec},
                )
                target_idx = (target_idx + 1) % len(target_order)
                continue

            xyz_mm, conf_mean, cams_min, std_mm = stable
            # Apply GT correction model to compensate systematic extrinsics bias
            xyz_mm_raw = xyz_mm.copy()
            xyz_mm = apply_correction(xyz_mm, correction_model, mode=args.correction_mode)
            calc_t0 = time.perf_counter()
            x_lat_m, y_fwd_m, dz_m = world_to_launcher_xy_delta(
                target_xyz_mm=xyz_mm,
                launcher_xyz_mm=launcher_xyz,
                launcher_yaw_deg=args.launcher_yaw_deg,
            )

            yaw_source_joint = yaw_source_map.get(joint, joint)
            yaw_source_used = False
            yaw_source_fallback_reason: Optional[str] = None
            x_lat_yaw_m = x_lat_m
            y_fwd_yaw_m = y_fwd_m
            if yaw_source_joint != joint:
                source_zone = zones.get(yaw_source_joint)
                source_stable = stable_target_from_buffer(
                    buf=buffers[yaw_source_joint],
                    now_ts=time.time(),
                    stable_frames=args.stable_frames,
                    stable_window_sec=args.stable_window_sec,
                    min_conf=args.min_conf,
                    min_cams=args.min_cams,
                    stable_std_mm=args.stable_std_mm,
                    zone=source_zone,
                    zone_margin_mm=args.zone_margin_mm,
                )
                if source_stable is None:
                    if not buffers[yaw_source_joint]:
                        yaw_source_fallback_reason = "source_buffer_empty"
                    else:
                        yaw_source_fallback_reason = "source_not_stable"
                    print(
                        f"[WARN] Yaw source unavailable for {joint}: source={yaw_source_joint}, "
                        f"fallback={yaw_source_fallback_reason}"
                    )
                else:
                    source_xyz_mm = apply_correction(source_stable[0], correction_model, mode=args.correction_mode)
                    x_lat_src_m, y_fwd_src_m, _ = world_to_launcher_xy_delta(
                        target_xyz_mm=source_xyz_mm,
                        launcher_xyz_mm=launcher_xyz,
                        launcher_yaw_deg=args.launcher_yaw_deg,
                    )
                    if abs(x_lat_src_m) <= 1e-9 and abs(y_fwd_src_m) <= 1e-9:
                        yaw_source_fallback_reason = "source_degenerate_xy"
                        print(
                            f"[WARN] Yaw source degenerate for {joint}: source={yaw_source_joint}, "
                            "fallback=source_degenerate_xy"
                        )
                    else:
                        yaw_source_used = True
                        x_lat_yaw_m = x_lat_src_m
                        y_fwd_yaw_m = y_fwd_src_m

            yaw_extra = {
                "yaw_source_joint": yaw_source_joint,
                "yaw_source_used": yaw_source_used,
            }
            if yaw_source_fallback_reason:
                yaw_extra["yaw_source_fallback_reason"] = yaw_source_fallback_reason

            d_m = math.sqrt(x_lat_m * x_lat_m + y_fwd_m * y_fwd_m + dz_m * dz_m)
            if args.fixed_speed_kmh > 0:
                v_ms = args.fixed_speed_kmh / 3.6
            else:
                v_ms = speed_from_distance(
                    d_m, args.v_base_mps, args.v_slope_mps_per_m, args.v_min_mps, args.v_max_mps
                )
            v_ms = max(0.1, v_ms * args.speed_scale)

            if args.horizontal_only:
                # Keep vertical axis fixed and use only horizontal yaw for aiming.
                sol = (float(args.horizontal_fixed_v_deg), 0.0)
            elif args.solver == "v1":
                z_launcher_m = args.z_launcher_m if args.z_launcher_m is not None else (args.launcher_z_mm / 1000.0)
                sol = calculate_kinematics_v1(
                    x_lat_m=x_lat_m,
                    y_fwd_m=y_fwd_m,
                    z_target_m=float(xyz_mm[2]) / 1000.0,
                    v_ms=v_ms,
                    z_launcher_m=z_launcher_m,
                    g=args.g,
                )
            else:
                sol = solve_angles_ballistic(x_lat_m, y_fwd_m, dz_m, v_ms=v_ms, g=args.g)
            exec_ms = (time.perf_counter() - calc_t0) * 1000.0
            if sol is None:
                print(f"[WARN] Unreachable target for {joint} at v={v_ms:.2f} m/s")
                log_decision(
                    decision="OUT_OF_RANGE",
                    joint_name=joint,
                    raw_world_xyz_mm=xyz_mm_raw,
                    corrected_world_xyz_mm=xyz_mm,
                    transformed_launcher_xyz={
                        "x_lateral_m": x_lat_m,
                        "y_forward_m": y_fwd_m,
                        "dz_m": dz_m,
                        "distance_m": d_m,
                    },
                    calculated_pitch_yaw_v={
                        "pitch_deg": None,
                        "yaw_deg": None,
                        "speed_mps": v_ms,
                        "rpm_cmd": int(round(v_ms * args.velocity_to_rpm)),
                    },
                    execution_time_ms=exec_ms,
                    extra={
                        "reason": "unreachable",
                        "conf_mean": conf_mean,
                        "cams_min": cams_min,
                        "std_mm": std_mm,
                        "acquire_elapsed_sec": acquire_elapsed_sec,
                        **yaw_extra,
                    },
                )
                target_idx = (target_idx + 1) % len(target_order)
                continue

            v_deg, _h_deg_target = sol
            h_deg = math.degrees(math.atan2(x_lat_yaw_m, y_fwd_yaw_m))
            v_deg += args.pitch_trim_deg
            h_deg += args.yaw_trim_deg
            if abs(v_deg) > args.max_abs_angle_deg or abs(h_deg) > args.max_abs_angle_deg:
                print(
                    f"[WARN] Angle out of bounds for {joint}: v={v_deg:.2f}, h={h_deg:.2f}, "
                    f"limit={args.max_abs_angle_deg}"
                )
                log_decision(
                    decision="OUT_OF_RANGE",
                    joint_name=joint,
                    raw_world_xyz_mm=xyz_mm_raw,
                    corrected_world_xyz_mm=xyz_mm,
                    transformed_launcher_xyz={
                        "x_lateral_m": x_lat_m,
                        "y_forward_m": y_fwd_m,
                        "dz_m": dz_m,
                        "distance_m": d_m,
                    },
                    calculated_pitch_yaw_v={
                        "pitch_deg": v_deg,
                        "yaw_deg": h_deg,
                        "speed_mps": v_ms,
                        "rpm_cmd": int(round(v_ms * args.velocity_to_rpm)),
                    },
                    execution_time_ms=exec_ms,
                    extra={
                        "reason": "angle_limit",
                        "angle_limit_deg": args.max_abs_angle_deg,
                        "conf_mean": conf_mean,
                        "cams_min": cams_min,
                        "std_mm": std_mm,
                        "acquire_elapsed_sec": acquire_elapsed_sec,
                        **yaw_extra,
                    },
                )
                target_idx = (target_idx + 1) % len(target_order)
                continue

            rpm = int(round(v_ms * args.velocity_to_rpm))
            wl = int(round(rpm + args.rpm_left_bias))
            wr = int(round(rpm + args.rpm_right_bias))
            yaw_note = f" yaw_src={yaw_source_joint}" if yaw_source_used else ""

            print(
                f"[TARGET] {joint} xyz=({xyz_mm[0]:.0f},{xyz_mm[1]:.0f},{xyz_mm[2]:.0f})mm "
                f"conf={conf_mean:.2f} cams={cams_min} std={std_mm:.1f}mm | "
                f"local=({x_lat_m:.2f},{y_fwd_m:.2f},{dz_m:.2f})m "
                f"v={v_deg:.2f}deg h={h_deg:.2f}deg speed={v_ms:.2f}m/s rpm={rpm}{yaw_note}"
            )

            # 1) Fast aim
            # In aim-only mode we keep wheels stopped by default to avoid unsafe spin.
            cmd_wl, cmd_wr = (wl, wr) if args.shoot_enabled else (args.aim_only_wheel_rpm, args.aim_only_wheel_rpm)
            send_cmd(f"set {v_deg:.2f} {h_deg:.2f} {cmd_wl} {cmd_wr}")
            wait_with_background(args.aim_settle_sec, stage="aim_settle", joint_name=joint)
            if estop:
                log_decision(decision="ESTOP", joint_name=joint, extra={"stage": "aim_settle"})
                continue

            # 2) Wait telemetry RPM (best-effort)
            telemetry_rpm_ok = not args.shoot_enabled
            rpm_gate_bypassed = False
            if args.shoot_enabled:
                tw = time.time()
                while (time.time() - tw) < args.wait_rpm_sec:
                    lines = drain_serial_lines(ser)
                    rpm_pair = read_rpm_from_lines(lines)
                    if rpm_pair is not None:
                        l_rpm, r_rpm = rpm_pair
                        if l_rpm >= args.min_feed_rpm and r_rpm >= args.min_feed_rpm:
                            telemetry_rpm_ok = True
                            break
                    drain_operator_commands(stage="rpm_gate_wait", joint_name=joint)
                    if estop:
                        break
                    time.sleep(0.03)

            if estop:
                log_decision(decision="ESTOP", joint_name=joint, extra={"stage": "rpm_gate_wait"})
                continue

            rpm_ok = telemetry_rpm_ok
            if args.shoot_enabled and (not telemetry_rpm_ok) and args.ignore_rpm_gate:
                rpm_ok = True
                rpm_gate_bypassed = True
                print("[WARN] RPM gate not reached; proceeding due to --ignore-rpm-gate")

            hold_sec = max(0.0, hold_sec_map.get(joint, args.target_hold_sec))

            # 3) Shoot or aim-only
            if args.shoot_enabled:
                if rpm_ok:
                    if hold_sec > 0:
                        print(f"[INFO] Hold target '{joint}' for {hold_sec:.1f}s with wheel spin")
                        hold_t0 = time.time()
                        hold_samples = 0
                        hold_valid = 0
                        hold_confs = []
                        hold_cams = []
                        hold_xyz = []
                        while (time.time() - hold_t0) < hold_sec:
                            drain_operator_commands(stage="hold", joint_name=joint)
                            if estop:
                                break
                            ingest_targets_once()
                            _ = drain_serial_lines(ser)
                            if buffers[joint]:
                                s_last = buffers[joint][-1]
                                hold_samples += 1
                                hold_confs.append(float(s_last.conf))
                                hold_cams.append(int(s_last.cams))
                                hold_xyz.append([float(s_last.x_mm), float(s_last.y_mm), float(s_last.z_mm)])
                                if s_last.conf >= args.min_conf and s_last.cams >= args.min_cams:
                                    hold_valid += 1
                            time.sleep(0.03)
                        hold_actual = max(0.0, time.time() - hold_t0)
                        hold_valid_ratio = (float(hold_valid) / float(hold_samples)) if hold_samples > 0 else 0.0
                        hold_xyz_arr = np.array(hold_xyz, dtype=np.float64) if hold_xyz else None
                        log_decision(
                            decision="HOLD_SUMMARY",
                            joint_name=joint,
                            raw_world_xyz_mm=xyz_mm_raw,
                            corrected_world_xyz_mm=xyz_mm,
                            execution_time_ms=0.0,
                            extra={
                                "hold_requested_sec": hold_sec,
                                "hold_actual_sec": hold_actual,
                                "hold_samples": hold_samples,
                                "hold_valid_ratio": hold_valid_ratio,
                                "hold_conf_mean": float(np.mean(hold_confs)) if hold_confs else 0.0,
                                "hold_cams_mean": float(np.mean(hold_cams)) if hold_cams else 0.0,
                                "hold_xyz_std_mm": float(np.linalg.norm(np.std(hold_xyz_arr, axis=0))) if hold_xyz_arr is not None else 0.0,
                                **yaw_extra,
                            },
                        )
                        send_cmd("stop")
                    else:
                        send_cmd("shoot")
                        wait_with_background(args.shoot_pulse_sec, stage="shoot_pulse", joint_name=joint)
                        if estop:
                            log_decision(decision="ESTOP", joint_name=joint, extra={"stage": "shoot_pulse"})
                            continue
                        send_cmd("stop")
                else:
                    print("[WARN] RPM gate not reached, skip shoot")
                    send_cmd("stop")
            else:
                print("[INFO] Aim-only mode (shoot disabled)")
                if hold_sec > 0:
                    print(f"[INFO] Hold target '{joint}' for {hold_sec:.1f}s (aim-only)")
                    hold_t0 = time.time()
                    while (time.time() - hold_t0) < hold_sec:
                        drain_operator_commands(stage="hold", joint_name=joint)
                        if estop:
                            break
                        ingest_targets_once()
                        _ = drain_serial_lines(ser)
                        time.sleep(0.03)

            if estop:
                log_decision(decision="ESTOP", joint_name=joint, extra={"stage": "shoot_or_hold"})
                continue

            log_decision(
                decision="OK",
                joint_name=joint,
                raw_world_xyz_mm=xyz_mm_raw,
                corrected_world_xyz_mm=xyz_mm,
                transformed_launcher_xyz={
                    "x_lateral_m": x_lat_m,
                    "y_forward_m": y_fwd_m,
                    "dz_m": dz_m,
                    "distance_m": d_m,
                },
                calculated_pitch_yaw_v={
                    "pitch_deg": v_deg,
                    "yaw_deg": h_deg,
                    "speed_mps": v_ms,
                    "rpm_cmd": rpm,
                    "wl": cmd_wl,
                    "wr": cmd_wr,
                },
                execution_time_ms=exec_ms,
                extra={
                    "conf_mean": conf_mean,
                    "cams_min": cams_min,
                    "std_mm": std_mm,
                    "acquire_elapsed_sec": acquire_elapsed_sec,
                    "solver": args.solver,
                    "horizontal_only": bool(args.horizontal_only),
                    "horizontal_fixed_v_deg": float(args.horizontal_fixed_v_deg),
                    "fixed_speed_kmh": args.fixed_speed_kmh,
                    "shoot_enabled": bool(args.shoot_enabled),
                    "rpm_gate_ok": bool(rpm_ok),
                    "rpm_gate_telemetry_ok": bool(telemetry_rpm_ok),
                    "rpm_gate_bypassed": bool(rpm_gate_bypassed),
                    "target_hold_sec": hold_sec,
                    **yaw_extra,
                },
            )

            # 4) Return to zero (optional)
            if args.home_between_targets:
                send_home_set()
                if args.home_wait_sec > 0:
                    print(f"[INFO] Waiting after home for {args.home_wait_sec:.1f}s")
                    wait_with_background(args.home_wait_sec, stage="home_wait", joint_name=joint)
                    if estop:
                        log_decision(decision="ESTOP", joint_name=joint, extra={"stage": "home_wait"})
                        continue
            elif args.return_center_after_each_target:
                send_cmd("center")
                wait_with_background(args.center_settle_sec, stage="center_settle", joint_name=joint)
                if estop:
                    log_decision(decision="ESTOP", joint_name=joint, extra={"stage": "center_settle"})
                    continue

            target_idx = (target_idx + 1) % len(target_order)
            completed_target_events += 1
            if args.max_target_events > 0 and completed_target_events >= args.max_target_events:
                started = False
                print(
                    f"[INFO] Reached --max-target-events={args.max_target_events}. "
                    "Sequence paused. Type 'start' to run again."
                )
            elif args.run_once_per_start and target_idx == 0:
                started = False
                print("[INFO] Completed one full target cycle. Sequence paused. Type 'start' to run again.")

    except KeyboardInterrupt as e:
        print(f"\n[INFO] Stopping controller... ({e})")
    finally:
        stop_ev.set()
        graceful_shutdown("finally")
        try:
            ser.close()
        except Exception:
            pass
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass
        if log_fp is not None:
            try:
                log_fp.close()
            except Exception:
                pass
        print("[DONE] Launcher runtime stopped")


if __name__ == "__main__":
    main()
