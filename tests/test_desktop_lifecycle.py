"""Desktop process lifecycle is owned by Rust, including app-close cleanup.

The real termination mechanics are exercised by Rust unit tests with a harmless
long-lived process group. These source contracts cover the Tauri wiring and the
React IPC boundary that cannot be driven without a desktop runtime.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "project-cam-desktop"
MAIN_RS = DESKTOP / "src-tauri/src/main.rs"
APP_TS = DESKTOP / "src/App.tsx"
SESSION_RS = DESKTOP / "src-tauri/src/session.rs"


def test_backend_exposes_the_explicit_process_state_command():
    text = MAIN_RS.read_text(encoding="utf-8")
    enum = text[text.index("enum ProcessState {"):]
    enum = enum[:enum.index("\n}")]
    for state in ("Idle", "Starting", "Running", "Stopping", "Faulted"):
        assert state in enum

    signature = text[text.index("fn pipeline_state("):]
    signature = signature[:signature.index("\n}")]
    assert "ProcessState" in signature
    handler = text[text.index("generate_handler!"):]
    assert "pipeline_state," in handler

    compatibility = text[text.index("fn pipeline_running("):]
    compatibility = compatibility[:compatibility.index("\n}")]
    assert "observed_process_state(&state).blocks_launch()" in compatibility


def test_frontend_reads_rust_state_and_never_writes_a_boolean_running_state():
    app = APP_TS.read_text(encoding="utf-8")
    for state in ("idle", "starting", "running", "stopping", "faulted"):
        assert f'"{state}"' in app
    assert 'invoke<ProcessState>("pipeline_state")' in app
    assert '"pipeline_running"' not in app
    assert "setRunning" not in app
    assert "useState(false)" not in app
    assert "function ProcessFooter(" in app
    assert "{state.toUpperCase()}" in app
    assert "const canStop = isBusyState(state);" in app


def test_frontend_reconciliation_is_unconditional_and_repairs_lost_exit_events():
    app = APP_TS.read_text(encoding="utf-8")
    poll = app[app.index("// Reconciliation is unconditional"):]
    poll = poll[:poll.index("const run: RunFn")]
    assert 'invoke<ProcessState>("pipeline_state")' in app
    assert "window.setInterval(reconcile, 1000)" in poll
    assert "if (!busy" not in poll
    assert "if (!running" not in poll


def test_window_close_and_runtime_exit_route_through_containment():
    text = MAIN_RS.read_text(encoding="utf-8")
    handler = text[text.index("fn handle_run_event("):text.index("fn main() {")]
    for required in (
        "WindowEvent::CloseRequested",
        "api.prevent_close();",
        "RunEvent::ExitRequested",
        "api.prevent_exit();",
        "request_app_shutdown",
        "RunEvent::Exit",
        "stop_before_exit",
    ):
        assert required in handler

    main = text[text.index("fn main() {"):]
    assert ".build(tauri::generate_context!())" in main
    assert "app.run(handle_run_event);" in main


def test_stop_and_app_close_share_one_non_stacking_escalation():
    text = MAIN_RS.read_text(encoding="utf-8")
    stop = text[text.index("fn request_stop("):text.index("fn stop_process(")]
    assert "stopping.swap(true, Ordering::SeqCst)" in stop
    assert "terminate_process_group(" in stop

    containment = text[
        text.index("fn request_app_shutdown("):text.index("fn stop_before_exit(")
    ]
    assert "request_stop(" in containment

    escalation = text[
        text.index("fn terminate_process_group<F>("):text.index("fn request_stop(")
    ]
    assert escalation.index("libc::SIGINT") < escalation.index("libc::SIGTERM")
    assert escalation.index("libc::SIGTERM") < escalation.index("libc::SIGKILL")

    fallback = text[text.index("fn stop_before_exit("):text.index("fn handle_run_event(")]
    assert "if already_stopping {" in fallback
    assert fallback.index("wait_for_stop_chain(") < fallback.index(
        "terminate_process_group("
    )


def test_containment_records_an_ordinary_lifecycle_stop():
    main = MAIN_RS.read_text(encoding="utf-8")
    stop = main[main.index("fn request_stop("):main.index("fn stop_process(")]
    for event in (
        '"stop_requested"',
        '"signal_sent"',
        '"signal_failed"',
        '"stop_complete"',
        '"stop_failed"',
    ):
        assert event in stop
    assert '"reason": reason.as_str()' in stop

    session = SESSION_RS.read_text(encoding="utf-8")
    assert (
        'pub const LIFECYCLE_SCHEMA: &str = "project_cam.desktop.lifecycle.v1";'
        in session
    )


def test_invalid_launch_still_resolves_before_session_creation():
    text = MAIN_RS.read_text(encoding="utf-8")
    launch = text[text.index("fn launch_profile("):text.index("fn spawn_resolved(")]
    assert "resolve_launch(&paths, request)?" in launch
    assert "create_session" not in launch
    assert "fn spawn_process" not in text
