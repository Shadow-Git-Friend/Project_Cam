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
  * `arm` requires a `reload` since the last shot, so a dry cycle cannot be
    recorded as a shot
  * `arm` and `fire` require the MEASURED flywheel RPM to agree with the command,
    freshly and for long enough to be stable -- not merely a commanded number
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
    measure <landing_distance_m>            undo        fit <height_m> [kind]

Protocol (stdout)
-----------------
Human-readable lines for the operator log, plus one machine line per change:

    @BLM {"schema": "project_cam.blm_console.v1", ...}

The `measure`/`fit` intents exist so a v(RPM) calibration session never has to
leave the console: `fit` calls the SAME `scripts/fit_rpm_speed.py` functions the
launcher reads its model from, rather than reimplementing the arithmetic.

`measure` deliberately takes NO rpm. The protocol requires the wheels commanded
to zero and confirmed below 50 RPM before anyone may walk downrange to the ball,
so by the time a distance can be measured the commanded RPM is 0 -- a caller
supplying it would record 0 for every shot. The RPM is captured by `fire`, at
the instant the shot was actually taken, and a distance attaches to that
pending shot. An rpm argument is not merely redundant: it is the one way a wrong
value could enter the evidence, so the vocabulary does not offer it.

Measurement procedure: docs/protocols/2026-08-03-rpm-speed-measurement.md
"""

import argparse
import importlib.util
import json
import math
import os
import re
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

SCHEMA = "project_cam.blm_console.v1"
STATUS_PREFIX = "@BLM "

# Shot evidence gets its OWN schema, separate from the status transport, because
# the word `shot_fired` changed meaning (2026-08-11). Under v1 it was written the
# moment `shoot` reached the serial writer; under v2 it is written only when the
# firmware reports the front limit. The four v1 rows already on disk therefore
# prove a command write and nothing more, and a reader must be able to tell the
# two apart without knowing which day the file was produced.
SHOT_EVIDENCE_SCHEMA = "project_cam.blm_shot_evidence.v2"

# The firmware's own proof that a ball physically travelled. Matched EXACTLY: it
# is the one line that promotes a request into a shot, so a substring or prefix
# match would let an unrelated message manufacture evidence.
SHOT_FIRED_ACK = "SYS: SHOT FIRED - FRONT LIMIT HIT"

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

# How long a `shoot` may stay unacknowledged before the outcome is declared
# unknown. Deliberately a starting default, not a commissioned number: S0-S2 do
# not exercise the physical shot path, so nothing here has yet measured the real
# command-to-front-limit latency. Tightening it needs that measurement from a
# separately authorised non-human backstop test, after every preceding gate
# passes.
SHOT_ACK_TIMEOUT_S = 5.0

# Wheel confirmation (added 2026-08-07).
#
# The firmware reports MEASURED flywheel RPM as `L:<n> R:<n>`, and until now the
# console collected it and gated on nothing: `arm` and `fire` both read the
# COMMANDED value. So a shot could be armed and taken 200 ms after commanding 500
# while the wheels were still at 120 — the firmware's own >=400 gate would refuse
# it, but the bridge had ALREADY incremented the shot count, created a pending
# shot and written `shot_fired` to the evidence log. A refused shot was recorded
# as a real one, and the landing distance of the previous ball could then attach
# to it.
#
# These numbers come from docs/protocols/2026-08-03-rpm-speed-measurement.md,
# which asked the operator to check them by eye ("both wheels 450-550, difference
# <= 75, three polls spanning at least two seconds"). Written down as a gate they
# hold whether or not anyone remembers the step.
RPM_BAND_FRAC = 0.10          # +/-10 % of the commanded RPM ...
RPM_BAND_FLOOR = 50.0         # ... and never tighter than +/-50 (the 450-550 at 500)
RPM_SPREAD_MAX = 75.0         # max |L - R|; a bigger split is not one delivery speed
WHEELS_STABLE_S = 2.0         # the protocol's "three polls spanning >= 2 s" ...
WHEELS_STABLE_MIN_SAMPLES = 3  # ... and the "three polls" half of it, separately.

# Telemetry older than this is not evidence of anything. The firmware suppresses
# telemetry while the pusher moves, and a dead reader thread leaves the LAST
# numbers in place forever — so a frozen "0 / 0" would read as "the wheels are
# stopped, it is safe to walk out to the ball".
TELEMETRY_MAX_AGE_S = 2.0
# Both wheels below this, freshly measured, before anyone may walk downrange.
RPM_SAFE_APPROACH = 50.0

# `info` prints the limit-switch pin levels (`Front:1 Back:0 Ball:0`). The
# switches are INPUT_PULLUP and trigger on LOW, so a pressed switch reads 0 and a
# detected ball is `Ball:0` — which is what the written protocol means by
# "Ball=LOW". INFERRED from the firmware wiring, not measured here, which is
# exactly why the ball reading is displayed, recorded and used to warn, but is
# NOT a gate: an inverted polarity would refuse every shot with a ball loaded.
BALL_PRESENT_LEVEL = 0

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
        exact(1)
        distance = _number(rest[0], "landing_distance_m")
        if distance <= 0 or distance > 60:
            raise CommandError(
                f"landing_distance_m must be between 0 and 60, got {distance:g}")
        return Intent("measure", (distance,))
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
class FireRequest:
    """A `shoot` that reached the serial writer. NOT yet a shot.

    Below the firmware's 400 RPM gate `STATE_SHOOTING` simply holds the pusher in
    place and sends nothing at all, so a refused shot and a successful one are
    indistinguishable to the writer. Only the front-limit acknowledgement tells
    them apart, and until it arrives this object is the whole record: the outcome
    is unknown, and no distance may attach to it.

    The pre-fire RPM pair is captured HERE rather than at confirmation because it
    cannot be re-read later — the firmware gates telemetry on `STATE_IDLE` and is
    in `STATE_SHOOTING` for the entire acknowledgement window.
    """

    request_seq: int
    rpm: float
    requested_at: str
    requested_monotonic: float
    rpm_left_pre_fire: float
    rpm_right_pre_fire: float
    rpm_pre_fire_sample_age_s: float
    pitch_deg: float
    yaw_deg: float
    timed_out: bool = False


@dataclass
class PendingShot:
    """A shot the FIRMWARE confirmed, waiting for its landing distance.

    `rpm` is the wheel RPM commanded at the instant `fire` was accepted, which is
    the only moment it is knowable: the protocol spins the wheels down before the
    operator may walk out and measure.

    `rpm_*_pre_fire` are what the flywheels were MEASURED at before the request
    went out, and `rpm_pre_fire_sample_age_s` is how old that reading already was.
    The name says `pre_fire` because a contemporaneous measurement is structurally
    impossible here, and a field called `measured` would invite the reader to
    assume one. The model stays indexed by the commanded RPM — that is the only
    value a launcher can be told to reproduce — but a v(RPM) curve whose
    independent variable was never checked against the machine is not auditable,
    so both travel together.
    """

    rpm: float
    seq: int
    request_seq: int
    confirmed_at: str
    rpm_left_pre_fire: float
    rpm_right_pre_fire: float
    rpm_pre_fire_sample_age_s: float


@dataclass
class Measurement:
    rpm: float
    distance_m: float
    at: str
    shot_seq: int
    request_seq: int
    rpm_left_pre_fire: float
    rpm_right_pre_fire: float
    rpm_pre_fire_sample_age_s: float


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
    # When the measured wheels ENTERED the band around the commanded RPM. None
    # means they are not in it. Reset by any command that changes the target, so a
    # stability timer can never be inherited from a different RPM.
    rpm_band_since: Optional[float] = None
    # The window is described by ARRIVALS, not by elapsed wall time. The old form
    # stored only `rpm_band_since` and compared it to the clock, so ONE reading
    # followed by two seconds of silence read as two seconds of proven stability
    # — and on `control_12` that silence is the normal state, because the
    # continuous stream is BLE-only and nothing arrives unless someone polls.
    rpm_band_last_sample_at: Optional[float] = None
    rpm_band_sample_count: int = 0
    # Whether a ball has been loaded since the last shot. Bookkeeping the console
    # is entitled to: it sent the `reload` and it sent the `shoot`. Without it a
    # second `arm`+`fire` with no reload is a dry cycle that still gets recorded
    # as a shot, and the ONE ball on the floor then attaches to the wrong one.
    loaded: bool = False
    # An aim the operator actually established. Distinct from `pitch_deg`, which
    # is also filled in by `wheels` (the firmware takes one combined
    # `set v h wl wr`, so an RPM-only change must still state the angles).
    aim_established: bool = False
    # Parsed from `info`, so the operator does not have to read Ball=LOW out of raw
    # serial text. None until a poll has been seen.
    ball_present: Optional[bool] = None
    ball_seen_at: float = 0.0
    info_at: float = 0.0
    # Dedup memory for the serial reader. Held here rather than in the reader
    # closure so that requesting `info` can RESET it — see `_do_info`.
    last_serial_line: str = ""
    shots_fired: int = 0
    # `shoot` commands written to the port. Deliberately distinct from
    # `shots_fired`, which counts only firmware-confirmed physical shots: the gap
    # between the two IS the diagnostic.
    fire_requests_sent: int = 0
    fire_request: Optional[FireRequest] = None
    last_confirmed_request_seq: int = 0
    pending_shot: Optional[PendingShot] = None
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
        shot_ack_timeout_s: float = SHOT_ACK_TIMEOUT_S,
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
        # Telemetry and acknowledgements arrive on the reader thread while intents
        # arrive on the main loop. Re-entrant because `handle()` calls helpers that
        # read the same state. Held ACROSS the `shoot` write, so a fast
        # acknowledgement cannot be processed before the request that explains it
        # has been installed.
        self._state_lock = threading.RLock()
        self._arm_timeout_s = arm_timeout_s
        if not math.isfinite(shot_ack_timeout_s) or shot_ack_timeout_s <= 0:
            raise ValueError(
                "shot_ack_timeout_s must be finite and positive, got "
                f"{shot_ack_timeout_s!r}"
            )
        self._shot_ack_timeout_s = float(shot_ack_timeout_s)
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

    def refresh_arm(self) -> None:
        """Drop an arm that has expired OR whose wheels are no longer confirmed.

        An armed console whose flywheels cannot be verified is the same misleading
        state as a latched ESTOP with live-looking controls: the panel says the
        next hold fires a shot, and the machine may not be able to. Called from
        `handle` and from the heartbeat, so it holds without an operator action.
        """
        self.expire_arm()
        if not self.state.armed:
            return
        # The FULL predicate, so a sample arriving after a stale gap clears the
        # arm instead of preserving it: that reading restarts the window, and one
        # fresh-but-unproven value is not what the arm was granted on.
        reason = self.wheels_stable_reason()
        if reason is not None:
            self.state.armed = False
            self.state.arm_expires_at = 0.0
            self._log(f"ARM cleared — {reason}")

    def refresh_safety(self) -> None:
        """Everything the console must re-decide without an operator action.

        Called from the heartbeat, so an unacknowledged shot resolves itself
        rather than waiting for the operator to press something — which they
        will not do, because the panel is what tells them anything is wrong.
        """
        with self._state_lock:
            self.refresh_arm()
            request = self.state.fire_request
            if request is None or request.timed_out:
                return
            if (self._now() - request.requested_monotonic
                    < self._shot_ack_timeout_s):
                return
            # Latch and record BEFORE the write, so a stop whose transmission
            # fails still leaves a console that refuses actuation. Same
            # asymmetry `_do_stop` already keeps.
            self.state.estop_latched = True
            self.state.armed = False
            self.state.arm_expires_at = 0.0
            self.state.wheel_rpm = 0.0
            self._reset_wheel_band()
            # Marked rather than dropped: the request stays so a LATE exact
            # acknowledgement is still recognisable as this shot instead of
            # arriving as an unexplained one. The latch stays set regardless.
            request.timed_out = True
            self._append_fire_event("shot_confirmation_timeout", request)
            self._log(
                "shot outcome unknown — no front-limit ACK; this includes the "
                "firmware's silent below 400 RPM refusal. STOP latched by design."
            )
            try:
                self._send("stop")
            except Exception as error:
                self._log(f"STOP write failed after ACK timeout: {error}")

    # ---- measured flywheel state --------------------------------------

    def note_telemetry(self, left: float, right: float) -> None:
        """Absorb one `L:<n> R:<n>` reading.

        Lives on the controller rather than in the reader thread so the band and
        stability logic is testable without a serial port, and so there is exactly
        one implementation of "the wheels agree with the command".
        """
        with self._state_lock:
            # The gap is measured against the PREVIOUS sample, so this has to be
            # computed before `telemetry_at` is overwritten.
            now = self._now()
            last = self.state.rpm_band_last_sample_at
            if self._rpm_in_band(left, right):
                if (self.state.rpm_band_since is None or last is None
                        or now - last > TELEMETRY_MAX_AGE_S):
                    # Either the first in-band sample, or the first after a
                    # silence longer than a reading stays evidence. Two readings
                    # either side of a gap do not describe the gap.
                    self.state.rpm_band_since = now
                    self.state.rpm_band_last_sample_at = now
                    self.state.rpm_band_sample_count = 1
                elif now > last:
                    # Same instant means one arrival, not two: a burst must not
                    # be able to buy a count it did not earn.
                    self.state.rpm_band_last_sample_at = now
                    self.state.rpm_band_sample_count += 1
            else:
                self._reset_wheel_band()
            self.state.rpm_left = left
            self.state.rpm_right = right
            self.state.telemetry_at = now
            self.refresh_arm()

    def _reset_wheel_band(self) -> None:
        """Forget the stability window. Any change of target invalidates it."""
        self.state.rpm_band_since = None
        self.state.rpm_band_last_sample_at = None
        self.state.rpm_band_sample_count = 0

    def rpm_band(self) -> float:
        """Half-width of the acceptance band around the commanded RPM."""
        return max(RPM_BAND_FLOOR, RPM_BAND_FRAC * self.state.wheel_rpm)

    def _rpm_in_band(self, left: float, right: float) -> bool:
        commanded = self.state.wheel_rpm
        band = self.rpm_band()
        return (abs(left - commanded) <= band
                and abs(right - commanded) <= band
                and abs(left - right) <= RPM_SPREAD_MAX)

    def telemetry_age_s(self) -> Optional[float]:
        """Seconds since the last flywheel reading, or None if there never was one.

        Published, because the number itself is worthless without it: the panel's
        "MEASURED 0 rpm" is what the operator reads before walking downrange.
        """
        if self.state.telemetry_at == 0.0:
            return None
        return max(0.0, self._now() - self.state.telemetry_at)

    def wheels_unconfirmed_reason(self) -> Optional[str]:
        """None when the MEASURED wheels agree with the command; else why not."""
        age = self.telemetry_age_s()
        if age is None:
            return ("no flywheel telemetry has arrived on this link, so the "
                    "console cannot tell whether the wheels are spinning")
        if age > TELEMETRY_MAX_AGE_S:
            return (f"the last flywheel reading is {age:.1f} s old "
                    f"(limit {TELEMETRY_MAX_AGE_S:.0f} s)")
        left, right = self.state.rpm_left, self.state.rpm_right
        if left is None or right is None:
            return "no flywheel reading has been parsed yet"
        if abs(left - right) > RPM_SPREAD_MAX:
            return (f"the wheels disagree: L={left:.0f} R={right:.0f}, over the "
                    f"{RPM_SPREAD_MAX:.0f} RPM spread limit")
        band = self.rpm_band()
        commanded = self.state.wheel_rpm
        if abs(left - commanded) > band or abs(right - commanded) > band:
            return (f"measured L={left:.0f} R={right:.0f} is outside the "
                    f"commanded {commanded:.0f} +/-{band:.0f} RPM")
        return None

    def wheels_in_band_s(self) -> float:
        """The span the SAMPLES cover, not the time since the first one.

        Advancing the clock without a new reading must never grow this number:
        silence is the absence of evidence, and the whole point of the window is
        that it is made of arrivals.
        """
        first = self.state.rpm_band_since
        last = self.state.rpm_band_last_sample_at
        if first is None or last is None:
            return 0.0
        return max(0.0, last - first)

    def wheels_stable_reason(self) -> Optional[str]:
        """None when the wheels are confirmed AND proven steady; else why not.

        The full arm predicate: agreement with the command, then enough separate
        arrivals, then enough span between them. One implementation, used by
        `arm`, by the redundant pre-send check in `fire`, and by the heartbeat —
        so a console can never display a readiness its own gate would refuse.
        """
        reason = self.wheels_unconfirmed_reason()
        if reason is not None:
            return reason
        count = self.state.rpm_band_sample_count
        if count < WHEELS_STABLE_MIN_SAMPLES:
            return (f"only {count}/{WHEELS_STABLE_MIN_SAMPLES} separate in-band "
                    "samples have arrived")
        span = self.wheels_in_band_s()
        if span < WHEELS_STABLE_S:
            return f"the in-band samples span {span:.1f}/{WHEELS_STABLE_S:.1f} s"
        return None

    def safe_to_approach(self) -> bool:
        """Whether the machine itself says the flywheels are stopped.

        Deliberately conservative in three independent ways: the command must be
        zero, the reading must be FRESH, and both wheels must be under the
        threshold. Absent telemetry is never "safe" — the whole failure mode being
        guarded is a stale zero that reads like a stopped machine.
        """
        if self.state.wheel_rpm != 0:
            return False
        age = self.telemetry_age_s()
        if age is None or age > TELEMETRY_MAX_AGE_S:
            return False
        left, right = self.state.rpm_left, self.state.rpm_right
        if left is None or right is None:
            return False
        return left < RPM_SAFE_APPROACH and right < RPM_SAFE_APPROACH

    # ---- serial input -------------------------------------------------

    def note_serial_line(self, raw: str) -> bool:
        """Absorb one non-telemetry firmware line. True if it is worth echoing.

        Consecutive identical lines are collapsed (boot spam, repeated warnings),
        but `_do_info` clears the memory first, so a SOLICITED reply is never the
        thing that gets deduplicated away. That was a real defect: the protocol
        asks for three polls spanning two seconds to prove the machine is stable,
        a stable machine answers with IDENTICAL text, and the 2nd and 3rd replies
        vanished — the more stable the rig, the less visible the confirmation.
        """
        with self._state_lock:
            # BEFORE the dedup, and not merely as an optimisation: two consecutive
            # shots produce two IDENTICAL acknowledgement lines, so a
            # dedup-first order would swallow the second one and leave a real
            # shot permanently unconfirmed. Idempotence is decided by the request
            # state instead, which is the thing that actually distinguishes them.
            if raw == SHOT_FIRED_ACK:
                return self._confirm_fire_request()
            if raw == self.state.last_serial_line:
                return False
            self.state.last_serial_line = raw
            self.state.info_lines.append(raw)
            del self.state.info_lines[:-12]
            if self.state.info_at == 0.0:
                self.state.info_at = self._now()
            return self._note_ball_state(raw)

    def _note_ball_state(self, raw: str) -> bool:
        ball = parse_ball_state(raw)
        if ball is not None:
            self.state.ball_present = ball
            self.state.ball_seen_at = self._now()
            if self.state.loaded and not ball:
                # Not a refusal: the polarity of this reading is inferred from the
                # firmware wiring, so it warns rather than blocking a session. It
                # is also the ONLY evidence of the reload timeout path, where the
                # feeder gives up after 10 s and IDLEs with no ball.
                self._log(
                    "WARNING: the firmware reports no ball at the feeder, but a "
                    "reload was sent — reload may have timed out. Check the "
                    "chamber before firing."
                )
        return True

    def info_age_s(self) -> Optional[float]:
        if self.state.info_at == 0.0:
            return None
        return max(0.0, self._now() - self.state.info_at)

    # ---- gates --------------------------------------------------------

    def _require_live(self, kind: str) -> None:
        if kind in ACTUATING and self.state.estop_latched:
            raise CommandError("ESTOP latched — send clear before any actuation")

    def _refuse(self, message: str) -> None:
        self.state.last_refusal = message
        raise CommandError(message)

    # ---- intents ------------------------------------------------------

    def handle(self, intent: Intent) -> None:
        with self._state_lock:
            # An outstanding request means a ball may or may not have left the
            # barrel. Nothing that could change the physical outcome — or the
            # evidence it will attach to — is allowed until that is resolved.
            # STOP and DISARM stay reachable because they only ever reduce
            # capability; CLEAR is listed so it reaches its own refusal rather
            # than this generic one.
            if (self.state.fire_request is not None
                    and intent.kind not in ("stop", "disarm", "clear")):
                self._refuse(
                    "no confirmed shot — shoot request is awaiting firmware "
                    "confirmation"
                )
            self.refresh_arm()
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
        if rpm != self.state.wheel_rpm:
            self._reset_wheel_band()
        self.state.pitch_deg, self.state.yaw_deg = pitch, yaw
        self.state.aim_established = True
        self.state.wheel_rpm = rpm
        # Changing the aim invalidates the operator's clearance judgement.
        if self.state.armed:
            self.state.armed = False
            self._log("aim changed — ARM cleared, arm again to fire")
        self._send(f"set {pitch:.0f} {yaw:.0f} {rpm:.0f} {rpm:.0f}")

    def _do_wheels(self, intent: Intent) -> None:
        (rpm,) = intent.args
        # The firmware takes ONE combined `set v h wl wr`, so an RPM-only change
        # must still state the angles. Filling in 0/0 when nothing was aimed does
        # NOT count as an aim the operator established: otherwise pressing an RPM
        # preset alone satisfied the "send an aim before arming" gate with an angle
        # nobody chose.
        pitch = self.state.pitch_deg if self.state.pitch_deg is not None else 0.0
        yaw = self.state.yaw_deg if self.state.yaw_deg is not None else 0.0
        if rpm != self.state.wheel_rpm:
            self._reset_wheel_band()
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
        # Reload homes the axes, so 0/0 is an aim the machine really holds.
        self.state.aim_established = True
        self.state.wheel_rpm = 0.0
        self._reset_wheel_band()
        # The console's own record that a ball was requested. It is bookkeeping,
        # not detection: the firmware's DISPENSING state also exits on a 10 s
        # TIMEOUT with no ball, which is why `note_serial_line` warns when a poll
        # contradicts this.
        self.state.loaded = True
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
        self.state.aim_established = True
        self._send("center")

    def _do_info(self, _intent: Intent) -> None:
        # Start a fresh block and forget the dedup memory, so THIS poll's reply is
        # always visible even when it is byte-identical to the previous one. The
        # protocol's three-polls-over-two-seconds check depends on seeing all
        # three, and a stable machine answers identically every time.
        self.state.info_lines = []
        self.state.last_serial_line = ""
        self.state.info_at = 0.0
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
        self.state.aim_established = True
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
        self._reset_wheel_band()
        # A stop can land in the middle of a feeder cycle, so after it nothing may
        # be assumed about the chamber. Requiring another reload is cheap; a dry
        # shot recorded as a real one is not.
        self.state.loaded = False
        self._log("STOP — latched; send clear to release")
        self._send("stop")

    def _do_clear(self, _intent: Intent) -> None:
        request = self.state.fire_request
        if request is not None and request.timed_out:
            # CLEAR releases a latch the OPERATOR caused. This one stands for "a
            # ball may or may not be on the floor and the chamber state is
            # unknown", which no keystroke can resolve — it needs the chamber
            # inspected after confirmed spin-down, i.e. a new session.
            self._refuse(
                f"shot {request.request_seq}'s outcome is unresolved — close the "
                "console, confirm the wheels have stopped, inspect the chamber, "
                "and start a new session"
            )
        if not self.state.estop_latched:
            self._log("nothing latched")
            return
        self.state.estop_latched = False
        self._log("ESTOP latch released — wheels are at 0, aim again before firing")
        self._log("the stop cleared the chamber state — reload before arming")

    def _do_arm(self, _intent: Intent) -> None:
        if not self.state.allow_fire:
            self._refuse("this console was launched without fire control")
        # Arming is not actuation, so the latch check above does not cover it —
        # but an armed console behind a latched ESTOP is a misleading state.
        if self.state.estop_latched:
            self._refuse("ESTOP latched — send clear before arming")
        if not self.state.aim_established:
            self._refuse("send an aim before arming")
        if self.state.wheel_rpm < RPM_MIN_FIRE:
            self._refuse(
                f"wheels must be commanded to >= {RPM_MIN_FIRE} RPM before arming "
                f"(currently {self.state.wheel_rpm:.0f})"
            )
        if not self.state.loaded:
            # Otherwise a second arm+fire with no reload is a dry cycle that still
            # increments the shot count and writes `shot_fired`, and the single
            # ball on the floor then attaches to the shot that launched nothing.
            self._refuse(
                "no ball has been loaded since the last shot — send reload first"
            )
        reason = self.wheels_stable_reason()
        if reason is not None:
            self._refuse(f"the flywheels are not confirmed: {reason}")
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
        # Deliberately redundant with `refresh_arm`, which normally clears the arm
        # first and produces the "not armed" refusal above. The two run in
        # DIFFERENT THREADS — telemetry arrives on the reader, a shot on the main
        # loop — so a fire landing between heartbeats must not depend on the
        # heartbeat having noticed. The commanded value is not evidence: it is what
        # was asked for, and this is the only check on what happened.
        reason = self.wheels_stable_reason()
        if reason is not None:
            self._refuse(f"the flywheels are not confirmed: {reason}")
        if self.state.fire_request is not None:
            self._refuse("a shoot request is still awaiting firmware confirmation")
        if self.state.pending_shot is not None:
            # Two balls on the floor and no way to tell which is which. Refusing
            # is the only way every physical ball keeps exactly one place to
            # attach its measurement.
            self._refuse("record the confirmed shot distance before firing again")
        # Disarm BEFORE the write. If the serial write raises, the console must
        # not be left armed holding a shot the operator believes was refused.
        self.state.armed = False
        self.state.arm_expires_at = 0.0
        sample_age = self.telemetry_age_s()
        left, right = self.state.rpm_left, self.state.rpm_right
        if sample_age is None or left is None or right is None:
            # `wheels_unconfirmed_reason` above already rejects this, so reaching
            # here would mean the reading vanished between the two checks. Refuse
            # rather than record a shot with no provenance for its RPM.
            self._refuse("the pre-fire RPM sample disappeared before shoot")
        request = FireRequest(
            request_seq=self.state.fire_requests_sent + 1,
            rpm=self.state.wheel_rpm,
            requested_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            requested_monotonic=self._now(),
            rpm_left_pre_fire=left,
            rpm_right_pre_fire=right,
            rpm_pre_fire_sample_age_s=sample_age,
            pitch_deg=self.state.pitch_deg or 0.0,
            yaw_deg=self.state.yaw_deg or 0.0,
        )
        # Installed BEFORE the write, because the acknowledgement can arrive on
        # the reader thread the instant the command lands. The state lock held by
        # `handle` is what makes that ordering safe.
        self.state.fire_request = request
        try:
            self._send("shoot")
        except Exception:
            # No ball left the barrel, so this must not burn a sequence number or
            # leave a request the operator would have to resolve.
            self.state.fire_request = None
            raise
        self.state.fire_requests_sent = request.request_seq
        self.state.loaded = False
        self._append_fire_event("shot_requested", request)
        self._log(
            f"shoot request {request.request_seq} sent at {request.rpm:.0f} RPM "
            f"commanded, wheels last measured L={left:.0f} R={right:.0f} "
            f"({sample_age:.1f} s before) — awaiting firmware front-limit ACK"
        )

    def _confirm_fire_request(self) -> bool:
        """Promote the outstanding request into a shot. The ONLY path that can.

        Called with the state lock held, from `note_serial_line`.
        """
        request = self.state.fire_request
        if request is None:
            if self.state.last_confirmed_request_seq:
                # A repeat of the acknowledgement that already promoted a shot.
                # One ball, one record.
                return False
            self._handle_orphan_shot_ack()
            return True
        self.state.shots_fired += 1
        shot = PendingShot(
            rpm=request.rpm,
            seq=self.state.shots_fired,
            request_seq=request.request_seq,
            confirmed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            rpm_left_pre_fire=request.rpm_left_pre_fire,
            rpm_right_pre_fire=request.rpm_right_pre_fire,
            rpm_pre_fire_sample_age_s=request.rpm_pre_fire_sample_age_s,
        )
        self.state.pending_shot = shot
        self.state.fire_request = None
        self.state.last_confirmed_request_seq = request.request_seq
        self._append_shot_fired(shot)
        self._log(
            f"shot {shot.seq} confirmed by firmware front limit — awaiting distance"
        )
        return True

    def _handle_orphan_shot_ack(self) -> None:
        """The firmware reports physical travel the console cannot explain.

        Whatever the cause — a second writer on the port, a stale buffer, a
        firmware fault — the console's model of what the machine has done is
        now wrong, and a calibration pass built on it would not be evidence.
        """
        self.state.estop_latched = True
        self.state.armed = False
        self.state.arm_expires_at = 0.0
        self.state.wheel_rpm = 0.0
        self._reset_wheel_band()
        self._write_shot_record({
            "schema": SHOT_EVIDENCE_SCHEMA,
            "event": "orphan_shot_ack",
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session_id": self._session_id,
        })
        self._log("orphan firmware shot ACK — STOP latched; session invalid")
        try:
            self._send("stop")
        except Exception as error:
            self._log(f"STOP write failed after orphan ACK: {error}")

    # ---- calibration bookkeeping --------------------------------------

    def _do_measure(self, intent: Intent) -> None:
        (distance,) = intent.args
        pending = self.state.pending_shot
        if pending is None:
            # A distance with no CONFIRMED shot behind it is not a measurement of
            # anything. Before 2026-08-11 a command write was enough to open this
            # door, so a distance could be recorded against a shot the firmware
            # had silently refused.
            self._refuse(
                "no confirmed shot is waiting for a distance — fire first, and "
                "record each shot before taking the next"
            )
        entry = Measurement(rpm=pending.rpm, distance_m=distance,
                            at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                            shot_seq=pending.seq,
                            request_seq=pending.request_seq,
                            rpm_left_pre_fire=pending.rpm_left_pre_fire,
                            rpm_right_pre_fire=pending.rpm_right_pre_fire,
                            rpm_pre_fire_sample_age_s=(
                                pending.rpm_pre_fire_sample_age_s))
        self.state.measurements.append(entry)
        self.state.pending_shot = None
        self._append_shot_log(entry)
        self._log(
            f"recorded shot {pending.seq}: {pending.rpm:.0f} RPM -> "
            f"{distance:.3f} m ({len(self.state.measurements)} measurement(s))"
        )

    def _do_undo(self, _intent: Intent) -> None:
        if not self.state.measurements:
            self._log("no measurements to undo")
            return
        dropped = self.state.measurements.pop()
        # The JSONL keeps the retraction rather than rewriting history: an
        # operator log that can be silently edited is not evidence.
        self._append_shot_log(dropped, retracted=True)
        # The shot still happened, so it goes back to awaiting a distance. A
        # mistyped distance must cost a re-entry, never a re-shoot.
        self.state.pending_shot = PendingShot(
            rpm=dropped.rpm, seq=dropped.shot_seq,
            request_seq=dropped.request_seq, confirmed_at=dropped.at,
            rpm_left_pre_fire=dropped.rpm_left_pre_fire,
            rpm_right_pre_fire=dropped.rpm_right_pre_fire,
            rpm_pre_fire_sample_age_s=dropped.rpm_pre_fire_sample_age_s,
        )
        self._log(
            f"undid shot {dropped.shot_seq}: {dropped.rpm:.0f} RPM -> "
            f"{dropped.distance_m:.3f} m — awaiting a distance again"
        )

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

    def _append_fire_event(self, event: str, request: FireRequest) -> None:
        """One writer for every request-scoped event, so a `shot_requested` and
        the `shot_confirmation_timeout` that may follow it carry identical
        provenance and can be joined on `request_seq`."""
        self._write_shot_record({
            "schema": SHOT_EVIDENCE_SCHEMA,
            "event": event,
            "method": "A_landing_distance",
            "request_seq": request.request_seq,
            # `rpm` stays the COMMANDED value: it is what indexes the model and
            # what a launcher can be told to reproduce. The pre-fire pair travels
            # beside it so the independent variable is auditable rather than
            # assumed — a v(RPM) curve fitted against an unchecked x is not.
            "rpm": request.rpm,
            "rpm_left_pre_fire": request.rpm_left_pre_fire,
            "rpm_right_pre_fire": request.rpm_right_pre_fire,
            "rpm_pre_fire_sample_age_s": request.rpm_pre_fire_sample_age_s,
            "requested_at": request.requested_at,
            "session_id": self._session_id,
        })

    def _append_shot_fired(self, shot: PendingShot) -> None:
        """Record the confirmed shot itself, not only its measurement.

        This is what makes the pass auditable from one file: a confirmed shot
        with no matching measurement is visible as such, so a rejected attempt
        cannot be quietly dropped and a measurement cannot be invented for a shot
        that was never taken.
        """
        self._write_shot_record({
            "schema": SHOT_EVIDENCE_SCHEMA,
            "event": "shot_fired",
            "method": "A_landing_distance",
            "request_seq": shot.request_seq,
            "rpm": shot.rpm,
            "rpm_left_pre_fire": shot.rpm_left_pre_fire,
            "rpm_right_pre_fire": shot.rpm_right_pre_fire,
            "rpm_pre_fire_sample_age_s": shot.rpm_pre_fire_sample_age_s,
            "shot_seq": shot.seq,
            "confirmed_at": shot.confirmed_at,
            "session_id": self._session_id,
        })

    def _append_shot_log(self, entry: Measurement, retracted: bool = False) -> None:
        self._write_shot_record({
            "schema": SHOT_EVIDENCE_SCHEMA,
            "event": "retracted_measurement" if retracted else "measurement",
            "method": "A_landing_distance",
            "request_seq": entry.request_seq,
            "rpm": entry.rpm,
            "rpm_left_pre_fire": entry.rpm_left_pre_fire,
            "rpm_right_pre_fire": entry.rpm_right_pre_fire,
            "rpm_pre_fire_sample_age_s": entry.rpm_pre_fire_sample_age_s,
            "shot_seq": entry.shot_seq,
            "landing_distance_m": entry.distance_m,
            "at": entry.at,
            "session_id": self._session_id,
        })

    def _write_shot_record(self, record: Dict[str, object]) -> None:
        if self._shot_log is None:
            return
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
        with self._state_lock:
            return self._status_locked()

    def _status_locked(self) -> Dict[str, object]:
        state = self.state
        telemetry_age = self.telemetry_age_s()
        unconfirmed = self.wheels_unconfirmed_reason()
        unstable = self.wheels_stable_reason()
        info_age = self.info_age_s()
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
            "aim_established": state.aim_established,
            "wheel_rpm": state.wheel_rpm,
            "rpm_left": state.rpm_left,
            "rpm_right": state.rpm_right,
            # A measured RPM without its age is not evidence: the firmware stops
            # sending while the pusher moves, and a dead reader leaves the last
            # numbers on screen forever. None means none has ever arrived.
            "telemetry_age_s": (None if telemetry_age is None
                                else round(telemetry_age, 1)),
            "telemetry_max_age_s": TELEMETRY_MAX_AGE_S,
            # The verdicts, computed HERE rather than in the UI, because these are
            # the same predicates the arm and fire gates use. Two implementations
            # of one safety rule is one implementation too many.
            "wheels_confirmed": unconfirmed is None,
            "wheels_unconfirmed_reason": unconfirmed or "",
            # The FULL arm predicate, published separately: agreement with the
            # command is necessary but not sufficient, and a panel that showed
            # only `wheels_confirmed` would look ready while ARM refuses.
            "wheels_stable": unstable is None,
            "wheels_unstable_reason": unstable or "",
            "wheels_sample_count": state.rpm_band_sample_count,
            "wheels_stable_min_samples": WHEELS_STABLE_MIN_SAMPLES,
            "wheels_in_band_s": round(self.wheels_in_band_s(), 1),
            "wheels_band_rpm": round(self.rpm_band(), 1),
            "wheels_stable_required_s": WHEELS_STABLE_S,
            "rpm_spread_max": RPM_SPREAD_MAX,
            # Whether the MACHINE says the flywheels are stopped. The protocol step
            # before anyone walks downrange to the ball.
            "safe_to_approach": self.safe_to_approach(),
            "rpm_safe_approach": RPM_SAFE_APPROACH,
            # Bookkeeping (a reload since the last shot) and, separately, whatever
            # the last poll's ball switch actually said.
            "loaded": state.loaded,
            "ball_present": state.ball_present,
            "info_age_s": None if info_age is None else round(info_age, 1),
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
            # The UI gates RECORD SHOT on this and shows whose RPM it will carry,
            # so the operator can see the distance is attaching to the shot they
            # just took rather than to whatever the RPM control currently reads.
            "shot_ack_timeout_s": self._shot_ack_timeout_s,
            # Published so the panel can say "awaiting firmware confirmation"
            # instead of showing a console that merely looks idle.
            "fire_request": (
                None if state.fire_request is None else {
                    "request_seq": state.fire_request.request_seq,
                    "rpm": state.fire_request.rpm,
                    "rpm_left_pre_fire": state.fire_request.rpm_left_pre_fire,
                    "rpm_right_pre_fire": state.fire_request.rpm_right_pre_fire,
                    "rpm_pre_fire_sample_age_s": (
                        state.fire_request.rpm_pre_fire_sample_age_s),
                    "confirmation_age_s": round(
                        self._now() - state.fire_request.requested_monotonic, 1),
                    "timed_out": state.fire_request.timed_out,
                }
            ),
            "pending_shot": (
                None if state.pending_shot is None
                else {"rpm": state.pending_shot.rpm,
                      "seq": state.pending_shot.seq,
                      "request_seq": state.pending_shot.request_seq,
                      "rpm_left_pre_fire": state.pending_shot.rpm_left_pre_fire,
                      "rpm_right_pre_fire": state.pending_shot.rpm_right_pre_fire,
                      "rpm_pre_fire_sample_age_s": (
                          state.pending_shot.rpm_pre_fire_sample_age_s)}
            ),
            "last_refusal": state.last_refusal,
            "info_lines": state.info_lines[-6:],
            "measurements": [
                {"rpm": m.rpm, "distance_m": m.distance_m, "shot_seq": m.shot_seq}
                for m in state.measurements
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


NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"

# The 4 Hz stream. `control_12` emits it only to a connected BLE client, so over
# USB alone it never arrives — which is exactly why the second form below has to
# work.
COMPACT_RPM = re.compile(
    rf"^L:\s*(?P<left>{NUMBER})\s+R:\s*(?P<right>{NUMBER})(?:\s|$)")
# A solicited `info` reply, and on `control_12` the ONLY way a measured RPM
# reaches this console. The `/target` half is deliberately matched and discarded:
# the bridge already owns the commanded value, and reading the machine's echo of
# it back as though it were independent evidence is how a commanded number gets
# mistaken for a measured one.
INFO_RPM = re.compile(
    rf"^INFO \| RPM:\s*L=(?P<left>{NUMBER})/{NUMBER},\s*"
    rf"R=(?P<right>{NUMBER})/{NUMBER}\s*$")


def parse_telemetry(line: str) -> Optional[Tuple[float, float]]:
    """Measured flywheel RPM from either firmware form -> (left, right).

    Anchored at the start of the line in both cases: a measured RPM is the input
    to `safe_to_approach`, i.e. to the decision to walk in front of the barrel,
    so it may only come from a line whose whole shape the console recognises.
    """
    match = COMPACT_RPM.match(line) or INFO_RPM.match(line)
    if match is None:
        return None
    try:
        return float(match.group("left")), float(match.group("right"))
    except ValueError:
        return None


# `control_12` prints levels (`Ball=HIGH`), older/other firmware prints the pin
# digit (`Ball:0`). Both are accepted; anything else is not a reading.
BALL_FIELD = re.compile(
    r"\bBall\s*[:=]\s*(?P<value>\d+|HIGH|LOW)\b", re.IGNORECASE)


def parse_ball_state(line: str) -> Optional[bool]:
    """`Front:1 Back:0 Ball:0` -> True (a ball is sitting at the feeder).

    Parsed so the operator does not have to read `Ball=LOW` out of raw serial
    text — the protocol asked for exactly that, from a line the console already
    had in hand. Returns None when the line says nothing about the ball.

    Polarity comes from the firmware wiring (INPUT_PULLUP, triggered on LOW, so a
    pressed switch reads 0), which makes it INFERRED rather than measured. That is
    why it never gates a shot: an inverted reading would refuse every shot with a
    ball loaded. It is displayed, and it warns when it contradicts the console's
    own bookkeeping — which is the only visible sign of the firmware's 10 s
    dispense TIMEOUT, where a reload completes with an empty chamber.
    """
    match = BALL_FIELD.search(line)
    if match is None:
        return None
    raw = match.group("value").upper()
    # HIGH/LOW are the pin LEVELS the firmware prints, so they map onto the same
    # inferred polarity as the digits — this is a change of notation, not of
    # meaning, and LOW stays "a ball is there".
    level = 0 if raw == "LOW" else 1 if raw == "HIGH" else int(raw)
    return level == BALL_PRESENT_LEVEL


def consume_serial_line(controller: BlmController, raw: str) -> bool:
    """Route one firmware line. True if the operator should see it.

    One router for both forms, because an `info` reply is BOTH a measurement and
    something the operator asked to see: it updates the flywheel state and stays
    in the poll block. The compact stream updates the same state silently — at
    4 Hz it would bury every other line in the log.
    """
    telemetry = parse_telemetry(raw)
    if telemetry is not None:
        controller.note_telemetry(*telemetry)
        if raw.startswith("L:"):
            return False
    return controller.note_serial_line(raw)


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
            # One router, so an `info` reply can be both a measurement and a
            # visible answer. Everything goes through the controller, keeping the
            # band/stability logic and the arm re-check in exactly one place.
            if not consume_serial_line(controller, raw):
                continue
            emit(f"  <- {raw}")

    threading.Thread(target=reader, daemon=True).start()

    def heartbeat() -> None:
        # Republishes so the UI sees flywheel telemetry, its AGE and the arm
        # countdown without having to poll the backend. `refresh_safety` also drops
        # an arm whose wheels stopped being confirmed, and resolves a `shoot` the
        # firmware never acknowledged — neither state may persist just because no
        # command happened to arrive.
        while not stop_event.wait(0.5):
            controller.refresh_safety()
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
