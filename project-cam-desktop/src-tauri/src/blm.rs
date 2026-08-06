//! The launcher console's intent vocabulary.
//!
//! The UI does not write serial, and it does not write the bridge's protocol
//! text either: it names one of these variants and the backend renders the line.
//! That keeps the same property the launch boundary has — there is no variant
//! that can express "send these bytes" — one layer further in, so a compromised
//! or buggy frontend cannot compose a firmware command.
//!
//! Ranges are duplicated from `garage_lab_combined/scripts/blm_bridge.py` on
//! purpose. The bridge is authoritative (it also clamps, because a human piping
//! it by hand is a supported path); this layer REFUSES instead of clamping, so a
//! UI that sends an out-of-range angle produces a visible error rather than a
//! silently different shot.

use serde::Deserialize;

/// Beyond this the ESP32 reboots — see .claude/rules/safety.md "Known Hazards".
pub const ANGLE_LIMIT_DEG: f64 = 30.0;
pub const YAW_LIMIT_DEG: f64 = 30.0;

/// The DEFAULT pitch envelope a session starts with — conservative, because no
/// downward travel cannot jam the barrel against the ball feeder.
///
/// Deliberately not a hard limit here. The collision is at a fixed PHYSICAL
/// position while the firmware's angle is measured from a zero adopted at boot or
/// by `set_zero`, so a constant in this frame means a different physical place
/// after every re-zero. The live envelope is per-session state in
/// `blm_bridge.py`, declared by the operator with `limits`, translated when the
/// zero moves, and enforced there; this layer only guards the firmware bound,
/// which IS frame-independent.
pub const PITCH_DEFAULT_MIN_DEG: f64 = 0.0;
pub const PITCH_DEFAULT_MAX_DEG: f64 = 30.0;

// A declarable limit may only ever sit inside the firmware bound. Widening one
// past it would hand the operator an angle that reboots the ESP32, so this fails
// the build rather than waiting for someone to notice at the bench.
const _: () = assert!(PITCH_DEFAULT_MIN_DEG >= -ANGLE_LIMIT_DEG);
const _: () = assert!(PITCH_DEFAULT_MAX_DEG <= ANGLE_LIMIT_DEG);
const _: () = assert!(YAW_LIMIT_DEG <= ANGLE_LIMIT_DEG);
const _: () = assert!(PITCH_DEFAULT_MIN_DEG < PITCH_DEFAULT_MAX_DEG);
pub const RPM_MAX: f64 = 1200.0;
/// The firmware refuses `shoot` below this; the bridge refuses to arm below it.
///
/// Not referenced by the renderer, and deliberately so: the gate needs the wheel
/// state, which only the bridge holds. It lives here as the Rust side of the
/// three-layer parity check (tests/test_desktop_launcher_console.py) — one value
/// per layer, compared, so the number cannot drift in one of them.
#[allow(dead_code)]
pub const RPM_MIN_FIRE: f64 = 400.0;
/// A fire request must carry this exact word. An empty-payload invoke cannot
/// fire, so a stray call or a mis-wired button is not a shot.
pub const FIRE_CONFIRMATION: &str = "FIRE";

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FitKind {
    Linear,
    Quadratic,
    Interp,
}

impl FitKind {
    fn as_str(self) -> &'static str {
        match self {
            Self::Linear => "linear",
            Self::Quadratic => "quadratic",
            Self::Interp => "interp",
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(tag = "command", rename_all = "snake_case", deny_unknown_fields)]
pub enum ConsoleCommand {
    Aim {
        pitch_deg: f64,
        yaw_deg: f64,
        wheel_rpm: f64,
    },
    Wheels {
        wheel_rpm: f64,
    },
    Reload {},
    Arm {},
    Disarm {},
    Fire {
        confirm: String,
    },
    Stop {},
    Clear {},
    Center {},
    /// Adopt the barrel's current physical position as zero. Moves nothing, so it
    /// is not actuation — and it is needed precisely when the reference is wrong.
    SetZero {},
    /// Declare the pitch travel measured from the CURRENT zero. The bridge holds
    /// and enforces it; a re-zero translates the same physical endpoints into
    /// the new coordinate frame.
    Limits {
        pitch_min_deg: f64,
        pitch_max_deg: f64,
    },
    Info {},
    /// Record a method-A landing distance for the v(RPM) fit.
    Measure {
        rpm: f64,
        landing_distance_m: f64,
    },
    Undo {},
    Fit {
        height_m: f64,
        kind: FitKind,
    },
}

fn finite(value: f64, name: &str) -> Result<f64, String> {
    if !value.is_finite() {
        return Err(format!("{name} must be a finite number"));
    }
    Ok(value)
}

/// Guard the FIRMWARE bound only. The mechanical envelope is per-session state
/// that only the bridge holds, and it clamps and reports against it — refusing
/// here on a fixed number would either jam the machine (too wide) or delete
/// legitimate travel (too narrow), depending on where zero happens to sit.
fn pitch(value: f64) -> Result<f64, String> {
    let value = finite(value, "pitch_deg")?;
    if value.abs() > ANGLE_LIMIT_DEG {
        return Err(format!(
            "pitch_deg must be within +/-{ANGLE_LIMIT_DEG} deg (the firmware bound), \
             got {value}"
        ));
    }
    Ok(value)
}

fn yaw(value: f64) -> Result<f64, String> {
    let value = finite(value, "yaw_deg")?;
    if value.abs() > YAW_LIMIT_DEG {
        return Err(format!(
            "yaw_deg must be within +/-{YAW_LIMIT_DEG} deg, got {value}"
        ));
    }
    Ok(value)
}

fn rpm(value: f64) -> Result<f64, String> {
    let value = finite(value, "wheel_rpm")?;
    if !(0.0..=RPM_MAX).contains(&value) {
        return Err(format!(
            "wheel_rpm must be between 0 and {RPM_MAX}, got {value}"
        ));
    }
    Ok(value)
}

impl ConsoleCommand {
    /// Render one line of the bridge protocol, or refuse.
    pub fn render(&self) -> Result<String, String> {
        Ok(match self {
            Self::Aim {
                pitch_deg,
                yaw_deg,
                wheel_rpm,
            } => format!(
                "aim {:.0} {:.0} {:.0}",
                pitch(*pitch_deg)?,
                yaw(*yaw_deg)?,
                rpm(*wheel_rpm)?
            ),
            Self::Wheels { wheel_rpm } => format!("wheels {:.0}", rpm(*wheel_rpm)?),
            Self::Reload {} => "reload".into(),
            Self::Arm {} => "arm".into(),
            Self::Disarm {} => "disarm".into(),
            Self::Fire { confirm } => {
                if confirm != FIRE_CONFIRMATION {
                    return Err(format!("fire requires confirm == {FIRE_CONFIRMATION:?}"));
                }
                "fire".into()
            }
            Self::Stop {} => "stop".into(),
            Self::Clear {} => "clear".into(),
            Self::Center {} => "center".into(),
            // Bridge protocol, not the raw firmware word. Python alone owns the
            // `set_zero` -> `setzero` translation.
            Self::SetZero {} => "set_zero".into(),
            Self::Limits {
                pitch_min_deg,
                pitch_max_deg,
            } => {
                let low = pitch(*pitch_min_deg)?;
                let high = pitch(*pitch_max_deg)?;
                if low >= high {
                    return Err(format!(
                        "pitch_min_deg must be below pitch_max_deg, got {low} >= {high}"
                    ));
                }
                if low > 0.0 || high < 0.0 {
                    return Err(format!(
                        "pitch travel must contain the current zero, got [{low}, {high}]"
                    ));
                }
                format!("limits {low:.0} {high:.0}")
            }
            Self::Info {} => "info".into(),
            Self::Measure {
                rpm: shot_rpm,
                landing_distance_m,
            } => {
                let distance = finite(*landing_distance_m, "landing_distance_m")?;
                if distance <= 0.0 || distance > 60.0 {
                    return Err(format!(
                        "landing_distance_m must be between 0 and 60, got {distance}"
                    ));
                }
                format!("measure {:.0} {:.4}", rpm(*shot_rpm)?, distance)
            }
            Self::Undo {} => "undo".into(),
            Self::Fit { height_m, kind } => {
                let height = finite(*height_m, "height_m")?;
                if height <= 0.0 || height > 5.0 {
                    return Err(format!("height_m must be between 0 and 5, got {height}"));
                }
                format!("fit {:.4} {}", height, kind.as_str())
            }
        })
    }

    /// True for anything that can move the machine or release a ball. Used for
    /// the evidence trail: an `info` poll is not an actuation and must not read
    /// like one.
    pub fn is_actuating(&self) -> bool {
        matches!(
            self,
            Self::Aim { .. }
                | Self::Wheels { .. }
                | Self::Reload {}
                | Self::Fire { .. }
                | Self::Center {}
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(json: serde_json::Value) -> Result<ConsoleCommand, serde_json::Error> {
        serde_json::from_value(json)
    }

    fn render(json: serde_json::Value) -> Result<String, String> {
        parse(json).map_err(|error| error.to_string())?.render()
    }

    #[test]
    fn every_intent_renders_the_line_the_bridge_parses() {
        let cases = [
            (
                serde_json::json!({"command": "aim", "pitch_deg": 12.0,
                                   "yaw_deg": -7.0, "wheel_rpm": 800}),
                "aim 12 -7 800",
            ),
            (
                serde_json::json!({"command": "wheels", "wheel_rpm": 500}),
                "wheels 500",
            ),
            (serde_json::json!({"command": "reload"}), "reload"),
            (serde_json::json!({"command": "arm"}), "arm"),
            (serde_json::json!({"command": "disarm"}), "disarm"),
            (
                serde_json::json!({"command": "fire", "confirm": "FIRE"}),
                "fire",
            ),
            (serde_json::json!({"command": "stop"}), "stop"),
            (serde_json::json!({"command": "clear"}), "clear"),
            (serde_json::json!({"command": "center"}), "center"),
            (serde_json::json!({"command": "set_zero"}), "set_zero"),
            (
                serde_json::json!({"command": "limits", "pitch_min_deg": -25.0,
                                   "pitch_max_deg": 30.0}),
                "limits -25 30",
            ),
            (serde_json::json!({"command": "info"}), "info"),
            (
                serde_json::json!({"command": "measure", "rpm": 800,
                                   "landing_distance_m": 3.945}),
                "measure 800 3.9450",
            ),
            (serde_json::json!({"command": "undo"}), "undo"),
            (
                serde_json::json!({"command": "fit", "height_m": 0.52,
                                   "kind": "linear"}),
                "fit 0.5200 linear",
            ),
        ];
        for (payload, expected) in cases {
            assert_eq!(render(payload.clone()).unwrap(), expected, "{payload:?}");
        }
    }

    #[test]
    fn a_shot_needs_the_exact_confirmation_word() {
        assert!(render(serde_json::json!({"command": "fire", "confirm": "FIRE"})).is_ok());
        for wrong in ["", "fire", "Fire", "YES", "FIRE "] {
            assert!(
                render(serde_json::json!({"command": "fire", "confirm": wrong})).is_err(),
                "accepted confirm {wrong:?}"
            );
        }
        // A payload with no confirmation at all cannot be a shot.
        assert!(parse(serde_json::json!({"command": "fire"})).is_err());
    }

    #[test]
    fn out_of_range_geometry_and_rpm_are_refused_not_clamped() {
        // The firmware reboots beyond +/-30, so a UI asking for 45 is a bug that
        // must surface rather than quietly becoming a 30-degree shot.
        for bad in [
            serde_json::json!({"command": "aim", "pitch_deg": 45.0,
                               "yaw_deg": 0.0, "wheel_rpm": 800}),
            serde_json::json!({"command": "aim", "pitch_deg": 0.0,
                               "yaw_deg": -31.0, "wheel_rpm": 800}),
            serde_json::json!({"command": "aim", "pitch_deg": 0.0,
                               "yaw_deg": 0.0, "wheel_rpm": 1600}),
            serde_json::json!({"command": "aim", "pitch_deg": 0.0,
                               "yaw_deg": 0.0, "wheel_rpm": -1}),
            serde_json::json!({"command": "wheels", "wheel_rpm": 1201}),
            serde_json::json!({"command": "measure", "rpm": 800,
                               "landing_distance_m": 0.0}),
            serde_json::json!({"command": "measure", "rpm": 800,
                               "landing_distance_m": 61.0}),
            serde_json::json!({"command": "fit", "height_m": 0.0, "kind": "linear"}),
            serde_json::json!({"command": "fit", "height_m": 6.0, "kind": "linear"}),
        ] {
            assert!(render(bad.clone()).is_err(), "accepted {bad:?}");
        }
        // Exactly at the limits is legitimate operating range.
        assert!(
            render(serde_json::json!({"command": "aim", "pitch_deg": 30.0,
                                          "yaw_deg": -30.0, "wheel_rpm": 1200}))
            .is_ok()
        );
    }

    #[test]
    fn this_layer_guards_the_firmware_bound_and_leaves_the_envelope_to_the_bridge() {
        // REWRITTEN 2026-08-06, twice in one day, and the second version is the
        // one that is actually right.
        //
        // First attempt: refuse pitch < 0 here, after an operator drove the barrel
        // into the ball feeder. That looked like the fix and was the wrong frame —
        // the collision is at a fixed PHYSICAL position, while this angle is
        // measured from a zero adopted at boot or by `set_zero`. A constant in
        // this frame points somewhere else after every re-zero, and it also
        // deleted legitimate downward travel: how much room is left below zero
        // depends on where zero was put, which only the operator can see.
        //
        // So the division is: this layer guards +/-30, which is frame-independent
        // because it is about the ESP32 rebooting. The mechanical envelope is
        // per-session state in the bridge, declared with `limits` and clamped
        // there.
        for inside in [-30.0, -12.0, 0.0, 15.0, 30.0] {
            assert!(
                render(serde_json::json!({
                    "command": "aim", "pitch_deg": inside, "yaw_deg": 0.0, "wheel_rpm": 0
                }))
                .is_ok(),
                "{inside} is inside the firmware bound and must reach the bridge"
            );
        }
        for outside in [-30.5, 31.0, 45.0] {
            let refused = render(serde_json::json!({
                "command": "aim", "pitch_deg": outside, "yaw_deg": 0.0, "wheel_rpm": 0
            }))
            .unwrap_err();
            assert!(refused.contains("firmware bound"), "{outside}: {refused}");
        }

        // A declared envelope is bounded by the same firmware limit and must be
        // ordered — an inverted one would silently clamp every angle to a point.
        assert!(render(serde_json::json!({
            "command": "limits", "pitch_min_deg": -25.0, "pitch_max_deg": 30.0
        }))
        .is_ok());
        for bad in [
            serde_json::json!({"command": "limits", "pitch_min_deg": -31.0,
                               "pitch_max_deg": 30.0}),
            serde_json::json!({"command": "limits", "pitch_min_deg": 0.0,
                               "pitch_max_deg": 31.0}),
            serde_json::json!({"command": "limits", "pitch_min_deg": 10.0,
                               "pitch_max_deg": 10.0}),
            serde_json::json!({"command": "limits", "pitch_min_deg": 20.0,
                               "pitch_max_deg": 5.0}),
            serde_json::json!({"command": "limits", "pitch_min_deg": 10.0,
                               "pitch_max_deg": 20.0}),
            serde_json::json!({"command": "limits", "pitch_min_deg": -20.0,
                               "pitch_max_deg": -10.0}),
        ] {
            assert!(render(bad.clone()).is_err(), "accepted {bad:?}");
        }
    }

    #[test]
    fn non_finite_and_smuggled_fields_are_refused() {
        for raw in [
            r#"{"command":"aim","pitch_deg":NaN,"yaw_deg":0,"wheel_rpm":800}"#,
            r#"{"command":"aim","pitch_deg":Infinity,"yaw_deg":0,"wheel_rpm":800}"#,
            r#"{"command":"aim","pitch_deg":1e400,"yaw_deg":0,"wheel_rpm":800}"#,
            // No raw passthrough, under any key.
            r#"{"command":"stop","raw":"shoot"}"#,
            r#"{"command":"info","line":"set 0 0 900 900"}"#,
            r#"{"command":"aim","pitch_deg":0,"yaw_deg":0,"wheel_rpm":800,"extra":1}"#,
            // Unknown verbs cannot reach the bridge.
            r#"{"command":"shoot"}"#,
            r#"{"command":"setzero"}"#,
            r#"{"command":"jf500"}"#,
            // Duplicate keys must not resolve by last-wins.
            r#"{"command":"fire","confirm":"no","confirm":"FIRE"}"#,
            // Case-sensitive vocabulary.
            r#"{"command":"AIM","pitch_deg":0,"yaw_deg":0,"wheel_rpm":0}"#,
        ] {
            let parsed = serde_json::from_str::<ConsoleCommand>(raw);
            let refused = match parsed {
                Err(_) => true,
                Ok(command) => command.render().is_err(),
            };
            assert!(refused, "accepted adversarial console payload: {raw}");
        }
    }

    #[test]
    fn a_rendered_line_is_always_one_line_so_two_commands_cannot_be_smuggled() {
        // The bridge reads one intent per line. If any rendering could contain a
        // newline, a single approved intent could deliver a second, unapproved
        // one — so this holds for every variant, including the string-carrying
        // `fire` and the float formatting.
        let every = [
            serde_json::json!({"command": "aim", "pitch_deg": 30.0,
                               "yaw_deg": -30.0, "wheel_rpm": 950}),
            serde_json::json!({"command": "wheels", "wheel_rpm": 0}),
            serde_json::json!({"command": "reload"}),
            serde_json::json!({"command": "arm"}),
            serde_json::json!({"command": "disarm"}),
            serde_json::json!({"command": "fire", "confirm": "FIRE"}),
            serde_json::json!({"command": "stop"}),
            serde_json::json!({"command": "clear"}),
            serde_json::json!({"command": "center"}),
            serde_json::json!({"command": "set_zero"}),
            serde_json::json!({"command": "limits", "pitch_min_deg": -30.0,
                               "pitch_max_deg": 30.0}),
            serde_json::json!({"command": "info"}),
            serde_json::json!({"command": "measure", "rpm": 500,
                               "landing_distance_m": 2.4}),
            serde_json::json!({"command": "undo"}),
            serde_json::json!({"command": "fit", "height_m": 0.52,
                               "kind": "interp"}),
        ];
        for payload in every {
            let line = render(payload.clone()).unwrap();
            assert!(!line.contains('\n') && !line.contains('\r'), "{line:?}");
            assert_eq!(line.trim(), line, "{line:?}");
            assert!(!line.is_empty());
        }
    }

    #[test]
    fn only_machine_moving_intents_count_as_actuation() {
        let actuating = [
            serde_json::json!({"command": "aim", "pitch_deg": 0.0,
                               "yaw_deg": 0.0, "wheel_rpm": 800}),
            serde_json::json!({"command": "wheels", "wheel_rpm": 800}),
            serde_json::json!({"command": "reload"}),
            serde_json::json!({"command": "fire", "confirm": "FIRE"}),
            serde_json::json!({"command": "center"}),
        ];
        for payload in actuating {
            assert!(
                parse(payload.clone()).unwrap().is_actuating(),
                "{payload:?}"
            );
        }
        // Arming is a permission change, and stop/clear/info/bookkeeping move
        // nothing — recording them as actuation would make the evidence lie.
        for payload in [
            serde_json::json!({"command": "arm"}),
            serde_json::json!({"command": "disarm"}),
            serde_json::json!({"command": "stop"}),
            serde_json::json!({"command": "clear"}),
            serde_json::json!({"command": "set_zero"}),
            serde_json::json!({"command": "limits", "pitch_min_deg": 0.0,
                               "pitch_max_deg": 30.0}),
            serde_json::json!({"command": "info"}),
            serde_json::json!({"command": "measure", "rpm": 800,
                               "landing_distance_m": 3.9}),
            serde_json::json!({"command": "undo"}),
            serde_json::json!({"command": "fit", "height_m": 0.52,
                               "kind": "linear"}),
        ] {
            assert!(
                !parse(payload.clone()).unwrap().is_actuating(),
                "{payload:?}"
            );
        }
    }
}
