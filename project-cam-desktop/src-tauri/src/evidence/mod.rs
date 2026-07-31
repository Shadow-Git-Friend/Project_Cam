mod jsonl;
mod shots;
mod training;

use chrono::{SecondsFormat, Utc};
use serde::Serialize;
use serde_json::Value;
use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

use jsonl::read_jsonl_tail;
use shots::{parse_event_log, parse_legacy_shot};
use training::parse_training_record;

const MAX_SOURCE_BYTES: u64 = 2_000_000;
const MAX_SOURCE_FILES: usize = 200;
const MAX_SESSIONS: usize = 500;
const MAX_SHOTS: usize = 2_000;
const MANIFEST_SCHEMA: &str = "project_cam.desktop.session_manifest.v1";
const LIFECYCLE_SCHEMA: &str = "project_cam.desktop.lifecycle.v1";

#[derive(Clone, Debug, Serialize)]
pub struct SessionRow {
    pub session_id: String,
    pub source_schema: String,
    pub source_path: String,
    pub athlete: String,
    /// Stable athlete identity when the record carries one. The display name is
    /// editable and must never be the join key, so this is `None` rather than
    /// an empty string for unlinked historical sessions.
    pub athlete_id: Option<String>,
    pub launch_kind: String,
    pub drill: String,
    pub title: String,
    pub started_at: String,
    pub ended_at: String,
    pub status: String,
    pub headline: String,
    pub summary: Value,
    /// Raw comparability facts (`project_cam.capture_context.v1` + protocol),
    /// or `None` when the producing viewer sent none. Never a verdict: whether
    /// a session may seed a baseline is decided by the versioned comparison
    /// policy from these numbers, not frozen in here.
    pub evidence_context: Option<Value>,
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

fn slug_part(value: &str) -> String {
    let mut slug = String::new();
    let mut separator = false;
    for character in value.chars() {
        if character.is_ascii_alphanumeric() {
            slug.push(character.to_ascii_lowercase());
            separator = false;
        } else if !slug.is_empty() && !separator {
            slug.push('-');
            separator = true;
        }
    }
    slug.trim_matches('-').to_string()
}

pub(super) fn legacy_session_id(source: &Path, timestamp: &str) -> String {
    let source_name = source
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("source");
    let source_slug = slug_part(source_name);
    let timestamp_slug = slug_part(timestamp);
    format!(
        "legacy-{}-{}",
        if source_slug.is_empty() {
            "source"
        } else {
            &source_slug
        },
        if timestamp_slug.is_empty() {
            "unknown-time"
        } else {
            &timestamp_slug
        }
    )
}

fn read_json_object(path: &Path) -> Result<Value, String> {
    let metadata =
        fs::metadata(path).map_err(|error| format!("stat {}: {error}", path.display()))?;
    if metadata.len() > MAX_SOURCE_BYTES {
        return Err(format!(
            "{} exceeds the {} byte evidence limit",
            path.display(),
            MAX_SOURCE_BYTES
        ));
    }
    let bytes = fs::read(path).map_err(|error| format!("read {}: {error}", path.display()))?;
    let value: Value = serde_json::from_slice(&bytes)
        .map_err(|error| format!("parse {}: {error}", path.display()))?;
    if !value.is_object() {
        return Err(format!("{} is not a JSON object", path.display()));
    }
    Ok(value)
}

fn source_status(path: &Path) -> SourceStatus {
    SourceStatus {
        path: path.to_string_lossy().into_owned(),
        accepted: 0,
        rejected: 0,
        truncated: false,
        error: String::new(),
    }
}

fn string_value(record: &serde_json::Map<String, Value>, key: &str) -> String {
    record
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

fn lifecycle_status(path: &Path, session_id: &str, row: &mut SessionRow) -> SourceStatus {
    let mut status = source_status(path);
    let parsed = match read_jsonl_tail(path, MAX_SOURCE_BYTES) {
        Ok(parsed) => parsed,
        Err(error) => {
            status.error = error;
            return status;
        }
    };
    status.rejected = parsed.rejected;
    status.truncated = parsed.truncated;
    for value in parsed.values {
        let Some(record) = value.as_object() else {
            status.rejected += 1;
            continue;
        };
        if record.get("schema").and_then(Value::as_str) != Some(LIFECYCLE_SCHEMA)
            || record.get("session_id").and_then(Value::as_str) != Some(session_id)
        {
            status.rejected += 1;
            continue;
        }
        status.accepted += 1;
        let timestamp = string_value(record, "timestamp");
        match record.get("event").and_then(Value::as_str) {
            Some("launch_failed") => {
                row.status = "failed".to_string();
                row.ended_at = timestamp;
            }
            Some("process_exited") => {
                let code = record
                    .get("detail")
                    .and_then(Value::as_object)
                    .and_then(|detail| detail.get("code"))
                    .and_then(Value::as_i64);
                row.status = match code {
                    Some(0 | 130 | -2) => "complete",
                    Some(_) => "failed",
                    None => "partial",
                }
                .to_string();
                row.ended_at = timestamp;
            }
            Some(
                "launch_requested" | "process_started" | "stop_requested" | "signal_sent"
                | "signal_failed",
            ) => {}
            Some(other) => row
                .warnings
                .push(format!("unknown lifecycle event {other:?}")),
            None => {
                status.rejected += 1;
                status.accepted = status.accepted.saturating_sub(1);
            }
        }
    }
    status
}

fn manifest_row(path: &Path) -> Result<SessionRow, String> {
    let value = read_json_object(path)?;
    let record = value.as_object().expect("read_json_object checked object");
    if record.get("schema").and_then(Value::as_str) != Some(MANIFEST_SCHEMA) {
        return Err(format!("unsupported manifest schema in {}", path.display()));
    }
    let session_id = string_value(record, "session_id");
    if session_id.trim().is_empty() {
        return Err(format!("manifest {} has no session_id", path.display()));
    }
    let launch_kind = string_value(record, "launch_kind");
    let label = string_value(record, "label");
    Ok(SessionRow {
        session_id,
        source_schema: MANIFEST_SCHEMA.to_string(),
        source_path: path.to_string_lossy().into_owned(),
        athlete: string_value(record, "athlete"),
        athlete_id: None,
        launch_kind: if launch_kind.is_empty() {
            "unknown".to_string()
        } else {
            launch_kind.clone()
        },
        drill: string_value(record, "drill"),
        title: if label.is_empty() {
            launch_kind.to_ascii_uppercase()
        } else {
            label
        },
        started_at: string_value(record, "created_at"),
        ended_at: String::new(),
        status: "partial".to_string(),
        headline: String::new(),
        summary: serde_json::json!({}),
        evidence_context: None,
        warnings: Vec::new(),
    })
}

fn insert_shot_session(
    sessions: &mut BTreeMap<String, SessionRow>,
    domains: &mut HashSet<String>,
    shot: &ShotRow,
) {
    domains.insert(shot.session_id.clone());
    sessions
        .entry(shot.session_id.clone())
        .or_insert_with(|| SessionRow {
            session_id: shot.session_id.clone(),
            source_schema: shot.source_schema.clone(),
            source_path: shot.source_path.clone(),
            athlete: String::new(),
            athlete_id: None,
            launch_kind: "launcher".to_string(),
            drill: String::new(),
            title: "LAUNCHER SESSION".to_string(),
            started_at: shot.timestamp.clone(),
            ended_at: shot.timestamp.clone(),
            status: "partial".to_string(),
            headline: String::new(),
            summary: serde_json::json!({}),
            evidence_context: None,
            warnings: Vec::new(),
        });
}

fn merge_training(
    sessions: &mut BTreeMap<String, SessionRow>,
    domains: &mut HashSet<String>,
    training: SessionRow,
) {
    domains.insert(training.session_id.clone());
    if let Some(existing) = sessions.get_mut(&training.session_id) {
        if !training.athlete.is_empty() {
            existing.athlete = training.athlete;
        }
        existing.drill = training.drill;
        existing.title = training.title;
        existing.started_at = training.started_at;
        existing.ended_at = training.ended_at;
        existing.status = training.status;
        existing.headline = training.headline;
        existing.summary = training.summary;
        existing.warnings.extend(training.warnings);
    } else {
        sessions.insert(training.session_id.clone(), training);
    }
}

/// Directory entries NEWEST FIRST.
///
/// Both scan loops stop at `MAX_SOURCE_FILES`, so the traversal order decides
/// which evidence survives the cap. Session directories are named
/// `s-%Y%m%dT%H%M%S%3fZ-<uuid>` — fixed width, so a plain ascending sort is
/// chronological and would have kept the OLDEST sources and silently dropped
/// every newer session once a coach passed the cap. Sorting descending makes
/// the cap drop ancient history instead, which is the only useful direction:
/// the views rank newest-first anyway, and a row never read cannot be ranked.
fn directory_entries_newest_first(path: &Path, directories: bool) -> Vec<PathBuf> {
    let Ok(entries) = fs::read_dir(path) else {
        return Vec::new();
    };
    let mut paths: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let kind = entry.file_type().ok()?;
            if (directories && kind.is_dir()) || (!directories && kind.is_file()) {
                Some(entry.path())
            } else {
                None
            }
        })
        .collect();
    paths.sort();
    paths.reverse();
    paths
}

fn evidence_summary(sessions: &[SessionRow], shots: &[ShotRow]) -> EvidenceSummary {
    EvidenceSummary {
        total_sessions: sessions.len(),
        complete_sessions: sessions
            .iter()
            .filter(|row| row.status == "complete")
            .count(),
        aborted_or_failed_sessions: sessions
            .iter()
            .filter(|row| matches!(row.status.as_str(), "aborted" | "failed"))
            .count(),
        partial_sessions: sessions
            .iter()
            .filter(|row| !matches!(row.status.as_str(), "complete" | "aborted" | "failed"))
            .count(),
        launched_attempts: shots.iter().filter(|row| row.state == "launched").count(),
        blocked_attempts: shots.iter().filter(|row| row.state == "blocked").count(),
    }
}

pub fn load_session_evidence(
    repo_root: &Path,
    athlete_filter: Option<&str>,
    session_limit: usize,
    shot_limit: usize,
    running_session_id: Option<&str>,
) -> Result<SessionEvidence, String> {
    if !repo_root.is_dir() {
        return Err(format!(
            "repository root does not exist: {}",
            repo_root.display()
        ));
    }

    let mut sessions: BTreeMap<String, SessionRow> = BTreeMap::new();
    let mut domain_sessions = HashSet::new();
    let mut shots = Vec::new();
    let mut sources = Vec::new();
    let mut source_count = 0usize;

    let sessions_root = repo_root.join("garage_lab_combined/output/sessions");
    for session_dir in directory_entries_newest_first(&sessions_root, true) {
        if source_count >= MAX_SOURCE_FILES {
            break;
        }
        let manifest_path = session_dir.join("manifest.json");
        if manifest_path.is_file() {
            source_count += 1;
            let mut status = source_status(&manifest_path);
            match manifest_row(&manifest_path) {
                Ok(mut row) => {
                    status.accepted = 1;
                    let lifecycle_path = session_dir.join("lifecycle.jsonl");
                    if lifecycle_path.is_file() && source_count < MAX_SOURCE_FILES {
                        source_count += 1;
                        let session_id = row.session_id.clone();
                        sources.push(lifecycle_status(&lifecycle_path, &session_id, &mut row));
                    }
                    if row.launch_kind != "maintenance" {
                        domain_sessions.insert(row.session_id.clone());
                    }
                    sessions.insert(row.session_id.clone(), row);
                }
                Err(error) => {
                    status.rejected = 1;
                    status.error = error;
                }
            }
            sources.push(status);
        }

        let events_path = session_dir.join("events.jsonl");
        if events_path.is_file() && source_count < MAX_SOURCE_FILES {
            source_count += 1;
            let mut status = source_status(&events_path);
            match read_jsonl_tail(&events_path, MAX_SOURCE_BYTES) {
                Ok(parsed) => {
                    status.rejected = parsed.rejected;
                    status.truncated = parsed.truncated;
                    status.accepted = parsed.values.len();
                    let (parsed_shots, warnings) = parse_event_log(&parsed.values, &events_path);
                    if !warnings.is_empty() {
                        status.error = warnings.join("; ");
                    }
                    for shot in parsed_shots {
                        insert_shot_session(&mut sessions, &mut domain_sessions, &shot);
                        shots.push(shot);
                    }
                }
                Err(error) => status.error = error,
            }
            sources.push(status);
        }
    }

    let training_path =
        repo_root.join("garage_lab_combined/output/training_logs/sessions_index.jsonl");
    if training_path.is_file() && source_count < MAX_SOURCE_FILES {
        source_count += 1;
        let mut status = source_status(&training_path);
        match read_jsonl_tail(&training_path, MAX_SOURCE_BYTES) {
            Ok(parsed) => {
                status.rejected = parsed.rejected;
                status.truncated = parsed.truncated;
                for value in parsed.values {
                    match parse_training_record(&value, &training_path) {
                        Ok(training) => {
                            status.accepted += 1;
                            merge_training(&mut sessions, &mut domain_sessions, training);
                        }
                        Err(_) => status.rejected += 1,
                    }
                }
            }
            Err(error) => status.error = error,
        }
        sources.push(status);
    }

    for log_root in [
        repo_root.join("garage_lab_combined/output/blm_logs"),
        repo_root.join("output/blm_logs"),
    ] {
        for path in directory_entries_newest_first(&log_root, false)
            .into_iter()
            .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("jsonl"))
        {
            if source_count >= MAX_SOURCE_FILES {
                break;
            }
            source_count += 1;
            let mut status = source_status(&path);
            match read_jsonl_tail(&path, MAX_SOURCE_BYTES) {
                Ok(parsed) => {
                    status.rejected = parsed.rejected;
                    status.truncated = parsed.truncated;
                    for value in parsed.values {
                        match parse_legacy_shot(&value, &path, shots.len() + 1) {
                            Ok(Some(shot)) => {
                                status.accepted += 1;
                                insert_shot_session(&mut sessions, &mut domain_sessions, &shot);
                                shots.push(shot);
                            }
                            Ok(None) => {}
                            Err(_) => status.rejected += 1,
                        }
                    }
                }
                Err(error) => status.error = error,
            }
            sources.push(status);
        }
    }

    if let Some(running) = running_session_id {
        if let Some(row) = sessions.get_mut(running) {
            row.status = "running".to_string();
            domain_sessions.insert(running.to_string());
        }
    }
    sessions.retain(|session_id, _| domain_sessions.contains(session_id));

    let filter = athlete_filter
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_lowercase);
    let mut rows: Vec<SessionRow> = sessions
        .into_values()
        .filter(|row| {
            filter
                .as_ref()
                .is_none_or(|needle| row.athlete.to_lowercase() == *needle)
        })
        .collect();
    rows.sort_by(|left, right| {
        right
            .started_at
            .cmp(&left.started_at)
            .then_with(|| right.session_id.cmp(&left.session_id))
    });
    rows.truncate(session_limit.clamp(1, MAX_SESSIONS));

    let retained_ids: HashSet<&str> = rows.iter().map(|row| row.session_id.as_str()).collect();
    shots.retain(|shot| retained_ids.contains(shot.session_id.as_str()));
    shots.sort_by(|left, right| {
        right
            .timestamp
            .cmp(&left.timestamp)
            .then_with(|| right.sequence.cmp(&left.sequence))
    });
    shots.truncate(shot_limit.clamp(1, MAX_SHOTS));

    let summary = evidence_summary(&rows, &shots);
    Ok(SessionEvidence {
        generated_at: Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true),
        sessions: rows,
        shots,
        summary,
        sources,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;
    use uuid::Uuid;

    fn write_json(path: &Path, value: Value) {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
    }

    fn repository_tree() -> PathBuf {
        let root =
            std::env::temp_dir().join(format!("project-cam-evidence-test-{}", Uuid::new_v4()));
        let sessions = root.join("garage_lab_combined/output/sessions");
        let desktop = sessions.join("desktop-1");
        write_json(
            &desktop.join("manifest.json"),
            serde_json::json!({
                "schema": "project_cam.desktop.session_manifest.v1",
                "session_id": "desktop-1",
                "created_at": "2026-07-29T10:00:00Z",
                "athlete": "Арлен",
                "launch_kind": "training",
                "drill": "balance",
                "label": "DRILL · BALANCE",
                "program": "bash",
                "args": [],
            }),
        );
        fs::write(
            desktop.join("lifecycle.jsonl"),
            concat!(
                "{\"schema\":\"project_cam.desktop.lifecycle.v1\",\"timestamp\":\"2026-07-29T10:00:00Z\",\"session_id\":\"desktop-1\",\"event\":\"launch_requested\",\"detail\":{}}\n",
                "{\"schema\":\"project_cam.desktop.lifecycle.v1\",\"timestamp\":\"2026-07-29T10:01:00Z\",\"session_id\":\"desktop-1\",\"event\":\"process_exited\",\"detail\":{\"code\":0}}\n",
            ),
        )
        .unwrap();
        fs::write(
            desktop.join("events.jsonl"),
            concat!(
                "{\"schema_version\":\"project_cam.closed_loop.event_log.v1\",\"session_id\":\"desktop-1\",\"timestamp\":1,\"wall_clock_iso\":\"2026-07-29T10:00:30Z\",\"event_type\":\"aim_command_sent\",\"source\":\"launcher_runtime\",\"payload\":{\"joint_name\":\"right_knee\",\"wheel_left_rpm\":800,\"wheel_right_rpm\":810}}\n",
                "{\"schema_version\":\"project_cam.closed_loop.event_log.v1\",\"session_id\":\"desktop-1\",\"timestamp\":2,\"wall_clock_iso\":\"2026-07-29T10:00:31Z\",\"event_type\":\"safety_gate_blocked\",\"source\":\"launcher_runtime\",\"payload\":{\"serial_shoot_sent\":false,\"reason\":\"firing_line_blocked\"}}\n",
            ),
        )
        .unwrap();

        let maintenance = sessions.join("maintenance-1");
        write_json(
            &maintenance.join("manifest.json"),
            serde_json::json!({
                "schema": "project_cam.desktop.session_manifest.v1",
                "session_id": "maintenance-1",
                "created_at": "2026-07-29T11:00:00Z",
                "athlete": "",
                "launch_kind": "maintenance",
                "drill": "",
                "label": "FACE MODEL SETUP",
            }),
        );

        let training = root.join("garage_lab_combined/output/training_logs/sessions_index.jsonl");
        fs::create_dir_all(training.parent().unwrap()).unwrap();
        fs::write(
            training,
            concat!(
                "{\"schema\":\"project_cam.training.v1\",\"session_id\":\"desktop-1\",\"drill\":\"balance\",\"title\":\"SINGLE-LEG BALANCE\",\"role\":\"FIELD PLAYER\",\"athlete\":\"Арлен\",\"started\":\"2026-07-29T10:00:00Z\",\"ended\":\"2026-07-29T10:01:00Z\",\"aborted\":false,\"headline\":\"sway 31 mm\",\"summary\":{\"avg_sway_mm\":31.0}}\n",
                "{\"schema\":\"project_cam.training.v1\",\"drill\":\"gk_save\",\"title\":\"SAVE THE CORNERS\",\"role\":\"GOALKEEPER\",\"athlete\":\"Bob\",\"started\":\"2026-07-28T10:00:00Z\",\"ended\":\"2026-07-28T10:01:00Z\",\"aborted\":false,\"headline\":\"4/5 saves\",\"summary\":{\"save_pct\":80.0}}\n",
                "not-json\n",
            ),
        )
        .unwrap();
        root
    }

    #[test]
    fn repository_sources_merge_without_counting_maintenance_as_a_session() {
        let root = repository_tree();
        let result = load_session_evidence(&root, None, 50, 200, None).unwrap();
        assert_eq!(result.sessions.len(), 2);
        assert_eq!(result.shots.len(), 1);
        assert_eq!(result.shots[0].state, "blocked");
        assert_eq!(result.summary.total_sessions, 2);
        assert_eq!(result.summary.blocked_attempts, 1);
        assert!(result.sources.iter().any(|source| source.rejected == 1));
        let desktop = result
            .sessions
            .iter()
            .find(|row| row.session_id == "desktop-1")
            .unwrap();
        assert_eq!(desktop.headline, "sway 31 mm");
        assert_eq!(desktop.status, "complete");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn athlete_filter_is_unicode_case_insensitive_and_limits_keep_newest() {
        let root = repository_tree();
        let filtered = load_session_evidence(&root, Some("  арЛЕН "), 50, 200, None).unwrap();
        assert_eq!(filtered.sessions.len(), 1);
        assert_eq!(filtered.sessions[0].session_id, "desktop-1");
        assert_eq!(filtered.shots.len(), 1);

        let limited = load_session_evidence(&root, None, 1, 200, None).unwrap();
        assert_eq!(limited.sessions.len(), 1);
        assert_eq!(limited.sessions[0].session_id, "desktop-1");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn source_cap_keeps_the_newest_sessions_not_the_oldest() {
        // Both scan loops stop at MAX_SOURCE_FILES, so traversal order decides
        // which evidence survives. Session ids are fixed-width timestamps, so a
        // plain ascending sort kept the OLDEST and silently dropped everything
        // newer once a coach passed the cap — the views could then never show a
        // recent session, because a row never read cannot be ranked.
        let root = repository_tree();
        let sessions_root = root.join("garage_lab_combined/output/sessions");
        fs::create_dir_all(&sessions_root).unwrap();
        for day in 1..=6 {
            let id = format!("s-202607{day:02}T100000000Z-{}", Uuid::new_v4().simple());
            let dir = sessions_root.join(&id);
            fs::create_dir_all(&dir).unwrap();
            write_json(
                &dir.join("manifest.json"),
                serde_json::json!({
                    "schema": MANIFEST_SCHEMA,
                    "session_id": id,
                    "athlete": "Ann",
                    "launch_kind": "training",
                    "drill": "balance",
                    "label": "SINGLE-LEG BALANCE",
                    "started_at": format!("2026-07-{day:02}T10:00:00Z"),
                }),
            );
        }

        let ordered = directory_entries_newest_first(&sessions_root, true);
        let names: Vec<String> = ordered
            .iter()
            .map(|path| path.file_name().unwrap().to_string_lossy().into_owned())
            .collect();
        assert!(names.len() >= 6);
        assert!(
            names[0] > names[names.len() - 1],
            "traversal must be newest-first, got {names:?}"
        );
        assert!(names[0].starts_with("s-20260706"), "got {:?}", names[0]);

        // End to end: the newest day must be present in the returned rows.
        let evidence = load_session_evidence(&root, None, 500, 500, None).unwrap();
        assert!(
            evidence
                .sessions
                .iter()
                .any(|row| row.session_id.starts_with("s-20260706")),
            "newest session missing from evidence"
        );
    }

    #[test]
    fn current_session_overrides_missing_terminal_lifecycle() {
        let root = repository_tree();
        let running = load_session_evidence(&root, None, 50, 200, Some("desktop-1")).unwrap();
        assert_eq!(
            running
                .sessions
                .iter()
                .find(|row| row.session_id == "desktop-1")
                .unwrap()
                .status,
            "running"
        );
        fs::remove_dir_all(root).unwrap();
    }
}
