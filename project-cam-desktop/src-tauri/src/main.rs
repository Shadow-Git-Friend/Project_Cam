// Prevents an extra console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod blm;
mod evidence;
mod launch_profiles;
mod session;

use std::io::{BufRead, BufReader, Write as IoWrite};
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::Path;
use std::process::{ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WindowEvent};

use blm::ConsoleCommand;
use launch_profiles::{
    enumerate_serial_devices, resolve_launch, AppPaths, LaunchRequest, ResolvedLaunch, SerialDevice,
};
use session::{append_lifecycle, create_session, LaunchReceipt, SessionHandle};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum ProcessState {
    #[default]
    Idle,
    Starting,
    Running,
    Stopping,
    Faulted,
}

#[derive(Clone, Copy, Debug)]
enum ProcessFact {
    Spawned,
    GroupAlive,
    StopRequested,
    Exited(i32),
    LaunchFailed,
    StopFailed,
}

impl ProcessState {
    fn after(self, fact: ProcessFact) -> Self {
        match fact {
            ProcessFact::Spawned => Self::Starting,
            ProcessFact::GroupAlive if self == Self::Starting => Self::Running,
            ProcessFact::GroupAlive => self,
            ProcessFact::StopRequested
                if matches!(self, Self::Starting | Self::Running | Self::Stopping) =>
            {
                Self::Stopping
            }
            ProcessFact::StopRequested => self,
            ProcessFact::Exited(0) if self == Self::Faulted => Self::Faulted,
            ProcessFact::Exited(0) => Self::Idle,
            ProcessFact::Exited(_) | ProcessFact::LaunchFailed => Self::Faulted,
            ProcessFact::StopFailed if self == Self::Stopping => Self::Running,
            ProcessFact::StopFailed => self,
        }
    }

    fn blocks_launch(self) -> bool {
        matches!(self, Self::Starting | Self::Running | Self::Stopping)
    }
}

/// One running child at a time (mirrors the Python control center's interlock).
/// We store the process-group id so a stop reaps the whole tree — the launch
/// scripts spawn `bash -> python -> workers`, so killing only the bash PID would
/// orphan the pipeline.
#[derive(Default)]
struct PipelineState {
    pgid: Mutex<Option<i32>>,
    generation: Mutex<u64>,
    current_session: Mutex<Option<SessionHandle>>,
    process_state: Mutex<ProcessState>,
    stopping: AtomicBool,
    exit_after_stop: Mutex<Option<i32>>,
    allow_exit: AtomicBool,
    /// Writable stdin, present only while a profile that declared
    /// `stdin_writable` is running. Dropping it closes the pipe, which the BLM
    /// bridge reads as EOF and answers with `stop` only. Blind centering is not
    /// part of shutdown, so this handle going away is a safe state, not a leak.
    child_stdin: Mutex<Option<ChildStdin>>,
}

impl PipelineState {
    fn transition(&self, fact: ProcessFact) -> ProcessState {
        let mut state = self.process_state.lock().unwrap();
        *state = state.after(fact);
        *state
    }

    fn process_state(&self) -> ProcessState {
        *self.process_state.lock().unwrap()
    }
}

#[derive(Clone, Serialize)]
struct LogPayload {
    line: String,
    stream: String, // "out" | "err" | "sys"
}

#[derive(Clone, Serialize)]
struct ExitPayload {
    code: i32,
    label: String,
}

#[derive(Serialize)]
struct ReadinessItem {
    label: String,
    status: String,
    ready: bool,
}

/// Is the process group still alive? `kill(-pgid, 0)` probes without signalling:
/// 0 = alive, EPERM = alive but not ours, ESRCH = gone.
fn group_alive(pgid: i32) -> bool {
    if pgid <= 1 {
        return false;
    }
    unsafe {
        if libc::kill(-pgid, 0) == 0 {
            return true;
        }
    }
    std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

fn emit_sys(app: &AppHandle, msg: &str) {
    let _ = app.emit(
        "pipeline-log",
        LogPayload {
            line: msg.to_string(),
            stream: "sys".into(),
        },
    );
}

fn append_lifecycle_or_log(
    app: &AppHandle,
    session: Option<&SessionHandle>,
    event: &str,
    detail: serde_json::Value,
) {
    let Some(session) = session else {
        return;
    };
    if let Err(error) = append_lifecycle(session, event, detail) {
        emit_sys(app, &format!("session evidence write failed: {error}"));
    }
}

/// Launch one BACKEND-APPROVED profile.
///
/// The frontend names a profile and supplies semantic parameters only; the
/// executable, its arguments, the working directory, the label and the launch
/// context are all produced by `resolve_launch`. There is deliberately no
/// command that accepts a program path — that was the old `spawn_process`, and
/// it meant the backend placed no constraint on what could be executed.
#[tauri::command]
fn launch_profile(
    app: AppHandle,
    state: State<PipelineState>,
    paths: State<AppPaths>,
    request: LaunchRequest,
) -> Result<LaunchReceipt, String> {
    // Resolve BEFORE touching the filesystem: an invalid request must not leave
    // an orphan session directory behind as evidence of a launch that never was.
    let resolved = resolve_launch(&paths, request)?;
    spawn_resolved(app, state, resolved)
}

/// Spawn an approved launch in its own session/process group, streaming
/// stdout+stderr to the frontend as `pipeline-log` events and the final code as
/// `pipeline-exit`. Refuses if a process is already running.
fn spawn_resolved(
    app: AppHandle,
    state: State<PipelineState>,
    resolved: ResolvedLaunch,
) -> Result<LaunchReceipt, String> {
    let program = resolved.program().to_string_lossy().into_owned();
    let args: Vec<String> = resolved.args().to_vec();
    let cwd = resolved.cwd().to_path_buf();
    let label = resolved.label().to_string();
    let context = resolved.context().clone();
    let wants_stdin = resolved.stdin_writable();
    {
        let guard = state.pgid.lock().unwrap();
        if let Some(pg) = *guard {
            if group_alive(pg) {
                return Err("A process is already running; stop it first.".into());
            }
        }
    }

    let session = match create_session(&cwd, &context, &program, &args, &label) {
        Ok(session) => session,
        Err(error) => {
            state.transition(ProcessFact::LaunchFailed);
            return Err(error);
        }
    };
    let mut cmd = Command::new(&program);
    cmd.args(&args)
        .current_dir(&cwd)
        .env("PYTHONUNBUFFERED", "1")
        .env("PROJECT_CAM_SESSION_ID", &session.session_id)
        .env("PROJECT_CAM_SESSION_DIR", &session.session_dir)
        .env("PROJECT_CAM_EVENT_LOG_OUTPUT", session.event_log_path())
        // Only a profile that declared it gets a channel back in. Everything
        // else keeps /dev/null, so there is nothing to write to even by mistake.
        .stdin(if wants_stdin {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // Put the child in its own session so it leads a fresh process group
    // (pgid == child pid). Lets stop_process signal the entire tree.
    unsafe {
        cmd.pre_exec(|| {
            if libc::setsid() == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }

    let mut child = match cmd.spawn() {
        Ok(child) => child,
        Err(error) => {
            state.transition(ProcessFact::LaunchFailed);
            append_lifecycle_or_log(
                &app,
                Some(&session),
                "launch_failed",
                serde_json::json!({"error": error.to_string()}),
            );
            return Err(format!("Launch failed: {error}"));
        }
    };
    let pid = child.id() as i32;

    let generation = {
        let mut g = state.generation.lock().unwrap();
        *g += 1;
        *g
    };
    *state.pgid.lock().unwrap() = Some(pid);
    *state.child_stdin.lock().unwrap() = child.stdin.take();
    *state.current_session.lock().unwrap() = Some(session.clone());
    state.transition(ProcessFact::Spawned);
    // A fresh process gets a fresh stop-escalation slot.
    state.stopping.store(false, Ordering::SeqCst);
    append_lifecycle_or_log(
        &app,
        Some(&session),
        "process_started",
        serde_json::json!({"pgid": pid}),
    );
    if group_alive(pid) {
        state.transition(ProcessFact::GroupAlive);
    }

    emit_sys(&app, &format!("$ {}", resolved.display_command()));

    if let Some(out) = child.stdout.take() {
        let app_out = app.clone();
        thread::spawn(move || {
            for line in BufReader::new(out).lines().map_while(Result::ok) {
                let _ = app_out.emit(
                    "pipeline-log",
                    LogPayload {
                        line,
                        stream: "out".into(),
                    },
                );
            }
        });
    }

    if let Some(err) = child.stderr.take() {
        let app_err = app.clone();
        thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                let _ = app_err.emit(
                    "pipeline-log",
                    LogPayload {
                        line,
                        stream: "err".into(),
                    },
                );
            }
        });
    }

    // Waiter: reap the child, clear state (if still current), report exit.
    let app_wait = app.clone();
    let session_wait = session.clone();
    let exit_label = label.clone();
    thread::spawn(move || {
        let code = child
            .wait()
            .ok()
            .map(|status| {
                status
                    .code()
                    .or_else(|| status.signal().map(|signal| 128 + signal))
                    .unwrap_or(-1)
            })
            .unwrap_or(-1);
        append_lifecycle_or_log(
            &app_wait,
            Some(&session_wait),
            "process_exited",
            serde_json::json!({"code": code}),
        );
        // The wrapper can have descendants after its leader exits. Keep the
        // group addressable and the interlock closed until every descendant is
        // gone; app-close containment may still need this pgid.
        while group_alive(pid) {
            thread::sleep(Duration::from_millis(200));
        }
        let st = app_wait.state::<PipelineState>();
        {
            let gen_now = st.generation.lock().unwrap();
            if *gen_now == generation {
                *st.pgid.lock().unwrap() = None;
                *st.child_stdin.lock().unwrap() = None;
                *st.current_session.lock().unwrap() = None;
                st.transition(ProcessFact::Exited(code));
            }
        }
        let _ = app_wait.emit(
            "pipeline-exit",
            ExitPayload {
                code,
                label: exit_label,
            },
        );
    });

    Ok(session.receipt(&label, &resolved.display_command()))
}

#[derive(Clone, Copy)]
struct StopTimings {
    sigint_ms: u64,
    sigterm_ms: u64,
    sigkill_ms: u64,
    poll_ms: u64,
}

const PRODUCTION_STOP_TIMINGS: StopTimings = StopTimings {
    sigint_ms: 10_000,
    sigterm_ms: 3_000,
    sigkill_ms: 1_000,
    poll_ms: 200,
};

fn wait_dead(pgid: i32, timeout_ms: u64, poll_ms: u64) -> bool {
    let step = poll_ms.max(1);
    let mut waited = 0u64;
    while waited < timeout_ms {
        if !group_alive(pgid) {
            return true;
        }
        thread::sleep(Duration::from_millis(step));
        waited += step;
    }
    !group_alive(pgid)
}

/// The single process-group termination primitive used by STOP, window close,
/// runtime exit and the final exit fail-safe.
fn terminate_process_group<F>(pgid: i32, timings: StopTimings, mut on_signal: F) -> bool
where
    F: FnMut(i32, i32),
{
    if !group_alive(pgid) {
        return true;
    }

    let signal_result = unsafe { libc::kill(-pgid, libc::SIGINT) };
    on_signal(libc::SIGINT, signal_result);
    if wait_dead(pgid, timings.sigint_ms, timings.poll_ms) {
        return true;
    }

    let signal_result = unsafe { libc::kill(-pgid, libc::SIGTERM) };
    on_signal(libc::SIGTERM, signal_result);
    if wait_dead(pgid, timings.sigterm_ms, timings.poll_ms) {
        return true;
    }

    let signal_result = unsafe { libc::kill(-pgid, libc::SIGKILL) };
    on_signal(libc::SIGKILL, signal_result);
    wait_dead(pgid, timings.sigkill_ms, timings.poll_ms)
}

#[derive(Clone, Copy)]
enum StopReason {
    User,
    WindowClose,
    AppExit,
    ExitFallback,
}

impl StopReason {
    fn as_str(self) -> &'static str {
        match self {
            Self::User => "user",
            Self::WindowClose => "window_close",
            Self::AppExit => "app_exit",
            Self::ExitFallback => "exit_fallback",
        }
    }
}

fn signal_name(signal: i32) -> &'static str {
    match signal {
        libc::SIGINT => "SIGINT",
        libc::SIGTERM => "SIGTERM",
        libc::SIGKILL => "SIGKILL",
        _ => "UNKNOWN",
    }
}

fn finish_exit_if_requested(app: &AppHandle, state: &PipelineState) {
    let exit_code = state.exit_after_stop.lock().unwrap().take();
    if let Some(code) = exit_code {
        state.allow_exit.store(true, Ordering::SeqCst);
        app.exit(code);
    }
}

/// Start the one shared asynchronous stop chain. Repeated STOP/close/exit
/// requests join the existing chain through `stopping.swap` instead of stacking
/// independent escalation timers.
fn request_stop(app: &AppHandle, state: &PipelineState, reason: StopReason) -> bool {
    let pgid = *state.pgid.lock().unwrap();
    let pgid = match pgid {
        Some(p) if group_alive(p) => p,
        _ => return false,
    };

    // One escalation chain at a time — repeated STOP clicks must not stack
    // SIGINT->SIGTERM->SIGKILL timers.
    if state.stopping.swap(true, Ordering::SeqCst) {
        return true;
    }
    state.transition(ProcessFact::StopRequested);

    let session = state.current_session.lock().unwrap().clone();
    append_lifecycle_or_log(
        app,
        session.as_ref(),
        "stop_requested",
        serde_json::json!({"reason": reason.as_str()}),
    );

    let app_bg = app.clone();
    thread::spawn(move || {
        let stopped =
            terminate_process_group(pgid, PRODUCTION_STOP_TIMINGS, |signal, signal_result| {
                let name = signal_name(signal);
                append_lifecycle_or_log(
                    &app_bg,
                    session.as_ref(),
                    if signal_result == 0 {
                        "signal_sent"
                    } else {
                        "signal_failed"
                    },
                    serde_json::json!({"signal": name, "result": signal_result}),
                );
                emit_sys(&app_bg, &format!("{name} sent."));
            });
        append_lifecycle_or_log(
            &app_bg,
            session.as_ref(),
            if stopped {
                "stop_complete"
            } else {
                "stop_failed"
            },
            serde_json::json!({
                "reason": reason.as_str(),
                "group_dead": stopped,
            }),
        );

        let managed = app_bg.state::<PipelineState>();
        if !stopped {
            managed.transition(ProcessFact::StopFailed);
            emit_sys(
                &app_bg,
                "process group survived SIGKILL; application remains open",
            );
        }
        managed.stopping.store(false, Ordering::SeqCst);
        if stopped {
            finish_exit_if_requested(&app_bg, &managed);
        }
    });

    true
}

/// Graceful stop: SIGINT (10s) -> SIGTERM (3s) -> SIGKILL, on the process group.
/// Mirrors the Python control center so recordings finalize their MP4 moov atom.
/// Returns `true` if a live process group was signalled, `false` if nothing is
/// running.
#[tauri::command]
fn stop_process(app: AppHandle, state: State<PipelineState>) -> Result<bool, String> {
    Ok(request_stop(&app, &state, StopReason::User))
}

/// Serial devices currently present, each with its passive identification and the
/// most likely launcher first. The console's picker reads this, so a port reaches
/// the backend as a selection rather than as typed text — and the operator does
/// not have to know which `/dev/ttyUSB<n>` the launcher landed on this time.
///
/// Passive by design: identity comes from sysfs, no port is opened. So the field
/// is `likely_launcher`, not `is_launcher` — only opening the console and polling
/// the firmware proves what is on the other end.
#[tauri::command]
fn list_serial_ports() -> Vec<SerialDevice> {
    enumerate_serial_devices()
}

/// Send one typed intent to the running launcher console.
///
/// The frontend cannot write serial and cannot write the bridge's protocol text
/// either: it names a [`ConsoleCommand`] and the backend renders the line. The
/// bridge then re-validates and applies the operator gates (arm expiry,
/// auto-disarm after a shot, the ESTOP latch), so this command is a transport,
/// not an authority — it can deliver `fire`, but it cannot make a shot happen
/// that the bridge's own state does not permit.
#[tauri::command]
fn send_launcher_command(
    app: AppHandle,
    state: State<PipelineState>,
    command: ConsoleCommand,
) -> Result<String, String> {
    // Render (and therefore validate) before looking at process state, so an
    // out-of-range request is refused identically whether or not one is running.
    let line = command.render()?;
    if !matches!(
        observed_process_state(&state),
        ProcessState::Starting | ProcessState::Running
    ) {
        return Err("no launcher console is running".into());
    }
    {
        let mut guard = state
            .child_stdin
            .lock()
            .map_err(|_| "console channel poisoned".to_string())?;
        let stdin = guard
            .as_mut()
            .ok_or_else(|| "the running process has no command channel".to_string())?;
        // A write that fails must be reported as a refusal, never swallowed: the
        // operator would otherwise believe a stop or an aim had been delivered.
        writeln!(stdin, "{line}")
            .and_then(|()| stdin.flush())
            .map_err(|error| format!("console write failed: {error}"))?;
    }
    let session = state.current_session.lock().unwrap().clone();
    append_lifecycle_or_log(
        &app,
        session.as_ref(),
        "launcher_command",
        serde_json::json!({"command": line, "actuating": command.is_actuating()}),
    );
    Ok(line)
}

fn observed_process_state(state: &PipelineState) -> ProcessState {
    let current = state.process_state();
    if current == ProcessState::Starting {
        let pgid = *state.pgid.lock().unwrap();
        if matches!(pgid, Some(p) if group_alive(p)) {
            return state.transition(ProcessFact::GroupAlive);
        }
    }
    current
}

/// Authoritative process state. The UI reads this continuously and never
/// manufactures a local RUNNING boolean.
#[tauri::command]
fn pipeline_state(state: State<PipelineState>) -> ProcessState {
    observed_process_state(&state)
}

/// Compatibility shim for older callers, derived exclusively from the Rust
/// state machine.
#[tauri::command]
fn pipeline_running(state: State<PipelineState>) -> bool {
    observed_process_state(&state).blocks_launch()
}

const CALIBRATION_FILES: [&str; 9] = [
    "garage_lab_combined/config/cameras_6usb_test.yaml",
    "garage_lab_combined/cal/extrinsics_usb6/extrinsics_usb6.json",
    "garage_lab_combined/cal/extrinsics_usb6/Dimensions_mirrored_y.txt",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb01_C920_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb02_1080P_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb03_C920_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb04_1080P_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb05_1080P_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb06_1080P_intrinsics.json",
];

/// Inspect local file/device presence without opening cameras or loading models.
/// The booleans mean only that the local presence check passed.
#[tauri::command]
fn check_readiness(paths: State<AppPaths>) -> Vec<ReadinessItem> {
    let root = paths.repo_root();

    // Cameras: parse `device:` lines from the 6-USB config, count which exist.
    let cfg = root.join("garage_lab_combined/config/cameras_6usb_test.yaml");
    let mut devices: Vec<String> = Vec::new();
    if let Ok(text) = std::fs::read_to_string(&cfg) {
        for line in text.lines() {
            if let Some(rest) = line.trim().strip_prefix("device:") {
                devices.push(rest.trim().to_string());
            }
        }
    }
    let total = devices.len();
    let connected = devices.iter().filter(|d| Path::new(d).exists()).count();
    let cameras = ReadinessItem {
        label: "CAMERA DEVICES".into(),
        status: if total == 0 {
            "NOT CONFIGURED".into()
        } else {
            format!("{connected}/{total} DEVICE NODES")
        },
        ready: total > 0 && connected == total,
    };

    let calib_ready = CALIBRATION_FILES.iter().all(|f| root.join(f).is_file());
    let calibration = ReadinessItem {
        label: "CALIBRATION FILES".into(),
        status: if calib_ready { "PRESENT" } else { "MISSING" }.into(),
        ready: calib_ready,
    };

    let models_dir = root.join("models/face");
    let models_ready = [
        "face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx",
    ]
    .iter()
    .all(|f| models_dir.join(f).is_file());
    let face_models = ReadinessItem {
        label: "FACE MODEL FILES".into(),
        status: if models_ready { "PRESENT" } else { "MISSING" }.into(),
        ready: models_ready,
    };

    let data_home = std::env::var("XDG_DATA_HOME")
        .unwrap_or_else(|_| format!("{}/.local/share", std::env::var("HOME").unwrap_or_default()));
    let gallery_ready = Path::new(&data_home)
        .join("project-cam/face_gallery.npz")
        .is_file();
    let gallery = ReadinessItem {
        label: "GALLERY FILE".into(),
        status: if gallery_ready { "PRESENT" } else { "EMPTY" }.into(),
        ready: gallery_ready,
    };

    vec![cameras, calibration, face_models, gallery]
}

/// Names currently enrolled in the local face gallery, via `face_enroll.py --list`.
/// Fast (loads the .npz, no ML models) and read-only; used for the "you're
/// enrolled" indicator. Returns [] on any error so the UI just shows "not yet".
#[tauri::command]
fn face_list_names(paths: State<AppPaths>) -> Vec<String> {
    let script = paths
        .repo_root()
        .join("Parallel_working/scripts/face_enroll.py");
    let mut names = Vec::new();
    if let Ok(out) = Command::new(paths.python())
        .arg(&script)
        .arg("--list")
        .current_dir(paths.repo_root())
        .output()
    {
        let text = String::from_utf8_lossy(&out.stdout);
        for line in text.lines() {
            // Rows look like "  <name>: 12 sample(s)"; the header "Gallery: <path>"
            // and "(empty)" are skipped because their tail has no "sample".
            if let Some((name, rest)) = line.trim().split_once(": ") {
                if rest.contains("sample") {
                    names.push(name.trim().to_string());
                }
            }
        }
    }
    names
}

// The TRAINING view's "recent sessions" panel used to have its own reader here
// (`training_sessions`) which read the whole index with `read_to_string` and
// handed raw JSONL lines to the UI to parse. That was a second, unbounded and
// untyped path to evidence the typed loader already covers: the training index
// is parsed by `evidence::load_session_evidence` via `read_jsonl_tail`
// (byte-capped) into `SessionRow`, which carries drill/title/athlete/ended_at/
// headline/status. TRAINING now calls that command and filters to drill rows,
// so there is exactly ONE bounded reader and one rejection accounting.

#[tauri::command]
fn load_session_evidence(
    state: State<PipelineState>,
    paths: State<AppPaths>,
    athlete_filter: Option<String>,
    session_limit: usize,
    shot_limit: usize,
) -> Result<evidence::SessionEvidence, String> {
    let running = state
        .current_session
        .lock()
        .map_err(|_| "session state poisoned".to_string())?
        .as_ref()
        .map(|session| session.session_id.clone());
    evidence::load_session_evidence(
        paths.repo_root(),
        athlete_filter.as_deref(),
        session_limit,
        shot_limit,
        running.as_deref(),
    )
}

fn needs_containment(state: &PipelineState) -> bool {
    if state.stopping.load(Ordering::SeqCst) {
        return true;
    }
    matches!(*state.pgid.lock().unwrap(), Some(pgid) if group_alive(pgid))
}

/// Close/exit is delayed until the shared asynchronous stop chain reports that
/// the complete process group is dead. `app.exit` then emits a fresh
/// ExitRequested event, admitted exactly once by `allow_exit`.
fn request_app_shutdown(app: &AppHandle, code: i32, reason: StopReason) {
    let state = app.state::<PipelineState>();
    *state.exit_after_stop.lock().unwrap() = Some(code);
    let joined_stop = request_stop(app, &state, reason);
    if !joined_stop || (!state.stopping.load(Ordering::SeqCst) && !needs_containment(&state)) {
        finish_exit_if_requested(app, &state);
    }
}

fn wait_for_stop_chain(state: &PipelineState) {
    while state.stopping.load(Ordering::SeqCst) {
        thread::sleep(Duration::from_millis(PRODUCTION_STOP_TIMINGS.poll_ms));
    }
}

/// Final synchronous safety net. Normal close/exit requests are prevented and
/// handled asynchronously above; if the runtime nevertheless reaches Exit with
/// a live group, this callback uses the same graduated termination primitive
/// before Tauri terminates the desktop process.
fn stop_before_exit(app: &AppHandle) {
    let state = app.state::<PipelineState>();
    let pgid = *state.pgid.lock().unwrap();
    let Some(pgid) = pgid.filter(|pgid| group_alive(*pgid)) else {
        return;
    };
    let session = state.current_session.lock().unwrap().clone();
    let already_stopping = state.stopping.swap(true, Ordering::SeqCst);
    if already_stopping {
        loop {
            wait_for_stop_chain(&state);
            if !group_alive(pgid) {
                return;
            }
            if !state.stopping.swap(true, Ordering::SeqCst) {
                break;
            }
        }
    }
    state.transition(ProcessFact::StopRequested);
    append_lifecycle_or_log(
        app,
        session.as_ref(),
        "stop_requested",
        serde_json::json!({"reason": StopReason::ExitFallback.as_str()}),
    );

    let stopped =
        terminate_process_group(pgid, PRODUCTION_STOP_TIMINGS, |signal, signal_result| {
            append_lifecycle_or_log(
                app,
                session.as_ref(),
                if signal_result == 0 {
                    "signal_sent"
                } else {
                    "signal_failed"
                },
                serde_json::json!({
                    "signal": signal_name(signal),
                    "result": signal_result,
                    "reason": StopReason::ExitFallback.as_str(),
                }),
            );
        });
    append_lifecycle_or_log(
        app,
        session.as_ref(),
        if stopped {
            "stop_complete"
        } else {
            "stop_failed"
        },
        serde_json::json!({
            "reason": StopReason::ExitFallback.as_str(),
            "group_dead": stopped,
        }),
    );
    if !stopped {
        state.transition(ProcessFact::StopFailed);
    }
    state.stopping.store(false, Ordering::SeqCst);
}

fn handle_run_event(app: &AppHandle, event: RunEvent) {
    match event {
        RunEvent::WindowEvent {
            event: WindowEvent::CloseRequested { api, .. },
            ..
        } => {
            let state = app.state::<PipelineState>();
            if needs_containment(&state) {
                api.prevent_close();
                request_app_shutdown(app, 0, StopReason::WindowClose);
            }
        }
        RunEvent::ExitRequested { code, api, .. } => {
            let state = app.state::<PipelineState>();
            if state.allow_exit.swap(false, Ordering::SeqCst) {
                return;
            }
            if needs_containment(&state) {
                api.prevent_exit();
                request_app_shutdown(app, code.unwrap_or(0), StopReason::AppExit);
            }
        }
        RunEvent::Exit => stop_before_exit(app),
        _ => {}
    }
}

fn main() {
    // Fail fast and loudly: without a verified repository root there is no safe
    // launch surface at all, so refusing to start beats running with a guessed
    // one.
    let paths = AppPaths::discover().unwrap_or_else(|error| {
        eprintln!("[FATAL] {error}");
        std::process::exit(2);
    });
    let app = tauri::Builder::default()
        .manage(PipelineState::default())
        .manage(paths)
        .invoke_handler(tauri::generate_handler![
            launch_profile,
            stop_process,
            pipeline_state,
            pipeline_running,
            check_readiness,
            face_list_names,
            load_session_evidence,
            list_serial_ports,
            send_launcher_command
        ])
        .build(tauri::generate_context!())
        .expect("error while building Project Cam");
    app.run(handle_run_event);
}

#[cfg(test)]
mod lifecycle_tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn process_state_follows_observed_facts_and_fault_allows_relaunch() {
        assert_eq!(
            serde_json::to_string(&ProcessState::Faulted).unwrap(),
            r#""faulted""#
        );
        let mut state = ProcessState::Idle;

        state = state.after(ProcessFact::Spawned);
        assert_eq!(state, ProcessState::Starting);

        state = state.after(ProcessFact::GroupAlive);
        assert_eq!(state, ProcessState::Running);

        state = state.after(ProcessFact::StopRequested);
        assert_eq!(state, ProcessState::Stopping);

        state = state.after(ProcessFact::Exited(130));
        assert_eq!(state, ProcessState::Faulted);
        assert!(
            !state.blocks_launch(),
            "Faulted must not require an app restart"
        );

        state = state.after(ProcessFact::Spawned);
        assert_eq!(state, ProcessState::Starting);
        state = state.after(ProcessFact::GroupAlive);
        assert_eq!(state, ProcessState::Running);
        state = state.after(ProcessFact::Exited(0));
        assert_eq!(state, ProcessState::Idle);

        state = state.after(ProcessFact::LaunchFailed);
        assert_eq!(state, ProcessState::Faulted);
        state = state.after(ProcessFact::Exited(0));
        assert_eq!(
            state,
            ProcessState::Faulted,
            "a late clean exit must not clear a latched fault"
        );
        state = state.after(ProcessFact::StopRequested);
        assert_eq!(
            state,
            ProcessState::Faulted,
            "a stop request cannot acknowledge a latched fault"
        );

        state = state.after(ProcessFact::Spawned);
        state = state.after(ProcessFact::GroupAlive);
        state = state.after(ProcessFact::StopRequested);
        assert_eq!(state, ProcessState::Stopping);
        state = state.after(ProcessFact::StopFailed);
        assert_eq!(
            state,
            ProcessState::Running,
            "a still-live group is running once escalation has ended"
        );
        assert!(state.blocks_launch());

        assert_eq!(
            ProcessState::Idle.after(ProcessFact::StopFailed),
            ProcessState::Idle,
            "a late stop failure cannot resurrect an already reaped process"
        );
        assert_eq!(
            ProcessState::Faulted.after(ProcessFact::StopFailed),
            ProcessState::Faulted,
            "a late stop failure cannot clear a latched fault"
        );
    }

    #[test]
    fn stop_escalation_reaps_a_long_lived_process_group() {
        let marker = std::env::temp_dir().join(format!(
            "project-cam-lc1-ready-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let script = format!(
            "trap '' INT TERM; : > '{}'; sleep 5 & wait",
            marker.display()
        );
        let mut command = Command::new("/bin/sh");
        command
            .arg("-c")
            .arg(script)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        unsafe {
            command.pre_exec(|| {
                if libc::setsid() == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let mut child = command.spawn().expect("spawn harmless test process group");
        let pgid = child.id() as i32;
        for _ in 0..100 {
            if marker.exists() {
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        assert!(marker.exists(), "test process did not become ready");

        // Reap concurrently just like the production waiter. Otherwise a dead
        // group leader remains a zombie and kill(-pgid, 0) correctly sees its
        // process-group id until wait() consumes it.
        let waiter = thread::spawn(move || child.wait());
        let mut signals = Vec::new();
        let stopped = terminate_process_group(
            pgid,
            StopTimings {
                sigint_ms: 100,
                sigterm_ms: 100,
                sigkill_ms: 1_000,
                poll_ms: 10,
            },
            |signal, result| signals.push((signal, result)),
        );
        let status = waiter.join().unwrap().unwrap();
        let _ = fs::remove_file(&marker);

        assert!(stopped, "process group survived the complete escalation");
        assert!(!group_alive(pgid), "process group is still addressable");
        assert!(
            !status.success(),
            "SIGKILL test process unexpectedly succeeded"
        );
        assert_eq!(
            signals
                .iter()
                .map(|(signal, _)| *signal)
                .collect::<Vec<_>>(),
            [libc::SIGINT, libc::SIGTERM, libc::SIGKILL]
        );
    }
}
