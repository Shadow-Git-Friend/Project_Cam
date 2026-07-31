use super::{legacy_session_id, ShotRow};
use chrono::{SecondsFormat, Utc};
use serde_json::{Map, Value};
use std::collections::HashMap;
use std::path::Path;

const EVENT_SCHEMA: &str = "project_cam.closed_loop.event_log.v1";
const LEGACY_SCHEMA: &str = "project_cam.blm.legacy.v1";

fn object(value: &Value) -> Option<&Map<String, Value>> {
    value.as_object()
}

fn finite_number(record: &Map<String, Value>, key: &str) -> Option<f64> {
    record
        .get(key)
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
}

fn nonempty_string(record: &Map<String, Value>, key: &str) -> Option<String> {
    record
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn timestamp_string(record: &Map<String, Value>, preferred_numeric: &str) -> String {
    if let Some(value) = nonempty_string(record, "wall_clock_iso") {
        return value;
    }
    if let Some(value) = record.get(preferred_numeric).and_then(Value::as_str) {
        return value.to_string();
    }
    let Some(value) =
        finite_number(record, preferred_numeric).or_else(|| finite_number(record, "timestamp"))
    else {
        return String::new();
    };
    let seconds = value.trunc() as i64;
    let nanos = ((value - value.trunc()).abs() * 1_000_000_000.0).round() as u32;
    chrono::DateTime::<Utc>::from_timestamp(seconds, nanos.min(999_999_999))
        .map(|time| time.to_rfc3339_opts(SecondsFormat::Millis, true))
        .unwrap_or_else(|| value.to_string())
}

fn calibration_proven(record: &Map<String, Value>) -> bool {
    record
        .get("speed_calibrated")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        || nonempty_string(record, "calibration_model_id").is_some()
        || nonempty_string(record, "speed_calibration_model_id").is_some()
}

fn normalized_outcome(record: &Map<String, Value>) -> String {
    for key in ["hit", "success", "result", "outcome"] {
        let Some(value) = record.get(key) else {
            continue;
        };
        if let Some(flag) = value.as_bool() {
            return if flag { "hit" } else { "miss" }.to_string();
        }
        let Some(text) = value.as_str() else {
            continue;
        };
        match text.trim().to_ascii_lowercase().as_str() {
            "hit" | "success" | "successful" | "saved" | "true" | "yes" => {
                return "hit".to_string()
            }
            "miss" | "failed" | "failure" | "false" | "no" => return "miss".to_string(),
            "invalid" | "void" | "voided" => return "invalid".to_string(),
            _ => {}
        }
    }
    "unknown".to_string()
}

fn combined_number(
    primary: &Map<String, Value>,
    fallback: Option<&Map<String, Value>>,
    key: &str,
) -> Option<f64> {
    finite_number(primary, key).or_else(|| fallback.and_then(|value| finite_number(value, key)))
}

fn combined_string(
    primary: &Map<String, Value>,
    fallback: Option<&Map<String, Value>>,
    key: &str,
) -> String {
    nonempty_string(primary, key)
        .or_else(|| fallback.and_then(|value| nonempty_string(value, key)))
        .unwrap_or_default()
}

pub fn parse_event_log(values: &[Value], source: &Path) -> (Vec<ShotRow>, Vec<String>) {
    let mut shots = Vec::new();
    let mut warnings = Vec::new();
    let mut pending_aims: HashMap<String, Map<String, Value>> = HashMap::new();

    for value in values {
        let Some(record) = object(value) else {
            warnings.push("event record is not an object".to_string());
            continue;
        };
        if record.get("schema_version").and_then(Value::as_str) != Some(EVENT_SCHEMA) {
            warnings.push("unsupported event schema".to_string());
            continue;
        }
        let Some(session_id) = nonempty_string(record, "session_id") else {
            warnings.push("event record has no session_id".to_string());
            continue;
        };
        let Some(event_type) = record.get("event_type").and_then(Value::as_str) else {
            warnings.push(format!("{session_id}: event record has no event_type"));
            continue;
        };
        let payload = record
            .get("payload")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();

        match event_type {
            "aim_command_sent" => {
                pending_aims.insert(session_id, payload);
            }
            "ball_launched" | "safety_gate_blocked" => {
                let aim = pending_aims.remove(&session_id);
                let aim_ref = aim.as_ref();
                let speed_mps = combined_number(&payload, aim_ref, "speed_mps");
                let speed_calibrated = speed_mps.is_some()
                    && (calibration_proven(&payload) || aim_ref.is_some_and(calibration_proven));
                let mut row_warnings = Vec::new();
                if aim_ref.is_none() {
                    row_warnings.push("no preceding aim_command_sent".to_string());
                }
                shots.push(ShotRow {
                    session_id,
                    sequence: shots.len() + 1,
                    timestamp: timestamp_string(record, "timestamp"),
                    target: combined_string(&payload, aim_ref, "joint_name"),
                    wheel_left_rpm: combined_number(&payload, aim_ref, "wheel_left_rpm"),
                    wheel_right_rpm: combined_number(&payload, aim_ref, "wheel_right_rpm"),
                    speed_mps,
                    speed_calibrated,
                    pitch_deg: combined_number(&payload, aim_ref, "pitch_deg"),
                    yaw_deg: combined_number(&payload, aim_ref, "yaw_deg"),
                    state: if event_type == "safety_gate_blocked" {
                        "blocked"
                    } else {
                        "launched"
                    }
                    .to_string(),
                    outcome: "unknown".to_string(),
                    block_reason: nonempty_string(&payload, "reason").unwrap_or_default(),
                    source_schema: EVENT_SCHEMA.to_string(),
                    source_path: source.to_string_lossy().into_owned(),
                    warnings: row_warnings,
                });
            }
            "outcome_scored" => {
                let outcome = normalized_outcome(&payload);
                if outcome == "unknown" {
                    warnings.push(format!(
                        "{session_id}: outcome_scored has no explicit result"
                    ));
                    continue;
                }
                if let Some(shot) = shots.iter_mut().rev().find(|shot| {
                    shot.session_id == session_id
                        && shot.state == "launched"
                        && shot.outcome == "unknown"
                }) {
                    shot.outcome = outcome;
                } else {
                    warnings.push(format!("{session_id}: outcome has no matching launch"));
                }
            }
            "session_start" | "target_chosen" | "athlete_reacted" | "session_end" => {}
            other => warnings.push(format!("{session_id}: unknown event type {other:?}")),
        }
    }
    (shots, warnings)
}

fn nested_object<'a>(
    record: &'a Map<String, Value>,
    keys: &[&str],
) -> Option<&'a Map<String, Value>> {
    keys.iter()
        .find_map(|key| record.get(*key).and_then(Value::as_object))
}

fn nested_reason(record: &Map<String, Value>) -> String {
    nonempty_string(record, "decision_reason")
        .or_else(|| {
            record
                .get("fire_outcome")
                .and_then(Value::as_object)
                .and_then(|value| nonempty_string(value, "reason"))
        })
        .or_else(|| {
            record
                .get("extra")
                .and_then(Value::as_object)
                .and_then(|extra| {
                    nonempty_string(extra, "reason").or_else(|| {
                        extra
                            .get("fire_outcome")
                            .and_then(Value::as_object)
                            .and_then(|value| nonempty_string(value, "reason"))
                    })
                })
        })
        .unwrap_or_default()
}

pub fn parse_legacy_shot(
    value: &Value,
    source: &Path,
    sequence: usize,
) -> Result<Option<ShotRow>, String> {
    let record = value
        .as_object()
        .ok_or_else(|| "legacy shot record must be an object".to_string())?;
    let action = record.get("action").and_then(Value::as_str).unwrap_or("");
    let decision = record.get("decision").and_then(Value::as_str).unwrap_or("");
    let state = match (action, decision) {
        ("shoot_blocked", _) | (_, "FIRE_BLOCKED") => "blocked",
        (_, "FIRE_SENT") => "launched",
        ("shoot", _) => {
            let sent = record
                .get("fire_outcome")
                .and_then(Value::as_object)
                .and_then(|outcome| outcome.get("serial_shoot_sent"))
                .and_then(Value::as_bool);
            if sent == Some(true) {
                "launched"
            } else {
                "unknown"
            }
        }
        _ => return Ok(None),
    };

    let timestamp = timestamp_string(
        record,
        if action == "shoot" {
            "shoot_timestamp"
        } else {
            "timestamp"
        },
    );
    let session_id = nonempty_string(record, "session_id")
        .unwrap_or_else(|| legacy_session_id(source, &timestamp));
    let angles = nested_object(record, &["angles_clamped", "calculated_pitch_yaw_v"]);
    let single_rpm = finite_number(record, "wheel_rpm")
        .or_else(|| angles.and_then(|value| finite_number(value, "rpm_cmd")));
    let speed_mps = finite_number(record, "speed_mps")
        .or_else(|| angles.and_then(|v| finite_number(v, "speed_mps")));
    let speed_calibrated = speed_mps.is_some()
        && (calibration_proven(record) || angles.is_some_and(calibration_proven));

    Ok(Some(ShotRow {
        session_id,
        sequence,
        timestamp,
        target: nonempty_string(record, "joint")
            .or_else(|| nonempty_string(record, "input_joint_name"))
            .unwrap_or_default(),
        wheel_left_rpm: finite_number(record, "wheel_left_rpm").or(single_rpm),
        wheel_right_rpm: finite_number(record, "wheel_right_rpm").or(single_rpm),
        speed_mps,
        speed_calibrated,
        pitch_deg: angles.and_then(|value| finite_number(value, "pitch_deg")),
        yaw_deg: angles.and_then(|value| finite_number(value, "yaw_deg")),
        state: state.to_string(),
        outcome: normalized_outcome(record),
        block_reason: if state == "blocked" {
            nested_reason(record)
        } else {
            String::new()
        },
        source_schema: LEGACY_SCHEMA.to_string(),
        source_path: source.to_string_lossy().into_owned(),
        warnings: if state == "unknown" {
            vec!["shoot record lacks explicit fire confirmation".to_string()]
        } else {
            Vec::new()
        },
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    fn event(
        session_id: &str,
        event_type: &str,
        timestamp: f64,
        payload: serde_json::Value,
    ) -> serde_json::Value {
        serde_json::json!({
            "schema_version": "project_cam.closed_loop.event_log.v1",
            "session_id": session_id,
            "timestamp": timestamp,
            "wall_clock_iso": format!("2026-07-29T10:00:{timestamp:02.0}Z"),
            "event_type": event_type,
            "source": "launcher_runtime",
            "payload": payload,
        })
    }

    #[test]
    fn event_log_joins_aim_to_launched_and_blocked_attempts() {
        let values = vec![
            event(
                "session-1",
                "aim_command_sent",
                1.0,
                serde_json::json!({
                    "joint_name": "right_knee",
                    "pitch_deg": 12.5,
                    "yaw_deg": -2.0,
                    "speed_mps": 10.0,
                    "wheel_left_rpm": 800,
                    "wheel_right_rpm": 810,
                }),
            ),
            event(
                "session-1",
                "ball_launched",
                2.0,
                serde_json::json!({"serial_shoot_sent": true}),
            ),
            event(
                "session-1",
                "aim_command_sent",
                3.0,
                serde_json::json!({"joint_name": "left_shoulder", "speed_mps": 9.0}),
            ),
            event(
                "session-1",
                "safety_gate_blocked",
                4.0,
                serde_json::json!({
                    "serial_shoot_sent": false,
                    "reason": "firing_line_blocked",
                }),
            ),
        ];
        let (shots, warnings) = parse_event_log(&values, Path::new("events.jsonl"));
        assert!(warnings.is_empty());
        assert_eq!(shots.len(), 2);
        assert_eq!(shots[0].state, "launched");
        assert_eq!(shots[0].outcome, "unknown");
        assert_eq!(shots[0].target, "right_knee");
        assert_eq!(shots[0].wheel_left_rpm, Some(800.0));
        assert_eq!(shots[0].speed_mps, Some(10.0));
        assert!(!shots[0].speed_calibrated);
        assert_eq!(shots[1].state, "blocked");
        assert_eq!(shots[1].block_reason, "firing_line_blocked");
    }

    #[test]
    fn outcome_scored_updates_only_the_latest_unknown_launch() {
        let values = vec![
            event(
                "session-2",
                "ball_launched",
                1.0,
                serde_json::json!({"serial_shoot_sent": true}),
            ),
            event(
                "session-2",
                "outcome_scored",
                2.0,
                serde_json::json!({"result": "hit"}),
            ),
        ];
        let (shots, _) = parse_event_log(&values, Path::new("events.jsonl"));
        assert_eq!(shots.len(), 1);
        assert_eq!(shots[0].outcome, "hit");
    }

    #[test]
    fn speed_needs_explicit_calibration_proof() {
        let values = vec![
            event(
                "session-3",
                "aim_command_sent",
                1.0,
                serde_json::json!({
                    "speed_mps": 12.0,
                    "speed_calibrated": true,
                    "calibration_model_id": "rpm-2026-07-29",
                }),
            ),
            event(
                "session-3",
                "ball_launched",
                2.0,
                serde_json::json!({"serial_shoot_sent": true}),
            ),
        ];
        let (shots, _) = parse_event_log(&values, Path::new("events.jsonl"));
        assert_eq!(shots[0].speed_mps, Some(12.0));
        assert!(shots[0].speed_calibrated);
    }

    #[test]
    fn legacy_visual_check_never_becomes_a_shot_outcome() {
        let value = serde_json::json!({
            "session_id": "legacy-1",
            "action": "shoot",
            "joint": "right_knee",
            "wheel_rpm": 800,
            "angles_clamped": {"pitch_deg": 12.4, "yaw_deg": -3.0},
            "visual_check": "y",
            "shoot_timestamp": 1_800_000_000.0,
            "fire_outcome": {"serial_shoot_sent": true},
        });
        let shot = parse_legacy_shot(&value, Path::new("live_aim.jsonl"), 1)
            .unwrap()
            .unwrap();
        assert_eq!(shot.state, "launched");
        assert_eq!(shot.outcome, "unknown");
        assert_eq!(shot.wheel_left_rpm, Some(800.0));
        assert_eq!(shot.wheel_right_rpm, Some(800.0));
        assert_eq!(shot.speed_mps, None);
        assert!(!shot.speed_calibrated);
    }

    #[test]
    fn raw_fire_block_and_rpm_without_speed_are_explicit() {
        let blocked = serde_json::json!({
            "timestamp": 1_800_000_010.0,
            "session_id": "raw-1",
            "decision": "FIRE_BLOCKED",
            "decision_reason": "clearance_stale",
            "input_joint_name": "nose",
            "calculated_pitch_yaw_v": {
                "pitch_deg": 4.0,
                "yaw_deg": 1.0,
                "rpm_cmd": 900,
            },
        });
        let shot = parse_legacy_shot(&blocked, Path::new("runtime.jsonl"), 7)
            .unwrap()
            .unwrap();
        assert_eq!(shot.sequence, 7);
        assert_eq!(shot.state, "blocked");
        assert_eq!(shot.block_reason, "clearance_stale");
        assert_eq!(shot.wheel_left_rpm, Some(900.0));
        assert_eq!(shot.speed_mps, None);
    }
}
