"""The desktop backend, not the frontend, decides what may be executed.

`spawn_process` used to take `program`, `args` and `cwd` straight from the
frontend, so the Rust side placed no constraint at all on what ran. The drill
wrapper's own `case` allowlist covered only launches that went through the
wrapper — it was never a property of the launch boundary. These tests pin the
new boundary: named profiles resolved in Rust, and a frontend that cannot even
express a path.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "project-cam-desktop"
MAIN_RS = DESKTOP / "src-tauri/src/main.rs"
PROFILES_RS = DESKTOP / "src-tauri/src/launch_profiles.rs"
SESSION_RS = DESKTOP / "src-tauri/src/session.rs"
EVIDENCE_RS = DESKTOP / "src-tauri/src/evidence/mod.rs"
APP_TS = DESKTOP / "src/App.tsx"
LAUNCH_TS = DESKTOP / "src/launch.ts"
DATA_TS = DESKTOP / "src/data.ts"
DRILLS_TS = DESKTOP / "src/drills.ts"
SRC_TS = sorted((DESKTOP / "src").rglob("*.ts*"))


def frontend_sources():
    return {path: path.read_text(encoding="utf-8") for path in SRC_TS}


# ------------------------- the generic command is gone ----------------------

def test_generic_spawn_process_command_no_longer_exists():
    text = MAIN_RS.read_text(encoding="utf-8")
    assert "fn spawn_process" not in text
    handler = text[text.index("generate_handler!"):]
    assert "spawn_process" not in handler
    assert "launch_profile" in handler


def test_the_only_spawn_entry_point_takes_a_resolved_launch():
    """An internal spawn that accepts `ResolvedLaunch` cannot be handed a path:
    the type is only constructible by the resolver."""
    text = MAIN_RS.read_text(encoding="utf-8")
    assert "fn spawn_resolved(" in text
    signature = text[text.index("fn spawn_resolved("):]
    signature = signature[:signature.index(") -> ")]
    assert "resolved: ResolvedLaunch" in signature
    for forbidden in ("program: String", "args: Vec<String>", "cwd: String"):
        assert forbidden not in signature, forbidden


def test_resolution_happens_before_a_session_directory_is_created():
    """An invalid request must not leave an orphan session as evidence of a
    launch that never happened."""
    text = MAIN_RS.read_text(encoding="utf-8")
    body = text[text.index("fn launch_profile("):text.index("fn spawn_resolved(")]
    assert "resolve_launch(&paths, request)?" in body
    assert "create_session" not in body


def test_tauri_command_and_frontend_use_the_request_ipc_envelope():
    """Tauri maps invoke object keys to command parameter names. Pin both ends:
    changing Rust `request` to `payload` must not silently break every launch."""
    main = MAIN_RS.read_text(encoding="utf-8")
    signature = main[main.index("fn launch_profile("):]
    signature = signature[:signature.index(") -> ")]
    assert re.search(r"\brequest:\s*LaunchRequest\b", signature), signature

    app = APP_TS.read_text(encoding="utf-8")
    assert 'invoke<LaunchReceipt>("launch_profile", { request })' in app
    assert 'invoke<LaunchReceipt>("launch_profile", { payload' not in app


def test_app_paths_discovery_is_fail_closed_before_tauri_starts():
    """Without a verified repository root there is no safe launch surface.
    Startup must exit 2, never guess a root or continue with a default."""
    text = MAIN_RS.read_text(encoding="utf-8")
    body = text[text.index("fn main() {"):]
    discovery = body[:body.index("tauri::Builder::default()")]
    assert "AppPaths::discover().unwrap_or_else(|error|" in discovery
    assert "std::process::exit(2);" in discovery
    assert discovery.index("AppPaths::discover()") < discovery.index(
        "std::process::exit(2);")
    for forbidden in ("unwrap_or_default", "unwrap_or_else(|_| AppPaths",
                      "AppPaths::discover().ok()"):
        assert forbidden not in discovery


def test_launcher_kind_belongs_to_the_console_profile_alone():
    """CHANGED DELIBERATELY 2026-08-04, with the BLM console profile.

    This test previously asserted `LaunchKind::Launcher` did NOT exist, because
    no profile could actuate the launcher at all. The console does, so the
    variant is back — but exactly one profile may produce it, and it must still
    serialize as the same `"launcher"` string historical BLM shot logs carry, so
    the evidence reader keeps merging desktop consoles with legacy rows.
    """
    session = SESSION_RS.read_text(encoding="utf-8")
    enum_block = session[session.index("pub enum LaunchKind {"):]
    enum_block = enum_block[:enum_block.index("\n}")]
    assert re.search(r"^\s*Launcher,\s*$", enum_block, re.MULTILINE)

    profiles = PROFILES_RS.read_text(encoding="utf-8")
    resolver = profiles[profiles.index("pub fn resolve_launch("):profiles.index("#[cfg(test)]")]
    assert resolver.count("LaunchKind::Launcher") == 1, (
        "exactly one profile may produce a launcher session")
    console_arm = resolver[resolver.index("LaunchRequest::BlmConsole {"):]
    assert "LaunchKind::Launcher" in console_arm, (
        "the launcher kind must belong to the console arm")

    evidence = EVIDENCE_RS.read_text(encoding="utf-8")
    assert 'let launch_kind = string_value(record, "launch_kind");' in evidence
    assert 'launch_kind: "launcher".to_string(),' in evidence


# ------------------------- frontend cannot name a path ----------------------

@pytest.mark.parametrize("forbidden", ["spawn_process"])
def test_frontend_never_invokes_the_removed_command(forbidden):
    for path, text in frontend_sources().items():
        assert forbidden not in text, f"{path.name} still references {forbidden}"


def test_frontend_passes_no_program_args_cwd_or_interpreter():
    """The invoke payload must carry semantic fields only."""
    for path, text in frontend_sources().items():
        for forbidden in ("repoRoot:", "python:", "cwd:", "REPO_ROOT", "PYTHON"):
            assert forbidden not in text, f"{path.name} still passes {forbidden}"


def test_no_frontend_file_hardcodes_a_repository_path_or_script():
    """Match on real launch targets, not on any string containing ".sh" —
    `evidence.shots` would trip that, and a docs hint naming ./run.sh is not a
    launch path."""
    for path, text in frontend_sources().items():
        assert "/home/hanush" not in text, path.name
        for marker in ("Parallel_working", "garage_lab_combined", "venv/bin/python",
                       "face_enroll.py", "download_face_models.py"):
            assert marker not in text, f"{path.name} hardcodes {marker}"


def test_read_only_commands_take_no_path_arguments():
    """check_readiness / face_list_names / load_session_evidence all read from
    backend-owned AppPaths now."""
    text = MAIN_RS.read_text(encoding="utf-8")
    for command in ("check_readiness", "face_list_names", "load_session_evidence"):
        signature = text[text.index(f"fn {command}("):]
        signature = signature[:signature.index(")")]
        assert "repo_root: String" not in signature, command
        assert "python: String" not in signature, command
        assert "AppPaths" in signature, f"{command} must use State<AppPaths>"


# ----------------------------- profile id parity ----------------------------

def rust_profile_ids():
    text = PROFILES_RS.read_text(encoding="utf-8")
    block = text[text.index("pub enum LaunchRequest {"):]
    block = block[:block.index("\n}")]
    ids = []
    pending_rename = None
    for line in block.splitlines():
        renamed = re.search(r'#\[serde\(rename = "([a-z0-9_]+)"\)\]', line)
        if renamed:
            pending_rename = renamed.group(1)
            continue
        variant = re.match(r"\s{4}([A-Z][A-Za-z0-9]*)\s*\{", line)
        if not variant:
            continue
        # An explicit rename REPLACES the derived name; serde's snake_case would
        # otherwise give yolo_pose4cam / record3d.
        if pending_rename is not None:
            ids.append(pending_rename)
            pending_rename = None
        else:
            ids.append(re.sub(r"(?<!^)(?=[A-Z])", "_", variant.group(1)).lower())
    return set(ids)


def ts_profile_ids():
    # launch.ts is dedicated to the request contract, so every profile_id
    # literal in it belongs to the union. (Scanning the union alone is brittle:
    # the struct variants contain their own `;` separators.)
    return set(re.findall(r'profile_id:\s*"([a-z0-9_]+)"',
                          LAUNCH_TS.read_text(encoding="utf-8")))


def test_profile_ids_match_between_rust_and_typescript():
    rust, ts = rust_profile_ids(), ts_profile_ids()
    assert rust == ts, f"only in Rust: {sorted(rust - ts)}; only in TS: {sorted(ts - rust)}"
    assert {"free_view_usb6", "blm_overlay_usb6", "yolo_pose_4cam",
            "record_3d", "training_drill"} <= rust


def test_ui_catalog_only_names_declared_profiles():
    declared = ts_profile_ids()
    used = set(re.findall(r'profile_id:\s*"([a-z0-9_]+)"',
                          DATA_TS.read_text(encoding="utf-8")))
    assert used, "the launch catalog should name at least one profile"
    assert used <= declared, f"undeclared profile(s): {sorted(used - declared)}"


def test_launch_catalog_carries_no_script_path():
    text = DATA_TS.read_text(encoding="utf-8")
    assert "script:" not in text
    assert "Parallel_working" not in text


# ------------------------- drill workload is semantic -----------------------

def test_drill_catalog_uses_semantic_workload_keys_not_cli_flags():
    """`--rounds` meant holds / reps / sets / rounds depending on the drill, so
    a stored value was unreadable without knowing which drill it belonged to."""
    text = DRILLS_TS.read_text(encoding="utf-8")
    assert "roundsFlag" not in text
    assert '"--rounds"' not in text and '"--duration"' not in text
    keys = set(re.findall(r'workloadKey:\s*"([a-z_]+)"', text))
    assert keys == {"holds", "reps", "sets", "rounds", "duration_s",
                    "jumps", "hops_per_leg"}


def test_drill_ranges_match_the_rust_resolver():
    """Both sides range-check; if the bounds disagree the UI offers a value the
    backend will refuse."""
    ts = DRILLS_TS.read_text(encoding="utf-8")
    rust = PROFILES_RS.read_text(encoding="utf-8")
    expected = {
        "gk_save": (5, 20), "gk_updown": (15, 120), "balance": (2, 8),
        "shuttle": (1, 6), "line_hops": (1, 5),
        "reaction_zones": (5, 20),
    }
    for drill_id, (lo, hi) in expected.items():
        block = ts[ts.index(f'id: "{drill_id}"'):]
        block = block[:block.index("},")]
        assert f"roundsMin: {lo}," in block, drill_id
        assert f"roundsMax: {hi}," in block, drill_id
        assert re.search(rf"{lo}\.0,\s*{hi}\.0,\s*id,", rust), drill_id


def test_reaction_zones_projector_is_typed_boolean_not_a_raw_flag():
    catalog = DRILLS_TS.read_text(encoding="utf-8")
    catalog_block = catalog[catalog.index('id: "reaction_zones"'):]
    catalog_block = catalog_block[:catalog_block.index("},")]
    assert "roundsDefault: 10," in catalog_block
    assert "3.05" not in catalog_block

    launch = LAUNCH_TS.read_text(encoding="utf-8")
    assert (
        '{ drill: "reaction_zones"; rounds: number; projector: boolean }'
        in launch
    )
    assert 'case "reaction_zones":' in launch
    # The flag is the caller's decision, not a constant. It used to be hardcoded
    # `projector: true`, which forced a fullscreen board over the 3D arena view
    # on a single-monitor rig and made the tiled layout impossible.
    assert (
        'return { drill: "reaction_zones", rounds: workload, projector };'
        in launch
    )
    assert "projector = false" in launch, "fullscreen must be opt-in"

    profiles = PROFILES_RS.read_text(encoding="utf-8")
    request = profiles[profiles.index("pub enum TrainingDrillRequest {"):]
    request = request[:request.index("\n}")]
    assert re.search(
        r"ReactionZones\s*\{\s*rounds:\s*u32,\s*projector:\s*bool\s*\}",
        request,
    )
    assert "projector: String" not in request


def test_projector_toggle_is_offered_exactly_where_the_request_has_the_field():
    """`PROJECTOR_DRILLS` drives the UI toggle, so it must match the union.

    Offering it for a drill whose request has no `projector` field would be a
    launch rejected by serde's deny_unknown_fields; omitting it for one that
    does would strand the projector drills without a fullscreen board.
    """
    launch = LAUNCH_TS.read_text(encoding="utf-8")
    union = launch[launch.index("export type TrainingDrillRequest"):]
    union = union[:union.index("export type LaunchRequest")]
    with_field = {
        m.group(1)
        for m in re.finditer(r'drill: "(\w+)";[^|]*projector: boolean', union)
    }
    declared = set(
        re.search(r"PROJECTOR_DRILLS = \[([^\]]+)\]", launch)
        .group(1)
        .replace('"', "")
        .replace(" ", "")
        .split(",")
    ) - {""}
    assert declared == with_field, (declared, with_field)

    view = (
        ROOT / "project-cam-desktop/src/views/TrainingView.tsx"
    ).read_text(encoding="utf-8")
    assert "supportsProjector(drill.id)" in view
    assert "useState(false)" in view.split("const [projector")[1][:40]
    assert "drillRequest(drill.id, rounds, flip, projector)" in view


def test_seed_is_not_expressible_in_a_launch_request():
    """A pinned seed makes gk_save's cue sequence learnable, which would inflate
    reaction times without the athlete improving."""
    assert "seed" not in LAUNCH_TS.read_text(encoding="utf-8")
    profiles = PROFILES_RS.read_text(encoding="utf-8")
    request_block = profiles[profiles.index("pub enum TrainingDrillRequest {"):]
    request_block = request_block[:request_block.index("\n}")]
    assert "seed" not in request_block


# --------------------------------- safety -----------------------------------

def test_only_the_console_arm_may_reach_a_serial_port():
    """NARROWED DELIBERATELY 2026-08-04, with the BLM console profile.

    Until then this asserted that the resolver could not name a serial port at
    all. It kept passing after the console landed only because the port literals
    live above `resolve_launch` — i.e. it would have passed for the wrong reason,
    which is worse than failing. What still holds, and is what actually matters:

      * `--shoot-enabled` is unreachable from EVERY profile, console included.
        Firing is a runtime intent the bridge gates, never a launch argument.
      * the three actuating scripts stay unreachable — the console runs the
        bridge, which is the only serial writer the desktop app may start.
      * only the console arm resolves a serial port, and only via the validator.
    """
    text = PROFILES_RS.read_text(encoding="utf-8")
    resolver = text[text.index("pub fn resolve_launch("):text.index("#[cfg(test)]")]
    for forbidden in ("--shoot-enabled", "live_aim_test.py", "blm_follow.py",
                      "launcher_runtime_from_udp.py", "--wheel-rpm"):
        assert forbidden not in resolver, forbidden

    # Split the resolver at the console arm: no other arm may mention serial.
    console_at = resolver.index("LaunchRequest::BlmConsole {")
    others, console = resolver[:console_at], resolver[console_at:]
    for forbidden in ("/dev/tty", "serial_port", "validated_serial_port"):
        assert forbidden not in others, (
            f"{forbidden} reachable outside the console arm")
    assert "validated_serial_port(&serial_port)?" in console, (
        "the console must resolve its port through the validator, not raw text")
    assert "blm_bridge.py" in console

    # And the validator itself never hands back an unchecked string.
    shape = text[text.index("pub fn serial_port_shape("):text.index("pub fn validated_serial_port(")]
    assert "SERIAL_PREFIXES" in shape
    assert "is_ascii_digit" in shape


def test_training_profile_does_not_lower_the_camera_floor():
    text = PROFILES_RS.read_text(encoding="utf-8")
    arm = text[text.index("LaunchRequest::TrainingDrill {"):]
    arm = arm[:arm.index("LaunchRequest::FaceEnrollArena")]
    # Strip comments: the arm explains *why* it has no override, and that prose
    # names the flag.
    code = "\n".join(line for line in arm.splitlines()
                     if not line.strip().startswith("//"))
    assert "--min-active-cameras" not in code, (
        "drills must inherit the launcher's floor of 6")
