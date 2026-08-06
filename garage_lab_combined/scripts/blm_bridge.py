#!/usr/bin/env python3
"""Machine-driven BLM console: a line protocol in, serial out, status back.

Why this exists
---------------
`blm_interactive.py` is a human terminal: it forwards whatever you type straight
to the firmware. That is exactly wrong for a GUI, because a UI bug (or anything
that can reach the UI) would then be able to compose arbitrary serial. This
bridge accepts a CLOSED set of semantic intents, re-derives every serial command
itself, and refuses anything it does not recognise. Nothing typed on stdin
reaches the firmware verbatim.

It is also where the operator gates live, so they hold no matter which front end
is driving:

  * angles are clamped BEFORE transmission. Yaw is a fixed [-30, 30]; PITCH is a
    per-session envelope the operator declares with `limits`, defaulting to the
    conservative [0, 30]. It cannot be a constant: the barrel meets the ball
    feeder at a fixed PHYSICAL position while the firmware's angle is measured
    from a zero adopted at boot or by `set_zero`, so how much travel remains below
    zero depends on where zero was set. A re-zero translates the envelope into
    the new coordinate frame when the commanded offset is known
    (see .claude/rules/safety.md "Known Hazards")
  * `fire` requires an explicit `arm` first, and ARM EXPIRES (default 30 s)
  * a successful shot AUTO-DISARMS, so every shot needs its own deliberate arm
    ("no autonomous repeated fire" -- the garage firing policy)
  * `fire` additionally requires a commanded wheel RPM >= 400, mirroring the
    firmware's own gate, and an aim that was actually sent
  * `stop` LATCHES: after it, every actuating intent is refused until `clear`
  * without `--allow-fire` the arm/fire intents do not exist at all
  * any exit path -- normal, signal, exception -- sends `stop`. It does NOT
    re-centre: `center` is a blind move to the firmware's zero, which on this
    open-loop machine can be inside the feeder (`--center-on-exit` opts in)

Protocol (stdin, one intent per line)
-------------------------------------
    aim <pitch_deg> <yaw_deg> <wheel_rpm>   reload      arm        disarm
    wheels <wheel_rpm>                      fire        stop       clear
    center            set_zero              info        quit
    limits <pitch_min_deg> <pitch_max_deg>
    measure <rpm> <landing_distance_m>      undo        fit <height_m> [kind]

Protocol (stdout)
-----------------
Human-readable lines for the operator log, plus one machine line per change:

    @BLM {"schema": "project_cam.blm_console.v1", ...}

The `measure`/`fit` intents exist so a v(RPM) calibration session never has to
leave the console: `fit` calls the SAME `scripts/fit_rpm_speed.py` functions the
launcher reads its model from, rather than reimplementing the arithmetic.

Measurement procedure: docs/protocols/2026-08-03-rpm-speed-measurement.md
"""

import argparse
import importlib.util
import json
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

SCHEMA = "project_cam.blm_console.v1"
STATUS_PREFIX = "@BLM "

# Limits are duplicated from .claude/rules/safety.md on purpose: the firmware
# enforces its own too, and one check is not defence in depth.
#
# The firmware bound: beyond this on either axis the ESP32 reboots. This one IS a
# constant, because it is a property of the firmware and not of where zero sits.
ANGLE_LIMIT_DEG = 30.0
YAW_LIMIT_DEG = 30.0

# The pitch envelope is NOT a constant, and treating it as one was a design error
# (2026-08-06). The collision happens at a fixed PHYSICAL barrel position, while
# the firmware's angle is measured from a zero that is adopted at boot or by
# `set_zero` — so a fixed number in firmware-angle space describes a different
# physical place after every re-zero. It is also over-restrictive: how much travel
# remains below zero depends entirely on where zero was set, and only the operator
# can see that.
#
# So these are DEFAULTS for a session, deliberately conservative (no downward
# travel at all, which cannot jam), and the operator declares the measured
# envelope with `limits`. A re-zero translates the same physical endpoints into
# its new coordinate frame instead of restoring these defaults.
PITCH_DEFAULT_MIN_DEG = 0.0
PITCH_DEFAULT_MAX_DEG = 30.0
RPM_MAX = 1200
RPM_MIN_FIRE = 400
ARM_TIMEOUT_S = 30.0

# Serial pacing. The ESP32 answers a command in well under 300 ms; the pusher
# suppresses telemetry while it moves, so a reload/shoot needs a longer grace.
WRITE_SETTLE_S = 0.3


class CommandError(Exception):
    """A refused intent. Reported to the operator, never sent to the firmware."""


@dataclass(frozen=True)
class Intent:
    """A parsed, range-checked operator intention."""

    kind: str
    args: Tuple[float, ...] = ()
    text: str = ""


ACTUATING = frozenset({"aim", "wheels", "reload", "fire", "center"})


def clamp_pitch(value: float, low: float, high: float) -> float:
    """Clamp pitch into the session's declared envelope.

    The bounds are MECHANICAL, not firmware limits: past them the barrel meets the
    ball feeder. A stalled axis has no position feedback to reveal that, so
    refusing here is the only thing standing between an operator and a jam — which
    is why the envelope is enforced even though the operator is the one who
    declared it.
    """
    return max(low, min(high, value))


def clamp_yaw(value: float) -> float:
    """Clamp yaw to [-30, 30]. Symmetric; beyond it the firmware reboots."""
    return max(-YAW_LIMIT_DEG, min(YAW_LIMIT_DEG, value))


def validate_pitch_envelope(low: float, high: float) -> Tuple[float, float]:
    """Validate travel limits expressed in the current zero's coordinates.

    Zero is the barrel's current position immediately after `setzero`, so every
    legitimate envelope must contain it. Allowing [10, 20], for example, would
    put CENTER outside the declared safe travel.
    """
    for name, value in (("pitch_min_deg", low), ("pitch_max_deg", high)):
        if value != value or value in (float("inf"), float("-inf")):
            raise CommandError(f"{name} must be finite, got {value!r}")
        if abs(value) > ANGLE_LIMIT_DEG:
            raise CommandError(
                f"{name} must be within +/-{ANGLE_LIMIT_DEG:g} deg "
                f"(the firmware bound), got {value:g}"
            )
    if low >= high:
        raise CommandError(
            f"pitch_min_deg must be below pitch_max_deg, got {low:g} >= {high:g}"
        )
    if low > 0 or high < 0:
        raise CommandError(
            f"pitch travel must contain the current zero, got [{low:g}, {high:g}]"
        )
    return low, high


def _number(token: str, name: str) -> float:
    try:
        value = float(token)
    except ValueError:
        raise CommandError(f"{name} must be a number, got {token!r}")
    if value != value or value in (float("inf"), float("-inf")):
        raise CommandError(f"{name} must be finite, got {token!r}")
    return value


def _rpm(token: str) -> float:
    value = _number(token, "wheel_rpm")
    if value < 0 or value > RPM_MAX:
        raise CommandError(f"wheel_rpm must be between 0 and {RPM_MAX}, got {value:g}")
    return value


def parse_command(line: str) -> Optional[Intent]:
    """Parse one protocol line. Returns None for blank input.

    Unknown verbs raise rather than falling through to the serial port, which is
    the difference between this and a terminal.
    """
    stripped = line.strip()
    if not stripped:
        return None
    parts = stripped.split()
    verb = parts[0].lower()
    rest = parts[1:]

    def exact(count: int) -> None:
        if len(rest) != count:
            raise CommandError(f"{verb} takes {count} argument(s), got {len(rest)}")

    if verb == "aim":
        exact(3)
        return Intent("aim", (_number(rest[0], "pitch_deg"),
                              _number(rest[1], "yaw_deg"),
                              _rpm(rest[2])))
    if verb == "wheels":
        exact(1)
        return Intent("wheels", (_rpm(rest[0]),))
    if verb == "measure":
        exact(2)
        rpm = _rpm(rest[0])
        distance = _number(rest[1], "landing_distance_m")
        if distance <= 0 or distance > 60:
            raise CommandError(
                f"landing_distance_m must be between 0 and 60, got {distance:g}")
        return Intent("measure", (rpm, distance))
    if verb == "fit":
        if not rest or len(rest) > 2:
            raise CommandError("fit takes <height_m> [linear|quadratic|interp]")
        height = _number(rest[0], "height_m")
        if height <= 0 or height > 5:
            raise CommandError(f"height_m must be between 0 and 5, got {height:g}")
        kind = rest[1].lower() if len(rest) == 2 else "linear"
        if kind not in ("linear", "quadratic", "interp"):
            raise CommandError(f"unknown fit kind {kind!r}")
        return Intent("fit", (height,), kind)
    if verb == "limits":
        exact(2)
        low = _number(rest[0], "pitch_min_deg")
        high = _number(rest[1], "pitch_max_deg")
        validate_pitch_envelope(low, high)
        return Intent("limits", (low, high))
    if verb in ("reload", "arm", "disarm", "fire", "stop", "clear",
                "center", "set_zero", "info", "quit", "undo"):
        exact(0)
        return Intent(verb)
    raise CommandError(f"unknown command {verb!r}")


@dataclass
class Measurement:
    rpm: float
    distance_m: float
    at: str


@dataclass
class ConsoleState:
    port: str = ""
    connected: bool = False
    allow_fire: bool = False
    estop_latched: bool = False
    armed: bool = False
    arm_expires_at: float = 0.0
    pitch_deg: Optional[float] = None
    yaw_deg: Optional[float] = None
    # The session's declared pitch envelope, in the CURRENT zero's frame.
    pitch_min_deg: float = PITCH_DEFAULT_MIN_DEG
    pitch_max_deg: float = PITCH_DEFAULT_MAX_DEG
    wheel_rpm: float = 0.0
    rpm_left: Optional[float] = None
    rpm_right: Optional[float] = None
    telemetry_at: float = 0.0
    shots_fired: int = 0
    last_refusal: str = ""
    info_lines: List[str] = field(default_factory=list)
    measurements: List[Measurement] = field(default_factory=list)
    model_path: str = ""
    model_summary: str = ""


class BlmController:
    """Intent -> gate -> serial. No I/O of its own, so it is directly testable.

    `write` receives the exact firmware command string (no newline); `log` gets
    operator-facing text. Both are injected, so the gate behaviour can be tested
    without a serial port and without a running desktop app.
    """

    def __init__(
        self,
        write: Callable[[str], None],
        log: Callable[[str], None],
        *,
        allow_fire: bool = False,
        now: Callable[[], float] = time.monotonic,
        arm_timeout_s: float = ARM_TIMEOUT_S,
        shot_log: Optional[Path] = None,
        model_out: Optional[Path] = None,
        fitter=None,
        session_id: str = "",
        pitch_min_deg: float = PITCH_DEFAULT_MIN_DEG,
        pitch_max_deg: float = PITCH_DEFAULT_MAX_DEG,
    ) -> None:
        self._write = write
        self._log = log
        self._now = now
        self._arm_timeout_s = arm_timeout_s
        self._shot_log = shot_log
        self._model_out = model_out
        self._fitter = fitter
        self._session_id = session_id
        pitch_min_deg, pitch_max_deg = validate_pitch_envelope(
            pitch_min_deg, pitch_max_deg
        )
        self._default_pitch_min = pitch_min_deg
        self._default_pitch_max = pitch_max_deg
        self.state = ConsoleState(
            allow_fire=allow_fire,
            pitch_min_deg=pitch_min_deg,
            pitch_max_deg=pitch_max_deg,
        )
        if model_out is not None:
            self.state.model_path = str(model_out)

    # ---- arming -------------------------------------------------------

    def expire_arm(self) -> bool:
        """Drop a stale arm. An arm that outlives the operator's attention is
        exactly the state a launcher must not sit in."""
        if self.state.armed and self._now() >= self.state.arm_expires_at:
            self.state.armed = False
            self.state.arm_expires_at = 0.0
            self._log("ARM expired — arm again to fire")
            return True
        return False

    def arm_remaining_s(self) -> float:
        if not self.state.armed:
            return 0.0
        return max(0.0, self.state.arm_expires_at - self._now())

    # ---- gates --------------------------------------------------------

    def _require_live(self, kind: str) -> None:
        if kind in ACTUATING and self.state.estop_latched:
            raise CommandError("ESTOP latched — send clear before any actuation")

    def _refuse(self, message: str) -> None:
        self.state.last_refusal = message
        raise CommandError(message)

    # ---- intents ------------------------------------------------------

    def handle(self, intent: Intent) -> None:
        self.expire_arm()
        self._require_live(intent.kind)
        handler = getattr(self, f"_do_{intent.kind}")
        handler(intent)

    def _do_aim(self, intent: Intent) -> None:
        pitch_raw, yaw_raw, rpm = intent.args
        low, high = self.state.pitch_min_deg, self.state.pitch_max_deg
        pitch, yaw = clamp_pitch(pitch_raw, low, high), clamp_yaw(yaw_raw)
        if (pitch, yaw) != (pitch_raw, yaw_raw):
            self._log(
                f"angles clamped to pitch [{low:g}, {high:g}] / "
                f"yaw +/-{YAW_LIMIT_DEG:g} deg: "
                f"v={pitch_raw:g}->{pitch:g} h={yaw_raw:g}->{yaw:g}"
            )
        if pitch_raw < low:
            # Named separately because this is the one that jams the machine, and
            # it must not read as an ordinary rounding of an out-of-range number.
            self._log(
                f"WARNING: pitch {pitch_raw:g} deg is below the declared travel "
                f"limit {low:g} deg — the barrel meets the ball feeder past it. "
                "Use `limits` to declare a measured envelope if there is more room."
            )
        self.state.pitch_deg, self.state.yaw_deg = pitch, yaw
        self.state.wheel_rpm = rpm
        # Changing the aim invalidates the operator's clearance judgement.
        if self.state.armed:
            self.state.armed = False
            self._log("aim changed — ARM cleared, arm again to fire")
        self._send(f"set {pitch:.0f} {yaw:.0f} {rpm:.0f} {rpm:.0f}")

    def _do_wheels(self, intent: Intent) -> None:
        (rpm,) = intent.args
        pitch = self.state.pitch_deg if self.state.pitch_deg is not None else 0.0
        yaw = self.state.yaw_deg if self.state.yaw_deg is not None else 0.0
        self.state.pitch_deg, self.state.yaw_deg = pitch, yaw
        self.state.wheel_rpm = rpm
        if self.state.armed and rpm < RPM_MIN_FIRE:
            self.state.armed = False
            self._log("wheels below the fire gate — ARM cleared")
        self._send(f"set {pitch:.0f} {yaw:.0f} {rpm:.0f} {rpm:.0f}")

    def _do_reload(self, _intent: Intent) -> None:
        # Firmware `reload` is not feeder-only: it homes both aim axes and sets
        # both target RPMs to zero before retracting. Mirror those commanded
        # values here so a later wheels or SET ZERO intent cannot resurrect the
        # pre-reload aim, and invalidate the arm because the shot geometry moved.
        if self.state.armed:
            self._log("reloading centres the aim — ARM cleared")
        self.state.armed = False
        self.state.arm_expires_at = 0.0
        self.state.pitch_deg = 0.0
        self.state.yaw_deg = 0.0
        self.state.wheel_rpm = 0.0
        self._send("reload")

    def _do_center(self, _intent: Intent) -> None:
        # `center` physically returns the barrel to 0/0, so the stored aim must
        # follow it. The firmware takes ONE combined `set v h wl wr`, so a later
        # `wheels` command re-sends the stored angles — with a stale aim that
        # means the barrel jumps back up when the operator only asked to spin the
        # flywheels. Centering also moves the barrel, so it invalidates any arm.
        if self.state.armed:
            self.state.armed = False
            self.state.arm_expires_at = 0.0
            self._log("centering — ARM cleared")
        self.state.pitch_deg = 0.0
        self.state.yaw_deg = 0.0
        self._send("center")

    def _do_info(self, _intent: Intent) -> None:
        self._send("info")

    def _do_limits(self, intent: Intent) -> None:
        """Declare the MEASURED pitch travel available from the current zero.

        Only the operator can know this: how much room is left below zero depends
        on where zero was set, and the machine has no way to sense a limit before
        hitting it. Declaring it once and then enforcing it is the point — the
        alternative is re-deciding on every slider drag, which is what jammed the
        barrel. Recorded in the operator log so the session says what was allowed.
        """
        low, high = intent.args
        current = self.state.pitch_deg if self.state.pitch_deg is not None else 0.0
        if current < low or current > high:
            message = (
                f"current aim {current:g} deg is outside requested pitch travel "
                f"[{low:g}, {high:g}] — move inside it first"
            )
            self._log(message)
            self._refuse(message)

        self.state.pitch_min_deg = low
        self.state.pitch_max_deg = high
        if self.state.armed:
            self.state.armed = False
            self.state.arm_expires_at = 0.0
            self._log("travel limits changed — ARM cleared")
        self._log(
            f"pitch travel declared: [{low:g}, {high:g}] deg from the current zero"
        )

    def _do_set_zero(self, _intent: Intent) -> None:
        """Adopt the barrel's CURRENT physical position as the zero reference.

        Moves nothing, so it is not actuation and stays available under a latched
        ESTOP — which is exactly when it is needed, because the reason to re-zero
        is usually that an open-loop axis was driven into a stop and lost its
        reference. It does invalidate an arm: every angle now means something
        different from what the clearance judgement was made against.
        """
        if self.state.armed:
            self.state.armed = False
            self.state.arm_expires_at = 0.0
            self._log("re-zeroing — ARM cleared")

        # Preserve the SAME PHYSICAL endpoints in the new coordinate frame. If
        # the old commanded position was p and becomes zero, every old angle x
        # becomes x-p. Intersect the result with the firmware's fresh +/-30
        # frame: a physical endpoint can translate beyond it, but the ESP32
        # cannot accept a command there.
        zero_shift = self.state.pitch_deg if self.state.pitch_deg is not None else 0.0
        old_low = self.state.pitch_min_deg
        old_high = self.state.pitch_max_deg
        new_low = max(-ANGLE_LIMIT_DEG, old_low - zero_shift)
        new_high = min(ANGLE_LIMIT_DEG, old_high - zero_shift)
        validate_pitch_envelope(new_low, new_high)

        self.state.pitch_deg = 0.0
        self.state.yaw_deg = 0.0
        self.state.pitch_min_deg = new_low
        self.state.pitch_max_deg = new_high
        self._log(
            "zero reference set to the current position — level the barrel BEFORE "
            "this, because nothing here can measure whether it was level"
        )
        self._log(
            f"pitch travel translated [{old_low:g}, {old_high:g}] by "
            f"{-zero_shift:+g} deg into the new zero: [{new_low:g}, {new_high:g}]"
        )
        self._send("setzero")

    def _do_stop(self, _intent: Intent) -> None:
        # Latch FIRST: if the write throws, the console must already be refusing
        # actuation rather than sitting in a state that looks live.
        self.state.estop_latched = True
        self.state.armed = False
        self.state.arm_expires_at = 0.0
        self.state.wheel_rpm = 0.0
        self._log("STOP — latched; send clear to release")
        self._send("stop")

    def _do_clear(self, _intent: Intent) -> None:
        if not self.state.estop_latched:
            self._log("nothing latched")
            return
        self.state.estop_latched = False
        self._log("ESTOP latch released — wheels are at 0, aim again before firing")

    def _do_arm(self, _intent: Intent) -> None:
        if not self.state.allow_fire:
            self._refuse("this console was launched without fire control")
        # Arming is not actuation, so the latch check above does not cover it —
        # but an armed console behind a latched ESTOP is a misleading state.
        if self.state.estop_latched:
            self._refuse("ESTOP latched — send clear before arming")
        if self.state.pitch_deg is None:
            self._refuse("send an aim before arming")
        if self.state.wheel_rpm < RPM_MIN_FIRE:
            self._refuse(
                f"wheels must be commanded to >= {RPM_MIN_FIRE} RPM before arming "
                f"(currently {self.state.wheel_rpm:.0f})"
            )
        self.state.armed = True
        self.state.arm_expires_at = self._now() + self._arm_timeout_s
        self._log(f"ARMED for {self._arm_timeout_s:.0f} s — one shot, then re-arm")

    def _do_disarm(self, _intent: Intent) -> None:
        self.state.armed = False
        self.state.arm_expires_at = 0.0
        self._log("disarmed")

    def _do_fire(self, _intent: Intent) -> None:
        if not self.state.allow_fire:
            self._refuse("this console was launched without fire control")
        if not self.state.armed:
            self._refuse("not armed — arm immediately before firing")
        if self.state.wheel_rpm < RPM_MIN_FIRE:
            self._refuse(
                f"wheel RPM {self.state.wheel_rpm:.0f} is below the {RPM_MIN_FIRE} "
                "RPM gate"
            )
        # Disarm BEFORE the write. If the serial write raises, the console must
        # not be left armed holding a shot the operator believes was refused.
        self.state.armed = False
        self.state.arm_expires_at = 0.0
        self.state.shots_fired += 1
        self._send("shoot")
        self._log(
            f"shot {self.state.shots_fired} sent at {self.state.wheel_rpm:.0f} RPM "
            f"(v={self.state.pitch_deg:.0f} h={self.state.yaw_deg:.0f}) — disarmed"
        )

    # ---- calibration bookkeeping --------------------------------------

    def _do_measure(self, intent: Intent) -> None:
        rpm, distance = intent.args
        entry = Measurement(rpm=rpm, distance_m=distance,
                            at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.state.measurements.append(entry)
        self._append_shot_log(entry)
        self._log(
            f"recorded {rpm:.0f} RPM -> {distance:.3f} m "
            f"({len(self.state.measurements)} measurement(s))"
        )

    def _do_undo(self, _intent: Intent) -> None:
        if not self.state.measurements:
            self._log("no measurements to undo")
            return
        dropped = self.state.measurements.pop()
        # The JSONL keeps the retraction rather than rewriting history: an
        # operator log that can be silently edited is not evidence.
        self._append_shot_log(dropped, retracted=True)
        self._log(f"undid {dropped.rpm:.0f} RPM -> {dropped.distance_m:.3f} m")

    def _do_fit(self, intent: Intent) -> None:
        if self._fitter is None or self._model_out is None:
            self._refuse("this console was launched without the fit helper")
        (height_m,) = intent.args
        if not self.state.measurements:
            self._refuse("no measurements yet — record shots with measure first")
        points = [
            (m.rpm, self._fitter.speed_from_drop(m.distance_m, height_m, 9.81))
            for m in self.state.measurements
        ]
        points.sort()
        model = self._fitter.fit(points, 9.81, height_m, intent.text or "linear")
        self._model_out.parent.mkdir(parents=True, exist_ok=True)
        self._model_out.write_text(json.dumps(model, indent=2), encoding="utf-8")
        rmse = model.get("fit_rmse_mps", 0.0)
        n = model.get("n_shots", len(points))
        if model["model"] == "constant_mps":
            speed = f"{model['v_mps']:.2f} m/s at {model['rpm']:.0f} RPM"
        else:
            lo, hi = model["rpm_min"], model["rpm_max"]
            speed = f"{model['model']} over {lo:.0f}-{hi:.0f} RPM"
        self.state.model_summary = (
            f"{speed} · +/-{rmse:.2f} m/s over {n} shot(s)"
        )
        self._log(f"model written: {self.state.model_summary}")
        self._log(f"           -> {self._model_out}")
        if rmse > 1.0:
            self._log(
                "residual exceeds 1 m/s — state the spread, do not tighten a "
                "clearance margin with this model yet"
            )

    def _append_shot_log(self, entry: Measurement, retracted: bool = False) -> None:
        if self._shot_log is None:
            return
        record = {
            "schema": SCHEMA,
            "event": "retracted_measurement" if retracted else "measurement",
            "method": "A_landing_distance",
            "rpm": entry.rpm,
            "landing_distance_m": entry.distance_m,
            "at": entry.at,
            "session_id": self._session_id,
        }
        try:
            self._shot_log.parent.mkdir(parents=True, exist_ok=True)
            with self._shot_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        except OSError as error:
            # A calibration session must not die because a log path is
            # unwritable, but the operator has to know the evidence is missing.
            self._log(f"WARNING: could not append to the shot log: {error}")

    # ---- serial -------------------------------------------------------

    def _send(self, command: str) -> None:
        self._write(command)

    # ---- status -------------------------------------------------------

    def status(self) -> Dict[str, object]:
        state = self.state
        return {
            "schema": SCHEMA,
            "port": state.port,
            "connected": state.connected,
            "allow_fire": state.allow_fire,
            "estop_latched": state.estop_latched,
            "armed": state.armed,
            "arm_remaining_s": round(self.arm_remaining_s(), 1),
            "arm_timeout_s": self._arm_timeout_s,
            "pitch_deg": state.pitch_deg,
            "yaw_deg": state.yaw_deg,
            "wheel_rpm": state.wheel_rpm,
            "rpm_left": state.rpm_left,
            "rpm_right": state.rpm_right,
            "rpm_min_fire": RPM_MIN_FIRE,
            "angle_limit_deg": ANGLE_LIMIT_DEG,
            # The live envelope, not a constant: the UI's slider bounds come from
            # here so the control can never offer an angle the bridge will clamp.
            "pitch_min_deg": state.pitch_min_deg,
            "pitch_max_deg": state.pitch_max_deg,
            "pitch_default_min_deg": self._default_pitch_min,
            "pitch_default_max_deg": self._default_pitch_max,
            "yaw_limit_deg": YAW_LIMIT_DEG,
            "shots_fired": state.shots_fired,
            "last_refusal": state.last_refusal,
            "info_lines": state.info_lines[-6:],
            "measurements": [
                {"rpm": m.rpm, "distance_m": m.distance_m} for m in state.measurements
            ],
            "model_path": state.model_path,
            "model_summary": state.model_summary,
        }


# ---------------------------------------------------------------------------
# serial plumbing
# ---------------------------------------------------------------------------

BOOT_PREFIXES = ("ets ", "rst:", "configsip:", "clk_drv:", "mode:", "load:", "entry")


def shutdown_commands(center_on_exit: bool = False) -> List[str]:
    """What to send on the way out.

    `stop` IS the safety action: it kills the flywheels and the feeder. Moving the
    aim is not — and `center` is a BLIND move to the firmware's zero, which on an
    open-loop axis with no position feedback may be anywhere. On 2026-08-06 that
    zero sat inside the ball feeder after a jam, so every console exit drove the
    barrel straight back into it. Centering is therefore opt-in, and an operator
    who wants it can press CENTER deliberately once they trust the reference.
    """
    return ["stop", "center"] if center_on_exit else ["stop"]


def is_noise(line: str) -> bool:
    """ESP32 boot ROM chatter and baud-transition garbage."""
    if line.startswith(BOOT_PREFIXES):
        return True
    # A long run of two or fewer distinct characters is line noise, not a message.
    return len(line) > 20 and len(set(line)) <= 2


def parse_telemetry(line: str) -> Optional[Tuple[float, float]]:
    """`L:1234 R:1200` -> (left, right). Too chatty for the log, but it is the
    only continuous evidence that the flywheels are actually spinning."""
    if not line.startswith("L:") or " R:" not in line:
        return None
    try:
        left, right = line.split(" R:", 1)
        return float(left[2:].strip()), float(right.strip().split()[0])
    except (ValueError, IndexError):
        return None


def load_fitter(path: Path):
    """Import scripts/fit_rpm_speed.py by path.

    Deliberately reused rather than reimplemented: that module's `fit` is what
    writes the model the launcher and the clearance evaluator read, and it is
    covered by tests/test_rpm_speed_fit.py.
    """
    spec = importlib.util.spec_from_file_location("fit_rpm_speed", path)
    if spec is None or spec.loader is None:
        raise OSError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial-port", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--allow-fire", action="store_true",
                    help="Enable the arm/fire intents. Without it they are refused.")
    ap.add_argument("--arm-timeout-s", type=float, default=ARM_TIMEOUT_S)
    ap.add_argument("--pitch-min", type=float, default=PITCH_DEFAULT_MIN_DEG,
                    help="Default lower pitch travel limit for the session. The "
                         "operator can declare a measured envelope with `limits`.")
    ap.add_argument("--pitch-max", type=float, default=PITCH_DEFAULT_MAX_DEG)
    ap.add_argument("--center-on-exit", action="store_true",
                    help="Also send `center` when closing. OFF by default: it is a "
                         "blind move to the firmware's zero, which on this open-loop "
                         "machine may be inside the ball feeder.")
    ap.add_argument("--shot-log", default="garage_lab_combined/cal/blm/rpm_speed_shots.jsonl")
    ap.add_argument("--model-out", default="garage_lab_combined/cal/blm/rpm_speed_model.json")
    ap.add_argument("--fit-script", default="scripts/fit_rpm_speed.py")
    args = ap.parse_args()

    try:
        args.pitch_min, args.pitch_max = validate_pitch_envelope(
            args.pitch_min, args.pitch_max
        )
    except CommandError as error:
        ap.error(str(error))

    def emit(line: str) -> None:
        print(line, flush=True)

    def log(message: str) -> None:
        emit(f"[BLM] {message}")

    try:
        import serial
    except ImportError:
        emit("[BLM] ERROR: pyserial is not installed in this venv")
        return 2

    try:
        fitter = load_fitter(Path(args.fit_script))
    except Exception as error:  # noqa: BLE001 - the console still works without it
        fitter = None
        log(f"fit helper unavailable ({error}) — measure still records shots")

    log(f"opening {args.serial_port} @ {args.baud}")
    try:
        ser = serial.Serial(args.serial_port, args.baud, timeout=0.1)
    except Exception as error:  # noqa: BLE001 - surfaced to the operator log
        emit(f"[BLM] ERROR: could not open {args.serial_port}: {error}")
        return 2
    # The ESP32 resets when DTR asserts; anything written before it settles is
    # lost, and the boot banner would otherwise be read as telemetry.
    time.sleep(2)
    ser.reset_input_buffer()

    write_lock = threading.Lock()

    def write(command: str) -> None:
        with write_lock:
            ser.write((command + "\n").encode())
        log(f"-> {command}")
        time.sleep(WRITE_SETTLE_S)

    controller = BlmController(
        write,
        log,
        allow_fire=args.allow_fire,
        arm_timeout_s=args.arm_timeout_s,
        shot_log=Path(args.shot_log),
        model_out=Path(args.model_out),
        fitter=fitter,
        session_id=os.environ.get("PROJECT_CAM_SESSION_ID", ""),
        pitch_min_deg=args.pitch_min,
        pitch_max_deg=args.pitch_max,
    )
    controller.state.port = args.serial_port
    controller.state.connected = True

    status_lock = threading.Lock()

    def publish() -> None:
        with status_lock:
            emit(STATUS_PREFIX + json.dumps(controller.status()))

    stop_event = threading.Event()

    def reader() -> None:
        last = ""
        while not stop_event.is_set():
            try:
                raw = ser.readline().decode("utf-8", errors="ignore").strip()
            except Exception:  # noqa: BLE001 - a closed port ends the thread
                if not stop_event.is_set():
                    log("serial read failed — link lost")
                    controller.state.connected = False
                    publish()
                break
            if not raw or is_noise(raw):
                continue
            telemetry = parse_telemetry(raw)
            if telemetry is not None:
                controller.state.rpm_left, controller.state.rpm_right = telemetry
                controller.state.telemetry_at = time.monotonic()
                continue
            if raw == last:
                continue
            last = raw
            controller.state.info_lines.append(raw)
            del controller.state.info_lines[:-12]
            emit(f"  <- {raw}")

    threading.Thread(target=reader, daemon=True).start()

    def heartbeat() -> None:
        # Republishes so the UI sees flywheel telemetry and the arm countdown
        # without having to poll the backend.
        while not stop_event.wait(0.5):
            controller.expire_arm()
            publish()

    threading.Thread(target=heartbeat, daemon=True).start()

    shutting_down = threading.Event()

    def safe_shutdown() -> None:
        if shutting_down.is_set():
            return
        shutting_down.set()
        stop_event.set()
        commands = shutdown_commands(args.center_on_exit)
        try:
            for command in commands:
                with write_lock:
                    ser.write((command + "\n").encode())
                time.sleep(WRITE_SETTLE_S)
            time.sleep(0.3)
        except Exception:  # noqa: BLE001 - closing anyway
            pass
        try:
            ser.close()
        except Exception:  # noqa: BLE001
            pass
        emit(f"[BLM] {' + '.join(commands)} sent, serial closed")

    def on_signal(_signum, _frame) -> None:
        # A STOP from the desktop app arrives as SIGINT to the process group.
        safe_shutdown()
        os._exit(0)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    log("ready — fire control " + ("ENABLED" if args.allow_fire else "disabled"))
    publish()

    try:
        for line in sys.stdin:
            try:
                intent = parse_command(line)
            except CommandError as error:
                controller.state.last_refusal = str(error)
                log(f"REFUSED: {error}")
                publish()
                continue
            if intent is None:
                continue
            if intent.kind == "quit":
                break
            try:
                controller.handle(intent)
            except CommandError as error:
                log(f"REFUSED: {error}")
            except Exception as error:  # noqa: BLE001 - never leave the wheels up
                log(f"ERROR: {error} — sending stop")
                try:
                    controller.handle(Intent("stop"))
                except Exception:  # noqa: BLE001
                    pass
            publish()
    finally:
        safe_shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
