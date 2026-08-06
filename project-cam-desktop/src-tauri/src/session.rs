use chrono::{SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
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
    /// An operator console that holds the launcher's serial link. Added
    /// deliberately on 2026-08-04 with the BLM console profile: before that no
    /// profile could actuate the launcher at all, and a test asserted this
    /// variant's absence. It serializes as `"launcher"`, the same string
    /// historical BLM shot logs already carry, so the evidence reader merges
    /// desktop consoles and legacy rows into one concept.
    Launcher,
    #[default]
    Maintenance,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct LaunchContext {
    pub athlete: Option<String>,
    /// Stable identity, separate from the editable display name. Recorded in
    /// the manifest; never passed on a command line.
    #[serde(default)]
    pub athlete_id: Option<String>,
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
    /// Backend-decided label and display command. Returned so the MISSION LOG
    /// can name the launch without the frontend ever knowing a path.
    pub label: String,
    pub command: String,
}

impl SessionHandle {
    pub fn receipt(&self, label: &str, command: &str) -> LaunchReceipt {
        LaunchReceipt {
            session_id: self.session_id.clone(),
            session_dir: self.session_dir.to_string_lossy().into_owned(),
            label: label.to_string(),
            command: command.to_string(),
        }
    }

    pub fn event_log_path(&self) -> PathBuf {
        self.session_dir.join("events.jsonl")
    }
}

fn utc_now() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

pub fn create_session(
    repo_root: &Path,
    context: &LaunchContext,
    program: &str,
    args: &[String],
    label: &str,
) -> Result<SessionHandle, String> {
    if !repo_root.is_dir() {
        return Err(format!(
            "repository root does not exist: {}",
            repo_root.display()
        ));
    }

    let sessions_root = repo_root.join("garage_lab_combined/output/sessions");
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(&sessions_root)
        .map_err(|error| format!("create session root: {error}"))?;

    let session_id = format!(
        "s-{}-{}",
        Utc::now().format("%Y%m%dT%H%M%S%3fZ"),
        Uuid::new_v4().simple()
    );
    let session_dir = sessions_root.join(&session_id);
    fs::DirBuilder::new()
        .mode(0o700)
        .create(&session_dir)
        .map_err(|error| format!("create session directory: {error}"))?;

    let manifest = json!({
        "schema": MANIFEST_SCHEMA,
        "session_id": session_id,
        "created_at": utc_now(),
        "athlete": context.athlete.as_deref().unwrap_or(""),
        "athlete_id": context.athlete_id.as_deref().unwrap_or(""),
        "launch_kind": context.launch_kind,
        "drill": context.drill.as_deref().unwrap_or(""),
        "program": program,
        "args": args,
        "label": label,
    });
    let bytes = serde_json::to_vec_pretty(&manifest)
        .map_err(|error| format!("serialize session manifest: {error}"))?;
    let temp_path = session_dir.join("manifest.json.tmp");
    let manifest_path = session_dir.join("manifest.json");
    let mut temp = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temp_path)
        .map_err(|error| format!("create session manifest: {error}"))?;
    temp.write_all(&bytes)
        .map_err(|error| format!("write session manifest: {error}"))?;
    temp.sync_all()
        .map_err(|error| format!("sync session manifest: {error}"))?;
    fs::rename(&temp_path, &manifest_path)
        .map_err(|error| format!("publish session manifest: {error}"))?;

    let handle = SessionHandle {
        session_id,
        session_dir,
    };
    append_lifecycle(&handle, "launch_requested", json!({}))?;
    Ok(handle)
}

pub fn append_lifecycle(handle: &SessionHandle, event: &str, detail: Value) -> Result<(), String> {
    let record = json!({
        "schema": LIFECYCLE_SCHEMA,
        "timestamp": utc_now(),
        "session_id": handle.session_id,
        "event": event,
        "detail": detail,
    });
    let mut bytes = serde_json::to_vec(&record)
        .map_err(|error| format!("serialize lifecycle event: {error}"))?;
    bytes.push(b'\n');
    let mut output = OpenOptions::new()
        .append(true)
        .create(true)
        .mode(0o600)
        .open(handle.session_dir.join("lifecycle.jsonl"))
        .map_err(|error| format!("open lifecycle log: {error}"))?;
    output
        .write_all(&bytes)
        .map_err(|error| format!("append lifecycle event: {error}"))?;
    output
        .flush()
        .map_err(|error| format!("flush lifecycle event: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn repo() -> PathBuf {
        let root =
            std::env::temp_dir().join(format!("project-cam-session-test-{}", Uuid::new_v4()));
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn manifest_is_opaque_atomic_and_unicode_safe() {
        let root = repo();
        let context = LaunchContext {
            athlete: Some("Арлен".into()),
            athlete_id: Some("uuid-1".into()),
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
        append_lifecycle(&handle, "process_started", serde_json::json!({"pgid": 42})).unwrap();
        append_lifecycle(&handle, "process_exited", serde_json::json!({"code": 0})).unwrap();
        let lines = fs::read_to_string(handle.session_dir.join("lifecycle.jsonl")).unwrap();
        let values: Vec<serde_json::Value> = lines
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
        assert_eq!(values.len(), 3);
        assert_eq!(values[0]["event"], "launch_requested");
        assert_eq!(values[1]["event"], "process_started");
        assert_eq!(values[2]["event"], "process_exited");
        assert!(values.iter().all(|v| v["session_id"] == handle.session_id));
        fs::remove_dir_all(root).unwrap();
    }
}
