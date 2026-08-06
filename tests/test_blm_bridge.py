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
         tmp_path=None, arm_timeout_s=30.0, pitch_min_deg=None,
         pitch_max_deg=None):
    clock = clock or Clock()
    wire = wire or Wire()
    logs: list[str] = []
    controller = bridge.BlmController(
        wire,
        logs.append,
        allow_fire=allow_fire,
        now=clock,
        arm_timeout_s=arm_timeout_s,
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


def arm_and_aim(bridge, controller, rpm=800):
    send(bridge, controller, f"aim 0 0 {rpm}")
    send(bridge, controller, "arm")


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
    controller, wire, _, _ = make(bridge, fitter=fitter, tmp_path=tmp_path)
    for line in ["limits -20 30", "aim 12 -7 800", "wheels 500", "info", "center", "set_zero",
                 "reload", "aim 0 0 800", "arm", "fire", "measure 800 3.94",
                 "undo", "measure 800 3.9", "fit 0.52", "stop", "clear"]:
        send(bridge, controller, line)
    assert wire.sent, "nothing was sent at all"
    for command in wire.sent:
        assert FIRMWARE_COMMAND.match(command), f"unexpected serial write {command!r}"


def test_arguments_must_be_finite_numbers_in_range(bridge):
    for bad in ["aim x 0 800", "aim 0 0 nan", "aim 0 0 inf", "wheels -1",
                "wheels 1201", "aim 0 0 1300", "measure 800 0",
                "measure 800 61", "fit 0", "fit 6", "fit 0.5 cubic",
                "aim 0 0", "wheels", "fit"]:
        with pytest.raises(bridge.CommandError):
            bridge.parse_command(bad)
    # The operating envelope itself must remain expressible.
    for good in ["aim 30 -30 1200", "aim -30 30 0", "wheels 400",
                 "measure 500 2.4", "fit 0.52 interp", "fit 0.52"]:
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
    controller, wire, logs, _ = make(bridge)
    send(bridge, controller, "aim 20 -10 800")
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
    controller, wire, logs, _ = make(bridge)
    send(bridge, controller, "limits -30 30")
    send(bridge, controller, "aim -20 0 800")
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
    controller, wire, _, _ = make(bridge)
    # No aim yet.
    with pytest.raises(bridge.CommandError, match="aim before arming"):
        send(bridge, controller, "arm")
    # Aim, but the wheels are below the firmware's own 400 RPM gate.
    send(bridge, controller, "aim 0 0 300")
    with pytest.raises(bridge.CommandError, match="400 RPM"):
        send(bridge, controller, "arm")
    # Unarmed fire is refused even with everything else satisfied.
    send(bridge, controller, "aim 0 0 800")
    with pytest.raises(bridge.CommandError, match="not armed"):
        send(bridge, controller, "fire")
    assert "shoot" not in wire.sent

    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    assert wire.sent[-1] == "shoot"
    assert controller.state.shots_fired == 1


def test_one_shot_consumes_the_arm(bridge):
    """The garage firing policy: every shot is a deliberate, separate act. An arm
    that survived its shot would make a second click a second ball."""
    controller, wire, _, _ = make(bridge)
    arm_and_aim(bridge, controller)
    send(bridge, controller, "fire")
    assert not controller.state.armed
    with pytest.raises(bridge.CommandError, match="not armed"):
        send(bridge, controller, "fire")
    assert wire.sent.count("shoot") == 1


def test_the_arm_expires_on_its_own(bridge):
    controller, wire, logs, clock = make(bridge, arm_timeout_s=30.0)
    arm_and_aim(bridge, controller)
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
    controller, wire, _, _ = make(bridge)
    arm_and_aim(bridge, controller)
    send(bridge, controller, "aim 10 0 800")
    assert not controller.state.armed
    with pytest.raises(bridge.CommandError, match="not armed"):
        send(bridge, controller, "fire")

    arm_and_aim(bridge, controller)
    send(bridge, controller, "wheels 200")
    assert not controller.state.armed
    assert "shoot" not in wire.sent


def test_centering_resets_the_stored_aim_and_clears_the_arm(bridge):
    """The firmware takes ONE combined `set v h wl wr`, so the bridge's stored
    angles are re-sent by the next wheels command. Found live: `center` left the
    old angles in place, so asking only for flywheel RPM afterwards would have
    driven the barrel back up to where it had been before centering.
    """
    controller, wire, _, _ = make(bridge)
    send(bridge, controller, "aim 25 -10 800")
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
    controller, wire, _, _ = make(bridge)
    send(bridge, controller, "aim 12 -6 800")
    send(bridge, controller, "arm")

    send(bridge, controller, "reload")

    assert wire.sent[-1] == "reload"
    assert controller.state.pitch_deg == 0.0
    assert controller.state.yaw_deg == 0.0
    assert controller.state.wheel_rpm == 0.0
    assert not controller.state.armed

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
    controller, wire, _, _ = make(bridge, wire=Wire(fail_on="shoot"))
    arm_and_aim(bridge, controller)
    assert controller.state.armed
    with pytest.raises(OSError):
        send(bridge, controller, "fire")
    assert not controller.state.armed
    assert wire.sent[-1] == "shoot"


# ---------------------------------- ESTOP latch -----------------------------

def test_stop_latches_and_only_clear_releases_it(bridge):
    controller, wire, _, _ = make(bridge)
    arm_and_aim(bridge, controller)
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
    controller, _, _, _ = make(bridge, wire=Wire(fail=True))
    with pytest.raises(OSError):
        send(bridge, controller, "stop")
    assert controller.state.estop_latched
    assert not controller.state.armed
    assert controller.state.wheel_rpm == 0.0


# ------------------------------ calibration bookkeeping ---------------------

def test_a_written_model_always_carries_its_sample_count_and_residual(
        bridge, fitter, tmp_path):
    controller, _, logs, _ = make(bridge, fitter=fitter, tmp_path=tmp_path)
    for distance in (3.94, 3.88, 3.99):
        send(bridge, controller, f"measure 800 {distance}")
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
    controller, _, logs, _ = make(bridge, fitter=fitter, tmp_path=tmp_path)
    # Wildly inconsistent shots at one RPM: the spread IS the finding.
    for distance in (2.0, 4.0, 6.0):
        send(bridge, controller, f"measure 800 {distance}")
    send(bridge, controller, "fit 0.52")
    model = json.loads((tmp_path / "model.json").read_text())
    assert model["fit_rmse_mps"] > 1.0
    assert any("residual exceeds" in line for line in logs)


def test_the_shot_log_records_retractions_instead_of_rewriting_history(
        bridge, fitter, tmp_path):
    controller, _, _, _ = make(bridge, fitter=fitter, tmp_path=tmp_path)
    send(bridge, controller, "measure 800 3.94")
    send(bridge, controller, "measure 800 9.99")
    send(bridge, controller, "undo")
    assert [m.distance_m for m in controller.state.measurements] == [3.94]

    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [r["event"] for r in records] == [
        "measurement", "measurement", "retracted_measurement"]
    assert all(r["method"] == "A_landing_distance" for r in records)
    assert records[-1]["landing_distance_m"] == 9.99


def test_an_unwritable_shot_log_warns_but_does_not_end_the_session(
        bridge, fitter, tmp_path):
    """A calibration session is expensive to set up; losing it to a log path
    would be worse than continuing loudly without the file."""
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("occupied")
    controller = bridge.BlmController(
        Wire(), lambda message: logs.append(message), allow_fire=True,
        shot_log=blocked / "shots.jsonl", model_out=tmp_path / "m.json",
        fitter=fitter)
    logs: list[str] = []
    send(bridge, controller, "measure 800 3.94")
    assert [m.distance_m for m in controller.state.measurements] == [3.94]
    assert any("could not append" in line for line in logs)


# --------------------------------- serial reading ---------------------------

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


# ------------------------------------ status ---------------------------------

def test_status_reports_every_field_the_ui_gates_on(bridge, fitter, tmp_path):
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    required = {
        "schema", "port", "connected", "allow_fire", "estop_latched", "armed",
        "arm_remaining_s", "arm_timeout_s", "pitch_deg", "yaw_deg", "wheel_rpm",
        "rpm_left", "rpm_right", "rpm_min_fire", "angle_limit_deg",
        "pitch_min_deg", "pitch_max_deg", "pitch_default_min_deg",
        "pitch_default_max_deg", "yaw_limit_deg",
        "shots_fired", "last_refusal", "info_lines", "measurements",
        "model_path", "model_summary",
    }
    assert required <= set(controller.status())

    arm_and_aim(bridge, controller)
    armed = controller.status()
    assert armed["armed"] is True
    assert armed["arm_remaining_s"] == pytest.approx(30.0)
    assert armed["wheel_rpm"] == 800
    assert armed["schema"] == "project_cam.blm_console.v1"

    # A refusal is carried in the status, so the UI can show WHY, and the status
    # must be JSON-serialisable because that is how it reaches the app.
    with pytest.raises(bridge.CommandError):
        send(bridge, controller, "measure 800 0")
    json.dumps(controller.status())

    clock.advance(31.0)
    controller.expire_arm()
    assert controller.status()["armed"] is False
