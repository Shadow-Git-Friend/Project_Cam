"""The desktop app may now hold the launcher's serial link — under what terms.

Before 2026-08-04 `project-cam-desktop/` was orchestration/view/capture only, and
a test asserted no profile could name a serial port at all. The BLM console
profile crosses that line deliberately, so these tests pin the terms of the
crossing:

  * exactly ONE profile opens serial, and exactly one gets a writable stdin
  * the frontend still cannot compose serial text OR the bridge's protocol text —
    it names a typed intent and Rust renders the line
  * the three layers agree on the vocabulary and on the limits, so a rename or a
    changed bound cannot silently pass through one of them
  * the view-only guarantees of TRAINING are untouched

The gate BEHAVIOUR lives in tests/test_blm_bridge.py; this file is about the
seams between TypeScript, Rust and Python.
"""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "project-cam-desktop"
BLM_RS = DESKTOP / "src-tauri/src/blm.rs"
MAIN_RS = DESKTOP / "src-tauri/src/main.rs"
PROFILES_RS = DESKTOP / "src-tauri/src/launch_profiles.rs"
BLM_TS = DESKTOP / "src/blm.ts"
LAUNCH_TS = DESKTOP / "src/launch.ts"
APP_TS = DESKTOP / "src/App.tsx"
LAUNCHER_VIEW = DESKTOP / "src/views/LauncherView.tsx"
BRIDGE = ROOT / "garage_lab_combined/scripts/blm_bridge.py"
DRILL_WRAPPER = ROOT / "Parallel_working/run_training_drill.sh"
RPM_PROTOCOL = ROOT / "docs/protocols/2026-08-03-rpm-speed-measurement.md"


@pytest.fixture(scope="module")
def bridge():
    spec = importlib.util.spec_from_file_location("blm_bridge", BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def rust_console_variants() -> set:
    text = BLM_RS.read_text(encoding="utf-8")
    block = text[text.index("pub enum ConsoleCommand {"):]
    block = block[:block.index("\n}")]
    # Variant heads only: `Aim {`, `Reload {}`, ... never a field line.
    return {snake(name) for name in re.findall(r"^\s{4}([A-Z]\w*)\s*\{", block,
                                               re.MULTILINE)}


def ts_console_variants() -> set:
    text = BLM_TS.read_text(encoding="utf-8")
    block = text[text.index("export type ConsoleCommand ="):]
    # To the blank line that ends the declaration, NOT to the first `;` — the
    # first semicolon lives inside `{ command: "aim"; pitch_deg: number; ... }`,
    # which would silently reduce this contract to a single variant.
    block = block[:block.index("\n\n")]
    return set(re.findall(r'command:\s*"([a-z_]+)"', block))


def bridge_verbs(bridge) -> set:
    """Verbs the bridge's parser accepts, discovered by asking it."""
    candidates = rust_console_variants() | ts_console_variants() | {"quit"}
    accepted = set()
    samples = {
        "aim": "aim 0 0 800",
        "wheels": "wheels 800",
        "measure": "measure 3.9",
        "fit": "fit 0.52",
        "limits": "limits -20 30",
    }
    for verb in candidates:
        try:
            bridge.parse_command(samples.get(verb, verb))
        except bridge.CommandError:
            continue
        accepted.add(verb)
    return accepted


# ----------------------------- one vocabulary, three layers -----------------

def test_the_console_vocabulary_matches_across_typescript_rust_and_python(bridge):
    rust, ts = rust_console_variants(), ts_console_variants()
    assert rust, "no Rust console variants found — did the enum move?"
    assert rust == ts, (
        f"TypeScript/Rust console command drift: only in Rust {rust - ts}, "
        f"only in TS {ts - rust}")
    accepted = bridge_verbs(bridge)
    assert rust <= accepted, (
        f"Rust can render intents the bridge refuses: {rust - accepted}")
    # `setzero` is the raw firmware word and must exist only behind the bridge.
    # Rust speaks the typed bridge protocol (`set_zero`) like the frontend does.
    rust_source = BLM_RS.read_text(encoding="utf-8")
    assert 'Self::SetZero {} => "set_zero".into()' in rust_source


def test_the_bridge_accepts_nothing_the_ui_cannot_express(bridge):
    """`quit` is the one extra verb, and it exists for a human piping the bridge
    by hand. Anything else would be a channel the typed layers do not cover."""
    extra = bridge_verbs(bridge) - rust_console_variants()
    assert extra == {"quit"}, f"undeclared bridge verbs: {extra}"


def test_no_layer_can_attach_an_rpm_to_a_landing_distance(bridge):
    """Found 2026-08-07, before the first calibration pass.

    RECORD SHOT sent the RPM control's current value, and the protocol requires
    the wheels commanded to zero and read below 50 RPM before anyone may walk
    downrange to the ball — so every measurement in the pass would have been
    logged as `rpm: 0` while Task 5 requires 500. The RPM must come from the
    shot, captured when it was fired, and no layer may offer an alternative
    route: an optional override is exactly how a wrong value gets in.
    """
    rust = BLM_RS.read_text(encoding="utf-8")
    ts = BLM_TS.read_text(encoding="utf-8")

    measure_rs = rust[rust.index("Measure {"):]
    measure_rs = measure_rs[:measure_rs.index("}")]
    assert "rpm" not in measure_rs, f"Rust Measure regained an rpm: {measure_rs!r}"

    measure_ts = ts[ts.index('command: "measure"'):]
    measure_ts = measure_ts[:measure_ts.index("\n")]
    assert "rpm" not in measure_ts, f"TS measure regained an rpm: {measure_ts!r}"

    # Python refuses the two-argument form outright rather than ignoring the
    # extra token, so a stale caller fails loudly instead of silently.
    with pytest.raises(bridge.CommandError):
        bridge.parse_command("measure 500 3.9")
    assert bridge.parse_command("measure 3.9").args == (3.9,)


def test_the_status_record_matches_between_the_bridge_and_typescript(bridge):
    """The status object IS the UI's whole view of the machine, and until now
    nothing checked that the two descriptions of it agreed. A field the bridge
    added would be invisible to the panel; a field TypeScript declared and the
    bridge never sent would read as `undefined` — which for a boolean gate is
    silently falsy, i.e. a safety condition that never fires.
    """
    controller = bridge.BlmController(lambda _line: None, lambda _message: None)
    python_fields = set(controller.status())

    ts = BLM_TS.read_text(encoding="utf-8")
    block = ts[ts.index("export type ConsoleStatus = {"):]
    block = block[:block.index("\n};")]
    ts_fields = set(re.findall(r"^  (\w+)\??:", block, re.MULTILINE))

    assert python_fields == ts_fields, (
        f"only in the bridge {sorted(python_fields - ts_fields)}, "
        f"only in TypeScript {sorted(ts_fields - python_fields)}")


def test_the_ui_reads_the_wheel_verdicts_instead_of_recomputing_them(bridge):
    """Added 2026-08-07 with the measured-wheel gates.

    `arm`/`fire` now require the MEASURED flywheel RPM to agree with the command,
    freshly and for long enough to be stable. Those predicates live in the bridge
    because they are the same ones the gates use, and one safety rule must have one
    implementation — a panel that decided "confirmed" for itself could show a green
    ARM the bridge refuses, or worse, the reverse.
    """
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    blm = BLM_TS.read_text(encoding="utf-8")

    # The verdicts are consumed, not derived: no threshold arithmetic in the view.
    # (Optional chaining varies by call site, so match the field, not the prefix.)
    for verdict in ("wheels_confirmed", "safe_to_approach", "loaded",
                    "wheels_in_band_s", "wheels_unconfirmed_reason"):
        assert verdict in view, verdict
    for recomputed in ("RPM_SPREAD_MAX", "RPM_BAND_FRAC", "RPM_SAFE_APPROACH",
                       "WHEELS_STABLE_S"):
        assert recomputed not in view, (
            f"{recomputed} in the view means the rule is implemented twice")
        assert recomputed not in blm, recomputed

    # The arm button mirrors the bridge's gate, including the two conditions a
    # commanded RPM cannot express.
    can_arm = view[view.index("const canArm ="):view.index("const safeToApproach")]
    for condition in ("status.loaded", "status.wheels_confirmed",
                      "status.wheels_in_band_s >= status.wheels_stable_required_s",
                      "status.aim_established"):
        assert condition in can_arm, condition

    fire_blockers = blm[blm.index("export function fireBlockers("):
                        blm.index("export type CycleStep")]
    for condition in ("status.loaded", "status.wheels_confirmed",
                      "status.aim_established"):
        assert condition in fire_blockers, condition


def test_a_measured_rpm_is_never_displayed_once_its_reading_is_stale():
    """The number an operator reads before walking downrange. The firmware stops
    sending while the pusher moves and a dead reader leaves the last values in
    place forever, so a frozen "0 / 0" would read as a stopped machine."""
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    assert "const telemetryFresh =" in view
    assert "status.telemetry_age_s <= status.telemetry_max_age_s" in view
    # Both measured rows are gated on freshness, and they blank rather than lying.
    for wheel in ("rpm_left", "rpm_right"):
        assert f'telemetryFresh ? fmt(status?.{wheel}) : "—"' in view, wheel
    # And the age itself is on screen, not merely used internally.
    assert "telemetry_age_s.toFixed(1)" in view
    assert "DO NOT APPROACH" in view


def test_the_per_shot_cycle_is_named_on_screen(bridge):
    """Firmware `reload` homes BOTH aim axes and zeroes the wheel targets, and a
    shot consumes the arm — so the RPM and the arm genuinely have to be
    re-established for every single shot. That is correct behaviour which surprised
    the operator mid-pass, so the sequence belongs on the panel rather than on a
    printed sheet.
    """
    blm = BLM_TS.read_text(encoding="utf-8")
    step = blm[blm.index("export function cycleStep("):]
    # Every branch reads a bridge-computed field; the function orders and names
    # them and decides no safety question of its own.
    for field in ("estop_latched", "pending_shot", "safe_to_approach", "loaded",
                  "aim_established", "wheels_confirmed", "wheels_in_band_s",
                  "allow_fire", "armed"):
        assert field in step, field

    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    assert "cycleStep(" in view
    assert "step.title" in view and "step.detail" in view

    # The bridge is what makes the cycle mandatory rather than advisory.
    controller = bridge.BlmController(lambda _line: None, lambda _message: None,
                                      allow_fire=True)
    assert controller.state.loaded is False, (
        "a console must not assume a ball is already in the chamber")


def test_the_limits_agree_across_the_layers(bridge):
    """Duplicated on purpose (Rust refuses, Python clamps), so the numbers must
    be pinned together — a limit that drifts in one layer is the whole risk."""
    rust = BLM_RS.read_text(encoding="utf-8")
    ts = BLM_TS.read_text(encoding="utf-8")

    def rust_const(name):
        return float(re.search(rf"const {name}: f64 = ([\d.]+);", rust).group(1))

    def ts_const(name):
        return float(re.search(rf"export const {name} = ([\d.]+);", ts).group(1))

    for name, python_value in (
        ("ANGLE_LIMIT_DEG", bridge.ANGLE_LIMIT_DEG),
        # The DEFAULT envelope, not a hard limit — see the dedicated test below.
        ("PITCH_DEFAULT_MIN_DEG", bridge.PITCH_DEFAULT_MIN_DEG),
        ("PITCH_DEFAULT_MAX_DEG", bridge.PITCH_DEFAULT_MAX_DEG),
        ("YAW_LIMIT_DEG", bridge.YAW_LIMIT_DEG),
        ("RPM_MAX", float(bridge.RPM_MAX)),
        ("RPM_MIN_FIRE", float(bridge.RPM_MIN_FIRE)),
    ):
        assert rust_const(name) == python_value, name
        assert ts_const(name) == python_value, name

    word = re.search(r'FIRE_CONFIRMATION: &str = "(\w+)";', rust).group(1)
    assert f'FIRE_CONFIRMATION = "{word}"' in ts
    assert 'confirm: FIRE_CONFIRMATION' in LAUNCHER_VIEW.read_text(encoding="utf-8")


def test_actuation_classification_agrees_with_the_bridge(bridge):
    """The evidence trail records which intents can move the machine. If Rust and
    the bridge disagree, a lifecycle record calls a shot a poll or vice versa."""
    rust = BLM_RS.read_text(encoding="utf-8")
    block = rust[rust.index("pub fn is_actuating(&self) -> bool {"):]
    block = block[:block.index("\n    }")]
    rust_actuating = {snake(name) for name in re.findall(r"Self::(\w+)", block)}
    assert rust_actuating == set(bridge.ACTUATING), (
        f"Rust {rust_actuating} vs bridge {set(bridge.ACTUATING)}")


# ------------------------- exactly one live channel -------------------------

def test_only_the_console_profile_gets_a_writable_stdin():
    text = PROFILES_RS.read_text(encoding="utf-8")
    resolver = text[text.index("pub fn resolve_launch("):text.index("#[cfg(test)]")]
    assert resolver.count("stdin_writable: true") == 1, (
        "exactly one profile may hold a live command channel")
    console_at = resolver.index("LaunchRequest::BlmConsole {")
    assert "stdin_writable: true" in resolver[console_at:]
    # Every other arm must state it explicitly rather than inheriting a default:
    # 8 non-console profiles, each declaring `false`.
    assert resolver.count("stdin_writable: false") == 8


def test_stdin_is_piped_only_for_a_profile_that_declared_it():
    text = MAIN_RS.read_text(encoding="utf-8")
    spawn = text[text.index("fn spawn_resolved("):text.index("struct StopTimings")]
    assert "let wants_stdin = resolved.stdin_writable();" in spawn
    assert "Stdio::piped()" in spawn and "Stdio::null()" in spawn
    # The channel must be dropped when the process is reaped, or a dead pipe
    # would keep accepting writes that go nowhere.
    assert "*st.child_stdin.lock().unwrap() = None;" in spawn


def test_a_command_needs_a_live_console_and_is_rendered_by_the_backend():
    text = MAIN_RS.read_text(encoding="utf-8")
    command = text[text.index("fn send_launcher_command("):]
    command = command[:command.index("\nfn observed_process_state(")]
    # Rendering (and therefore validation) happens before anything is written.
    assert command.index("command.render()?") < command.index("child_stdin")
    assert "ProcessState::Starting | ProcessState::Running" in command
    assert "no launcher console is running" in command
    # A failed write must surface, never be swallowed into an Ok.
    assert "console write failed" in command
    # And the actuation is recorded.
    assert '"launcher_command"' in command
    assert "command.is_actuating()" in command


# ----------------------- the frontend still composes nothing -----------------

def test_the_frontend_cannot_compose_serial_or_protocol_text():
    for path in (BLM_TS, LAUNCHER_VIEW, APP_TS, LAUNCH_TS):
        text = path.read_text(encoding="utf-8")
        # No device node may be spelled in the UI: ports come from the backend.
        assert "/dev/tty" not in text, path.name
        # No firmware verb may appear as a string the UI could send.
        for firmware in ('"shoot"', '"set ', '"setzero"', '"jv', '"jh', '"jf',
                         '"js', "'shoot'"):
            assert firmware not in text, f"{path.name} spells firmware {firmware}"

    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    # The port reaches the request as a selected value, never as free text: the
    # picker is a <select> over the backend list, not an <input>.
    assert 'invoke<SerialDevice[]>("list_serial_ports")' in view
    assert "<select" in view
    assert re.search(r'send\(\{\s*command:\s*"', view), (
        "the view must send typed intents")


def test_a_shot_needs_a_sustained_hold_and_a_confirmed_room():
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    # Hold, not click.
    assert "FIRE_HOLD_MS" in view
    assert "onPointerDown={beginHold}" in view
    assert "onPointerUp={clearHold}" in view
    # Releasing the gate mid-hold aborts rather than queueing the shot.
    assert "if (!canFire) clearHold();" in view
    # Room-clear is operator-only and must not survive a session.
    assert "roomClear" in view
    assert "if (!live) setRoomClear(false);" in view

    blm = BLM_TS.read_text(encoding="utf-8")
    fire_blockers = blm[blm.index("export function fireBlockers("):
                        blm.index("export type CycleStep")]
    for condition in ("estop_latched", "allow_fire", "armed", "roomClear",
                      "RPM_MIN_FIRE",
                      # Was `pitch_deg` until 2026-08-07. That field is also filled
                      # in by an RPM-only change, because the firmware takes one
                      # combined `set v h wl wr` — so it was satisfied by touching
                      # only the RPM control, with an angle nobody chose.
                      "aim_established"):
        assert condition in fire_blockers, condition


def test_aim_and_wheels_are_independent_controls():
    """Found on the first live run, in the session lifecycle records: every
    command read `aim <angle> 0 500` while the operator had only touched the aim
    slider, so nudging the barrel spun the flywheels up. The firmware takes one
    combined `set v h wl wr`, so an aim must carry an RPM — it has to be the one
    the console already holds, never this panel's pending slider value.
    """
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    aim = view[view.index("const sendAim ="):view.index("const sendWheels =")]
    assert "wheel_rpm: commandedRpm" in aim, (
        "an aim must carry the RPM the console already holds")
    for local in ("wheel_rpm: rpm", "nextRpm"):
        assert local not in aim, f"sendAim still reads a local {local}"

    # The RPM control goes through the intent that reuses the stored angles, so
    # it cannot move the barrel either.
    assert 'command: "wheels"' in view
    assert "sendWheels(preset)" in view
    assert "sendWheels(v)" in view


def test_a_latched_estop_disables_the_controls_and_announces_itself():
    """The state where the sliders move and the machine refuses. Before this it
    was signalled only by a small pill and one log line, which reads as a broken
    panel rather than a latched stop.
    """
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    assert "const latched = status?.estop_latched === true;" in view
    assert "const canActuate = live && !latched;" in view
    # Pitch, yaw, RPM, presets, LEVEL, RELOAD and CENTER all die with the latch.
    assert view.count("disabled={!canActuate}") >= 7, view.count(
        "disabled={!canActuate}")

    # STOP must NOT be gated by the latch: it is idempotent and disabling it
    # would remove the operator's stop while the machine may still be moving.
    stop_at = view.index('send({ command: "stop" })')
    assert "disabled={!live}" in view[stop_at:stop_at + 200]

    # The strip announces the latch and carries its own release.
    latched_at = view.index("{latched ? (")
    banner = view[latched_at:latched_at + 1400]
    assert "ESTOP LATCHED" in banner
    assert 'send({ command: "clear" })' in banner


def test_the_controls_adopt_the_console_state_instead_of_drifting():
    """`stop` zeroes the commanded RPM and `center` zeroes the angles, neither of
    which the operator typed here. Without adoption the panel keeps displaying an
    aim and an RPM the machine is no longer holding."""
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    assert "const adopted = useRef(" in view
    for field in ("commandedPitch", "commandedYaw", "commandedRpm"):
        assert f"{field} !== adopted.current." in view, field

    # A slider must not start on a value the console is not commanding.
    assert "useState(RPM_PRESETS[0])" not in view, (
        "the RPM slider must start at 0, not on a preset it is not commanding")

    # A release that changed nothing must not re-send the command.
    assert "if (v !== commandedPitch) sendAim(v, yaw);" in view
    assert "if (v !== commandedRpm) sendWheels(v);" in view


def test_the_pitch_envelope_lives_in_the_bridge_not_in_a_constant(bridge):
    """REWRITTEN 2026-08-06, replacing a same-day version that clamped pitch to a
    hardcoded [0, 30].

    That stopped the jam and was the wrong frame. The barrel meets the ball feeder
    at a fixed PHYSICAL position, while the firmware's angle is measured from a
    zero adopted at boot or by `set_zero` — so a constant in that frame points at a
    different physical place after every re-zero, and it also deleted the downward
    travel the machine really has. Division of responsibility now:

      * Rust guards +/-30, which is frame-independent (the ESP32 reboots past it)
      * the bridge holds the per-session envelope, clamps to it, and translates
        it into the new frame on a re-zero
      * the slider takes its bounds from the console status, so it can never offer
        an angle the bridge will clamp
    """
    # Rust must NOT hardcode a pitch floor any more.
    rust = BLM_RS.read_text(encoding="utf-8")
    pitch_fn = rust[rust.index("fn pitch(value: f64)"):rust.index("fn yaw(value: f64)")]
    assert "ANGLE_LIMIT_DEG" in pitch_fn
    assert "PITCH_DEFAULT_MIN_DEG" not in pitch_fn, (
        "the default envelope is not a limit to refuse against")

    # The bridge owns it, as session state seeded from the launch defaults.
    assert bridge.clamp_pitch(-12.0, 0.0, 30.0) == 0.0
    assert bridge.clamp_pitch(-12.0, -25.0, 30.0) == -12.0
    assert bridge.clamp_pitch(-40.0, -25.0, 30.0) == -25.0
    # Yaw stays a fixed limit: it has no mechanical obstruction to declare.
    assert bridge.clamp_yaw(-45.0) == -bridge.YAW_LIMIT_DEG

    # The slider follows the live envelope rather than a constant.
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    assert "status?.pitch_min_deg ?? PITCH_DEFAULT_MIN_DEG" in view
    pitch_slider = view[view.index('label="PITCH"'):view.index('label="YAW"')]
    assert "min={pitchMin}" in pitch_slider, pitch_slider
    assert "max={pitchMax}" in pitch_slider
    yaw_slider = view[view.index('label="YAW"'):view.index('label="WHEEL RPM"')]
    assert "min={-YAW_LIMIT_DEG}" in yaw_slider
    # And the operator has a way to declare the measured travel.
    assert 'command: "limits"' in view
    # JSX wraps the explanatory phrase across a source newline.
    assert "feeder" in view
    # When SET ZERO translates the live envelope, the editable magnitudes must
    # follow it; otherwise APPLY TRAVEL would silently restore stale values.
    assert "setTravelDown(String(Math.max(0, -pitchMin)))" in view
    assert "setTravelUp(String(Math.max(0, pitchMax)))" in view


def test_the_serial_device_record_matches_between_rust_and_typescript():
    rust = PROFILES_RS.read_text(encoding="utf-8")
    block = rust[rust.index("pub struct SerialDevice {"):]
    block = block[:block.index("\n}")]
    rust_fields = set(re.findall(r"pub (\w+):", block))

    ts = BLM_TS.read_text(encoding="utf-8")
    ts_block = ts[ts.index("export type SerialDevice = {"):]
    ts_block = ts_block[:ts_block.index("\n};")]
    ts_fields = set(re.findall(r"^\s{2}(\w+):", ts_block, re.MULTILINE))

    assert rust_fields == ts_fields, (
        f"only in Rust {rust_fields - ts_fields}, only in TS {ts_fields - rust_fields}")
    assert "likely_launcher" in rust_fields


def test_detection_is_passive_and_never_claims_to_have_verified_the_launcher():
    """Identity comes from sysfs with no port opened, so the field is
    `likely_launcher`. Claiming certainty here would be the same mistake the
    readiness panel avoids: presence is not proof of what is on the other end."""
    rust = PROFILES_RS.read_text(encoding="utf-8")
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    for source, name in ((rust, "launch_profiles.rs"), (view, "LauncherView.tsx")):
        assert "is_launcher" not in source.replace("likely_launcher", ""), name
    # The UI has to say how it knows, and that polling is what proves it.
    assert "without opening the port" in view
    assert "POLL FIRMWARE" in view

    # A USB video device must be classified out: both /dev/ttyACM nodes on this
    # rig are webcams that expose a CDC-ACM interface.
    classify = rust[rust.index("fn classify("):rust.index("pub fn enumerate_serial_devices(")]
    for marker in ('"camera"', '"webcam"', '"video"'):
        assert marker in classify, marker
    assert "10c4:ea60" in rust, "the rig's CP2102 bridge must be recognised"


def test_the_port_choice_is_preselected_without_overriding_the_operator():
    blm = BLM_TS.read_text(encoding="utf-8")
    auto = blm[blm.index("export function autoSelectPort("):]
    auto = auto[:auto.index("\n}")]
    # A deliberate choice that is still present must survive the periodic refresh.
    assert "devices.some((device) => device.path === current)) return current" in auto
    assert "device.likely_launcher" in auto

    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    assert "autoSelectPort(found, current)" in view
    # The full list stays selectable: auto-selection is a default, not a lock.
    assert "onChange={(e) => setPort(e.target.value)}" in view


def test_a_stable_by_id_path_is_launchable_so_a_replug_does_not_break_the_choice():
    """The launcher moved from /dev/ttyUSB0 to /dev/ttyUSB1 after one USB
    re-enumeration on 2026-08-06, which is why the by-id form is accepted."""
    rust = PROFILES_RS.read_text(encoding="utf-8")
    assert 'SERIAL_BY_ID_DIR: &str = "/dev/serial/by-id"' in rust
    shape = rust[rust.index("pub fn serial_port_shape("):rust.index("pub fn validated_serial_port(")]
    assert "SERIAL_BY_ID_DIR" in shape
    # A by-id name must not be able to climb out of its directory.
    for guard in ('contains(\'/\')', '== ".."', "is_control"):
        assert guard in shape, guard
    # And the target is re-checked after canonicalizing, not trusted by name.
    validated = rust[rust.index("pub fn validated_serial_port("):rust.index("pub struct ResolvedLaunch")]
    assert "canonicalize()" in validated
    assert "does not resolve to a serial device node" in validated


def test_status_telemetry_is_routed_out_of_the_mission_log():
    app = APP_TS.read_text(encoding="utf-8")
    assert "parseStatusLine(line)" in app
    # A status line must not also be appended as log text, and a finished console
    # must not leave its last status looking live.
    listener = app[app.index('listen<{ line: string; stream: string }>'):]
    listener = listener[:listener.index("unlistenExit")]
    assert "setBlmStatus(status);" in listener
    assert "return;" in listener
    assert "setBlmStatus(null);" in app


# --------------------------- the other views are unchanged -------------------

def test_training_and_the_drill_wrapper_remain_view_only():
    """The console is the exception, not a precedent: drills stay pose consumers
    with no serial path, and the wrapper's allowlist is untouched."""
    wrapper = DRILL_WRAPPER.read_text(encoding="utf-8")
    for forbidden in ("--shoot-enabled", "/dev/tty", "live_aim_test",
                      "blm_follow", "blm_bridge"):
        assert forbidden not in wrapper, forbidden

    training = (DESKTOP / "src/views/TrainingView.tsx").read_text(encoding="utf-8")
    assert "blm_console" not in training
    assert "send_launcher_command" not in training
    # Only the launcher view may send console intents.
    for view in (DESKTOP / "src/views").glob("*.tsx"):
        if view.name == "LauncherView.tsx":
            continue
        assert "ConsoleCommand" not in view.read_text(encoding="utf-8"), view.name


def test_the_console_is_reachable_only_from_its_own_view():
    for path in sorted((DESKTOP / "src").rglob("*.ts*")):
        text = path.read_text(encoding="utf-8")
        if 'profile_id: "blm_console"' not in text:
            continue
        assert path.name in ("LauncherView.tsx", "launch.ts"), (
            f"{path.name} may not launch the console")


def test_the_rpm_protocol_uses_the_live_ball_profile_that_matches_this_rig():
    """The former command silently produced no calibration evidence:

    * the stock mirrored-skeleton wrapper hardcodes ``--no-track-ball``;
    * it requires all six configured cameras although five are currently live;
    * 960 does not match the active ball TensorRT engine exported at 672.

    Pin the executable protocol, not just prose explaining those failures.
    """
    protocol = RPM_PROTOCOL.read_text(encoding="utf-8")
    commands = "\n".join(re.findall(r"```(?:bash)?\n(.*?)```", protocol, re.DOTALL))
    assert "run_live_lowlag.sh" in commands
    for required in (
        "TRACK_BALL=1",
        "BALL_EVERY=1",
        "BALL_IMGSZ=672",
        "--min-active-cameras 5",
        "--ball-log-jsonl",
    ):
        assert required in commands, required

    assert "run_live_usb6_mirrored_skeleton.sh" not in commands
    assert "--ball-imgsz 960" not in commands
    assert "blm_interactive.py" not in protocol, (
        "calibration must use the gated desktop console rather than raw serial")


def fixed_yaw_500_section() -> str:
    protocol = RPM_PROTOCOL.read_text(encoding="utf-8")
    heading = "#### Fixed-YAW 500 RPM speed-only pass"
    assert heading in protocol
    return protocol[
        protocol.index(heading):protocol.index("### Method B, per RPM")
    ]


def test_the_fixed_yaw_500_rpm_pass_is_reload_first():
    section = fixed_yaw_500_section()
    # Firmware RELOAD zeros the wheel targets, so spinning first is not merely
    # inefficient: it leaves the UI, bridge state and physical sequence apart.
    assert section.index("Press **RELOAD**") < section.index("Command **500 RPM**")


def test_the_fixed_yaw_500_rpm_pass_pins_gates_and_claim_boundary():
    section = fixed_yaw_500_section()
    for required in (
        "`Ball=LOW`",
        "three polls spanning at least two seconds",
        "within 75 RPM",
        "below 50 RPM",
        "±25 cm",
        "do not use **YAW**, **CENTER**, or **SET ZERO**",
        "does not validate aiming accuracy",
        "automatic firing at a person",
    ):
        assert required in section, required
