"""The desktop launcher console's gates.

`project-cam-desktop/` may now hold the launcher's serial link (2026-08-04), and
`garage_lab_combined/scripts/blm_bridge.py` is the only place that writes it. The
bridge is therefore where the operator gates live, and these tests are about the
properties a shot depends on rather than about plumbing:

  * nothing typed on stdin reaches the firmware verbatim
  * a shot needs an arm, the arm expires, and one shot consumes it
  * ESTOP latches, and it latches even when the serial write fails
  * a fit model always carries its sample count and residual

Ranges are duplicated in `src-tauri/src/blm.rs` on purpose: that layer refuses
out-of-range values, this one clamps. Parity is pinned by
tests/test_desktop_launcher_console.py.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "garage_lab_combined/scripts/blm_bridge.py"
FIT = ROOT / "scripts/fit_rpm_speed.py"

# Every serial command the firmware accepts from this bridge. Anything else
# reaching the port would mean an intent was passed through as text.
FIRMWARE_COMMAND = re.compile(
    r"^(set -?\d+ -?\d+ \d+ \d+|reload|shoot|stop|center|setzero|info)$"
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bridge():
    return _load(BRIDGE, "blm_bridge")


@pytest.fixture(scope="module")
def fitter():
    return _load(FIT, "fit_rpm_speed")


class Clock:
    """Injected time, so arm expiry is tested rather than waited for."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class Wire:
    """Collects what would have gone down the serial port.

    `fail_on` fails a single command so a broken write can be tested at the exact
    step that matters (a shot, a stop) without breaking the setup around it.
    """

    def __init__(self, fail: bool = False, fail_on: str = "") -> None:
        self.sent: list[str] = []
        self.fail = fail
        self.fail_on = fail_on

    def __call__(self, command: str) -> None:
        self.sent.append(command)
        if self.fail or (self.fail_on and command == self.fail_on):
            raise OSError("serial write failed")


def make(bridge, *, allow_fire=True, clock=None, wire=None, fitter=None,
         tmp_path=None, arm_timeout_s=30.0, shot_ack_timeout_s=5.0,
         pitch_min_deg=None, pitch_max_deg=None):
    clock = clock or Clock()
    wire = wire or Wire()
    logs: list[str] = []
    controller = bridge.BlmController(
        wire,
        logs.append,
        allow_fire=allow_fire,
        now=clock,
        arm_timeout_s=arm_timeout_s,
        shot_ack_timeout_s=shot_ack_timeout_s,
        shot_log=(tmp_path / "shots.jsonl") if tmp_path else None,
        model_out=(tmp_path / "model.json") if tmp_path else None,
        fitter=fitter,
        **({} if pitch_min_deg is None else {"pitch_min_deg": pitch_min_deg}),
        **({} if pitch_max_deg is None else {"pitch_max_deg": pitch_max_deg}),
    )
    return controller, wire, logs, clock


def send(bridge, controller, line: str):
    """Drive the controller exactly as main() does: parse, then handle."""
    intent = bridge.parse_command(line)
    if intent is None:
        return
    controller.handle(intent)


def spin_up(controller, clock, rpm, *, hold_s=2.5, spread=0.0):
    """Feed the MEASURED flywheel telemetry the arm gate now requires.

    Every firing test has to do this, which is the point: before 2026-08-07 the
    gates read the commanded RPM only, so a test could arm a launcher whose wheels
    had never reported spinning — exactly what the live console allowed.

    THREE arrivals, because two endpoints two seconds apart say nothing about
    what happened in between — and on `control_12` the only source of a measured
    RPM is a manual poll, so "the operator polled twice" is a real possibility
    the gate has to reject. This mirrors the protocol's "three polls spanning at
    least two seconds".
    """
    controller.note_telemetry(rpm, rpm + spread)
    clock.advance(hold_s / 2.0)
    controller.note_telemetry(rpm, rpm + spread)
    clock.advance(hold_s / 2.0)
    controller.note_telemetry(rpm, rpm + spread)


def ready_to_arm(bridge, controller, clock, rpm=800, pitch=0, yaw=0):
    """The real per-shot cycle: reload, aim, spin up, confirm."""
    send(bridge, controller, "reload")
    send(bridge, controller, f"aim {pitch} {yaw} {rpm}")
    spin_up(controller, clock, rpm)


def arm_and_aim(bridge, controller, clock, rpm=800):
    ready_to_arm(bridge, controller, clock, rpm=rpm)
    send(bridge, controller, "arm")


# The firmware says a ball physically left the barrel by reporting the front
# limit switch, and it says it exactly once per shot. Sending `shoot` says only
# that a command reached the port: below the 400 RPM gate the firmware sits in
# STATE_SHOOTING and answers NOTHING at all, so a refused shot and a fired shot
# look identical to the writer.
SHOT_ACK = "SYS: SHOT FIRED - FRONT LIMIT HIT"


def confirm_shot(controller):
    assert controller.note_serial_line(SHOT_ACK)


# ----------------------------- the closed vocabulary ------------------------

def test_an_unrecognised_verb_never_reaches_the_firmware(bridge):
    """The difference between this and a terminal. `blm_interactive.py` forwards
    whatever it is given; a UI-driven bridge must not."""
    for line in ["shoot now", "setzero", "jf500", "js90", "jv100",
                 "set 0 0 900 900", "aim; shoot", "reload extra", "ARMED",
                 "fire please", "stop now", "", "   "]:
        if not line.strip():
            assert bridge.parse_command(line) is None
            continue
        with pytest.raises(bridge.CommandError):
            bridge.parse_command(line)


def test_every_intent_writes_only_known_firmware_commands(bridge, fitter, tmp_path):
    controller, wire, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    for line in ["limits -20 30", "aim 12 -7 800", "wheels 500", "info", "center",
                 "set_zero", "reload", "aim 0 0 800"]:
        send(bridge, controller, line)
    # The arm gate needs the flywheels to have REPORTED the commanded RPM, and the
    # telemetry path is not an intent — it arrives on the reader thread.
    spin_up(controller, clock, 800)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    # The firmware's front-limit report is what turns the request into a shot;
    # without it the measurement intents below are refused, not silently skipped.
    confirm_shot(controller)
    for line in ["measure 3.94", "undo", "measure 3.9", "fit 0.52",
                 "stop", "clear"]:
        send(bridge, controller, line)
    assert wire.sent, "nothing was sent at all"
    assert "shoot" in wire.sent, "the shot never happened, so this proves nothing"
    for command in wire.sent:
        assert FIRMWARE_COMMAND.match(command), f"unexpected serial write {command!r}"


def test_arguments_must_be_finite_numbers_in_range(bridge):
    for bad in ["aim x 0 800", "aim 0 0 nan", "aim 0 0 inf", "wheels -1",
                "wheels 1201", "aim 0 0 1300", "measure 0",
                "measure 61", "fit 0", "fit 6", "fit 0.5 cubic",
                "aim 0 0", "wheels", "fit"]:
        with pytest.raises(bridge.CommandError):
            bridge.parse_command(bad)
    # The operating envelope itself must remain expressible.
    for good in ["aim 30 -30 1200", "aim -30 30 0", "wheels 400",
                 "measure 2.4", "fit 0.52 interp", "fit 0.52"]:
        assert bridge.parse_command(good) is not None


def test_closing_the_console_stops_but_does_not_blindly_recentre(bridge):
    """Found live 2026-08-06. The exit path sent `stop` then `center`, and `center`
    is a BLIND move to the firmware's zero. After a jam that zero sat inside the
    ball feeder, so every console exit drove the barrel straight back into it.

    `stop` is the safety action — it kills the flywheels and the feeder. Moving the
    aim is not, so centering is opt-in.
    """
    assert bridge.shutdown_commands() == ["stop"]
    assert bridge.shutdown_commands(False) == ["stop"]
    assert bridge.shutdown_commands(True) == ["stop", "center"]


def test_setzero_adopts_the_current_position_without_moving_and_clears_the_arm(bridge):
    """The reference-fixing command, needed exactly when an open-loop axis has been
    driven into a stop. It moves nothing, so it stays available under a latch."""
    controller, wire, logs, clock = make(bridge)
    ready_to_arm(bridge, controller, clock, rpm=800, pitch=20, yaw=-10)
    send(bridge, controller, "arm")
    assert controller.state.armed

    send(bridge, controller, "set_zero")
    assert wire.sent[-1] == "setzero"
    # The current position IS the new zero, so the stored aim must follow.
    assert controller.state.pitch_deg == 0.0
    assert controller.state.yaw_deg == 0.0
    # Every angle now means something else than the clearance judgement assumed.
    assert not controller.state.armed
    assert any("level the barrel" in line for line in logs), logs

    # Available while latched: it changes a reference, it does not actuate.
    send(bridge, controller, "stop")
    assert controller.state.estop_latched
    send(bridge, controller, "set_zero")
    assert wire.sent[-1] == "setzero"
    assert "set_zero" not in bridge.ACTUATING


def test_the_pitch_envelope_is_session_state_the_operator_declares(bridge):
    """Reworked 2026-08-06, the same day the first version shipped.

    Clamping pitch to a hardcoded [0, 30] stopped the jam but was the wrong frame:
    the barrel meets the ball feeder at a fixed PHYSICAL position, while this angle
    is measured from a zero adopted at boot or by `set_zero`. A constant therefore
    points at a different physical place after every re-zero — and it deleted the
    downward travel the machine really has, because how much room is left below
    zero depends on where zero was put. Only the operator can see that.
    """
    controller, wire, logs, _ = make(bridge)
    # Conservative default: no downward travel, which cannot jam from zero.
    assert controller.state.pitch_min_deg == bridge.PITCH_DEFAULT_MIN_DEG == 0.0
    send(bridge, controller, "aim -12 0 0")
    assert wire.sent == ["set 0 0 0 0"], wire.sent
    assert any("ball feeder" in line for line in logs), logs
    assert any("limits" in line for line in logs), (
        "the refusal must point at the way to declare more travel")

    # Declared travel is then honoured.
    send(bridge, controller, "limits -25 30")
    assert (controller.state.pitch_min_deg, controller.state.pitch_max_deg) == (-25.0, 30.0)
    send(bridge, controller, "aim -12 0 0")
    assert wire.sent[-1] == "set -12 0 0 0"
    # ...and still enforced at its edge.
    send(bridge, controller, "aim -40 0 0")
    assert wire.sent[-1] == "set -25 0 0 0"

    # Yaw is unaffected: it is a fixed firmware-bound limit, not an envelope. The
    # pitch here is the 0 this command asked for, not the -25 left by the previous
    # one — an aim states both axes.
    send(bridge, controller, "aim 0 -45 0")
    assert wire.sent[-1] == "set 0 -30 0 0"


def test_a_declared_envelope_must_be_ordered_and_inside_the_firmware_bound(bridge):
    for bad in ["limits -31 30", "limits 0 31", "limits 10 10", "limits 20 5",
                "limits 10 20", "limits -20 -10", "limits 0", "limits 0 10 20",
                "limits a b"]:
        with pytest.raises(bridge.CommandError):
            bridge.parse_command(bad)
    for good in ["limits -30 30", "limits 0 30", "limits -5 5"]:
        assert bridge.parse_command(good) is not None


def test_declaring_an_envelope_that_excludes_the_current_aim_is_refused(bridge):
    """Changing limits is non-actuating, so it must not pretend the mechanism
    moved to a clamped angle. Move inside first, then narrow the envelope."""
    controller, wire, logs, clock = make(bridge)
    send(bridge, controller, "limits -30 30")
    send(bridge, controller, "reload")
    send(bridge, controller, "aim -20 0 800")
    spin_up(controller, clock, 800)
    send(bridge, controller, "arm")

    with pytest.raises(bridge.CommandError, match="move inside it first"):
        send(bridge, controller, "limits -5 30")

    assert controller.state.pitch_deg == -20.0
    assert (controller.state.pitch_min_deg, controller.state.pitch_max_deg) == (-30.0, 30.0)
    assert controller.state.armed
    assert wire.sent[-1] == "set -20 0 800 800"
    assert any("current aim" in line for line in logs), logs


def test_a_re_zero_translates_the_envelope_into_the_new_frame(bridge):
    """SET ZERO changes coordinates, not the physical safe endpoints.

    With the old safe range [0, 30] and the barrel commanded to +12, the same
    physical endpoints are -12 and +18 relative to the new zero. Losing that
    translation was the regression: every re-zero restored [0, 30] and deleted
    all legitimate downward travel.
    """
    controller, wire, logs, _ = make(bridge)
    send(bridge, controller, "aim 12 7 0")
    send(bridge, controller, "set_zero")
    assert controller.state.pitch_deg == 0.0
    assert controller.state.yaw_deg == 0.0
    assert controller.state.pitch_min_deg == -12.0
    assert controller.state.pitch_max_deg == 18.0
    assert wire.sent[-1] == "setzero"
    assert any("translated" in line for line in logs), logs

    # CENTER is now the zero just adopted by SET ZERO.
    send(bridge, controller, "center")
    assert wire.sent[-1] == "center"
    assert controller.state.pitch_deg == 0.0
    assert controller.state.yaw_deg == 0.0


def test_a_re_zero_intersects_translated_travel_with_the_firmware_bound(bridge):
    controller, _, _, _ = make(bridge, pitch_min_deg=-20.0, pitch_max_deg=25.0)
    send(bridge, controller, "aim -15 0 0")
    send(bridge, controller, "set_zero")
    # Physical endpoints translate to [-5, 40], but firmware accepts only +/-30.
    assert controller.state.pitch_min_deg == -5.0
    assert controller.state.pitch_max_deg == 30.0


def test_the_launch_default_envelope_is_configurable(bridge):
    """A rig whose zero sits mid-travel can start from its real envelope rather
    than re-declaring it every session."""
    controller, wire, _, _ = make(bridge, pitch_min_deg=-20.0, pitch_max_deg=25.0)
    send(bridge, controller, "aim -15 0 0")
    assert wire.sent[-1] == "set -15 0 0 0"


def test_the_launch_default_envelope_must_contain_zero(bridge):
    for low, high in [(10.0, 20.0), (-20.0, -10.0), (20.0, 5.0), (-31.0, 30.0)]:
        with pytest.raises(bridge.CommandError):
            make(bridge, pitch_min_deg=low, pitch_max_deg=high)


def test_angles_are_clamped_and_the_clamp_is_reported(bridge):
    """The firmware reboots beyond +/-30. A silent clamp would be a different
    shot than the operator asked for, so it is logged."""
    controller, wire, logs, _ = make(bridge)
    send(bridge, controller, "aim 45 -60 800")
    assert wire.sent == ["set 30 -30 800 800"]
    assert any("clamped" in line for line in logs)
    assert controller.state.pitch_deg == 30.0
    assert controller.state.yaw_deg == -30.0


# --------------------------------- firing gates -----------------------------

def test_without_fire_control_the_shot_intents_do_not_work(bridge):
    controller, wire, _, _ = make(bridge, allow_fire=False)
    send(bridge, controller, "aim 0 0 800")
    for line in ["arm", "fire"]:
        with pytest.raises(bridge.CommandError, match="without fire control"):
            send(bridge, controller, line)
    assert "shoot" not in wire.sent
    assert controller.state.shots_fired == 0


def test_a_shot_requires_an_arm_and_the_arm_requires_an_aim_above_the_gate(bridge):
    controller, wire, _, clock = make(bridge)
    # No aim yet.
    with pytest.raises(bridge.CommandError, match="aim before arming"):
        send(bridge, controller, "arm")
    # Aim, but the wheels are below the firmware's own 400 RPM gate.
    send(bridge, controller, "aim 0 0 300")
    with pytest.raises(bridge.CommandError, match="400 RPM"):
        send(bridge, controller, "arm")
    # Above the gate and confirmed spinning, but no ball was ever loaded.
    send(bridge, controller, "aim 0 0 800")
    spin_up(controller, clock, 800)
    with pytest.raises(bridge.CommandError, match="no ball has been loaded"):
        send(bridge, controller, "arm")
    # Unarmed fire is refused even with everything else satisfied.
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 800")
    spin_up(controller, clock, 800)
    with pytest.raises(bridge.CommandError, match="not armed"):
        send(bridge, controller, "fire")
    assert "shoot" not in wire.sent

    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    assert wire.sent[-1] == "shoot"
    # A written command is a request; the count moves only on the firmware's
    # front-limit report.
    assert controller.state.shots_fired == 0
    confirm_shot(controller)
    assert controller.state.shots_fired == 1


def test_pressing_an_rpm_preset_is_not_an_aim(bridge):
    """`wheels` has to send the angles too — the firmware takes one combined
    `set v h wl wr` — and it filled in 0/0 when nothing had been aimed. That made
    the "send an aim before arming" gate satisfiable by touching only the RPM
    control, with an angle nobody chose."""
    controller, wire, _, clock = make(bridge)
    send(bridge, controller, "reload")
    # The reload homes the axes, so 0/0 IS established after it. Start from a
    # console that has not reloaded to isolate the wheels path.
    controller.state.aim_established = False

    send(bridge, controller, "wheels 800")
    assert wire.sent[-1] == "set 0 0 800 800", "the angles must still be stated"
    assert controller.state.pitch_deg == 0.0
    assert not controller.state.aim_established, (
        "an RPM-only change is not an aim the operator established")
    spin_up(controller, clock, 800)
    with pytest.raises(bridge.CommandError, match="aim before arming"):
        send(bridge, controller, "arm")

    send(bridge, controller, "aim 0 0 800")
    assert controller.state.aim_established
    spin_up(controller, clock, 800)
    send(bridge, controller, "arm")
    assert controller.state.armed


def test_arming_needs_the_measured_wheels_not_just_the_commanded_ones(bridge):
    """The defect this gate exists for (found 2026-08-07).

    `arm` and `fire` both read the COMMANDED RPM, and the firmware's MEASURED
    `L:/R:` telemetry was collected and used for nothing. So a shot could be armed
    and taken 200 ms after commanding 500 while the wheels were still at 120: the
    firmware refused it, but the bridge had already counted the shot, created a
    pending shot and written `shot_fired` to the evidence log. A refused shot was
    recorded as a real one.
    """
    controller, wire, logs, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")

    # No telemetry at all: absent evidence is not confirmation.
    with pytest.raises(bridge.CommandError, match="no flywheel telemetry"):
        send(bridge, controller, "arm")

    # Spinning up, still far below the command.
    controller.note_telemetry(120.0, 118.0)
    with pytest.raises(bridge.CommandError, match="outside the commanded"):
        send(bridge, controller, "arm")

    # One wheel lagging: not one delivery speed, whatever the mean says.
    controller.note_telemetry(500.0, 380.0)
    with pytest.raises(bridge.CommandError, match="wheels disagree"):
        send(bridge, controller, "arm")

    # In band, but one arrival says nothing about duration.
    controller.note_telemetry(498.0, 505.0)
    clock.advance(0.5)
    with pytest.raises(bridge.CommandError,
                       match="1/3 separate in-band samples"):
        send(bridge, controller, "arm")

    # Three arrivals, none separated by more than the freshness limit, together
    # spanning the required two seconds. Two readings either side of a silence
    # would NOT do — they describe their own instants, not the gap between them.
    clock.advance(1.0)
    controller.note_telemetry(501.0, 497.0)
    clock.advance(1.0)
    controller.note_telemetry(502.0, 499.0)
    send(bridge, controller, "arm")
    assert controller.state.armed
    assert "shoot" not in wire.sent


def test_a_stale_reading_is_not_confirmation_and_it_disarms(bridge):
    """The firmware stops sending telemetry while the pusher moves, and a dead
    reader thread leaves the last numbers in place forever. An armed console whose
    flywheels cannot be verified is the same misleading state as a latched ESTOP
    with live-looking controls."""
    controller, wire, logs, clock = make(bridge)
    arm_and_aim(bridge, controller, clock, rpm=500)
    assert controller.state.armed

    clock.advance(bridge.TELEMETRY_MAX_AGE_S + 0.5)
    controller.refresh_arm()
    assert not controller.state.armed
    assert any("ARM cleared" in line and "old" in line for line in logs), logs

    with pytest.raises(bridge.CommandError, match="not armed"):
        send(bridge, controller, "fire")
    assert "shoot" not in wire.sent
    # And it cannot be re-armed on the stale reading either.
    with pytest.raises(bridge.CommandError, match="s old"):
        send(bridge, controller, "arm")


def test_waiting_after_one_sample_never_manufactures_a_stability_window(bridge):
    """The old timer stored only WHEN the wheels entered the band and compared it
    to the clock, so a single reading plus two seconds of silence read as two
    seconds of proven stability. On `control_12` that silence is the normal
    state: the continuous stream is BLE-only, so nothing arrives unless the
    operator polls."""
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    controller.note_telemetry(500, 500)
    clock.advance(2.0)
    with pytest.raises(bridge.CommandError, match="1/3 separate in-band samples"):
        send(bridge, controller, "arm")


def test_three_samples_in_30ms_do_not_satisfy_two_seconds(bridge):
    """Count alone is not evidence of duration — a burst is one instant seen
    three times."""
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    for _ in range(3):
        controller.note_telemetry(500, 500)
        clock.advance(0.01)
    with pytest.raises(bridge.CommandError, match=r"0\.0/2\.0 s"):
        send(bridge, controller, "arm")


def test_a_burst_of_polls_plus_waiting_is_not_a_two_second_window(bridge):
    """The distinction the whole window rests on: span is what the SAMPLES
    cover, never how long ago the first one was.

    Constructed so nothing else can refuse it — four in-band arrivals, none
    separated by more than the freshness limit, and the last one still fresh.
    Only the span is short. Measuring from the clock instead would arm here.
    """
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    for _ in range(3):
        controller.note_telemetry(500, 500)
        clock.advance(0.01)
    clock.advance(1.87)
    controller.note_telemetry(500, 500)
    clock.advance(0.6)

    assert controller.state.rpm_band_sample_count == 4
    assert controller.telemetry_age_s() < bridge.TELEMETRY_MAX_AGE_S
    assert controller.wheels_in_band_s() == pytest.approx(1.9)
    with pytest.raises(bridge.CommandError, match=r"span 1\.9/2\.0 s"):
        send(bridge, controller, "arm")


def test_a_fresh_sample_after_a_silence_clears_an_existing_arm(bridge):
    """The reading agrees with the command and is perfectly fresh — and it is
    the FIRST of a restarted window, so it no longer supports the arm that was
    granted on the old one. Checking only agreement would keep the arm alive
    across a silence on a single unproven value."""
    controller, _, _, clock = make(bridge)
    arm_and_aim(bridge, controller, clock, rpm=500)
    assert controller.state.armed

    clock.advance(bridge.TELEMETRY_MAX_AGE_S + 0.5)
    controller.note_telemetry(500, 500)
    assert controller.state.rpm_band_sample_count == 1
    assert not controller.state.armed


def test_a_gap_over_the_freshness_limit_restarts_count_and_span(bridge):
    """Two readings either side of a silence do not describe the silence. The
    window starts again rather than spanning across it."""
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    controller.note_telemetry(500, 500)
    clock.advance(bridge.TELEMETRY_MAX_AGE_S + 0.1)
    controller.note_telemetry(500, 500)
    assert controller.state.rpm_band_sample_count == 1
    assert controller.wheels_in_band_s() == 0.0


def test_three_samples_spanning_two_seconds_pass(bridge):
    controller, _, _, clock = make(bridge)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    assert controller.state.armed
    assert controller.state.rpm_band_sample_count == 3
    assert controller.wheels_in_band_s() >= 2.0


def test_identical_values_count_when_they_are_separate_arrivals(bridge):
    """A stable machine answers three polls with identical text, so requiring
    the numbers to CHANGE would mean the steadier the rig the harder it is to
    arm. Separate arrivals are what count — but two lines read at the same
    instant are one arrival, not two."""
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "aim 0 0 500")
    controller.note_telemetry(500, 500)
    controller.note_telemetry(500, 500)
    assert controller.state.rpm_band_sample_count == 1
    clock.advance(0.1)
    controller.note_telemetry(500, 500)
    assert controller.state.rpm_band_sample_count == 2


def test_a_second_shot_needs_another_reload(bridge, fitter, tmp_path):
    """Otherwise arm+fire again is a DRY cycle that still increments the shot
    count and writes `shot_fired`. The single ball on the floor then attaches to
    the shot that launched nothing, while the one that really flew is logged as
    fired-and-unmeasured."""
    controller, wire, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    fire_at(bridge, controller, clock, rpm=500)
    assert controller.state.shots_fired == 1
    assert not controller.state.loaded

    spin_up(controller, clock, 500)
    with pytest.raises(bridge.CommandError, match="no ball has been loaded"):
        send(bridge, controller, "arm")
    assert wire.sent.count("shoot") == 1
    assert controller.state.shots_fired == 1

    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [r["event"] for r in records] == ["shot_requested", "shot_fired"], (
        "a refused arm must leave no further shot in the evidence")


def test_a_stop_clears_the_chamber_state(bridge):
    """A stop can land mid-feeder-cycle, so afterwards nothing may be assumed about
    the chamber. Another reload is cheap; a dry shot in the evidence is not."""
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    assert controller.state.loaded
    send(bridge, controller, "stop")
    assert not controller.state.loaded
    send(bridge, controller, "clear")
    send(bridge, controller, "aim 0 0 500")
    spin_up(controller, clock, 500)
    with pytest.raises(bridge.CommandError, match="no ball has been loaded"):
        send(bridge, controller, "arm")


def test_changing_the_target_rpm_restarts_the_stability_clock(bridge):
    """A stability timer inherited from a different RPM would confirm wheels that
    have never been measured at the new one."""
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    spin_up(controller, clock, 500)
    assert controller.wheels_in_band_s() >= bridge.WHEELS_STABLE_S

    send(bridge, controller, "wheels 800")
    assert controller.wheels_in_band_s() == 0.0
    # Reaching the new target is not the same as having held it: the timer starts
    # from the first in-band reading at the NEW command, not from the old one.
    controller.note_telemetry(800.0, 795.0)
    assert controller.wheels_in_band_s() == 0.0
    with pytest.raises(bridge.CommandError, match="1/3 separate in-band samples"):
        send(bridge, controller, "arm")


def test_safe_to_approach_is_the_machine_saying_the_wheels_stopped(bridge):
    """The protocol step that ends with a person walking into the line of fire.
    Three independent conditions, and absent telemetry is never one of them: a
    frozen "0 / 0" is exactly what would be misread as permission."""
    controller, _, _, clock = make(bridge)
    # A machine that has never reported is not a stopped machine. Note that two
    # guards cover this — the missing age AND the missing values — because
    # `note_telemetry` sets them together; the coupling is pinned below, since
    # decoupling them would leave this case defended by only one of them.
    assert controller.telemetry_age_s() is None
    assert controller.state.rpm_left is None
    assert not controller.safe_to_approach(), "never measured is not safe"

    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    spin_up(controller, clock, 500)
    assert not controller.safe_to_approach(), "spinning wheels are not safe"

    send(bridge, controller, "wheels 0")
    controller.note_telemetry(220.0, 215.0)
    assert not controller.safe_to_approach(), "still coasting down"

    controller.note_telemetry(12.0, 8.0)
    assert controller.safe_to_approach()

    clock.advance(bridge.TELEMETRY_MAX_AGE_S + 0.5)
    assert not controller.safe_to_approach(), (
        "a stale zero must never read as a stopped machine")


def test_a_reading_and_its_timestamp_are_always_set_together(bridge):
    """Found by the mutation sweep, 2026-08-07.

    `safe_to_approach` rejects an unmeasured machine twice: once for the missing
    age, once for the missing values. That is only redundant while the two are
    written together — split them and one of those cases keeps a single guard,
    which is thin for the check that precedes a person walking downrange.
    """
    controller, _, _, clock = make(bridge)
    assert (controller.state.telemetry_at == 0.0) is (controller.state.rpm_left is None)
    controller.note_telemetry(500.0, 495.0)
    assert controller.state.telemetry_at != 0.0
    assert controller.state.rpm_left == 500.0
    assert controller.telemetry_age_s() == 0.0


def test_one_shot_consumes_the_arm(bridge):
    """The garage firing policy: every shot is a deliberate, separate act. An arm
    that survived its shot would make a second click a second ball."""
    controller, wire, _, clock = make(bridge)
    arm_and_aim(bridge, controller, clock)
    send(bridge, controller, "fire")
    # The arm is consumed by the REQUEST, not by the confirmation: a shot whose
    # outcome is unknown must not leave the console armed either.
    assert not controller.state.armed
    confirm_shot(controller)
    with pytest.raises(bridge.CommandError, match="not armed"):
        send(bridge, controller, "fire")
    assert wire.sent.count("shoot") == 1


def test_the_arm_expires_on_its_own(bridge):
    controller, wire, logs, clock = make(bridge, arm_timeout_s=30.0)
    arm_and_aim(bridge, controller, clock)
    clock.advance(29.0)
    assert controller.arm_remaining_s() == pytest.approx(1.0)
    clock.advance(1.5)
    with pytest.raises(bridge.CommandError, match="not armed"):
        send(bridge, controller, "fire")
    assert "shoot" not in wire.sent
    assert any("expired" in line for line in logs)


def test_changing_the_aim_or_dropping_the_wheels_clears_the_arm(bridge):
    """A clearance judgement belongs to one specific shot: move the barrel and it
    no longer applies."""
    controller, wire, _, clock = make(bridge)
    arm_and_aim(bridge, controller, clock)
    send(bridge, controller, "aim 10 0 800")
    assert not controller.state.armed
    with pytest.raises(bridge.CommandError, match="not armed"):
        send(bridge, controller, "fire")

    arm_and_aim(bridge, controller, clock)
    send(bridge, controller, "wheels 200")
    assert not controller.state.armed
    assert "shoot" not in wire.sent


def test_centering_resets_the_stored_aim_and_clears_the_arm(bridge):
    """The firmware takes ONE combined `set v h wl wr`, so the bridge's stored
    angles are re-sent by the next wheels command. Found live: `center` left the
    old angles in place, so asking only for flywheel RPM afterwards would have
    driven the barrel back up to where it had been before centering.
    """
    controller, wire, _, clock = make(bridge)
    ready_to_arm(bridge, controller, clock, rpm=800, pitch=25, yaw=-10)
    send(bridge, controller, "arm")
    assert controller.state.armed

    send(bridge, controller, "center")
    assert controller.state.pitch_deg == 0.0
    assert controller.state.yaw_deg == 0.0
    # Centering moves the barrel, so it invalidates the clearance judgement the
    # arm stood for, exactly as an aim change does.
    assert not controller.state.armed

    send(bridge, controller, "wheels 800")
    assert wire.sent[-1] == "set 0 0 800 800", (
        "wheels after center must not resurrect the pre-center aim")


def test_reload_adopts_the_firmware_center_and_spindown(bridge):
    """The firmware's reload handler homes both aim axes and sets target RPM to
    zero. Keeping the pre-reload state in the bridge makes the next wheels or
    SET ZERO command reuse an angle that the mechanism no longer holds."""
    controller, wire, _, clock = make(bridge)
    ready_to_arm(bridge, controller, clock, rpm=800, pitch=12, yaw=-6)
    send(bridge, controller, "arm")

    send(bridge, controller, "reload")

    assert wire.sent[-1] == "reload"
    assert controller.state.pitch_deg == 0.0
    assert controller.state.yaw_deg == 0.0
    assert controller.state.wheel_rpm == 0.0
    assert not controller.state.armed
    # The reload commanded the wheels to zero, so a stability window measured at
    # 800 RPM must not carry over into the next arm.
    assert controller.wheels_in_band_s() == 0.0

    # Re-zeroing at the position RELOAD just commanded is a zero shift, not the
    # stale +12 degrees from before the reload.
    send(bridge, controller, "set_zero")
    assert controller.state.pitch_min_deg == 0.0
    assert controller.state.pitch_max_deg == 30.0


def test_wheels_and_aim_do_not_disturb_each_other(bridge):
    """Two independent controls over one combined firmware command."""
    controller, wire, _, _ = make(bridge)
    send(bridge, controller, "aim 12 -6 0")
    assert wire.sent[-1] == "set 12 -6 0 0"
    # Spinning up keeps the aim.
    send(bridge, controller, "wheels 800")
    assert wire.sent[-1] == "set 12 -6 800 800"
    # Re-aiming keeps the wheels, when the caller passes the commanded RPM.
    send(bridge, controller, "aim 20 -6 800")
    assert wire.sent[-1] == "set 20 -6 800 800"
    assert controller.state.wheel_rpm == 800


def test_a_fire_whose_write_fails_does_not_stay_armed(bridge):
    """Otherwise the operator sees a refusal and a live arm, and the next click
    fires a shot they believe was cancelled."""
    controller, wire, _, clock = make(bridge, wire=Wire(fail_on="shoot"))
    arm_and_aim(bridge, controller, clock)
    assert controller.state.armed
    with pytest.raises(OSError):
        send(bridge, controller, "fire")
    assert not controller.state.armed
    assert wire.sent[-1] == "shoot"


# --------------------------- confirmed-shot evidence ------------------------

def test_shoot_is_only_a_request_until_the_front_limit_ack(
        bridge, fitter, tmp_path):
    """The defect this whole slice exists for: `shot_fired` used to mean
    "the command reached the serial writer", and a landing distance could
    attach to a shot the firmware had silently refused."""
    controller, wire, _, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")

    assert wire.sent[-1] == "shoot"
    assert controller.state.fire_request is not None
    assert controller.state.shots_fired == 0
    assert controller.state.pending_shot is None
    with pytest.raises(bridge.CommandError, match="confirmed shot"):
        send(bridge, controller, "measure 3.94")

    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in records] == ["shot_requested"]

    confirm_shot(controller)
    assert controller.state.fire_request is None
    assert controller.state.shots_fired == 1
    assert controller.state.pending_shot is not None
    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in records] == [
        "shot_requested", "shot_fired"]


def test_confirmed_evidence_names_the_last_pre_fire_sample_and_its_age(
        bridge, fitter, tmp_path):
    """A measured RPM in a shot record CANNOT be contemporaneous with the shot:
    the firmware gates telemetry on STATE_IDLE and is in STATE_SHOOTING for the
    whole acknowledgement window. So the field says what it is — the last
    confirmed pre-fire sample — and carries its age rather than inviting the
    reader to assume it was measured as the ball left."""
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    ready_to_arm(bridge, controller, clock, rpm=500)
    clock.advance(0.4)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    confirm_shot(controller)

    rows = [json.loads(line) for line in
            (tmp_path / "shots.jsonl").read_text().splitlines()]
    for row in rows:
        assert row["schema"] == "project_cam.blm_shot_evidence.v2"
        assert row["rpm_left_pre_fire"] == 500.0
        assert row["rpm_right_pre_fire"] == 500.0
        assert row["rpm_pre_fire_sample_age_s"] == pytest.approx(0.4)
        assert "rpm_left_measured" not in row
        assert "rpm_right_measured" not in row
    assert rows[0]["request_seq"] == rows[1]["request_seq"] == 1


def test_duplicate_front_limit_ack_is_idempotent(bridge, fitter, tmp_path):
    """One ball, one record — however many times the line arrives.

    And a repeat must be recognised AS a repeat: falling through to the
    unexplained-acknowledgement path would report physical motion the console
    cannot account for, which is a much louder thing to say than "that line
    arrived twice".
    """
    controller, _, logs, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    # Pinned so this cannot pass against the pre-ACK implementation, where the
    # count was already 1 here and the acknowledgement did nothing at all.
    assert controller.state.shots_fired == 0
    confirm_shot(controller)
    assert not controller.note_serial_line(SHOT_ACK), (
        "a repeat is not news; echoing it would read as a second shot")
    assert controller.state.shots_fired == 1
    rows = [json.loads(line) for line in
            (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows].count("shot_fired") == 1
    assert not any("no matching request" in line for line in logs)


def test_only_the_exact_front_limit_line_confirms_a_shot(
        bridge, fitter, tmp_path):
    """Evidence of physical travel is a single exact line. A substring or prefix
    match would let an echo, a truncated read, or a future firmware message
    manufacture a shot that never happened."""
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    for near_miss in (
        SHOT_ACK + " (retry)",
        "echo: " + SHOT_ACK,
        "SYS: SHOT FIRED",
        "SYS: RETRACTED - DISPENSING BALL",
        "SYS: RELOAD DONE - TIMEOUT",
    ):
        controller.note_serial_line(near_miss)
    assert controller.state.shots_fired == 0
    assert controller.state.pending_shot is None
    assert controller.state.fire_request is not None, (
        "the request must still be outstanding, not resolved by a near miss")


def test_outstanding_request_refuses_every_competing_command(bridge):
    """While the outcome of a physical shot is unknown, nothing may change it.
    STOP and shutdown stay available; `info` is refused because the current
    firmware spends 200 ms inside four delay(50) calls, during which the
    cooperative stepper state machine does not run."""
    controller, wire, _, clock = make(bridge)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    for command in (
        "aim 0 0 500", "wheels 0", "reload", "center", "set_zero",
        "info", "measure 3.0", "undo", "arm", "fire",
    ):
        with pytest.raises(bridge.CommandError, match="awaiting firmware"):
            send(bridge, controller, command)
    assert wire.sent[-1] == "shoot"


def test_missing_ack_times_out_to_latched_stop_without_a_shot(
        bridge, fitter, tmp_path):
    """The firmware has NO refusal message: below 400 RPM `STATE_SHOOTING` holds
    the pusher and says nothing at all. So a missing acknowledgement is the only
    detector of a blocked shot, and it must end the session rather than leave a
    console that looks ready."""
    controller, wire, logs, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path, shot_ack_timeout_s=5.0)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    clock.advance(5.0)
    controller.refresh_safety()

    assert controller.state.estop_latched
    # The request is KEPT, not discarded: a late acknowledgement must still be
    # recognisable rather than arriving as an unexplained one.
    assert controller.state.fire_request is not None
    assert controller.state.fire_request.timed_out
    assert controller.state.shots_fired == 0
    assert controller.state.pending_shot is None
    assert wire.sent[-1] == "stop"
    assert any("below 400 RPM" in line and "outcome unknown" in line
               for line in logs)
    rows = [json.loads(line) for line in
            (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows] == [
        "shot_requested", "shot_confirmation_timeout"]


def test_timeout_latches_even_when_the_stop_write_fails(bridge, fitter, tmp_path):
    """Same asymmetry the supervisor keeps for a failed stop: a stop whose
    transmission failed must never leave the console looking live.

    What this pins is that the latch does not DEPEND on the write succeeding —
    not the order of two statements. The bridge gets there two ways (latching
    first, and guarding the write), and either alone would satisfy the property;
    removing both is what this catches, including the exception then escaping
    the heartbeat and killing the thread that resolves every later shot.
    """
    wire = Wire(fail_on="stop")
    controller, _, _, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path, wire=wire,
        shot_ack_timeout_s=5.0)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    clock.advance(5.0)
    controller.refresh_safety()
    assert controller.state.estop_latched
    assert controller.state.fire_request.timed_out
    assert controller.state.shots_fired == 0


def test_orphan_front_limit_ack_latches_and_stops(bridge, fitter, tmp_path):
    """Physical travel the console cannot explain. Whatever else is true, the
    evidence state is no longer trustworthy, so the session ends."""
    controller, wire, _, _ = make(bridge, fitter=fitter, tmp_path=tmp_path)
    controller.note_serial_line(SHOT_ACK)
    assert controller.state.estop_latched
    assert wire.sent == ["stop"]
    rows = [json.loads(line) for line in
            (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows] == ["orphan_shot_ack"]


def test_clear_cannot_recover_an_unknown_shot_outcome(bridge, fitter, tmp_path):
    """CLEAR releases an ESTOP the operator caused. It must not release one that
    stands for "a ball may or may not be on the floor" — that needs the chamber
    inspected after confirmed spin-down, i.e. a new session."""
    controller, _, _, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path, shot_ack_timeout_s=5.0)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    clock.advance(5.0)
    controller.refresh_safety()
    with pytest.raises(bridge.CommandError, match="outcome is unresolved"):
        send(bridge, controller, "clear")


# ---------------------------------- ESTOP latch -----------------------------

def test_stop_latches_and_only_clear_releases_it(bridge):
    controller, wire, _, clock = make(bridge)
    arm_and_aim(bridge, controller, clock)
    send(bridge, controller, "stop")
    assert controller.state.estop_latched
    assert not controller.state.armed
    assert wire.sent[-1] == "stop"

    for line in ["aim 0 0 800", "wheels 800", "reload", "center", "fire"]:
        with pytest.raises(bridge.CommandError, match="ESTOP latched"):
            send(bridge, controller, line)
    with pytest.raises(bridge.CommandError, match="ESTOP latched"):
        send(bridge, controller, "arm")
    # info is diagnostic, not actuation, so it stays available while latched.
    send(bridge, controller, "info")
    assert wire.sent[-1] == "info"

    send(bridge, controller, "clear")
    assert not controller.state.estop_latched
    send(bridge, controller, "aim 0 0 800")
    assert wire.sent[-1] == "set 0 0 800 800"


def test_stop_latches_even_when_the_serial_write_fails(bridge):
    """A stop that failed to transmit must never leave the console looking live —
    the same asymmetry the desktop supervisor keeps for a failed stop."""
    controller, _, _, clock = make(bridge, wire=Wire(fail=True))
    with pytest.raises(OSError):
        send(bridge, controller, "stop")
    assert controller.state.estop_latched
    assert not controller.state.armed
    assert controller.state.wheel_rpm == 0.0


# ------------------------------ calibration bookkeeping ---------------------

def fire_at(bridge, controller, clock, rpm=500):
    """One complete PHYSICAL shot, exactly as the protocol requires it: reload,
    aim, spin up, confirm the MEASURED wheels, arm, fire — and then the
    firmware's own front-limit report, which is the only thing that makes it a
    shot rather than a request. A test that stops at `fire` now gets no
    measurable shot at all, exactly like the machine."""
    ready_to_arm(bridge, controller, clock, rpm=rpm)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    confirm_shot(controller)


def test_a_measurement_carries_the_rpm_THAT_WAS_FIRED_not_the_current_command(
        bridge, fitter, tmp_path):
    """The defect this contract exists to prevent (found 2026-08-07).

    The protocol forbids anyone walking downrange until the wheels are commanded
    to zero and read below 50 RPM, so the commanded RPM is ALWAYS 0 by the time a
    landing distance can exist. A measurement that took its RPM from the current
    command therefore recorded `rpm: 0` for every shot in the pass, and Task 5
    requires `rpm = 500`. The RPM has to come from the shot.
    """
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    fire_at(bridge, controller, clock, rpm=500)
    # The mandatory safety step between firing and measuring.
    send(bridge, controller, "wheels 0")
    assert controller.state.wheel_rpm == 0.0

    send(bridge, controller, "measure 3.94")

    recorded = controller.state.measurements[-1]
    assert recorded.rpm == 500, "the fired RPM, not the stopped-wheel command"
    assert recorded.distance_m == 3.94
    assert recorded.shot_seq == 1

    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    measurement = [r for r in records if r["event"] == "measurement"][-1]
    assert measurement["rpm"] == 500
    assert measurement["shot_seq"] == 1


def test_a_distance_with_no_shot_behind_it_is_refused(bridge, fitter, tmp_path):
    """A distance is a measurement OF a shot. Without one there is nothing to
    measure, and accepting it would let a typo become evidence."""
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    with pytest.raises(bridge.CommandError, match="no confirmed shot is waiting"):
        send(bridge, controller, "measure 3.94")
    assert controller.state.measurements == []

    # And it is refused again once the pending shot has been consumed.
    fire_at(bridge, controller, clock, rpm=500)
    send(bridge, controller, "measure 3.94")
    with pytest.raises(bridge.CommandError, match="no confirmed shot is waiting"):
        send(bridge, controller, "measure 4.10")
    assert len(controller.state.measurements) == 1


def test_the_vocabulary_offers_no_way_to_supply_an_rpm_with_a_distance(bridge):
    """An optional rpm override would be the one route by which a wrong value
    could enter the evidence — which is the defect being fixed."""
    for line in ["measure 500 3.94", "measure 3.94 500", "measure"]:
        with pytest.raises(bridge.CommandError):
            bridge.parse_command(line)
    assert bridge.parse_command("measure 3.94").args == (3.94,)


def test_an_unmeasured_confirmed_shot_blocks_the_next_one(
        bridge, fitter, tmp_path):
    """Two balls on the floor and no way to tell them apart.

    This used to be permitted with a warning, and the first shot stayed in the
    log as fired-and-unmeasured. A warning is not enough: the operator has
    already walked out and picked up a ball by then, and only one of the two
    shots can honestly receive that distance. Refusing keeps every physical ball
    with exactly one place to attach its measurement.
    """
    controller, wire, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    fire_at(bridge, controller, clock, rpm=500)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    spin_up(controller, clock, 500)
    send(bridge, controller, "arm")
    with pytest.raises(bridge.CommandError, match="record the confirmed shot"):
        send(bridge, controller, "fire")
    assert wire.sent.count("shoot") == 1

    send(bridge, controller, "measure 3.94")
    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [r["event"] for r in records] == [
        "shot_requested", "shot_fired", "measurement"]
    assert [r["shot_seq"] for r in records[1:]] == [1, 1]
    assert records[-1]["landing_distance_m"] == 3.94


def test_a_failed_write_leaves_no_shot_to_measure(bridge, fitter, tmp_path):
    """Fail-closed: if the `shoot` command never reached the firmware, no ball
    left the barrel and there is nothing a distance may attach to."""
    controller, _, _, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path, wire=Wire(fail_on="shoot"))
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    with pytest.raises(OSError):
        send(bridge, controller, "fire")
    assert controller.state.pending_shot is None
    # Nor may it burn a sequence number that will never appear in the log, or
    # consume the loaded ball that is demonstrably still in the chamber.
    assert controller.state.shots_fired == 0
    assert controller.state.loaded
    with pytest.raises(bridge.CommandError, match="no confirmed shot is waiting"):
        send(bridge, controller, "measure 3.94")


def test_undo_returns_the_shot_to_awaiting_rather_than_discarding_it(
        bridge, fitter, tmp_path):
    """A mistyped distance must cost a re-entry, never a re-shoot: the shot
    happened, so it goes back to waiting with its own RPM intact."""
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    fire_at(bridge, controller, clock, rpm=500)
    send(bridge, controller, "wheels 0")
    send(bridge, controller, "measure 39.4")   # a slipped decimal point
    send(bridge, controller, "undo")

    assert controller.state.measurements == []
    assert controller.state.pending_shot is not None
    assert controller.state.pending_shot.rpm == 500
    assert controller.state.pending_shot.seq == 1

    send(bridge, controller, "measure 3.94")
    assert controller.state.measurements[-1].rpm == 500
    assert controller.state.measurements[-1].distance_m == 3.94
    assert controller.state.measurements[-1].shot_seq == 1


def test_undo_refuses_to_overwrite_a_newer_pending_shot(
        bridge, fitter, tmp_path):
    """UNDO puts a retracted measurement's shot back to awaiting-distance. If a
    NEWER confirmed shot is already waiting there, doing so would silently
    replace it — and the ball on the floor belongs to the newer one, so the next
    distance typed would land on the older shot's record."""
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    fire_at(bridge, controller, clock, rpm=500)
    send(bridge, controller, "measure 3.0")
    fire_at(bridge, controller, clock, rpm=650)

    with pytest.raises(bridge.CommandError, match="newer confirmed shot"):
        send(bridge, controller, "undo")
    assert controller.state.pending_shot.rpm == 650
    assert [m.rpm for m in controller.state.measurements] == [500]


def test_a_written_model_always_carries_its_sample_count_and_residual(
        bridge, fitter, tmp_path):
    controller, _, logs, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    for distance in (3.94, 3.88, 3.99):
        fire_at(bridge, controller, clock, rpm=800)
        send(bridge, controller, f"measure {distance}")
    send(bridge, controller, "fit 0.52")

    model = json.loads((tmp_path / "model.json").read_text())
    assert model["model"] == "constant_mps"
    assert model["n_shots"] == 3
    assert "fit_rmse_mps" in model
    assert model["v_mps"] == pytest.approx(
        sum(fitter.speed_from_drop(d, 0.52, 9.81) for d in (3.94, 3.88, 3.99)) / 3
    )
    assert controller.state.model_summary
    assert any("model written" in line for line in logs)


def test_a_fit_without_measurements_is_refused(bridge, fitter, tmp_path):
    controller, _, _, _ = make(bridge, fitter=fitter, tmp_path=tmp_path)
    with pytest.raises(bridge.CommandError, match="no measurements"):
        send(bridge, controller, "fit 0.52")
    assert not (tmp_path / "model.json").exists()


def test_a_large_residual_is_called_out_rather_than_shipped_quietly(
        bridge, fitter, tmp_path):
    controller, _, logs, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    # Wildly inconsistent shots at one RPM: the spread IS the finding.
    for distance in (2.0, 4.0, 6.0):
        fire_at(bridge, controller, clock, rpm=800)
        send(bridge, controller, f"measure {distance}")
    send(bridge, controller, "fit 0.52")
    model = json.loads((tmp_path / "model.json").read_text())
    assert model["fit_rmse_mps"] > 1.0
    assert any("residual exceeds" in line for line in logs)


def test_the_shot_log_records_retractions_instead_of_rewriting_history(
        bridge, fitter, tmp_path):
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    fire_at(bridge, controller, clock, rpm=800)
    send(bridge, controller, "measure 3.94")
    fire_at(bridge, controller, clock, rpm=800)
    send(bridge, controller, "measure 9.99")
    send(bridge, controller, "undo")
    assert [m.distance_m for m in controller.state.measurements] == [3.94]

    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [r["event"] for r in records] == [
        "shot_requested", "shot_fired", "measurement",
        "shot_requested", "shot_fired", "measurement", "retracted_measurement"]
    assert all(r["method"] == "A_landing_distance" for r in records)
    assert records[-1]["landing_distance_m"] == 9.99


def test_an_unwritable_shot_log_warns_but_does_not_end_the_session(
        bridge, fitter, tmp_path):
    """A calibration session is expensive to set up; losing it to a log path
    would be worse than continuing loudly without the file."""
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("occupied")
    clock = Clock()
    controller = bridge.BlmController(
        Wire(), lambda message: logs.append(message), allow_fire=True, now=clock,
        shot_log=blocked / "shots.jsonl", model_out=tmp_path / "m.json",
        fitter=fitter)
    logs: list[str] = []
    fire_at(bridge, controller, clock, rpm=800)
    send(bridge, controller, "measure 3.94")
    assert [m.distance_m for m in controller.state.measurements] == [3.94]
    assert any("could not append" in line for line in logs)


# --------------------------------- serial reading ---------------------------


@pytest.mark.parametrize(("line", "firmware_id"), [
    ("SYS: FW control_13 READY", "control_13"),
    ("INFO | FW: control_13", "control_13"),
])
def test_firmware_identity_is_parsed_from_boot_and_info(
        bridge, line, firmware_id):
    """The panel reports what the connected firmware said, never the filename
    the host happened to launch beside it."""
    controller, _, _, _ = make(bridge, allow_fire=False)

    assert controller.note_serial_line(line)
    assert controller.state.firmware_id == firmware_id
    assert controller.status()["firmware_id"] == firmware_id


def test_unrecognised_text_cannot_claim_the_control_13_identity(bridge):
    """Only the two exact control_13 identity records are evidence. A filename,
    a custom label, or a different firmware generation cannot make the UI claim
    the USB-telemetry firmware is connected."""
    controller, _, _, _ = make(bridge, allow_fire=False)

    for line in (
        "control_13",
        "INFO | FW: custom",
        "SYS: FW control_12 READY",
        "prefix SYS: FW control_13 READY",
    ):
        controller.note_serial_line(line)

    assert controller.state.firmware_id == ""
    assert controller.status()["firmware_id"] == ""


def test_the_recorded_control_12_info_rpm_line_is_telemetry(bridge):
    """The exact lines the stand produced on 2026-08-11. The firmware answered
    with real numbers and the panel showed `— / —`, because the parser accepted
    only the compact `L:<n> R:<n>` stream — which `control_12` emits solely to a
    connected BLE client, never over USB."""
    assert bridge.parse_telemetry("INFO | RPM: L=22/0, R=8/0") == (22.0, 8.0)
    assert bridge.parse_telemetry(
        "INFO | RPM: L=500/500, R=493/500") == (500.0, 493.0)

    # A measured RPM is the input to `safe_to_approach` — the decision to walk in
    # front of the barrel — so it may only come from a line whose WHOLE shape the
    # console recognises. An echo or a quoted fragment is not a measurement.
    for not_a_reading in (
        ">>> INFO | RPM: L=500/500, R=500/500",
        "echo INFO | RPM: L=500/500, R=500/500",
        "INFO | RPM: L=500/500, R=500/500 (stale)",
        "INFO | RPM: L=500, R=500",
    ):
        assert bridge.parse_telemetry(not_a_reading) is None, not_a_reading


@pytest.mark.parametrize(("line", "present"), [
    ("INFO | LMT: Front=HIGH, Back=LOW, Ball=HIGH", False),
    ("INFO | LMT: Front=HIGH, Back=LOW, Ball=LOW", True),
    ("Front:1 Back:0 Ball:1", False),
    ("Front:1 Back:0 Ball:0", True),
])
def test_ball_parser_accepts_control_12_levels_and_legacy_digits(
        bridge, line, present):
    """`control_12` prints words, not digits — which is why the panel said NOT
    POLLED while the firmware was reporting `Ball=HIGH`. LOW stays the present
    level: the switches are INPUT_PULLUP and trigger on LOW, so this is the same
    inferred polarity as before, written in the other notation."""
    assert bridge.parse_ball_state(line) is present


def test_info_rpm_updates_telemetry_and_stays_in_the_poll_block(bridge):
    controller, _, _, _ = make(bridge, allow_fire=False)
    echoed = bridge.consume_serial_line(
        controller, "INFO | RPM: L=22/0, R=8/0")
    assert echoed
    assert (controller.state.rpm_left, controller.state.rpm_right) == (22.0, 8.0)
    assert controller.state.info_lines[-1] == "INFO | RPM: L=22/0, R=8/0"


def test_compact_telemetry_updates_state_without_flooding_the_log(bridge):
    """A solicited poll is evidence the operator asked for and must stay
    visible; the 4 Hz stream is not, and would bury everything else."""
    controller, _, _, _ = make(bridge, allow_fire=False)
    echoed = bridge.consume_serial_line(controller, "L:22 R:8")
    assert not echoed
    assert (controller.state.rpm_left, controller.state.rpm_right) == (22.0, 8.0)
    assert controller.state.info_lines == []


def test_boot_noise_is_filtered_and_telemetry_is_parsed_not_logged(bridge):
    for noise in ["ets Jun  8 2016 00:22:57", "rst:0x1 (POWERON_RESET)",
                  "configsip: 0, SPIWP:0xee", "load:0x3fff0030,len:1184",
                  "entry 0x400805f0", "M" * 40]:
        assert bridge.is_noise(noise), noise
    for real in ["IDLE", "Front:1 Back:0 Ball:1", "OK", "L:0 R:0 extra"]:
        assert not bridge.is_noise(real), real

    assert bridge.parse_telemetry("L:812 R:798") == (812.0, 798.0)
    assert bridge.parse_telemetry("L:0 R:0") == (0.0, 0.0)
    for not_telemetry in ["IDLE", "L:812", "R:798", "Limit L:1", ""]:
        assert bridge.parse_telemetry(not_telemetry) is None


def test_an_identical_repeat_poll_is_still_visible(bridge):
    """The protocol asks for three polls spanning two seconds to prove the machine
    is stable — and a stable machine answers with IDENTICAL text, which the
    consecutive-line dedup then swallowed. The more stable the rig, the less
    visible the confirmation: exactly backwards.
    """
    controller, wire, _, clock = make(bridge)
    reply = "IDLE Ang: V=0.0 H=0.0 Front:1 Back:1 Ball:1"

    send(bridge, controller, "info")
    assert controller.note_serial_line(reply) is True
    # Repeated spam inside ONE block is still collapsed.
    assert controller.note_serial_line(reply) is False

    clock.advance(2.0)
    send(bridge, controller, "info")
    assert controller.state.info_lines == [], "each poll starts its own block"
    assert controller.note_serial_line(reply) is True, (
        "a solicited reply must never be the thing that gets deduplicated away")
    assert controller.status()["info_lines"] == [reply]

    clock.advance(2.0)
    send(bridge, controller, "info")
    assert controller.note_serial_line(reply) is True


def test_a_poll_carries_its_own_age(bridge):
    """A dead link otherwise shows the last reply forever, and three polls that all
    read the same are indistinguishable from one poll and two silences."""
    controller, _, _, clock = make(bridge)
    assert controller.status()["info_age_s"] is None

    send(bridge, controller, "info")
    assert controller.status()["info_age_s"] is None, "no reply has arrived yet"
    controller.note_serial_line("IDLE")
    assert controller.status()["info_age_s"] == 0.0
    clock.advance(3.0)
    assert controller.status()["info_age_s"] == 3.0

    send(bridge, controller, "info")
    assert controller.status()["info_age_s"] is None, (
        "a new poll must not inherit the previous reply's age")


def test_the_ball_switch_is_parsed_and_warns_but_never_gates(bridge):
    """The protocol asked the operator to read `Ball=LOW` out of raw serial text
    the console already had. The switches are INPUT_PULLUP and trigger on LOW, so
    `Ball:0` is a detected ball — INFERRED from the wiring, which is why it informs
    and warns rather than refusing: an inverted reading would block every shot with
    a ball loaded.
    """
    assert bridge.parse_ball_state("Front:1 Back:0 Ball:0") is True
    assert bridge.parse_ball_state("Front:1 Back:0 Ball:1") is False
    assert bridge.parse_ball_state("Ball = 0") is True
    for silent in ["IDLE", "Front:1 Back:0", "Ballistics:1", ""]:
        assert bridge.parse_ball_state(silent) is None, silent

    # The reading now arrives in the notation `control_12` actually prints, and
    # neither notation may become a gate.
    for line, present in (
        ("INFO | LMT: Front=HIGH, Back=LOW, Ball=HIGH", False),
        ("INFO | LMT: Front=HIGH, Back=LOW, Ball=LOW", True),
    ):
        controller, _, logs, clock = make(bridge)
        send(bridge, controller, "reload")
        # The firmware's DISPENSING state also exits on a 10 s TIMEOUT with an
        # empty chamber, and this warning is the only visible sign of it.
        controller.note_serial_line(line)
        assert controller.state.ball_present is present, line
        assert any("reports no ball" in entry for entry in logs) is not present

        # ...and it does not refuse the shot either way, because the polarity is
        # inferred from the wiring rather than measured on the stand.
        send(bridge, controller, "aim 0 0 500")
        spin_up(controller, clock, 500)
        send(bridge, controller, "arm")
        assert controller.state.armed, line


def test_a_shot_records_the_measured_rpm_beside_the_commanded_one(
        bridge, fitter, tmp_path):
    """The model stays indexed by the COMMANDED RPM — that is the only value a
    launcher can be told to reproduce — but a v(RPM) curve whose independent
    variable was never checked against the machine is not auditable."""
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    # Inside the band, so the shot is allowed, but not exactly the commanded value.
    spin_up(controller, clock, 470, spread=40.0)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    confirm_shot(controller)

    pending = controller.state.pending_shot
    assert pending.rpm == 500, "the commanded value indexes the model"
    assert (pending.rpm_left_pre_fire, pending.rpm_right_pre_fire) == (470.0, 510.0)

    send(bridge, controller, "wheels 0")
    send(bridge, controller, "measure 3.94")
    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    for record in records:
        assert record["rpm"] == 500
        assert record["rpm_left_pre_fire"] == 470.0
        assert record["rpm_right_pre_fire"] == 510.0
        # The name has to keep saying `pre_fire`: the firmware gates telemetry on
        # STATE_IDLE, so nothing measured DURING the shot can ever appear here.
        assert "rpm_left_measured" not in record


# ------------------------------------ status ---------------------------------

def test_status_reports_every_field_the_ui_gates_on(bridge, fitter, tmp_path):
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    required = {
        "schema", "port", "connected", "allow_fire", "estop_latched", "armed",
        "arm_remaining_s", "arm_timeout_s", "pitch_deg", "yaw_deg", "wheel_rpm",
        "rpm_left", "rpm_right", "rpm_min_fire", "angle_limit_deg",
        "pitch_min_deg", "pitch_max_deg", "pitch_default_min_deg",
        "pitch_default_max_deg", "yaw_limit_deg",
        "shots_fired", "pending_shot", "last_refusal", "info_lines",
        "measurements", "model_path", "model_summary",
        # The measured-wheel layer. Every one of these gates something, and the
        # UI must read the verdict rather than recomputing the rule.
        "aim_established", "telemetry_age_s", "telemetry_max_age_s",
        "wheels_confirmed", "wheels_unconfirmed_reason", "wheels_in_band_s",
        "wheels_band_rpm", "wheels_stable_required_s", "rpm_spread_max",
        "safe_to_approach", "rpm_safe_approach", "loaded", "ball_present",
        "info_age_s",
    }
    assert required <= set(controller.status())

    # A fresh console claims nothing it has not seen.
    fresh = controller.status()
    assert fresh["telemetry_age_s"] is None
    assert fresh["wheels_confirmed"] is False
    assert fresh["safe_to_approach"] is False
    assert fresh["loaded"] is False
    assert fresh["ball_present"] is None
    assert fresh["aim_established"] is False

    arm_and_aim(bridge, controller, clock)
    armed = controller.status()
    assert armed["armed"] is True
    assert armed["arm_remaining_s"] == pytest.approx(30.0)
    assert armed["wheel_rpm"] == 800
    assert armed["schema"] == "project_cam.blm_console.v1"
    assert armed["wheels_confirmed"] is True
    assert armed["wheels_unconfirmed_reason"] == ""
    assert armed["wheels_in_band_s"] >= armed["wheels_stable_required_s"]
    assert armed["telemetry_age_s"] == 0.0
    assert armed["loaded"] is True

    # A refusal is carried in the status, so the UI can show WHY, and the status
    # must be JSON-serialisable because that is how it reaches the app.
    with pytest.raises(bridge.CommandError):
        send(bridge, controller, "measure 0")
    json.dumps(controller.status())

    clock.advance(31.0)
    controller.expire_arm()
    assert controller.status()["armed"] is False
