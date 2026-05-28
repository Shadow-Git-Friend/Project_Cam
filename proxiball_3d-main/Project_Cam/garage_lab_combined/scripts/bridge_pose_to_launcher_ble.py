#!/usr/bin/env python3
"""
Bridge 3D body keypoints (world frame, mm) -> RoboLauncher BLE commands.

Input:
  - motion JSON from process_4cam_to_3d.py (list of frames with "joints")

Output:
  - BLE commands in launcher format:
      set <v_deg> <h_deg> <wl_rpm> <wr_rpm>\n
  - Optional "shoot\n"

Default mode is DRY-RUN (no BLE writes) for safety.
"""

import argparse
import asyncio
import json
import math
import re
from pathlib import Path

import numpy as np

try:
    from bleak import BleakClient, BleakScanner
except Exception:  # pragma: no cover
    BleakClient = None
    BleakScanner = None


JOINT_NAME_TO_IDX = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}


def build_world_to_launcher_rotation(yaw_deg: float) -> np.ndarray:
    """
    Launcher yaw is defined in world frame:
      yaw=0 means launcher +X points to world +X.
    """
    yaw = math.radians(yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    # R_world_from_launcher for yaw around +Z.
    r_wl = np.array(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    # world -> launcher
    return r_wl.T


def world_to_launcher(point_w_mm, launcher_pos_w_mm, r_lw):
    p = np.asarray(point_w_mm, dtype=np.float64).reshape(3)
    t = np.asarray(launcher_pos_w_mm, dtype=np.float64).reshape(3)
    return r_lw @ (p - t)


def point_to_angles_deg(point_l_mm):
    x, y, z = point_l_mm
    horiz = math.hypot(x, y)
    h = math.degrees(math.atan2(y, x))
    v = math.degrees(math.atan2(z, max(horiz, 1e-9)))
    dist_m = math.sqrt(x * x + y * y + z * z) / 1000.0
    return v, h, dist_m


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def rpm_from_distance(dist_m, base, per_meter):
    return max(0.0, base + per_meter * dist_m)


def parse_rpm_telemetry(msg: str):
    m = re.search(r"L:\s*([0-9]+(?:\.[0-9]+)?)\s+R:\s*([0-9]+(?:\.[0-9]+)?)", msg)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


async def resolve_device(name_or_addr: str):
    if BleakScanner is None:
        raise RuntimeError("bleak is not installed. Install with: ./venv/bin/pip install bleak")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        if d.address.lower() == name_or_addr.lower():
            return d.address
        if d.name and d.name.lower() == name_or_addr.lower():
            return d.address
    raise RuntimeError(f"BLE device not found: {name_or_addr}")


async def run(args):
    motion_path = Path(args.motion_json)
    frames = json.loads(motion_path.read_text())
    if not isinstance(frames, list) or not frames:
        raise RuntimeError(f"Invalid motion JSON: {motion_path}")

    if args.joint.isdigit():
        joint_idx = int(args.joint)
    else:
        if args.joint not in JOINT_NAME_TO_IDX:
            raise RuntimeError(f"Unknown joint '{args.joint}'.")
        joint_idx = JOINT_NAME_TO_IDX[args.joint]

    launcher_pos = np.array(
        [args.launcher_x_mm, args.launcher_y_mm, args.launcher_z_mm], dtype=np.float64
    )
    r_lw = build_world_to_launcher_rotation(args.launcher_yaw_deg)

    client = None
    latest_rpm = {"L": None, "R": None}
    shot_sent = False

    async def on_notify(_, data):
        try:
            txt = data.decode(errors="ignore")
        except Exception:
            return
        parsed = parse_rpm_telemetry(txt)
        if parsed:
            latest_rpm["L"], latest_rpm["R"] = parsed
        if args.verbose_ble:
            print(f"[BLE RX] {txt.strip()}")

    async def send_line(line: str):
        if args.dry_run:
            print(f"[DRY] {line.strip()}")
            return
        await client.write_gatt_char(args.rx_uuid, line.encode("utf-8"), response=False)

    if not args.dry_run:
        if BleakClient is None:
            raise RuntimeError("bleak is not installed. Install with: ./venv/bin/pip install bleak")
        addr = await resolve_device(args.ble_device)
        print(f"[INFO] Connecting BLE: {args.ble_device} -> {addr}")
        client = BleakClient(addr)
        await client.connect()
        await client.start_notify(args.tx_uuid, on_notify)
        print("[INFO] BLE connected")

    ema_target = None
    invalid_streak = 0
    valid_count = 0

    try:
        for i, fr in enumerate(frames):
            joints = fr.get("joints")
            if not isinstance(joints, list) or len(joints) <= joint_idx:
                invalid_streak += 1
                if invalid_streak >= args.invalid_stop_after:
                    await send_line("stop\n")
                await asyncio.sleep(1.0 / args.fps)
                continue

            pt = joints[joint_idx]
            if pt is None or len(pt) != 3:
                invalid_streak += 1
                if invalid_streak >= args.invalid_stop_after:
                    await send_line("stop\n")
                await asyncio.sleep(1.0 / args.fps)
                continue

            p_w = np.array(pt, dtype=np.float64)
            if not np.isfinite(p_w).all():
                invalid_streak += 1
                await asyncio.sleep(1.0 / args.fps)
                continue

            invalid_streak = 0
            valid_count += 1

            if ema_target is None:
                ema_target = p_w
            else:
                a = float(args.ema_alpha)
                ema_target = a * p_w + (1.0 - a) * ema_target

            p_l = world_to_launcher(ema_target, launcher_pos, r_lw)
            if p_l[0] <= args.min_forward_mm:
                # target is behind/too close to launcher forward axis
                await asyncio.sleep(1.0 / args.fps)
                continue

            v_deg, h_deg, dist_m = point_to_angles_deg(p_l)
            v_cmd = clamp(v_deg + args.v_offset_deg, -args.max_abs_angle_deg, args.max_abs_angle_deg)
            h_cmd = clamp(h_deg + args.h_offset_deg, -args.max_abs_angle_deg, args.max_abs_angle_deg)

            rpm = rpm_from_distance(dist_m, args.rpm_base, args.rpm_per_meter)
            wl = int(round(rpm + args.rpm_left_bias))
            wr = int(round(rpm + args.rpm_right_bias))

            set_cmd = f"set {v_cmd:.1f} {h_cmd:.1f} {wl} {wr}\n"
            await send_line(set_cmd)

            if args.print_frames:
                print(
                    f"[F{i:04d}] joint={joint_idx} world=({p_w[0]:.0f},{p_w[1]:.0f},{p_w[2]:.0f}) "
                    f"launcher=({p_l[0]:.0f},{p_l[1]:.0f},{p_l[2]:.0f}) v={v_cmd:.1f} h={h_cmd:.1f} "
                    f"wl={wl} wr={wr}"
                )

            if args.fire_once and not shot_sent and valid_count >= args.fire_after_valid_frames:
                l_ok = latest_rpm["L"] is None or latest_rpm["L"] >= args.min_feed_rpm
                r_ok = latest_rpm["R"] is None or latest_rpm["R"] >= args.min_feed_rpm
                if l_ok and r_ok:
                    await send_line("shoot\n")
                    shot_sent = True
                    print(f"[INFO] SHOOT at frame {i}")

            await asyncio.sleep(1.0 / args.fps)
    finally:
        if not args.dry_run:
            try:
                if args.stop_on_exit:
                    await send_line("stop\n")
                await client.stop_notify(args.tx_uuid)
            except Exception:
                pass
            await client.disconnect()
            print("[INFO] BLE disconnected")


def build_argparser():
    ap = argparse.ArgumentParser(description="Send 3D body joint targets to RoboLauncher over BLE")
    ap.add_argument("--motion-json", required=True, help="Output from process_4cam_to_3d.py")
    ap.add_argument("--joint", default="nose", help="COCO joint name or index (0..16)")

    # Launcher pose in world frame (mm)
    ap.add_argument("--launcher-x-mm", type=float, required=True)
    ap.add_argument("--launcher-y-mm", type=float, required=True)
    ap.add_argument("--launcher-z-mm", type=float, required=True)
    ap.add_argument(
        "--launcher-yaw-deg",
        type=float,
        required=True,
        help="Yaw of launcher +X axis in world frame. 0 means facing +X.",
    )

    # Command shaping
    ap.add_argument("--max-abs-angle-deg", type=float, default=30.0)
    ap.add_argument("--v-offset-deg", type=float, default=0.0)
    ap.add_argument("--h-offset-deg", type=float, default=0.0)
    ap.add_argument("--rpm-base", type=float, default=1200.0)
    ap.add_argument("--rpm-per-meter", type=float, default=220.0)
    ap.add_argument("--rpm-left-bias", type=float, default=0.0)
    ap.add_argument("--rpm-right-bias", type=float, default=0.0)
    ap.add_argument("--ema-alpha", type=float, default=0.25)
    ap.add_argument("--min-forward-mm", type=float, default=200.0)

    # Runtime
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--invalid-stop-after", type=int, default=10)
    ap.add_argument("--print-frames", action="store_true")

    # BLE
    ap.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--ble-device", default="RoboLauncher", help="BLE device name or MAC")
    ap.add_argument("--rx-uuid", default="6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
    ap.add_argument("--tx-uuid", default="6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
    ap.add_argument("--verbose-ble", action="store_true")
    ap.add_argument("--stop-on-exit", action=argparse.BooleanOptionalAction, default=True)

    # Optional fire control
    ap.add_argument("--fire-once", action="store_true")
    ap.add_argument("--fire-after-valid-frames", type=int, default=15)
    ap.add_argument("--min-feed-rpm", type=float, default=400.0)
    return ap


def main():
    args = build_argparser().parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
