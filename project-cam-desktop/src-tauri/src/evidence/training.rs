use super::{legacy_session_id, SessionRow};
use serde_json::{Map, Value};
use std::path::Path;

const TRAINING_SCHEMA: &str = "project_cam.training.v1";

fn required_string<'a>(record: &'a Map<String, Value>, key: &str) -> Result<&'a str, String> {
    record
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("training record requires non-empty string {key:?}"))
}

fn sanitize_json(value: &Value) -> Value {
    match value {
        Value::Array(values) => Value::Array(values.iter().map(sanitize_json).collect()),
        Value::Object(values) => Value::Object(
            values
                .iter()
                .map(|(key, value)| (key.clone(), sanitize_json(value)))
                .collect(),
        ),
        Value::Number(number) => match number.as_f64() {
            Some(value) if value.is_finite() => Value::Number(number.clone()),
            _ => Value::Null,
        },
        other => other.clone(),
    }
}

pub fn parse_training_record(value: &Value, source: &Path) -> Result<SessionRow, String> {
    let record = value
        .as_object()
        .ok_or_else(|| "training record must be an object".to_string())?;
    if record.get("schema").and_then(Value::as_str) != Some(TRAINING_SCHEMA) {
        return Err("unsupported training schema".to_string());
    }
    let drill = required_string(record, "drill")?;
    let title = required_string(record, "title")?;
    let started = required_string(record, "started")?;
    let ended = required_string(record, "ended")?;
    let aborted = record
        .get("aborted")
        .and_then(Value::as_bool)
        .ok_or_else(|| "training record requires boolean \"aborted\"".to_string())?;
    let athlete = record
        .get("athlete")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let session_id = record
        .get("session_id")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| legacy_session_id(source, started));

    // Optional additions to the SAME v1 schema. A blank id is not an identity,
    // so it becomes None rather than an empty string that could join rows.
    let athlete_id = record
        .get("athlete_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string);

    // The comparability block is optional evidence ABOUT a session, never a
    // precondition for it: the drill happened whatever the context says, so a
    // malformed block degrades to None plus a warning instead of hiding the row.
    let mut warnings = Vec::new();
    let evidence_context = match record.get("evidence_context") {
        None | Some(Value::Null) => None,
        Some(value) if value.is_object() => Some(sanitize_json(value)),
        Some(_) => {
            warnings.push(
                "evidence_context ignored: expected a JSON object; session kept without a \
                 comparability claim"
                    .to_string(),
            );
            None
        }
    };

    Ok(SessionRow {
        session_id,
        source_schema: TRAINING_SCHEMA.to_string(),
        source_path: source.to_string_lossy().into_owned(),
        athlete: athlete.to_string(),
        athlete_id,
        launch_kind: "training".to_string(),
        drill: drill.to_string(),
        title: title.to_string(),
        started_at: started.to_string(),
        ended_at: ended.to_string(),
        status: if aborted { "aborted" } else { "complete" }.to_string(),
        headline: record
            .get("headline")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        summary: sanitize_json(record.get("summary").unwrap_or(&Value::Object(Map::new()))),
        evidence_context,
        warnings,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    fn record() -> serde_json::Value {
        serde_json::json!({
            "schema": "project_cam.training.v1",
            "session_id": "desktop-1",
            "drill": "balance",
            "title": "SINGLE-LEG BALANCE",
            "role": "FIELD PLAYER",
            "athlete": "Арлен",
            "started": "2026-07-29T10:00:00",
            "ended": "2026-07-29T10:01:00",
            "aborted": false,
            "headline": "sway 31 mm",
            "summary": {"avg_sway_mm": 31.0, "nested": {"touchdowns": 0}}
        })
    }

    #[test]
    fn current_training_record_preserves_desktop_session_identity() {
        let row = parse_training_record(
            &record(),
            Path::new("garage_lab_combined/output/training_logs/sessions_index.jsonl"),
        )
        .unwrap();
        assert_eq!(row.session_id, "desktop-1");
        assert_eq!(row.athlete, "Арлен");
        assert_eq!(row.launch_kind, "training");
        assert_eq!(row.status, "complete");
        assert_eq!(row.summary["avg_sway_mm"], 31.0);
    }

    #[test]
    fn historical_training_record_gets_a_deterministic_join_key() {
        let mut value = record();
        value.as_object_mut().unwrap().remove("session_id");
        value["aborted"] = serde_json::json!(true);
        let source = Path::new("logs/sessions_index.jsonl");
        let first = parse_training_record(&value, source).unwrap();
        let second = parse_training_record(&value, source).unwrap();
        assert_eq!(first.session_id, second.session_id);
        assert!(first.session_id.starts_with("legacy-sessions-index-jsonl-"));
        assert_eq!(first.status, "aborted");
    }

    #[test]
    fn unknown_or_malformed_training_schema_is_rejected() {
        let mut unknown = record();
        unknown["schema"] = serde_json::json!("project_cam.training.v2");
        assert!(parse_training_record(&unknown, Path::new("index.jsonl")).is_err());

        let mut malformed = record();
        malformed["aborted"] = serde_json::json!("false");
        assert!(parse_training_record(&malformed, Path::new("index.jsonl")).is_err());
    }

    #[test]
    fn rich_v1_carries_athlete_id_and_evidence_context() {
        let mut value = record();
        value["athlete_id"] = serde_json::json!("uuid-1");
        value["evidence_context"] = serde_json::json!({
            "protocol_id": "balance.v1",
            "applied_parameters": {"holds": 4, "hold_s": 20.0},
            "camera_open_ratio_by_role": {"cam0": 1.0, "cam5": 0.0},
            "pose_valid_frame_ratio": 0.97
        });
        let row = parse_training_record(&value, Path::new("index.jsonl")).unwrap();
        assert_eq!(row.athlete_id.as_deref(), Some("uuid-1"));
        let context = row.evidence_context.expect("context kept");
        assert_eq!(context["protocol_id"], "balance.v1");
        assert_eq!(context["camera_open_ratio_by_role"]["cam5"], 0.0);
        assert!(row.warnings.is_empty());
    }

    #[test]
    fn legacy_v1_without_the_new_fields_still_reads() {
        // Sessions recorded before the comparability block must stay visible;
        // they simply carry no claim rather than an invented one.
        let row = parse_training_record(&record(), Path::new("index.jsonl")).unwrap();
        assert!(row.athlete_id.is_none());
        assert!(row.evidence_context.is_none());
        assert!(row.warnings.is_empty());
    }

    #[test]
    fn blank_athlete_id_is_none_not_an_empty_string() {
        let mut value = record();
        value["athlete_id"] = serde_json::json!("   ");
        let row = parse_training_record(&value, Path::new("index.jsonl")).unwrap();
        assert!(row.athlete_id.is_none());
    }

    #[test]
    fn malformed_evidence_context_keeps_the_session_and_warns() {
        // An optional block must never be able to hide a real session: the
        // drill happened whatever the context says.
        for bad in [
            serde_json::json!("balance.v1"),
            serde_json::json!([1, 2, 3]),
            serde_json::json!(7),
        ] {
            let mut value = record();
            value["evidence_context"] = bad;
            let row = parse_training_record(&value, Path::new("index.jsonl")).unwrap();
            assert!(row.evidence_context.is_none());
            assert!(
                row.warnings.iter().any(|w| w.contains("evidence_context")),
                "expected a warning, got {:?}",
                row.warnings
            );
        }
    }

    #[test]
    fn non_finite_numbers_inside_the_context_are_sanitized() {
        let mut value = record();
        value["evidence_context"] = serde_json::json!({"pose_valid_frame_ratio": 0.5});
        let row = parse_training_record(&value, Path::new("index.jsonl")).unwrap();
        let context = row.evidence_context.unwrap();
        assert_eq!(context["pose_valid_frame_ratio"], 0.5);
    }
}
