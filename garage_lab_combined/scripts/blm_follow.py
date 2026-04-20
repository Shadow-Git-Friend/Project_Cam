#!/usr/bin/env python3
"""
Continuous BLM follow mode (with optional reload + shoot).

The launcher continuously tracks a chosen body joint as the person moves.
Aim-only by default. With --shoot-enabled, you can type `reload` and `shoot`
to fire at the currently tracked joint without breaking the follow loop.

Procedure:
  1. Start the live viewer in Terminal 1 (sends UDP on port 5005):
        ./Parallel_working/run_live_blm.sh
  2. Start this script in Terminal 2:

     # Aim-only follow:
     ./venv/bin/python garage_lab_combined/scripts/blm_follow.py \
         --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 \
         --joint right_shoulder --correction-mode linear

     # Follow + shoot (wheels spin at 800 RPM, manual `shoot` trigger):
     ./venv/bin/python garage_lab_combined/scripts/blm_follow.py \
         --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 \
         --joint right_shoulder --correction-mode linear \
         --shoot-enabled --wheel-rpm 800

Commands while running:
  <joint_name>  switch tracked joint (e.g. left_wrist, nose)
  reload        load a ball (requires --shoot-enabled)
  shoot         fire at current target (requires --shoot-enabled, RPM gate ≥400)
  pause/resume  halt or restart aim loop
  quit          safe exit

Safety:
  - Pitch clamped to [0, 30] deg, yaw to [-30, 30] deg before sending
  - If joint goes stale (>1s) or unreachable, holds the last position
  - Deadband: only resends `set` when delta > --min-delta-deg
  - Rate limit: at most 1 send per --min-interval-s seconds
  - Aim loop pauses during reload/shoot (no `set` interference)
  - Ctrl+C → stop + center, KeyboardInterrupt-safe
"""

import argparse
import json
import select
import socket
import sys
import threading
import time
from typing import Callable, Dict, Optional

import numpy as np
from launcher_common import apply_correction, load_correction_model, solve_angles_ballistic, world_to_launcher_xy_delta

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: ./venv/bin/pip install pyserial")
    sys.exit(1)

try:
    import termios
    import tty
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False


# --------------- safe-print plumbing ---------------
# All status prints from the aim loop and serial reader go through safe_print().
# Once the LineEditor is active, safe_print is rebound to a version that clears
# the user's in-progress input line, prints the message, and redraws the input.

def _default_safe_print(msg: str) -> None:
    print(msg)


safe_print: Callable[[str], None] = _default_safe_print


# --------------- Serial reader thread ---------------

class SerialReader:
    """Background thread that drains serial output and tracks firmware state."""

    def __init__(self, ser: serial.Serial, verbose: bool = False):
        self.ser = ser
        self.verbose = verbose
        self._running = True
        self._last_msg = ""
        self.last_state_msg = ""  # last firmware state message (RELOAD DONE, SHOT FIRED, ...)
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
                if line.startswith("clk_drv:") or line.startswith("mode:") or line.startswith("load:"):
                    continue
                if line.startswith("entry "):
                    continue
                # Filter baud-transition garbage
                if len(line) > 20 and len(set(line)) <= 2:
                    continue
                # Filter wheel RPM telemetry
                if line.startswith("L:") and " R:" in line:
                    continue
                # Deduplicate
                if line == self._last_msg:
                    continue
                self._last_msg = line
                # Track firmware state events
                if "RELOAD DONE" in line or "SHOT FIRED" in line or "RETRACT" in line or "DISPENS" in line:
                    self.last_state_msg = line
                    safe_print(f"  <- {line}")
                elif self.verbose:
                    safe_print(f"  <- {line}")
            except serial.SerialException:
                break
            except Exception:
                pass

    def stop(self):
        self._running = False


# --------------- UDP listener ---------------

class UDPJointListener:
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
            except socket.timeout:
                pass
            except Exception:
                pass
        sock.close()

    def get_joint(self, name: str) -> Optional[dict]:
        with self.lock:
            return self.joints.get(name)

    def stop(self):
        self._running = False


# --------------- joint names ---------------

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
    ser.write((cmd_str + "\n").encode())


# --------------- line editor (raw-mode stdin reader) ---------------

class LineEditor:
    """Character-at-a-time stdin reader.

    Calls on_line(text) for each completed line. Provides safe_print(msg) which
    erases the user's in-progress input, prints the message, then redraws the
    input — so periodic status prints from other threads do not corrupt the
    typed buffer (the bug where 'sh' + status print + retyped 'shoot' became
    'sshoot' in cooked-mode input()).

    Falls back to plain blocking input() if the terminal does not support raw
    mode (e.g. when stdin is not a TTY).
    """

    def __init__(self, on_line: Callable[[str], None]):
        self.on_line = on_line
        self.buffer = ""
        self._lock = threading.Lock()
        self._running = True
        self._raw = False
        self.old_settings = None
        try:
            self.fd = sys.stdin.fileno()
            if _HAS_TERMIOS and sys.stdin.isatty():
                self.old_settings = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
                self._raw = True
        except Exception:
            self._raw = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        if not self._raw:
            # Fallback path: cooked-mode input(). No safe_print redraw possible.
            while self._running:
                try:
                    line = input()
                except (EOFError, KeyboardInterrupt):
                    self.on_line("__quit__")
                    return
                self.on_line(line)
            return

        while self._running:
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not r:
                    continue
                ch = sys.stdin.read(1)
                if not ch:
                    continue
                completed = None
                with self._lock:
                    if ch == '\x03':  # Ctrl+C
                        sys.stdout.write('\r\n')
                        sys.stdout.flush()
                        completed = "__quit__"
                    elif ch == '\x04':  # Ctrl+D
                        completed = "__quit__"
                    elif ch in ('\r', '\n'):
                        completed = self.buffer
                        self.buffer = ""
                        sys.stdout.write('\r\n')
                        sys.stdout.flush()
                    elif ch in ('\x7f', '\b'):
                        if self.buffer:
                            self.buffer = self.buffer[:-1]
                            sys.stdout.write('\b \b')
                            sys.stdout.flush()
                    elif ch.isprintable():
                        self.buffer += ch
                        sys.stdout.write(ch)
                        sys.stdout.flush()
                if completed is not None:
                    self.on_line(completed)
                    if completed == "__quit__":
                        return
            except Exception:
                pass

    def safe_print(self, msg: str) -> None:
        """Print without clobbering the user's typed-but-unsubmitted input."""
        with self._lock:
            if self._raw:
                # Erase the echoed input characters from the current line.
                erase_len = len(self.buffer) + 4
                sys.stdout.write('\r' + ' ' * erase_len + '\r')
                sys.stdout.write(msg + '\n')
                # Re-display the in-progress buffer so the user knows it survived.
                if self.buffer:
                    sys.stdout.write(self.buffer)
                sys.stdout.flush()
            else:
                print(msg)

    def stop(self):
        self._running = False
        if self._raw and self.old_settings is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
            except Exception:
                pass


# --------------- command handler ---------------

class CommandHandler:
    """Dispatches typed commands. reload/shoot block the editor reader briefly,
    which is fine — the user shouldn't be typing other things mid-cycle."""

    def __init__(self, state: dict, state_lock: threading.Lock,
                 ser, serial_reader, shoot_enabled: bool,
                 auto_reload: bool = False):
        self.state = state
        self.state_lock = state_lock
        self.ser = ser
        self.serial_reader = serial_reader
        self.shoot_enabled = shoot_enabled
        self.auto_reload = auto_reload

    def _do_reload(self):
        with self.state_lock:
            self.state["busy"] = True
        safe_print("  Reloading: retract pusher → dispense ball → center aim...")
        self.serial_reader.last_state_msg = ""
        send_serial(self.ser, "reload")
        t0 = time.time()
        while time.time() - t0 < 15:
            if "RELOAD DONE" in self.serial_reader.last_state_msg:
                break
            time.sleep(0.2)
        self.serial_reader.last_state_msg = ""
        with self.state_lock:
            self.state["busy"] = False
            self.state["armed"] = True
            # Force a resend on next cycle since reload re-centered the launcher
            self.state["last_v"] = None
            self.state["last_h"] = None
        safe_print("  [RELOAD COMPLETE] ARMED — tracking active.")

    def _do_shoot(self):
        with self.state_lock:
            if not self.state.get("armed"):
                safe_print("  [BLOCKED] Not armed — type 'reload' first.")
                return
            self.state["busy"] = True
        safe_print("  Firing at current target...")
        self.serial_reader.last_state_msg = ""
        send_serial(self.ser, "shoot")
        t0 = time.time()
        while time.time() - t0 < 10:
            if "SHOT FIRED" in self.serial_reader.last_state_msg:
                break
            time.sleep(0.2)
        self.serial_reader.last_state_msg = ""
        with self.state_lock:
            self.state["busy"] = False
            self.state["armed"] = False
            self.state["last_v"] = None
            self.state["last_h"] = None
        if self.auto_reload:
            safe_print("  [SHOT COMPLETE] auto-reloading...")
            self._do_reload()
        else:
            safe_print("  [SHOT COMPLETE] DISARMED — type 'reload' for next shot.")

    def handle(self, raw: str):
        cmd = (raw or "").strip().lower()
        if cmd == "__quit__":
            with self.state_lock:
                self.state["quit"] = True
            return
        if not cmd:
            return
        if cmd in ("quit", "exit", "q"):
            with self.state_lock:
                self.state["quit"] = True
            return
        if cmd in ("pause", "stop"):
            with self.state_lock:
                self.state["paused"] = True
            safe_print("  [PAUSED] type 'resume' to continue")
            return
        if cmd in ("resume", "go"):
            with self.state_lock:
                self.state["paused"] = False
            safe_print("  [RESUMED]")
            return
        if cmd == "joints":
            safe_print(f"  Targetable: {', '.join(TARGETABLE_JOINTS)}")
            return
        if cmd == "reload":
            if not self.shoot_enabled:
                safe_print("  [BLOCKED] reload requires --shoot-enabled")
                return
            self._do_reload()
            return
        if cmd == "shoot":
            if not self.shoot_enabled:
                safe_print("  [BLOCKED] shoot requires --shoot-enabled")
                return
            self._do_shoot()
            return
        joint = cmd.replace("-", "_").replace(" ", "_")
        if joint in TARGETABLE_JOINTS:
            with self.state_lock:
                self.state["target"] = joint
                self.state["last_v"] = None
                self.state["last_h"] = None
            safe_print(f"  → tracking {joint}")
        else:
            safe_print(f"  Unknown command '{raw}'. "
                       f"Joints / reload / shoot / pause / resume / quit")


# --------------- main ---------------

def main():
    ap = argparse.ArgumentParser(description="Continuous BLM follow mode (aim-only)")
    ap.add_argument("--serial-port", required=True)
    ap.add_argument("--baud-rate", type=int, default=921600)
    ap.add_argument("--udp-host", default="0.0.0.0")
    ap.add_argument("--udp-port", type=int, default=5005)
    ap.add_argument("--launcher-x-mm", type=float, default=600.0)
    ap.add_argument("--launcher-y-mm", type=float, default=1560.0)
    ap.add_argument("--launcher-z-mm", type=float, default=500.0)
    ap.add_argument("--launcher-yaw-deg", type=float, required=True)
    ap.add_argument("--v-base-mps", type=float, default=10.0)
    ap.add_argument("--joint", default="right_shoulder",
                    help=f"Initial joint to track. One of: {', '.join(TARGETABLE_JOINTS)}")
    ap.add_argument("--correction-model",
                    default="garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/correction_model.json")
    ap.add_argument("--correction-mode", choices=["none", "bias", "linear"], default="linear")
    ap.add_argument("--pitch-trim-deg", type=float, default=0.0)
    ap.add_argument("--yaw-trim-deg", type=float, default=0.0)
    ap.add_argument("--shoot-enabled", action="store_true",
                    help="Enable reload/shoot commands. Without this flag, both are blocked.")
    ap.add_argument("--wheel-rpm", type=float, default=0.0,
                    help="Flywheel RPM. Default 0 = wheels off (aim-only). "
                         "Set ≥400 to satisfy firmware shoot gate when --shoot-enabled.")
    ap.add_argument("--min-interval-s", type=float, default=0.15,
                    help="Minimum seconds between consecutive `set` commands")
    ap.add_argument("--min-delta-deg", type=float, default=0.5,
                    help="Deadband: only resend if pitch or yaw changed by this much")
    ap.add_argument("--max-staleness-s", type=float, default=1.0,
                    help="Skip aim if joint data is older than this")
    ap.add_argument("--print-every", type=int, default=10,
                    help="Print one status line per N sends")
    ap.add_argument("--verbose-serial", action="store_true",
                    help="Print all (filtered) serial output")
    ap.add_argument("--voice-port", type=int, default=0,
                    help="If >0, bind UDP localhost:<port> for voice commands "
                         "from voice_bridge.py. 0 = disabled.")
    ap.add_argument("--auto-reload", action="store_true",
                    help="After each shot, automatically reload. Target and "
                         "wheel RPM persist, so the next 'go' fires at the "
                         "same joint without re-aiming. Requires --shoot-enabled.")
    args = ap.parse_args()

    if args.joint not in TARGETABLE_JOINTS:
        print(f"ERROR: --joint must be one of: {', '.join(TARGETABLE_JOINTS)}")
        sys.exit(1)

    # If shoot is enabled but wheel RPM is below the firmware gate, default it
    if args.shoot_enabled and args.wheel_rpm < 400:
        print(f"[INFO] --shoot-enabled set with wheel-rpm={args.wheel_rpm:.0f} (<400 RPM gate). "
              f"Bumping to 800 RPM.")
        args.wheel_rpm = 800.0

    launcher_xyz = np.array([args.launcher_x_mm, args.launcher_y_mm, args.launcher_z_mm])

    correction_model = None
    if args.correction_mode != "none":
        correction_model = load_correction_model(args.correction_model)
        if correction_model:
            print(f"[OK] Correction model loaded ({args.correction_mode} mode)")
        else:
            print("[WARN] Correction model failed; falling back to mode=none")
            args.correction_mode = "none"

    udp = UDPJointListener(args.udp_host, args.udp_port)
    print(f"[OK] UDP listener on {args.udp_host}:{args.udp_port}")

    ser = serial.Serial(args.serial_port, args.baud_rate, timeout=0.1)
    time.sleep(2)
    ser.reset_input_buffer()
    serial_reader = SerialReader(ser, verbose=args.verbose_serial)

    send_serial(ser, "center")
    time.sleep(0.5)
    print(f"[OK] Serial connected: {args.serial_port}, BLM centered")

    if args.shoot_enabled:
        print(f"[!!] SHOOT ENABLED — wheels will spin at {args.wheel_rpm:.0f} RPM")
        print("[!!] Tracking is DISARMED until you type 'reload' (safety).")
    elif args.wheel_rpm > 0:
        print(f"[!!] WHEELS WILL SPIN at {args.wheel_rpm:.0f} RPM (no shoot, just spin)")
    else:
        print("[OK] Wheels OFF (pure aim follow)")

    # When shoot-enabled, start DISARMED — must reload before tracking begins.
    # In aim-only mode there's no ball involved, so tracking is armed from start.
    initial_armed = not args.shoot_enabled

    state = {
        "target": args.joint,
        "paused": False,
        "busy": False,        # true during reload/shoot — pauses aim loop
        "armed": initial_armed,
        "quit": False,
        "last_v": None,
        "last_h": None,
    }
    state_lock = threading.Lock()

    print("\n" + "=" * 60)
    print(f"  BLM Follow Mode  —  initial joint: {args.joint}")
    print("=" * 60)
    if args.shoot_enabled:
        print("Workflow: type 'reload' first → then a joint name → 'shoot' when ready.")
        print("Commands: reload / shoot / <joint> / pause / resume / quit")
    else:
        print("Commands: <joint> / pause / resume / quit")
    print(f"Targetable: {', '.join(TARGETABLE_JOINTS)}")
    print()

    handler = CommandHandler(state, state_lock, ser, serial_reader,
                             args.shoot_enabled, auto_reload=args.auto_reload)
    editor = LineEditor(on_line=handler.handle)

    if args.voice_port > 0:
        def _voice_listener(port, on_cmd):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("127.0.0.1", port))
            while True:
                try:
                    data, _ = s.recvfrom(256)
                    cmd = data.decode("utf-8", errors="ignore").strip()
                    if cmd:
                        safe_print(f"  [VOICE] {cmd}")
                        on_cmd(cmd)
                except Exception as e:
                    safe_print(f"  [VOICE ERR] {e}")
        threading.Thread(
            target=_voice_listener,
            args=(args.voice_port, handler.handle),
            daemon=True,
        ).start()
        print(f"[OK] Voice UDP listener on 127.0.0.1:{args.voice_port}")

    # Re-bind global safe_print so all status output goes through the editor
    # (clears + redraws the in-progress input line on every print).
    global safe_print
    safe_print = editor.safe_print

    last_send_t = 0.0
    send_count = 0
    skip_unreach = 0
    skip_stale = 0
    wl = int(args.wheel_rpm)
    wr = int(args.wheel_rpm)

    try:
        while True:
            with state_lock:
                if state["quit"]:
                    break
                paused = state["paused"]
                busy = state["busy"]
                armed = state["armed"]
                target = state["target"]
                last_v = state["last_v"]
                last_h = state["last_h"]

            if paused or busy or not armed:
                time.sleep(0.05)
                continue

            joint_data = udp.get_joint(target)
            if joint_data is None:
                time.sleep(0.05)
                continue

            now = time.time()
            age = now - joint_data["ts"]
            if age > args.max_staleness_s:
                skip_stale += 1
                time.sleep(0.05)
                continue

            # Compute aim
            raw_xyz = np.array([joint_data["x_mm"], joint_data["y_mm"], joint_data["z_mm"]])
            corrected_xyz = apply_correction(raw_xyz, correction_model, mode=args.correction_mode)

            x_lat_m, y_fwd_m, dz_m = world_to_launcher_xy_delta(
                corrected_xyz, launcher_xyz, args.launcher_yaw_deg
            )

            sol = solve_angles_ballistic(x_lat_m, y_fwd_m, dz_m, v_ms=args.v_base_mps)
            if sol is None:
                skip_unreach += 1
                time.sleep(0.05)
                continue

            v_deg, h_deg = sol
            v_deg += args.pitch_trim_deg
            h_deg += args.yaw_trim_deg

            # SAFETY clamp
            v_deg = max(0.0, min(30.0, v_deg))
            h_deg = max(-30.0, min(30.0, h_deg))

            # Rate limit
            if now - last_send_t < args.min_interval_s:
                time.sleep(0.02)
                continue

            # Deadband
            if last_v is not None and last_h is not None:
                if abs(v_deg - last_v) < args.min_delta_deg and abs(h_deg - last_h) < args.min_delta_deg:
                    time.sleep(0.02)
                    continue

            cmd_str = f"set {v_deg:.1f} {h_deg:.1f} {wl} {wr}"
            send_serial(ser, cmd_str)
            last_send_t = now
            send_count += 1
            with state_lock:
                state["last_v"] = v_deg
                state["last_h"] = h_deg

            if args.print_every > 0 and send_count % args.print_every == 0:
                d_m = math.sqrt(x_lat_m**2 + y_fwd_m**2)
                safe_print(
                    f"  [{send_count:5d}] {target:<15} pitch={v_deg:5.1f}  yaw={h_deg:6.1f}  "
                    f"dist={d_m:.2f}m  conf={joint_data['conf']:.2f}  "
                    f"(stale_skip={skip_stale} unreach_skip={skip_unreach})"
                )

    except KeyboardInterrupt:
        pass

    print("\nShutting down safely...")
    try:
        send_serial(ser, "stop")
        time.sleep(0.3)
        send_serial(ser, "center")
        time.sleep(1)
    except Exception:
        pass
    serial_reader.stop()
    udp.stop()
    editor.stop()
    try:
        ser.close()
    except Exception:
        pass
    print(f"Done. Sent {send_count} aim updates.")


if __name__ == "__main__":
    main()
