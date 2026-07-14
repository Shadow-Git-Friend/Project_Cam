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
import math
import select
import socket
import sys
import threading
import time
from typing import Callable, Dict, Optional

import numpy as np
from launcher_common import apply_correction, load_correction_model, solve_angles_ballistic, world_to_launcher_xy_delta

# Make src/ importable for the closed_loop helpers (safety gates, event logger).
_REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from project_cam.closed_loop import (  # noqa: E402
    ArmedShotContext,
    arm_shot_context,
    evaluate_joint_gate,
    request_shoot,
)

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
        self.latest_safety: Optional[dict] = None
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
                self._store_packet(pkt, received_at=time.time())
            except socket.timeout:
                pass
            except Exception:
                pass
        sock.close()

    def _store_packet(self, pkt: dict, *, received_at: float) -> None:
        """Atomically store joints and the safety object from one datagram."""
        with self.lock:
            self.last_packet_ts = received_at
            self.packet_count += 1
            safety = pkt.get("safety")
            self.latest_safety = safety if isinstance(safety, dict) else None
            joints_obj = pkt.get("joints", {})
            if not isinstance(joints_obj, dict):
                return
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
                    "ts": received_at,
                }

    def get_joint(self, name: str) -> Optional[dict]:
        with self.lock:
            return self.joints.get(name)

    def get_safety_snapshot(self) -> Optional[dict]:
        with self.lock:
            return self.latest_safety

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


def commit_aim_command(
    state: dict,
    state_lock: threading.Lock,
    *,
    expected_target: str,
    expected_generation: int,
    command: str,
    command_v: float,
    command_h: float,
    armed_context: Optional[ArmedShotContext],
    send_command: Callable[[str], None],
) -> bool:
    """Commit one serial aim and its context under the shoot-state lock."""
    with state_lock:
        if (
            state.get("busy")
            or not state.get("armed")
            or state.get("target") != expected_target
            or state.get("aim_generation") != expected_generation
        ):
            return False
        send_command(command)
        state["last_v"] = command_v
        state["last_h"] = command_h
        state["armed_context"] = armed_context
        return True


def send_fire_command_if_current(
    state: dict,
    state_lock: threading.Lock,
    *,
    command: str,
    expected_generation: int,
    expected_context: Optional[ArmedShotContext],
    send_command: Callable[[str], None],
) -> None:
    """Serialize fire output and reject stale shoot callbacks fail-closed."""
    with state_lock:
        if command == "shoot" and (
            expected_context is None
            or not state.get("busy")
            or not state.get("armed")
            or state.get("aim_generation") != expected_generation
            or state.get("armed_context") is not expected_context
        ):
            raise RuntimeError("armed shot context was invalidated before serial send")
        send_command(command)


def send_reload_command_if_current(
    state: dict,
    state_lock: threading.Lock,
    *,
    expected_generation: int,
    send_command: Callable[[str], None],
) -> bool:
    """Send reload only while its exclusive-action generation still owns state."""
    with state_lock:
        if (
            not state.get("busy")
            or state.get("aim_generation") != expected_generation
        ):
            return False
        send_command("reload")
        return True


def _invalidate_armed_aim_locked(state: dict) -> int:
    """Clear one aim and advance its generation while the caller owns the lock."""
    state["aim_generation"] = int(state.get("aim_generation", 0)) + 1
    state["armed_context"] = None
    state["last_v"] = None
    state["last_h"] = None
    return state["aim_generation"]


def stop_and_release_launcher_action(
    state: dict,
    state_lock: threading.Lock,
    *,
    send_command: Callable[[str], None],
) -> bool:
    """Fail one exclusive action closed before publishing it as no longer busy."""
    with state_lock:
        _invalidate_armed_aim_locked(state)
        state["armed"] = False
        stop_sent = True
        try:
            send_command("stop")
        except Exception:
            stop_sent = False
        state["busy"] = False
        return stop_sent


def invalidate_operator_command(
    state: dict,
    state_lock: threading.Lock,
    *,
    updates: dict,
    shoot_enabled: bool,
    send_command: Callable[[str], None],
) -> bool:
    """Publish an operator invalidation, then physically stop active hardware."""
    with state_lock:
        had_context = state.get("armed_context") is not None
        action_active = bool(state.get("busy"))
        state.update(updates)
        _invalidate_armed_aim_locked(state)
        if not shoot_enabled or not (had_context or action_active):
            return False
        try:
            send_command("stop")
        except Exception:
            return False
        return True


def invalidate_armed_aim(
    state: dict,
    state_lock: threading.Lock,
    *,
    send_command: Callable[[str], None],
) -> bool:
    """Publish aim invalidation before a serialized best-effort stop."""
    with state_lock:
        _invalidate_armed_aim_locked(state)
        try:
            send_command("stop")
        except Exception:
            return False
        return True


def begin_exclusive_launcher_action(
    state: dict,
    state_lock: threading.Lock,
    *,
    capture_armed_context: bool,
    send_command: Callable[[str], None],
) -> tuple[bool, Optional[ArmedShotContext], int]:
    """Atomically claim reload/shoot or invalidate a conflicting busy action."""
    with state_lock:
        if state.get("quit"):
            invalidated_generation = _invalidate_armed_aim_locked(state)
            state["armed"] = False
            try:
                send_command("stop")
            except Exception:
                pass
            return False, None, invalidated_generation
        if state.get("busy"):
            invalidated_generation = _invalidate_armed_aim_locked(state)
            try:
                send_command("stop")
            except Exception:
                pass
            return False, None, invalidated_generation

        armed_context = None
        if capture_armed_context and state.get("armed"):
            armed_context = state.get("armed_context")
        state["busy"] = True
        state["aim_generation"] = int(state.get("aim_generation", 0)) + 1
        action_generation = state["aim_generation"]
        if not capture_armed_context:
            state["armed_context"] = None
            state["last_v"] = None
            state["last_h"] = None
        return True, armed_context, action_generation


def continue_exclusive_launcher_action(
    state: dict,
    state_lock: threading.Lock,
    *,
    expected_generation: int,
    send_command: Callable[[str], None],
) -> tuple[bool, int]:
    """Atomically hand an owned action to auto-reload or stop if invalidated."""
    with state_lock:
        if (
            not state.get("busy")
            or state.get("aim_generation") != expected_generation
        ):
            invalidated_generation = int(state.get("aim_generation", 0))
        else:
            reload_generation = _invalidate_armed_aim_locked(state)
            return True, reload_generation

    stop_and_release_launcher_action(
        state,
        state_lock,
        send_command=send_command,
    )
    return False, invalidated_generation


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
                 get_safety_snapshot: Callable[[], Optional[dict]],
                 launcher_xyz_mm, launcher_yaw_deg: float,
                 auto_reload: bool = False):
        self.state = state
        self.state_lock = state_lock
        self.ser = ser
        self.serial_reader = serial_reader
        self.shoot_enabled = shoot_enabled
        self.get_safety_snapshot = get_safety_snapshot
        self.launcher_xyz_mm = launcher_xyz_mm
        self.launcher_yaw_deg = launcher_yaw_deg
        self.auto_reload = auto_reload

    def _do_reload(self, continuing_generation: Optional[int] = None):
        if continuing_generation is None:
            claimed, _, reload_generation = begin_exclusive_launcher_action(
                self.state,
                self.state_lock,
                capture_armed_context=False,
                send_command=lambda command: send_serial(self.ser, command),
            )
        else:
            claimed, reload_generation = continue_exclusive_launcher_action(
                self.state,
                self.state_lock,
                expected_generation=continuing_generation,
                send_command=lambda command: send_serial(self.ser, command),
            )
        if not claimed:
            safe_print("  [BLOCKED] launcher busy; aim invalidated and stop requested.")
            return
        safe_print("  Reloading: retract pusher → dispense ball → center aim...")
        self.serial_reader.last_state_msg = ""
        try:
            reload_sent = send_reload_command_if_current(
                self.state,
                self.state_lock,
                expected_generation=reload_generation,
                send_command=lambda command: send_serial(self.ser, command),
            )
        except Exception:
            reload_sent = False
        if not reload_sent:
            stop_and_release_launcher_action(
                self.state,
                self.state_lock,
                send_command=lambda command: send_serial(self.ser, command),
            )
            safe_print("  [BLOCKED] reload invalidated; launcher stopped and disarmed.")
            return
        t0 = time.time()
        reload_completed = False
        while time.time() - t0 < 15:
            if "RELOAD DONE" in self.serial_reader.last_state_msg:
                reload_completed = True
                break
            time.sleep(0.2)
        self.serial_reader.last_state_msg = ""
        if not reload_completed:
            stop_and_release_launcher_action(
                self.state,
                self.state_lock,
                send_command=lambda command: send_serial(self.ser, command),
            )
            safe_print(
                "  [BLOCKED] reload status timeout; launcher stopped and disarmed."
            )
            return
        with self.state_lock:
            reload_still_current = (
                self.state.get("busy")
                and self.state.get("aim_generation") == reload_generation
            )
            self.state["busy"] = False
            self.state["armed"] = bool(reload_still_current)
            self.state["armed_context"] = None
            # Force a resend on next cycle since reload re-centered the launcher
            self.state["last_v"] = None
            self.state["last_h"] = None
        if not reload_still_current:
            safe_print("  [RELOAD INVALIDATED] DISARMED — retry reload when idle.")
            return
        safe_print("  [RELOAD COMPLETE] ARMED — tracking active.")

    def _do_shoot(self):
        claimed, armed_context, shot_generation = begin_exclusive_launcher_action(
            self.state,
            self.state_lock,
            capture_armed_context=True,
            send_command=lambda command: send_serial(self.ser, command),
        )
        if not claimed:
            safe_print("  [BLOCKED] launcher busy; aim invalidated and stop requested.")
            return
        self.serial_reader.last_state_msg = ""
        outcome = request_shoot(
            lambda command: send_fire_command_if_current(
                self.state,
                self.state_lock,
                command=command,
                expected_generation=shot_generation,
                expected_context=armed_context,
                send_command=lambda serial_command: send_serial(
                    self.ser, serial_command
                ),
            ),
            shoot_enabled=self.shoot_enabled,
            latest_snapshot=self.get_safety_snapshot(),
            armed_context=armed_context,
            launcher_xyz_mm=self.launcher_xyz_mm,
            launcher_yaw_deg=self.launcher_yaw_deg,
            source="blm_follow",
        )
        safe_print(f"  [FIRE OUTCOME] {json.dumps(outcome, sort_keys=True)}")
        if not outcome["serial_shoot_sent"]:
            with self.state_lock:
                self.state["busy"] = False
                self.state["armed"] = False
                self.state["armed_context"] = None
                self.state["last_v"] = None
                self.state["last_h"] = None
            safe_print(
                f"  [BLOCKED] {outcome['reason']}: {outcome['message']}"
            )
            return
        safe_print("  Firing at current target...")
        t0 = time.time()
        shot_fired = False
        while time.time() - t0 < 10:
            if "SHOT FIRED" in self.serial_reader.last_state_msg:
                shot_fired = True
                break
            time.sleep(0.2)
        self.serial_reader.last_state_msg = ""
        if not shot_fired:
            stop_and_release_launcher_action(
                self.state,
                self.state_lock,
                send_command=lambda command: send_serial(self.ser, command),
            )
            safe_print(
                "  [BLOCKED] shot status timeout; launcher stopped and disarmed."
            )
            return
        with self.state_lock:
            shot_still_current = (
                self.state.get("busy")
                and self.state.get("aim_generation") == shot_generation
                and self.state.get("armed_context") is armed_context
            )
            self.state["armed"] = False
            self.state["armed_context"] = None
            self.state["last_v"] = None
            self.state["last_h"] = None
            if not (self.auto_reload and shot_still_current):
                self.state["busy"] = False
        if self.auto_reload and shot_still_current:
            safe_print("  [SHOT COMPLETE] auto-reloading...")
            self._do_reload(continuing_generation=shot_generation)
        else:
            safe_print("  [SHOT COMPLETE] DISARMED — type 'reload' for next shot.")

    def handle(self, raw: str):
        cmd = (raw or "").strip().lower()
        if cmd == "__quit__":
            invalidate_operator_command(
                self.state,
                self.state_lock,
                updates={"quit": True},
                shoot_enabled=self.shoot_enabled,
                send_command=lambda command: send_serial(self.ser, command),
            )
            return
        if not cmd:
            return
        if cmd in ("quit", "exit", "q"):
            invalidate_operator_command(
                self.state,
                self.state_lock,
                updates={"quit": True},
                shoot_enabled=self.shoot_enabled,
                send_command=lambda command: send_serial(self.ser, command),
            )
            return
        if cmd in ("pause", "stop"):
            invalidate_operator_command(
                self.state,
                self.state_lock,
                updates={"paused": True},
                shoot_enabled=self.shoot_enabled,
                send_command=lambda command: send_serial(self.ser, command),
            )
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
            invalidate_operator_command(
                self.state,
                self.state_lock,
                updates={"target": joint},
                shoot_enabled=self.shoot_enabled,
                send_command=lambda command: send_serial(self.ser, command),
            )
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
    ap.add_argument("--min-confidence", type=float, default=0.0,
                    help="Skip samples with conf below this (0 disables; recommended 0.55 for live)")
    ap.add_argument("--min-cameras", type=int, default=0,
                    help="Skip samples seen by fewer than N cameras (0 disables; recommended 2 for live)")
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

    ser = serial.Serial(
        args.serial_port,
        args.baud_rate,
        timeout=0.1,
        write_timeout=0.5,
    )
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
        "armed_context": None,
        "aim_generation": 0,
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
                             args.shoot_enabled, udp.get_safety_snapshot,
                             launcher_xyz, args.launcher_yaw_deg,
                             auto_reload=args.auto_reload)
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
    skip_low_conf = 0
    skip_low_cams = 0
    skip_missing = 0
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
                armed_context: ArmedShotContext | None = state["armed_context"]
                aim_generation = state["aim_generation"]

            if paused or busy or not armed:
                time.sleep(0.05)
                continue

            joint_data = udp.get_joint(target)
            now = time.time()
            latest_safety = udp.get_safety_snapshot()
            if args.shoot_enabled and armed_context is not None:
                context_changed = (
                    not isinstance(latest_safety, dict)
                    or latest_safety.get("primary_track_id") != armed_context.primary_track_id
                    or latest_safety.get("primary_epoch") != armed_context.primary_epoch
                    or latest_safety.get("y_mirrored") != armed_context.y_mirrored
                )
                if context_changed:
                    invalidate_armed_aim(
                        state,
                        state_lock,
                        send_command=lambda command: send_serial(ser, command),
                    )
                    safe_print("  [BLOCKED] Primary/mirror safety context changed; fresh aim required.")
                    time.sleep(0.05)
                    continue
            gate = evaluate_joint_gate(
                joint_data,
                min_confidence=args.min_confidence,
                min_cameras=args.min_cameras,
                max_staleness_s=args.max_staleness_s,
                now=now,
            )
            if not gate.ok:
                if args.shoot_enabled and armed_context is not None:
                    invalidate_armed_aim(
                        state,
                        state_lock,
                        send_command=lambda command: send_serial(ser, command),
                    )
                if gate.reason == "stale":
                    skip_stale += 1
                elif gate.reason == "low_confidence":
                    skip_low_conf += 1
                elif gate.reason == "low_camera_count":
                    skip_low_cams += 1
                else:
                    skip_missing += 1
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
                if args.shoot_enabled and armed_context is not None:
                    invalidate_armed_aim(
                        state,
                        state_lock,
                        send_command=lambda command: send_serial(ser, command),
                    )
                skip_unreach += 1
                time.sleep(0.05)
                continue

            v_deg, h_deg = sol
            v_deg += args.pitch_trim_deg
            h_deg += args.yaw_trim_deg

            # SAFETY clamp
            v_deg = max(0.0, min(30.0, v_deg))
            h_deg = max(-30.0, min(30.0, h_deg))
            command_v = float(f"{v_deg:.1f}")
            command_h = float(f"{h_deg:.1f}")

            # Rate limit
            if now - last_send_t < args.min_interval_s:
                time.sleep(0.02)
                continue

            # Deadband
            if last_v is not None and last_h is not None:
                if abs(command_v - last_v) < args.min_delta_deg and abs(command_h - last_h) < args.min_delta_deg:
                    time.sleep(0.02)
                    continue

            cmd_str = f"set {command_v:.1f} {command_h:.1f} {wl} {wr}"
            candidate_armed_context = None
            if args.shoot_enabled:
                candidate_armed_context, clearance = arm_shot_context(
                    latest_safety,
                    target_xyz_mm=corrected_xyz,
                    pitch_deg=command_v,
                    yaw_deg=command_h,
                    speed_mps=args.v_base_mps,
                    launcher_xyz_mm=launcher_xyz,
                    launcher_yaw_deg=args.launcher_yaw_deg,
                )
                if not clearance.ok or candidate_armed_context is None:
                    invalidate_armed_aim(
                        state,
                        state_lock,
                        send_command=lambda command: send_serial(ser, command),
                    )
                    safe_print(
                        f"  [BLOCKED] Aim clearance: {clearance.reason}: "
                        f"{clearance.message} {json.dumps(clearance.to_dict(), sort_keys=True)}"
                    )
                    time.sleep(0.05)
                    continue
            committed = commit_aim_command(
                state,
                state_lock,
                expected_target=target,
                expected_generation=aim_generation,
                command=cmd_str,
                command_v=command_v,
                command_h=command_h,
                armed_context=candidate_armed_context,
                send_command=lambda command: send_serial(ser, command),
            )
            if not committed:
                time.sleep(0.02)
                continue
            last_send_t = now
            send_count += 1

            if args.print_every > 0 and send_count % args.print_every == 0:
                d_m = math.sqrt(x_lat_m**2 + y_fwd_m**2)
                safe_print(
                    f"  [{send_count:5d}] {target:<15} pitch={command_v:5.1f}  yaw={command_h:6.1f}  "
                    f"dist={d_m:.2f}m  conf={joint_data['conf']:.2f}  "
                    f"(skip stale={skip_stale} unreach={skip_unreach} "
                    f"lowconf={skip_low_conf} lowcams={skip_low_cams} missing={skip_missing})"
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
