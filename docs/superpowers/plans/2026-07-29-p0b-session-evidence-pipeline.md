# P0B Session Evidence Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every desktop launch durable session identity/lifecycle evidence, normalize existing training and launcher logs in Rust, replace synthetic Tauri analytics with real `SESSIONS`/`SHOTS`, and make readiness failures visibly unknown.

**Architecture:** Add focused Rust `session` and `evidence` modules beside the existing Tauri supervisor. Rust owns filesystem access, bounded JSONL parsing, schema normalization, and launch evidence; React consumes typed DTOs only. Existing Python producers receive the desktop session ID through environment defaults, while raw JSONL remains authoritative and no database is introduced.

**Tech Stack:** Rust 2021, Tauri 2, serde/serde_json, chrono, uuid, React 18, TypeScript, pytest.

**Status (2026-07-29):** Implemented in the preserved dirty working tree.
Desktop launches now create durable session manifests/lifecycle JSONL, Python
producers inherit the session context, Rust exposes bounded normalized
evidence, and the React UI consumes factual `SESSIONS`/`SHOTS` DTOs with
unknown-first readiness. No commit, push, PR, or hardware actuation was
performed.

**Verification record:** `cargo fmt --check`, 16 Rust tests, clippy with
`-D warnings`, and the production frontend build all pass. The focused Python
evidence/safety set passes 162 tests; the hardware-free suite excluding the
five API modules passes 657 tests with one pre-existing CUDA warning. Pytest
collects 682 tests in total, but the 25 API tests are not claimed green in
this sandbox: the isolated hardware-free health test repeatedly stalls inside
FastAPI/TestClient and exceeded a 20-second timeout. Re-run those five files
in the known-good API/CI environment before repository integration.

---

## Working-Tree Constraint

Execute in `/home/hanush/Desktop/Project_Cam` on
`feature/multi-person-face-id-desktop-20260712`.

Do **not** create a new worktree: the Tauri application and the display,
training, report, and safety work under review exist only in this dirty tree.
Preserve every unrelated modification and untracked file.

Do **not** commit. Project rules assign commits and pushes to the user. Replace
each commit step normally required by the skill with a scoped status/diff
checkpoint.

Do not modify the protected geometry functions, UDP axis semantics, trajectory
geometry, or fire-control authorization.

## File Map

- Create `project-cam-desktop/src-tauri/src/session.rs`: opaque IDs, atomic
  manifest creation, append-only lifecycle records, child environment paths.
- Create `project-cam-desktop/src-tauri/src/evidence/mod.rs`: public DTOs,
  source discovery, merge/sort/filter orchestration.
- Create `project-cam-desktop/src-tauri/src/evidence/jsonl.rs`: bounded UTF-8
  JSONL tail reader with rejection diagnostics.
- Create `project-cam-desktop/src-tauri/src/evidence/training.rs`: strict
  `project_cam.training.v1` normalization.
- Create `project-cam-desktop/src-tauri/src/evidence/shots.rs`: closed-loop
  EventLogger and conservative legacy BLM normalization.
- Modify `project-cam-desktop/src-tauri/src/main.rs`: wire session persistence
  into spawn/stop/exit and expose `load_session_evidence`.
- Modify `project-cam-desktop/src-tauri/Cargo.toml`: direct chrono/uuid
  dependencies already present in `Cargo.lock`.
- Create `project-cam-desktop/src/evidence.ts`: frontend DTOs and the single
  Tauri loader.
- Create `project-cam-desktop/src/views/SessionsView.tsx`: factual session
  totals, session rows, and comparable per-drill trends.
- Create `project-cam-desktop/src/views/ShotsView.tsx`: launched/blocked
  attempts with separate RPM and calibrated-speed fields.
- Delete superseded `project-cam-desktop/src/views/AnalyticsView.tsx` and
  `project-cam-desktop/src/views/MatchesView.tsx`.
- Modify `project-cam-desktop/src/App.tsx`,
  `src/components/Sidebar.tsx`, `src/views/ControlView.tsx`,
  `src/views/TrainingView.tsx`, and `src/data.ts`: pass launch context, refresh
  evidence, use real navigation, and remove production fake data.
- Modify `src/project_cam/training/drills.py` and
  `garage_lab_combined/scripts/training_drill.py`: persist the inherited
  desktop session ID.
- Modify `garage_lab_combined/scripts/launcher_runtime_from_udp.py`: use
  desktop session/event-log environment variables as CLI defaults.
- Modify `tests/test_training_drills.py`,
  `tests/test_launcher_runtime_fire_control.py`,
  `tests/test_desktop_training_contracts.py`, and create
  `tests/test_desktop_session_evidence_contracts.py`.
- Modify `project-cam-desktop/README.md` and `CLAUDE.md` after verification.

### Task 1: Establish the Rust session-evidence primitive

**Files:**
- Modify: `project-cam-desktop/src-tauri/Cargo.toml`
- Create: `project-cam-desktop/src-tauri/src/session.rs`
- Modify: `project-cam-desktop/src-tauri/src/main.rs`

- [x] **Step 1: Add direct dependencies**

Add:

```toml
chrono = { version = "0.4.45", features = ["serde"] }
uuid = { version = "1.23.5", features = ["v4", "serde"] }
```

These exact versions are already locked transitively, so this must not update
unrelated crates.

- [x] **Step 2: Write the failing Rust tests**

Create `session.rs` with a `tests` module that calls the not-yet-implemented
API:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn repo() -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "project-cam-session-test-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn manifest_is_opaque_atomic_and_unicode_safe() {
        let root = repo();
        let context = LaunchContext {
            athlete: Some("Арлен".into()),
            launch_kind: LaunchKind::Training,
            drill: Some("balance".into()),
        };
        let handle = create_session(
            &root,
            &context,
            "bash",
            &["run.sh".into(), "--athlete".into(), "Арлен".into()],
            "DRILL · BALANCE",
        )
        .unwrap();
        assert!(handle.session_id.starts_with('s'));
        assert!(!handle.session_id.contains("Арлен"));
        assert!(handle.session_dir.ends_with(&handle.session_id));
        let raw = fs::read_to_string(handle.session_dir.join("manifest.json")).unwrap();
        let value: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(value["athlete"], "Арлен");
        assert_eq!(value["launch_kind"], "training");
        assert!(!handle.session_dir.join("manifest.json.tmp").exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn lifecycle_is_append_only_and_parseable() {
        let root = repo();
        let handle = create_session(
            &root,
            &LaunchContext::default(),
            "bash",
            &["true".into()],
            "TEST",
        )
        .unwrap();
        append_lifecycle(&handle, "process_started", serde_json::json!({"pgid": 42}))
            .unwrap();
        append_lifecycle(&handle, "process_exited", serde_json::json!({"code": 0}))
            .unwrap();
        let lines = fs::read_to_string(handle.session_dir.join("lifecycle.jsonl")).unwrap();
        let values: Vec<serde_json::Value> =
            lines.lines().map(|line| serde_json::from_str(line).unwrap()).collect();
        assert_eq!(values.len(), 3);
        assert_eq!(values[0]["event"], "launch_requested");
        assert_eq!(values[1]["event"], "process_started");
        assert_eq!(values[2]["event"], "process_exited");
        assert!(values.iter().all(|v| v["session_id"] == handle.session_id));
        fs::remove_dir_all(root).unwrap();
    }
}
```

- [x] **Step 3: Register the missing module and prove RED**

Add `mod session;` near the top of `main.rs`, then run:

```bash
cd project-cam-desktop/src-tauri
cargo test session::tests -- --nocapture
```

Expected: compilation fails because `LaunchContext`, `LaunchKind`,
`create_session`, and `append_lifecycle` are not defined.

- [x] **Step 4: Implement the minimal session module**

Implement these public types and functions:

```rust
use chrono::{SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use uuid::Uuid;

pub const MANIFEST_SCHEMA: &str = "project_cam.desktop.session_manifest.v1";
pub const LIFECYCLE_SCHEMA: &str = "project_cam.desktop.lifecycle.v1";

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LaunchKind {
    Training,
    Viewer,
    Recording,
    Launcher,
    #[default]
    Maintenance,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct LaunchContext {
    pub athlete: Option<String>,
    pub launch_kind: LaunchKind,
    pub drill: Option<String>,
}

#[derive(Clone, Debug)]
pub struct SessionHandle {
    pub session_id: String,
    pub session_dir: PathBuf,
}

#[derive(Clone, Debug, Serialize)]
pub struct LaunchReceipt {
    pub session_id: String,
    pub session_dir: String,
}
```

`create_session` must:

1. validate that `repo_root` exists;
2. create `garage_lab_combined/output/sessions` and the opaque session
   directory with mode `0o700`;
3. use `s-<UTC basic timestamp>-<uuid simple>` as the ID;
4. serialize the manifest with
   `serde_json::to_vec_pretty`;
5. create `manifest.json.tmp` using `create_new(true)` and mode `0o600`;
6. `write_all`, `sync_all`, and `rename` it to `manifest.json`;
7. append `launch_requested`;
8. return `SessionHandle`.

Use this signature:

```rust
pub fn create_session(
    repo_root: &Path,
    context: &LaunchContext,
    program: &str,
    args: &[String],
    label: &str,
) -> Result<SessionHandle, String>
```

`append_lifecycle` must open `lifecycle.jsonl` with append/create mode
`0o600`, serialize exactly one record, append `\n`, and call `flush`:

```rust
pub fn append_lifecycle(
    handle: &SessionHandle,
    event: &str,
    detail: Value,
) -> Result<(), String>
```

Add:

```rust
impl SessionHandle {
    pub fn receipt(&self) -> LaunchReceipt {
        LaunchReceipt {
            session_id: self.session_id.clone(),
            session_dir: self.session_dir.to_string_lossy().into_owned(),
        }
    }

    pub fn event_log_path(&self) -> PathBuf {
        self.session_dir.join("events.jsonl")
    }
}
```

- [x] **Step 5: Run the Rust tests and lockfile check**

Run:

```bash
cd project-cam-desktop/src-tauri
cargo fmt --check
cargo test session::tests -- --nocapture
git diff -- Cargo.lock
```

Expected: `2 passed`; the lock diff contains only root-package dependency
edges or is empty, with no unrelated crate upgrades.

### Task 2: Integrate session evidence into process launch and stop

**Files:**
- Modify: `project-cam-desktop/src-tauri/src/main.rs`
- Modify: `project-cam-desktop/src/App.tsx`
- Modify: `project-cam-desktop/src/views/ControlView.tsx`
- Modify: `project-cam-desktop/src/views/TrainingView.tsx`
- Create: `tests/test_desktop_session_evidence_contracts.py`

- [x] **Step 1: Write failing cross-layer contract tests**

Create:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "project-cam-desktop"
MAIN_RS = DESKTOP / "src-tauri/src/main.rs"
APP = DESKTOP / "src/App.tsx"
CONTROL = DESKTOP / "src/views/ControlView.tsx"
TRAINING = DESKTOP / "src/views/TrainingView.tsx"


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


def test_frontend_supplies_explicit_launch_contexts():
    app = APP.read_text(encoding="utf-8")
    assert "LaunchContext" in app
    assert "context: LaunchContext" in app
    assert 'await invoke<LaunchReceipt>("spawn_process"' in app
    assert "receipt.session_id" in app
    control = CONTROL.read_text(encoding="utf-8")
    training = TRAINING.read_text(encoding="utf-8")
    for kind in ('launch_kind: "viewer"', 'launch_kind: "recording"',
                 'launch_kind: "maintenance"'):
        assert kind in control
    assert 'launch_kind: "training"' in training
    assert "drill: drill.id" in training
```

- [x] **Step 2: Run the contracts to prove RED**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py -v
```

Expected: `2 failed`, because the supervisor and frontend do not yet know
session context or receipts.

- [x] **Step 3: Extend `PipelineState` and `spawn_process`**

Import:

```rust
use session::{
    append_lifecycle, create_session, LaunchContext, LaunchReceipt, SessionHandle,
};
```

Add:

```rust
current_session: Mutex<Option<SessionHandle>>,
```

Change the command signature to:

```rust
fn spawn_process(
    app: AppHandle,
    state: State<PipelineState>,
    program: String,
    args: Vec<String>,
    cwd: String,
    label: String,
    context: LaunchContext,
) -> Result<LaunchReceipt, String>
```

Before `Command::new`, call:

```rust
let session = create_session(Path::new(&cwd), &context, &program, &args, &label)?;
```

Add the three child variables:

```rust
.env("PROJECT_CAM_SESSION_ID", &session.session_id)
.env("PROJECT_CAM_SESSION_DIR", &session.session_dir)
.env("PROJECT_CAM_EVENT_LOG_OUTPUT", session.event_log_path())
```

Replace the spawn error mapping with:

```rust
let mut child = match cmd.spawn() {
    Ok(child) => child,
    Err(error) => {
        let _ = append_lifecycle(
            &session,
            "launch_failed",
            serde_json::json!({"error": error.to_string()}),
        );
        return Err(format!("Launch failed: {error}"));
    }
};
```

After the PID is known, append `process_started`, store
`current_session = Some(session.clone())`, and return `session.receipt()`.
The waiter appends `process_exited` before clearing the current session.

In `stop_process`, append `stop_requested` synchronously, then append each
signal event immediately after its `kill` call. A missing lifecycle write is
emitted to the mission log but must not prevent an emergency stop signal.

- [x] **Step 4: Add typed frontend launch context**

In `App.tsx` define:

```ts
export type LaunchContext = {
  athlete?: string;
  launch_kind: "training" | "viewer" | "recording" | "launcher" | "maintenance";
  drill?: string;
};

type LaunchReceipt = { session_id: string; session_dir: string };

export type RunFn = (
  program: string,
  args: string[],
  label: string,
  context: LaunchContext
) => void;
```

Pass `context` to `invoke`, capture the receipt, and append:

```ts
const receipt = await invoke<LaunchReceipt>("spawn_process", {
  program,
  args,
  cwd: REPO_ROOT,
  label,
  context,
});
append(`session ${receipt.session_id}`, "sys");
```

Update every call site:

```ts
{ athlete, launch_kind: "viewer" }
{ athlete, launch_kind: "recording" }
{ athlete, launch_kind: "training", drill: drill.id }
{ athlete, launch_kind: "maintenance" }
```

The recording launch is selected from `Launch.danger`; it is not inferred
from the label text.

- [x] **Step 5: Run cross-layer checks**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py -v
cd project-cam-desktop/src-tauri
cargo test
cd ../..
npm --prefix project-cam-desktop run build
```

Expected: `2 passed`, all Rust tests pass, and the production frontend build
completes.

### Task 3: Propagate session identity into Python producers

**Files:**
- Modify: `src/project_cam/training/drills.py`
- Modify: `garage_lab_combined/scripts/training_drill.py`
- Modify: `garage_lab_combined/scripts/launcher_runtime_from_udp.py`
- Modify: `tests/test_training_drills.py`
- Modify: `tests/test_launcher_runtime_fire_control.py`
- Modify: `tests/test_desktop_training_contracts.py`

- [x] **Step 1: Add failing training-record tests**

Extend the session round-trip test:

```python
record = build_session_record(
    d,
    "Арлен",
    "2026-07-16T10:00:00",
    "2026-07-16T10:01:00",
    aborted=False,
    session_id="desktop-session-1",
)
assert record["session_id"] == "desktop-session-1"
```

Add to `test_desktop_training_contracts.py`:

```python
def test_training_runner_inherits_the_desktop_session_id():
    text = RUNNER.read_text(encoding="utf-8")
    assert 'os.environ.get("PROJECT_CAM_SESSION_ID"' in text
    assert "session_id=desktop_session_id" in text
```

- [x] **Step 2: Add failing launcher-default tests**

Add:

```python
def test_desktop_session_defaults_are_opt_in_and_path_safe(monkeypatch, tmp_path):
    module = _load_runtime()
    monkeypatch.delenv("PROJECT_CAM_SESSION_ID", raising=False)
    monkeypatch.delenv("PROJECT_CAM_SESSION_DIR", raising=False)
    monkeypatch.delenv("PROJECT_CAM_EVENT_LOG_OUTPUT", raising=False)
    assert module.desktop_session_defaults() == ("", "")

    session_dir = tmp_path / "session"
    monkeypatch.setenv("PROJECT_CAM_SESSION_ID", "desktop-1")
    monkeypatch.setenv("PROJECT_CAM_SESSION_DIR", str(session_dir))
    assert module.desktop_session_defaults() == (
        "desktop-1",
        str(session_dir / "events.jsonl"),
    )

    monkeypatch.setenv("PROJECT_CAM_EVENT_LOG_OUTPUT", str(tmp_path / "explicit.jsonl"))
    assert module.desktop_session_defaults() == (
        "desktop-1",
        str(tmp_path / "explicit.jsonl"),
    )
```

- [x] **Step 3: Run the focused tests to prove RED**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_training_drills.py::test_session_record_and_index_roundtrip \
  tests/test_desktop_training_contracts.py::test_training_runner_inherits_the_desktop_session_id \
  tests/test_launcher_runtime_fire_control.py::test_desktop_session_defaults_are_opt_in_and_path_safe -v
```

Expected: `3 failed`.

- [x] **Step 4: Implement optional training session IDs**

Change the pure helper signature:

```python
def build_session_record(
    drill,
    athlete,
    started_iso,
    ended_iso,
    aborted=False,
    session_id="",
):
```

Build the existing record, then conditionally add:

```python
if session_id:
    record["session_id"] = str(session_id)
```

In `training_drill.py`, import `os`, resolve once:

```python
desktop_session_id = os.environ.get("PROJECT_CAM_SESSION_ID", "").strip()
```

and pass `session_id=desktop_session_id` to `build_session_record`.
Historical/standalone output stays byte-compatible apart from normal
timestamp differences because the field is absent when the environment is
empty.

- [x] **Step 5: Implement launcher environment defaults**

Add:

```python
def desktop_session_defaults(environ=None):
    env = os.environ if environ is None else environ
    session_id = str(env.get("PROJECT_CAM_SESSION_ID", "")).strip()
    explicit = str(env.get("PROJECT_CAM_EVENT_LOG_OUTPUT", "")).strip()
    if explicit:
        return session_id, explicit
    session_dir = str(env.get("PROJECT_CAM_SESSION_DIR", "")).strip()
    output = str(Path(session_dir) / "events.jsonl") if session_dir else ""
    return session_id, output
```

Before constructing the two argparse options:

```python
desktop_session_id, desktop_event_log = desktop_session_defaults()
```

Use those values as the `default=` values for `--session-id` and
`--event-log-output`. Explicit CLI values continue to win automatically.

- [x] **Step 6: Run producer tests**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_training_drills.py \
  tests/test_desktop_training_contracts.py \
  tests/test_launcher_runtime_fire_control.py -v
```

Expected: all tests in the three files pass.

### Task 4: Build the bounded JSONL reader and training normalizer

**Files:**
- Create: `project-cam-desktop/src-tauri/src/evidence/jsonl.rs`
- Create: `project-cam-desktop/src-tauri/src/evidence/training.rs`
- Create: `project-cam-desktop/src-tauri/src/evidence/mod.rs`
- Modify: `project-cam-desktop/src-tauri/src/main.rs`

- [x] **Step 1: Write failing JSONL tests**

In `jsonl.rs`, add tests proving:

```rust
#[test]
fn bounded_tail_drops_a_truncated_first_line_and_counts_bad_json() {
    let root = test_dir();
    let path = root.join("large.jsonl");
    let prefix = format!("{}\n", serde_json::json!({"old": "x".repeat(300)}));
    let valid = format!("{}\n", serde_json::json!({"keep": 1}));
    fs::write(&path, format!("{prefix}not-json\n{valid}")).unwrap();
    let parsed = read_jsonl_tail(&path, 128).unwrap();
    assert_eq!(parsed.values, vec![serde_json::json!({"keep": 1})]);
    assert_eq!(parsed.rejected, 1);
    assert!(parsed.truncated);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn non_finite_json_tokens_are_rejected() {
    let root = test_dir();
    let path = root.join("bad.jsonl");
    fs::write(&path, "{\"value\": NaN}\n{\"value\": 3.0}\n").unwrap();
    let parsed = read_jsonl_tail(&path, 1024).unwrap();
    assert_eq!(parsed.values.len(), 1);
    assert_eq!(parsed.rejected, 1);
    fs::remove_dir_all(root).unwrap();
}
```

- [x] **Step 2: Prove the module is RED**

Register `mod evidence;` in `main.rs`, and in `evidence/mod.rs` register:

```rust
mod jsonl;
mod training;
```

Run:

```bash
cd project-cam-desktop/src-tauri
cargo test evidence::jsonl::tests -- --nocapture
```

Expected: compilation fails because `read_jsonl_tail` and its result type are
missing.

- [x] **Step 3: Implement the bounded reader**

Define:

```rust
pub struct ParsedJsonl {
    pub values: Vec<serde_json::Value>,
    pub rejected: usize,
    pub truncated: bool,
}

pub fn read_jsonl_tail(path: &Path, max_bytes: u64) -> Result<ParsedJsonl, String>
```

Implementation requirements:

- seek to `len.saturating_sub(max_bytes.max(1))`;
- if starting after byte zero, discard bytes through the first newline;
- decode with `String::from_utf8_lossy`;
- ignore blank lines;
- parse each remaining line with `serde_json::from_str`;
- reject non-object top-level JSON;
- count every parse/type rejection;
- never read more than `max_bytes` plus the discarded partial-line fragment.

- [x] **Step 4: Define shared evidence DTOs**

In `evidence/mod.rs`, define serializable snake-case DTOs:

```rust
#[derive(Clone, Debug, Serialize)]
pub struct SessionRow {
    pub session_id: String,
    pub source_schema: String,
    pub source_path: String,
    pub athlete: String,
    pub launch_kind: String,
    pub drill: String,
    pub title: String,
    pub started_at: String,
    pub ended_at: String,
    pub status: String,
    pub headline: String,
    pub summary: Value,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct SourceStatus {
    pub path: String,
    pub accepted: usize,
    pub rejected: usize,
    pub truncated: bool,
    pub error: String,
}
```

Add `legacy_session_id(source, timestamp)` using a deterministic sanitized
source filename plus timestamp. It is an in-memory join key only.

- [x] **Step 5: Write and implement strict training normalization**

Add tests with one current record carrying `session_id`, one historical
record without it, one unknown schema, and one non-finite numeric value.

Implement:

```rust
pub fn parse_training_record(
    value: &Value,
    source: &Path,
) -> Result<SessionRow, String>
```

Accept only `schema == "project_cam.training.v1"`. Require string `drill`,
`title`, `started`, and `ended`; tolerate empty athlete; require boolean
`aborted`; retain only finite JSON numbers in `summary` via a recursive
sanitizer. Map status to `aborted` or `complete`. Use the exact session ID
when present, otherwise `legacy_session_id`.

- [x] **Step 6: Run the reader/training tests**

Run:

```bash
cd project-cam-desktop/src-tauri
cargo test evidence::jsonl::tests -- --nocapture
cargo test evidence::training::tests -- --nocapture
```

Expected: all new tests pass.

### Task 5: Normalize EventLogger and legacy launcher evidence conservatively

**Files:**
- Create: `project-cam-desktop/src-tauri/src/evidence/shots.rs`
- Modify: `project-cam-desktop/src-tauri/src/evidence/mod.rs`

- [x] **Step 1: Define the shot DTO**

Add:

```rust
#[derive(Clone, Debug, Serialize)]
pub struct ShotRow {
    pub session_id: String,
    pub sequence: usize,
    pub timestamp: String,
    pub target: String,
    pub wheel_left_rpm: Option<f64>,
    pub wheel_right_rpm: Option<f64>,
    pub speed_mps: Option<f64>,
    pub speed_calibrated: bool,
    pub pitch_deg: Option<f64>,
    pub yaw_deg: Option<f64>,
    pub state: String,
    pub outcome: String,
    pub block_reason: String,
    pub source_schema: String,
    pub source_path: String,
    pub warnings: Vec<String>,
}
```

- [x] **Step 2: Write failing semantic tests**

Create EventLogger fixtures for:

1. `aim_command_sent` followed by `ball_launched`;
2. `aim_command_sent` followed by `safety_gate_blocked`;
3. `ball_launched` with no outcome;
4. `outcome_scored` after a launch;
5. a legacy `live_aim_test.py` `action="shoot"` row with
   `visual_check="y"` and `fire_outcome.serial_shoot_sent=true`;
6. a raw `FIRE_BLOCKED` decision;
7. RPM with no speed.

Assertions:

```rust
assert_eq!(launched.state, "launched");
assert_eq!(launched.outcome, "unknown");
assert_eq!(blocked.state, "blocked");
assert_eq!(legacy_visual.outcome, "unknown");
assert_eq!(legacy_visual.wheel_left_rpm, Some(800.0));
assert_eq!(legacy_visual.speed_mps, None);
assert!(!legacy_visual.speed_calibrated);
```

- [x] **Step 3: Run to prove RED**

Run:

```bash
cd project-cam-desktop/src-tauri
cargo test evidence::shots::tests -- --nocapture
```

Expected: compilation fails because the shot normalizers do not exist.

- [x] **Step 4: Implement EventLogger sequence joining**

Implement:

```rust
pub fn parse_event_log(
    values: &[Value],
    source: &Path,
) -> (Vec<ShotRow>, Vec<String>)
```

Accept only
`schema_version == "project_cam.closed_loop.event_log.v1"`.
Maintain the latest finite `aim_command_sent` payload by session ID. On
`ball_launched` or `safety_gate_blocked`, create one shot using the matching
aim values, then clear the pending aim. Set:

- `launched` only when `serial_shoot_sent` is true or event type is
  `ball_launched`;
- `blocked` for `safety_gate_blocked`;
- outcome `unknown` until `outcome_scored`;
- block reason from payload `reason`;
- retain finite `speed_mps` as an observed/assumed value, but set
  `speed_calibrated=true` only when the payload also carries
  `speed_calibrated == true` or a non-empty calibration-model identifier.
  Existing EventLogger records do not carry that proof, so their speed
  remains explicitly uncalibrated.

For this single-launcher sequential stream, `outcome_scored` updates the most
recent outcome-unknown shot in the same session. Unknown event/schema records
become warnings, not shots.

- [x] **Step 5: Implement conservative legacy parsing**

Implement:

```rust
pub fn parse_legacy_shot(
    value: &Value,
    source: &Path,
    sequence: usize,
) -> Result<Option<ShotRow>, String>
```

Recognize explicit:

- `action == "shoot"` plus
  `fire_outcome.serial_shoot_sent == true` as launched;
- `action == "shoot_blocked"` as blocked;
- `decision == "FIRE_SENT"` as launched;
- `decision == "FIRE_BLOCKED"` as blocked.

Other `shoot` text is `state="unknown"`, never launched. Read nested
`angles_clamped` or `calculated_pitch_yaw_v`; use explicit finite
`speed_mps`; use RPM fields without converting them. Ignore `visual_check`
for outcome. Only `hit`, `success`, `result`, or an explicit
`outcome_scored` record may assign hit/miss/invalid.

- [x] **Step 6: Run shot tests**

Run:

```bash
cd project-cam-desktop/src-tauri
cargo test evidence::shots::tests -- --nocapture
```

Expected: all semantic tests pass, particularly the `visual_check` negative
control.

### Task 6: Discover, merge, filter, and expose evidence

**Files:**
- Modify: `project-cam-desktop/src-tauri/src/evidence/mod.rs`
- Modify: `project-cam-desktop/src-tauri/src/main.rs`

- [x] **Step 1: Write failing repository-tree aggregation tests**

Construct a temporary tree containing:

- one desktop manifest/lifecycle;
- one training index row with the same session ID;
- one historical training row;
- one `events.jsonl` with an aim and block;
- one malformed line;
- one maintenance manifest.

Assert:

```rust
let result = load_session_evidence(&root, None, 50, 200, None).unwrap();
assert_eq!(result.sessions.len(), 2);
assert_eq!(result.shots.len(), 1);
assert_eq!(result.shots[0].state, "blocked");
assert_eq!(result.summary.total_sessions, 2);
assert_eq!(result.summary.blocked_attempts, 1);
assert!(result.sources.iter().any(|s| s.rejected == 1));
```

Add an athlete-filter test using Unicode case-insensitive comparison via
lowercasing, and a limit test proving newest rows are retained.

- [x] **Step 2: Run to prove RED**

Run:

```bash
cd project-cam-desktop/src-tauri
cargo test evidence::tests -- --nocapture
```

Expected: compilation fails because the orchestrator and aggregate DTOs are
missing.

- [x] **Step 3: Implement discovery and deterministic merge**

Define:

```rust
#[derive(Clone, Debug, Serialize)]
pub struct EvidenceSummary {
    pub total_sessions: usize,
    pub complete_sessions: usize,
    pub aborted_or_failed_sessions: usize,
    pub partial_sessions: usize,
    pub launched_attempts: usize,
    pub blocked_attempts: usize,
}

#[derive(Clone, Debug, Serialize)]
pub struct SessionEvidence {
    pub generated_at: String,
    pub sessions: Vec<SessionRow>,
    pub shots: Vec<ShotRow>,
    pub summary: EvidenceSummary,
    pub sources: Vec<SourceStatus>,
}

pub fn load_session_evidence(
    repo_root: &Path,
    athlete_filter: Option<&str>,
    session_limit: usize,
    shot_limit: usize,
    running_session_id: Option<&str>,
) -> Result<SessionEvidence, String>
```

Use bounded constants:

```rust
const MAX_SOURCE_BYTES: u64 = 2_000_000;
const MAX_SOURCE_FILES: usize = 200;
const MAX_SESSIONS: usize = 500;
const MAX_SHOTS: usize = 2_000;
```

Clamp caller limits to those constants. Discover only:

- `garage_lab_combined/output/sessions/*/{manifest.json,lifecycle.jsonl,events.jsonl}`;
- `garage_lab_combined/output/training_logs/sessions_index.jsonl`;
- `garage_lab_combined/output/blm_logs/*.jsonl`;
- `output/blm_logs/*.jsonl`.

Merge rows by session ID in a `BTreeMap`. Training fields enrich the desktop
manifest row; they do not overwrite its launch kind/source identity.
Maintenance rows are excluded unless they have training/launcher domain
evidence. Sort sessions by newest timestamp descending and shots by timestamp
descending, then apply filters and limits.

Status precedence is deterministic:

- `running_session_id` matches -> `running`;
- a training row -> `complete` or `aborted` from its own schema;
- `launch_failed` -> `failed`;
- `process_exited` with code `0`, `130`, or `-2` -> `complete`;
- `process_exited` with any other numeric code -> `failed`;
- a manifest/lifecycle stream without a terminal event -> `partial`.

- [x] **Step 4: Add the Tauri command**

Add:

```rust
#[tauri::command]
fn load_session_evidence(
    state: State<PipelineState>,
    repo_root: String,
    athlete_filter: Option<String>,
    session_limit: usize,
    shot_limit: usize,
) -> Result<evidence::SessionEvidence, String> {
    let running = state
        .current_session
        .lock()
        .map_err(|_| "session state poisoned".to_string())?
        .as_ref()
        .map(|s| s.session_id.clone());
    evidence::load_session_evidence(
        Path::new(&repo_root),
        athlete_filter.as_deref(),
        session_limit,
        shot_limit,
        running.as_deref(),
    )
}
```

Register it in `generate_handler!`.

- [x] **Step 5: Run all Rust tests**

Run:

```bash
cd project-cam-desktop/src-tauri
cargo fmt
cargo test
cargo clippy --all-targets -- -D warnings
```

Expected: all tests pass and clippy reports no warnings.

### Task 7: Add the typed frontend evidence client

**Files:**
- Create: `project-cam-desktop/src/evidence.ts`
- Modify: `project-cam-desktop/src/App.tsx`
- Modify: `tests/test_desktop_session_evidence_contracts.py`

- [x] **Step 1: Add failing frontend contracts**

Append:

```python
EVIDENCE_TS = DESKTOP / "src/evidence.ts"


def test_frontend_has_one_typed_evidence_boundary():
    text = EVIDENCE_TS.read_text(encoding="utf-8")
    assert 'invoke<SessionEvidence>("load_session_evidence"' in text
    assert "BROWSER PREVIEW · NO LOCAL DATA ACCESS" in text
    app = APP.read_text(encoding="utf-8")
    assert "evidenceRevision" in app
    assert "setEvidenceRevision" in app
```

- [x] **Step 2: Run to prove RED**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py::test_frontend_has_one_typed_evidence_boundary -v
```

Expected: failure because `src/evidence.ts` does not exist.

- [x] **Step 3: Implement types and loader**

Define exact TypeScript counterparts for `SessionRow`, `ShotRow`,
`SourceStatus`, `EvidenceSummary`, and `SessionEvidence`. Add:

```ts
export const EMPTY_EVIDENCE: SessionEvidence = {
  generated_at: "",
  sessions: [],
  shots: [],
  summary: {
    total_sessions: 0,
    complete_sessions: 0,
    aborted_or_failed_sessions: 0,
    partial_sessions: 0,
    launched_attempts: 0,
    blocked_attempts: 0,
  },
  sources: [],
};

export async function loadEvidence(
  repoRoot: string,
  athleteFilter?: string
): Promise<SessionEvidence> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
    return {
      ...EMPTY_EVIDENCE,
      sources: [{
        path: "BROWSER PREVIEW · NO LOCAL DATA ACCESS",
        accepted: 0,
        rejected: 0,
        truncated: false,
        error: "",
      }],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<SessionEvidence>("load_session_evidence", {
    repoRoot,
    athleteFilter: athleteFilter?.trim() || null,
    sessionLimit: 100,
    shotLimit: 500,
  });
}
```

In `App.tsx`, increment `evidenceRevision` on every pipeline exit and pass it,
plus the shared athlete name, to both new evidence views.

- [x] **Step 4: Run type/build checks**

Run:

```bash
npm --prefix project-cam-desktop run build
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py -v
```

Expected: TypeScript build succeeds and all current contract tests pass.

### Task 8: Replace synthetic analytics with real Sessions and Shots views

**Files:**
- Create: `project-cam-desktop/src/views/SessionsView.tsx`
- Create: `project-cam-desktop/src/views/ShotsView.tsx`
- Delete: `project-cam-desktop/src/views/AnalyticsView.tsx`
- Delete: `project-cam-desktop/src/views/MatchesView.tsx`
- Modify: `project-cam-desktop/src/App.tsx`
- Modify: `project-cam-desktop/src/components/Sidebar.tsx`
- Modify: `project-cam-desktop/src/data.ts`
- Modify: `tests/test_desktop_session_evidence_contracts.py`

- [x] **Step 1: Add failing production-honesty contracts**

Append:

```python
SIDEBAR = DESKTOP / "src/components/Sidebar.tsx"
DATA = DESKTOP / "src/data.ts"
SESSIONS = DESKTOP / "src/views/SessionsView.tsx"
SHOTS = DESKTOP / "src/views/ShotsView.tsx"


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
    for forbidden in ("KPIS", "TREND", "RADAR", "MATCHES", "PREVIEW SEASON",
                      "51 km/h", "RATING"):
        assert forbidden not in data
    sessions = SESSIONS.read_text(encoding="utf-8")
    shots = SHOTS.read_text(encoding="utf-8")
    assert "loadEvidence" in sessions
    assert "loadEvidence" in shots
    assert "UNCALIBRATED" in shots
    assert "BLOCKED" in shots
    assert "visual_check" not in shots
```

- [x] **Step 2: Run to prove RED**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py::test_navigation_and_views_use_real_sessions_and_shots \
  tests/test_desktop_session_evidence_contracts.py::test_production_data_has_no_synthetic_athlete_or_shot_rows -v
```

Expected: both tests fail.

- [x] **Step 3: Implement `SessionsView`**

Props:

```ts
{ athlete: string; evidenceRevision: number }
```

On mount, explicit refresh, and revision change, call `loadEvidence`.
Maintain `loading`, `error`, and last successful evidence independently so a
failed refresh does not erase already displayed rows.

Render:

- header `SESSIONS` and athlete or `ALL ATHLETES`;
- four factual cards: total, complete, aborted/failed, partial;
- source-warning banner when rejected/truncated/error counts are nonzero;
- honest empty state when no sessions exist;
- newest-first rows with title, athlete, status, duration, headline, and
  source schema;
- a Recharts line/area trend only for one drill/metric pair with at least two
  finite points. Do not combine unlike metrics.

The initial comparable metrics are:

- `balance.summary.avg_sway_mm`;
- `gk_save.summary.save_pct`;
- `gk_save.summary.avg_reaction_s`;
- `line_hops.summary.best_rate_hz`;
- `shuttle.summary.best_total_s`;
- `gk_updown.summary.avg_recovery_s`.

If no pair has two values, show `NOT ENOUGH COMPARABLE SESSIONS`.

- [x] **Step 4: Implement `ShotsView`**

Use the same loading/error/refresh pattern. Render columns:

```text
SESSION | TIME | TARGET | RPM L/R | SPEED | PITCH/YAW | STATE | OUTCOME/REASON
```

Rules:

- speed is `<value> m/s` only when `speed_calibrated` and `speed_mps` are set;
- an uncalibrated finite `speed_mps` renders
  `<value> m/s · UNCALIBRATED`;
- RPM present but no speed renders `UNCALIBRATED`;
- `blocked` is red/orange and always shows `block_reason`;
- `launched` with unknown outcome renders `OUTCOME UNKNOWN`;
- `unknown` never receives a green success icon;
- missing values render `—`.

- [x] **Step 5: Replace navigation and remove fake data**

Change `ViewId` and navigation to:

```ts
"CONTROL" | "TRAINING" | "SESSIONS" | "SHOTS"
```

Wire the new views in `App.tsx`, delete the two superseded view files, and
remove `KPIS`, `TREND`, `RADAR`, `MATCHES`, `Kpi`, and `Match` from
`data.ts`. Retain launch/readiness constants only.

- [x] **Step 6: Run UI verification**

Run:

```bash
npm --prefix project-cam-desktop run build
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py -v
```

Expected: production build succeeds and all session-evidence contracts pass.

### Task 9: Make readiness presentation fail closed

**Files:**
- Modify: `project-cam-desktop/src/data.ts`
- Modify: `project-cam-desktop/src/views/ControlView.tsx`
- Modify: `project-cam-desktop/src-tauri/src/main.rs`
- Modify: `tests/test_desktop_session_evidence_contracts.py`

- [x] **Step 1: Add failing readiness-honesty test**

Append:

```python
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
```

- [x] **Step 2: Run to prove RED**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py::test_readiness_never_falls_back_to_static_green -v
```

Expected: failure on static green fallback and operational labels.

- [x] **Step 3: Implement unknown-first frontend state**

Replace `READINESS` with:

```ts
export const UNKNOWN_READINESS: Readiness[] = [
  { label: "CAMERA DEVICES", status: "UNKNOWN", ready: false },
  { label: "CALIBRATION FILES", status: "UNKNOWN", ready: false },
  { label: "FACE MODEL FILES", status: "UNKNOWN", ready: false },
  { label: "GALLERY FILE", status: "UNKNOWN", ready: false },
];
```

Initialize from this array. On command failure set all items to
`status: "CHECK FAILED", ready: false`. In browser preview keep unknown.
Rename the visible section to `LOCAL FILE / DEVICE CHECKS` and add:

```text
Presence checks only — not camera, model, GPU, launcher, or E-stop readiness.
```

- [x] **Step 4: Remove operational language from Rust presence checks**

Use:

- camera status `<connected>/<total> DEVICE NODES`;
- calibration `PRESENT`/`MISSING`;
- face models `PRESENT`/`MISSING`;
- gallery `PRESENT`/`EMPTY`.

The boolean continues to mean only that the local presence check passed.

- [x] **Step 5: Run readiness and build checks**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py -v
npm --prefix project-cam-desktop run build
cd project-cam-desktop/src-tauri && cargo test
```

Expected: all pass.

### Task 10: Documentation, hygiene, and final verification

**Files:**
- Modify: `project-cam-desktop/README.md`
- Modify: `CLAUDE.md`
- Verify: every file in this plan

- [x] **Step 1: Update the desktop README**

Document:

- canonical `garage_lab_combined/output/sessions/<session_id>/` layout;
- manifest/lifecycle/event log roles;
- `SESSIONS` and `SHOTS` as real-data views;
- historical training/BLM compatibility;
- unknown/partial/corrupt-source behavior;
- RPM versus calibrated speed distinction;
- the exact Rust/test/build commands.

Remove the stale paragraph claiming Analytics/Matches use demo data and the
obsolete shell-plugin wiring example.

- [x] **Step 2: Run the focused Python evidence set**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_event_log.py \
  tests/test_training_drills.py \
  tests/test_desktop_training_contracts.py \
  tests/test_desktop_session_evidence_contracts.py \
  tests/test_launcher_runtime_fire_control.py \
  tests/test_fire_control.py \
  tests/test_firing_line.py -v
```

Expected: exit code 0 with no hardware access.

- [x] **Step 3: Run Rust and frontend barriers**

Run:

```bash
cd project-cam-desktop/src-tauri
cargo fmt --check
cargo test
cargo clippy --all-targets -- -D warnings
cd ..
npm run build
```

Expected: all commands exit 0.

- [ ] **Step 4: Run the complete Python suite — BLOCKED in this sandbox**

The full run collects 682 tests but stalls in the API/TestClient group.
The isolated `test_health_ok_without_hardware` exceeded a 20-second timeout.
The remaining 657 hardware-free tests pass; re-run the 25 API tests in the
known-good API/CI environment before integration.

Run:

```bash
cd /home/hanush/Desktop/Project_Cam
venv/bin/python -m pytest -o addopts=''
```

Expected: exit code 0. Record the exact fresh count in `CLAUDE.md`; do not
copy the previous `669 passed` count after adding tests.

- [x] **Step 5: Append the completion record**

Add a dated `CLAUDE.md` entry recording:

- default-on desktop session manifest/lifecycle evidence;
- inherited training/launcher session IDs;
- bounded Rust normalization and its supported schemas;
- removal of synthetic production analytics/shot rows;
- correction that `visual_check` is aim appearance, not hit/miss;
- fail-closed readiness presentation;
- exact Rust, frontend, focused Python, and full Python results;
- no hardware validation and RPM/placement P0A still open;
- no commit created.

- [x] **Step 6: Run repository hygiene checks**

Run:

```bash
git diff --check
git status --short
git diff -- \
  src/project_cam/training/drills.py \
  garage_lab_combined/scripts/training_drill.py \
  garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  tests/test_training_drills.py \
  tests/test_launcher_runtime_fire_control.py \
  tests/test_desktop_training_contracts.py \
  tests/test_desktop_session_evidence_contracts.py \
  CLAUDE.md
```

Because `project-cam-desktop/` is currently untracked as a directory, inspect
its changed files directly with:

```bash
git status --short -- project-cam-desktop
rg -n "KPIS|TREND|RADAR|PREVIEW SESSION|6/6 ONLINE|visual_check.*outcome" \
  project-cam-desktop/src project-cam-desktop/src-tauri/src
```

Expected: no whitespace errors; no synthetic production data or green
readiness fallback; all unrelated user changes remain present.

- [x] **Step 7: Prepare the evidence handoff**

Report:

- session schemas and canonical paths;
- which historical sources are normalized;
- exact test/build results;
- that `visual_check` no longer becomes HIT/MISS;
- that missing speed remains `UNCALIBRATED`;
- that active hardware readiness, P0A measurements, and live validation remain
  open;
- that no commit, push, or PR was created.
