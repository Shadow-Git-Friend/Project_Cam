import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "project-cam-desktop"
MAIN_RS = DESKTOP / "src-tauri/src/main.rs"
APP = DESKTOP / "src/App.tsx"
CONTROL = DESKTOP / "src/views/ControlView.tsx"
TRAINING = DESKTOP / "src/views/TrainingView.tsx"
EVIDENCE_TS = DESKTOP / "src/evidence.ts"
SIDEBAR = DESKTOP / "src/components/Sidebar.tsx"
DATA = DESKTOP / "src/data.ts"
SESSIONS = DESKTOP / "src/views/SessionsView.tsx"
SHOTS = DESKTOP / "src/views/ShotsView.tsx"


def test_supervisor_writes_default_session_context_into_every_child():
    text = MAIN_RS.read_text(encoding="utf-8")
    for token in (
        "create_session(",
        "append_lifecycle(",
        "PROJECT_CAM_SESSION_ID",
        "PROJECT_CAM_SESSION_DIR",
        "PROJECT_CAM_EVENT_LOG_OUTPUT",
    ):
        assert token in text
    assert "Result<LaunchReceipt, String>" in text


def test_rust_backend_exposes_the_bounded_evidence_command():
    text = MAIN_RS.read_text(encoding="utf-8")
    assert "fn load_session_evidence(" in text
    assert "evidence::load_session_evidence(" in text
    handler = text[text.index("generate_handler!") :]
    assert "load_session_evidence" in handler


def test_backend_derives_the_launch_context_from_the_profile():
    """Inverted deliberately: the frontend used to declare its own
    `launch_kind`, so a UI bug could label a recording as a viewer session and
    the evidence would believe it. The launch context is now produced by the
    Rust resolver from the profile, and the frontend cannot state one.
    """
    app = APP.read_text(encoding="utf-8")
    assert 'await invoke<LaunchReceipt>("launch_profile"' in app
    assert "receipt.session_id" in app
    assert "context: LaunchContext" not in app

    control = CONTROL.read_text(encoding="utf-8")
    training = TRAINING.read_text(encoding="utf-8")
    for view in (control, training):
        assert "launch_kind" not in view

    profiles = (ROOT / "project-cam-desktop/src-tauri/src/launch_profiles.rs").read_text(
        encoding="utf-8")
    for kind in ("LaunchKind::Viewer", "LaunchKind::Recording",
                 "LaunchKind::Training", "LaunchKind::Maintenance"):
        assert kind in profiles, kind


def test_frontend_has_one_typed_evidence_boundary():
    text = EVIDENCE_TS.read_text(encoding="utf-8")
    assert 'invoke<SessionEvidence>("load_session_evidence"' in text
    assert "BROWSER PREVIEW · NO LOCAL DATA ACCESS" in text
    app = APP.read_text(encoding="utf-8")
    assert "evidenceRevision" in app
    assert "setEvidenceRevision" in app


def test_navigation_and_views_use_real_sessions_and_shots():
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert '"SESSIONS"' in sidebar
    assert '"SHOTS"' in sidebar
    assert '"ANALYTICS"' not in sidebar
    assert '"MATCHES"' not in sidebar
    app = APP.read_text(encoding="utf-8")
    assert "SessionsView" in app
    assert "ShotsView" in app


def test_production_data_has_no_synthetic_athlete_or_shot_rows():
    data = DATA.read_text(encoding="utf-8")
    for forbidden in (
        "KPIS",
        "TREND",
        "RADAR",
        "MATCHES",
        "PREVIEW SEASON",
        "51 km/h",
        "RATING",
    ):
        assert forbidden not in data
    sessions = SESSIONS.read_text(encoding="utf-8")
    shots = SHOTS.read_text(encoding="utf-8")
    assert "loadEvidence" in sessions
    assert "loadEvidence" in shots
    assert "UNCALIBRATED" in shots
    assert "BLOCKED" in shots
    assert "visual_check" not in shots


def test_readiness_never_falls_back_to_static_green():
    data = DATA.read_text(encoding="utf-8")
    control = CONTROL.read_text(encoding="utf-8")
    rust = MAIN_RS.read_text(encoding="utf-8")
    assert "UNKNOWN_READINESS" in data
    assert "6/6 ONLINE" not in data
    assert "keep static fallback" not in control
    assert "CHECK FAILED" in control
    assert "SYSTEM READINESS" not in control
    assert "LOCAL FILE / DEVICE CHECKS" in control
    for overclaim in ('"READY"', '"ONLINE"'):
        assert overclaim not in rust


# ---------------- P0B.2: comparability context reaches the desktop ----------

EVIDENCE_TS = ROOT / "project-cam-desktop/src/evidence.ts"
EVIDENCE_RS = ROOT / "project-cam-desktop/src-tauri/src/evidence/mod.rs"
TRAINING_RS = ROOT / "project-cam-desktop/src-tauri/src/evidence/training.rs"


def _ts_type_fields(text, type_name):
    """Field names of one exported TS type literal."""
    start = text.index(f"export type {type_name} = {{")
    body = text[start:text.index("};", start)]
    return set(re.findall(r"^\s{2}([a-z_]+)\??:", body, re.MULTILINE))


def test_session_row_fields_match_between_rust_and_typescript():
    """The DTO crosses a serde boundary by field name; a rename on one side
    silently yields `undefined` in the UI rather than a compile error."""
    rust = EVIDENCE_RS.read_text(encoding="utf-8")
    block = rust[rust.index("pub struct SessionRow {"):]
    block = block[:block.index("\n}")]
    rust_fields = set(re.findall(r"^\s{4}pub ([a-z_]+):", block, re.MULTILINE))

    ts_fields = _ts_type_fields(EVIDENCE_TS.read_text(encoding="utf-8"), "SessionRow")
    assert rust_fields == ts_fields, (
        f"only in Rust: {sorted(rust_fields - ts_fields)}; "
        f"only in TS: {sorted(ts_fields - rust_fields)}")
    assert {"athlete_id", "evidence_context"} <= rust_fields


def test_evidence_context_type_covers_every_field_the_producer_writes():
    """The Python producer and the TS consumer must agree on key names, or a
    real measurement reads as `undefined` in the desktop."""
    produced = {
        "protocol_id", "applied_parameters", "protocol_parameters_fingerprint",
        "context_schema", "configured_camera_roles", "opened_camera_roles",
        "calibration_fingerprint", "camera_open_ratio_by_role",
        "pose_valid_frame_ratio", "median_reported_joint_cameras",
        "packets_observed", "seed_pinned",
    }
    declared = _ts_type_fields(EVIDENCE_TS.read_text(encoding="utf-8"),
                               "SessionEvidenceContext")
    assert produced <= declared, f"missing from TS: {sorted(produced - declared)}"


def test_evidence_context_carries_no_verdict_field():
    """quality_class / baseline_eligible belong to the versioned comparison
    policy, not to a stored record."""
    declared = _ts_type_fields(EVIDENCE_TS.read_text(encoding="utf-8"),
                               "SessionEvidenceContext")
    assert "quality_class" not in declared
    assert "baseline_eligible" not in declared


def test_malformed_context_must_not_hide_a_session():
    """Pinned in Rust too, but assert the intent survives in the source: an
    optional block cannot be allowed to drop a drill that really happened."""
    text = TRAINING_RS.read_text(encoding="utf-8")
    assert "evidence_context ignored" in text
    assert "malformed_evidence_context_keeps_the_session_and_warns" in text
