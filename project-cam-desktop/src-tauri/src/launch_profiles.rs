//! Named launch profiles: the backend decides what may run.
//!
//! The frontend used to hand `spawn_process` a `program`, an `args` vector and a
//! `cwd`, so the Rust side placed no constraint at all on what got executed —
//! any UI bug or injected content could ask it to run an arbitrary binary. The
//! drill wrapper's own `case` allowlist protected only launches that went
//! through the wrapper; it was never a property of the launch boundary.
//!
//! Here the boundary is the type system: a request names a profile and carries
//! semantic parameters only. Paths, arguments, working directory, label and
//! launch context are all produced here. There is no variant that can express
//! "run this program".

use serde::Deserialize;
use std::path::{Path, PathBuf};

use crate::session::{LaunchContext, LaunchKind};

/// Files that must exist for a directory to be this repository. Guards against
/// resolving a root that merely has the right shape.
const REPO_SENTINELS: [&str; 3] = [
    "Parallel_working/run_training_drill.sh",
    "garage_lab_combined/scripts/training_drill.py",
    "project-cam-desktop/src-tauri/tauri.conf.json",
];

/// Identity fields are human labels or stable short IDs, never an argument
/// transport. Keeping them small and single-line prevents argv/display-log
/// injection and stops a malformed request creating a huge manifest.
const MAX_IDENTITY_CHARS: usize = 128;

const FORBIDDEN_COMMAND_TOKENS: [&str; 5] = [
    "--shoot-enabled",
    "/dev/tty",
    "live_aim_test",
    "blm_follow",
    "launcher_runtime",
];

/// Backend-owned filesystem anchors. The frontend never supplies these.
#[derive(Clone, Debug)]
pub struct AppPaths {
    repo_root: PathBuf,
    python: PathBuf,
}

impl AppPaths {
    /// Locate the repository from the compiled-in manifest directory
    /// (`<repo>/project-cam-desktop/src-tauri`) and verify it really is one.
    pub fn discover() -> Result<Self, String> {
        let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
        let root = manifest
            .parent()
            .and_then(Path::parent)
            .ok_or_else(|| "cannot derive repo root from manifest dir".to_string())?;
        Self::from_root(root)
    }

    pub fn from_root(root: &Path) -> Result<Self, String> {
        let repo_root = root
            .canonicalize()
            .map_err(|error| format!("repo root {}: {error}", root.display()))?;
        for sentinel in REPO_SENTINELS {
            if !repo_root.join(sentinel).exists() {
                return Err(format!(
                    "{} is not a Project_Cam checkout (missing {sentinel})",
                    repo_root.display()
                ));
            }
        }
        let python = repo_root.join("venv/bin/python");
        Ok(Self { repo_root, python })
    }

    pub fn repo_root(&self) -> &Path {
        &self.repo_root
    }

    pub fn python(&self) -> &Path {
        &self.python
    }

    /// Resolve a repo-relative script and refuse anything that escapes the
    /// repository — canonicalize first so a symlink pointing outside is caught
    /// by the containment check rather than by the textual path.
    fn script(&self, relative: &str) -> Result<PathBuf, String> {
        let candidate = self.repo_root.join(relative);
        let resolved = candidate
            .canonicalize()
            .map_err(|error| format!("{relative}: {error}"))?;
        if !resolved.is_file() {
            return Err(format!("{relative} is not a file"));
        }
        if !resolved.starts_with(&self.repo_root) {
            return Err(format!("{relative} resolves outside the repository"));
        }
        Ok(resolved)
    }
}

/// One drill with its own semantic workload. Ranges mirror `PROTOCOL_CATALOG`
/// in `src/project_cam/training/drills.py`; the Python entrypoint re-validates,
/// because this is a trust boundary and one check is not defence in depth.
#[derive(Clone, Debug, Deserialize)]
#[serde(tag = "drill", rename_all = "snake_case", deny_unknown_fields)]
pub enum TrainingDrillRequest {
    Balance { holds: u32 },
    Shuttle { reps: u32 },
    LineHops { sets: u32 },
    GkSave { rounds: u32, flip: bool },
    GkUpdown { duration_s: f64 },
    ReactionZones { rounds: u32, projector: bool },
    Cmj { jumps: u32 },
    HopSymmetry { hops_per_leg: u32 },
    ReactiveCut { reps: u32, projector: bool },
}

impl TrainingDrillRequest {
    fn drill_id(&self) -> &'static str {
        match self {
            Self::Balance { .. } => "balance",
            Self::Shuttle { .. } => "shuttle",
            Self::LineHops { .. } => "line_hops",
            Self::GkSave { .. } => "gk_save",
            Self::GkUpdown { .. } => "gk_updown",
            Self::ReactionZones { .. } => "reaction_zones",
            Self::Cmj { .. } => "cmj",
            Self::HopSymmetry { .. } => "hop_symmetry",
            Self::ReactiveCut { .. } => "reactive_cut",
        }
    }

    fn check(value: f64, lo: f64, hi: f64, drill: &str, name: &str) -> Result<(), String> {
        if !value.is_finite() || value < lo || value > hi {
            return Err(format!(
                "{drill}.{name} must be between {lo} and {hi}, got {value}"
            ));
        }
        Ok(())
    }

    /// Map the semantic workload onto the wrapper's legacy flag.
    ///
    /// `--rounds` means four different things depending on the drill (holds /
    /// reps / sets / rounds), which is exactly why the request carries the
    /// semantic name and this translation stays an implementation detail.
    fn workload_args(&self) -> Result<Vec<String>, String> {
        let id = self.drill_id();
        let mut args = Vec::new();
        match *self {
            Self::Balance { holds } => {
                Self::check(holds as f64, 2.0, 8.0, id, "holds")?;
                args.push("--rounds".into());
                args.push(holds.to_string());
            }
            Self::Shuttle { reps } => {
                Self::check(reps as f64, 1.0, 6.0, id, "reps")?;
                args.push("--rounds".into());
                args.push(reps.to_string());
            }
            Self::LineHops { sets } => {
                Self::check(sets as f64, 1.0, 5.0, id, "sets")?;
                args.push("--rounds".into());
                args.push(sets.to_string());
            }
            Self::GkSave { rounds, flip } => {
                Self::check(rounds as f64, 5.0, 20.0, id, "rounds")?;
                args.push("--rounds".into());
                args.push(rounds.to_string());
                if flip {
                    args.push("--flip".into());
                }
            }
            Self::GkUpdown { duration_s } => {
                Self::check(duration_s, 15.0, 120.0, id, "duration_s")?;
                args.push("--duration".into());
                args.push(format!("{duration_s}"));
            }
            Self::ReactionZones { rounds, projector } => {
                Self::check(rounds as f64, 5.0, 20.0, id, "rounds")?;
                args.push("--rounds".into());
                args.push(rounds.to_string());
                if projector {
                    args.push("--fullscreen".into());
                }
            }
            Self::Cmj { jumps } => {
                Self::check(jumps as f64, 3.0, 10.0, id, "jumps")?;
                args.push("--rounds".into());
                args.push(jumps.to_string());
            }
            Self::HopSymmetry { hops_per_leg } => {
                Self::check(hops_per_leg as f64, 2.0, 5.0, id, "hops_per_leg")?;
                args.push("--rounds".into());
                args.push(hops_per_leg.to_string());
            }
            Self::ReactiveCut { reps, projector } => {
                Self::check(reps as f64, 4.0, 12.0, id, "reps")?;
                args.push("--rounds".into());
                args.push(reps.to_string());
                if projector {
                    args.push("--fullscreen".into());
                }
            }
        }
        Ok(args)
    }
}

/// Options every viewer profile accepts. These replace the argument vector the
/// frontend used to compose by hand: same capabilities, but each one is a
/// validated semantic field rather than a free-form flag.
#[derive(Clone, Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ViewerOptions {
    /// Track up to N people. 1 keeps the legacy single-person path.
    #[serde(default)]
    pub people: Option<u8>,
    /// Label the primary person from the local gallery (identification only —
    /// never a fire-authorization signal, see .claude/rules/safety.md).
    #[serde(default)]
    pub athlete: Option<String>,
    #[serde(default)]
    pub auto_orbit: bool,
    #[serde(default)]
    pub limb_heat: bool,
}

impl ViewerOptions {
    fn args(&self) -> Result<Vec<String>, String> {
        let mut args = Vec::new();
        if let Some(count) = self.people {
            if !(1..=6).contains(&count) {
                return Err(format!("people must be between 1 and 6, got {count}"));
            }
            if count > 1 {
                args.push("--multi-person".into());
                args.push(count.to_string());
            }
        }
        if let Some(name) = self.athlete()? {
            args.push("--face-id".into());
            args.push("--primary-person".into());
            args.push(name);
        }
        if self.auto_orbit {
            args.push("--auto-orbit".into());
        }
        if self.limb_heat {
            args.push("--limb-heat".into());
        }
        Ok(args)
    }

    fn athlete(&self) -> Result<Option<String>, String> {
        optional_identity(self.athlete.as_deref(), "athlete", true)
    }
}

/// Everything the frontend is allowed to ask for.
///
/// `deny_unknown_fields` matters as much as the variant list: it is what makes
/// a smuggled `program`, `cwd` or `args` key a hard deserialization error
/// instead of a silently ignored extra.
#[derive(Clone, Debug, Deserialize)]
#[serde(tag = "profile_id", rename_all = "snake_case", deny_unknown_fields)]
pub enum LaunchRequest {
    // Empty struct variants, not unit variants: `deny_unknown_fields` is not
    // applied to unit variants of an internally tagged enum, so
    // `{"profile_id": "free_view_usb6", "program": "/bin/sh"}` would be
    // accepted with the extra key silently ignored. `{}` makes it an error.
    FreeViewUsb6 {
        #[serde(default)]
        viewer: ViewerOptions,
    },
    BlmOverlayUsb6 {
        #[serde(default)]
        viewer: ViewerOptions,
    },
    #[serde(rename = "yolo_pose_4cam")]
    YoloPose4cam {
        #[serde(default)]
        viewer: ViewerOptions,
    },
    #[serde(rename = "record_3d")]
    Record3d {
        #[serde(default)]
        viewer: ViewerOptions,
    },
    TrainingDrill {
        drill: TrainingDrillRequest,
        /// Display name, shown on the board and passed to the wrapper.
        #[serde(default)]
        athlete: Option<String>,
        /// Stable identity for the session manifest. Deliberately separate: the
        /// display name is editable and must never be the join key.
        #[serde(default)]
        athlete_id: Option<String>,
        #[serde(default)]
        face_id: bool,
        #[serde(default)]
        people: Option<u8>,
    },
    FaceEnrollArena {
        athlete: String,
    },
    FaceEnrollSingle {
        athlete: String,
        camera: String,
    },
    FaceModelsDownload {},
}

/// A launch the backend has approved. Fields are private so no caller can build
/// one by hand — the only way to obtain it is [`resolve_launch`].
#[derive(Clone, Debug)]
pub struct ResolvedLaunch {
    program: PathBuf,
    args: Vec<String>,
    cwd: PathBuf,
    label: String,
    context: LaunchContext,
}

impl ResolvedLaunch {
    pub fn program(&self) -> &Path {
        &self.program
    }
    pub fn args(&self) -> &[String] {
        &self.args
    }
    pub fn cwd(&self) -> &Path {
        &self.cwd
    }
    pub fn label(&self) -> &str {
        &self.label
    }
    pub fn context(&self) -> &LaunchContext {
        &self.context
    }

    /// Display-only command string for the MISSION LOG, repo-relative so the
    /// log does not leak absolute paths back into the UI as something to reuse.
    pub fn display_command(&self) -> String {
        let program = self
            .program
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_else(|| self.program.to_string_lossy().into_owned());
        let args: Vec<String> = self
            .args
            .iter()
            .map(|arg| {
                Path::new(arg)
                    .strip_prefix(&self.cwd)
                    .map(|rel| rel.to_string_lossy().into_owned())
                    .unwrap_or_else(|_| arg.clone())
            })
            .collect();
        format!("{program} {}", args.join(" "))
            .trim_end()
            .to_string()
    }
}

fn non_empty(value: &str, field: &str) -> Result<String, String> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return Err(format!("{field} must not be blank"));
    }
    Ok(trimmed.to_string())
}

fn validated_identity(value: &str, field: &str, command_bound: bool) -> Result<String, String> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return Err(format!("{field} must not be blank"));
    }
    if trimmed.chars().count() > MAX_IDENTITY_CHARS {
        return Err(format!(
            "{field} must be at most {MAX_IDENTITY_CHARS} characters"
        ));
    }
    if trimmed.chars().any(char::is_control) {
        return Err(format!("{field} must not contain control characters"));
    }
    if command_bound {
        let normalized = trimmed.to_ascii_lowercase();
        if normalized.starts_with('-')
            || FORBIDDEN_COMMAND_TOKENS
                .iter()
                .any(|token| normalized.contains(token))
        {
            return Err(format!("{field} contains a reserved launch token"));
        }
    }
    Ok(trimmed.to_string())
}

fn optional_identity(
    value: Option<&str>,
    field: &str,
    command_bound: bool,
) -> Result<Option<String>, String> {
    let Some(value) = value else {
        return Ok(None);
    };
    if value.trim().is_empty() {
        return Ok(None);
    }
    validated_identity(value, field, command_bound).map(Some)
}

pub fn resolve_launch(paths: &AppPaths, request: LaunchRequest) -> Result<ResolvedLaunch, String> {
    let bash = PathBuf::from("/bin/bash");
    let cwd = paths.repo_root().to_path_buf();

    let resolved = match request {
        LaunchRequest::FreeViewUsb6 { viewer } => {
            let script = paths.script("Parallel_working/run_live_usb6_mirrored_skeleton.sh")?;
            // Free viewing may run degraded: a knowingly unplugged camera is a
            // legitimate session. Drills keep the launcher's own floor of 6,
            // because that floor exists against MISCONFIGURATION and because
            // 2-camera precision must not enter a baseline. Appended last so
            // argparse's last-wins overrides the script's own value.
            ResolvedLaunch {
                program: bash,
                args: {
                    let mut args = vec![script.to_string_lossy().into_owned()];
                    args.extend(viewer.args()?);
                    // Last wins in argparse, so this must follow the script's
                    // own --min-active-cameras 6.
                    args.push("--min-active-cameras".into());
                    args.push("2".into());
                    args
                },
                cwd,
                label: "6-CAMERA CINEMATIC ARENA".into(),
                context: LaunchContext {
                    athlete: viewer.athlete()?,
                    athlete_id: None,
                    launch_kind: LaunchKind::Viewer,
                    drill: None,
                },
            }
        }
        LaunchRequest::BlmOverlayUsb6 { viewer } => {
            // View-only aim overlay. It broadcasts UDP and draws where the BLM
            // would point; it never opens serial. No fire-control argument is
            // constructible here, which is the point of the profile.
            let script = paths.script("Parallel_working/run_live_usb6_blm.sh")?;
            ResolvedLaunch {
                program: bash,
                args: {
                    let mut args = vec![script.to_string_lossy().into_owned()];
                    args.extend(viewer.args()?);
                    args
                },
                cwd,
                label: "6-CAMERA + BLM AIM OVERLAY".into(),
                context: LaunchContext {
                    athlete: viewer.athlete()?,
                    athlete_id: None,
                    launch_kind: LaunchKind::Viewer,
                    drill: None,
                },
            }
        }
        LaunchRequest::YoloPose4cam { viewer } => {
            let script = paths.script("Parallel_working/run_live_parallel_yolopose.sh")?;
            ResolvedLaunch {
                program: bash,
                args: {
                    let mut args = vec![script.to_string_lossy().into_owned()];
                    args.extend(viewer.args()?);
                    args
                },
                cwd,
                label: "4-CAMERA YOLO-POSE".into(),
                context: LaunchContext {
                    athlete: viewer.athlete()?,
                    athlete_id: None,
                    launch_kind: LaunchKind::Viewer,
                    drill: None,
                },
            }
        }
        LaunchRequest::Record3d { viewer } => {
            let script = paths.script("Parallel_working/run_record_3d.sh")?;
            ResolvedLaunch {
                program: bash,
                args: {
                    let mut args = vec![script.to_string_lossy().into_owned()];
                    args.extend(viewer.args()?);
                    args
                },
                cwd,
                label: "RECORD 3D SESSION".into(),
                context: LaunchContext {
                    athlete: viewer.athlete()?,
                    athlete_id: None,
                    launch_kind: LaunchKind::Recording,
                    drill: None,
                },
            }
        }
        LaunchRequest::TrainingDrill {
            drill,
            athlete,
            athlete_id,
            face_id,
            people,
        } => {
            let script = paths.script("Parallel_working/run_training_drill.sh")?;
            let drill_id = drill.drill_id().to_string();
            let mut args = vec![script.to_string_lossy().into_owned(), drill_id.clone()];
            let athlete = optional_identity(athlete.as_deref(), "athlete", true)?;
            let athlete_id = optional_identity(athlete_id.as_deref(), "athlete_id", false)?;
            if let Some(name) = athlete.as_deref() {
                args.push("--athlete".into());
                args.push(name.to_string());
                if face_id {
                    args.push("--face-id".into());
                }
            } else if face_id {
                return Err("face_id requires an athlete name".to_string());
            }
            if let Some(count) = people {
                if !(1..=6).contains(&count) {
                    return Err(format!("people must be between 1 and 6, got {count}"));
                }
                if count > 1 {
                    args.push("--people".into());
                    args.push(count.to_string());
                }
            }
            args.extend(drill.workload_args()?);
            // NOTE: no --min-active-cameras override. Drills inherit the
            // launcher's floor of 6 on purpose.
            ResolvedLaunch {
                program: bash,
                args,
                cwd,
                label: format!("DRILL · {}", drill_id.to_uppercase()),
                context: LaunchContext {
                    athlete,
                    athlete_id,
                    launch_kind: LaunchKind::Training,
                    drill: Some(drill_id),
                },
            }
        }
        LaunchRequest::FaceEnrollArena { athlete } => {
            let athlete = validated_identity(&athlete, "athlete", true)?;
            let script = paths.script("Parallel_working/scripts/face_enroll.py")?;
            let config = paths.script("garage_lab_combined/config/cameras_6usb_test.yaml")?;
            ResolvedLaunch {
                program: paths.python().to_path_buf(),
                args: vec![
                    script.to_string_lossy().into_owned(),
                    "--name".into(),
                    athlete.clone(),
                    "--arena-config".into(),
                    config.to_string_lossy().into_owned(),
                    "--replace".into(),
                ],
                cwd,
                label: format!("SCAN FACE · {athlete}"),
                context: LaunchContext {
                    athlete: Some(athlete),
                    athlete_id: None,
                    launch_kind: LaunchKind::Maintenance,
                    drill: None,
                },
            }
        }
        LaunchRequest::FaceEnrollSingle { athlete, camera } => {
            let athlete = validated_identity(&athlete, "athlete", true)?;
            // Index or device node only — never a free-form argument.
            let camera = non_empty(&camera, "camera")?;
            let valid = camera.chars().all(|c| c.is_ascii_digit())
                || (camera.starts_with("/dev/video")
                    && camera["/dev/video".len()..]
                        .chars()
                        .all(|c| c.is_ascii_digit()));
            if !valid {
                return Err(format!(
                    "camera must be an index or /dev/videoN, got {camera:?}"
                ));
            }
            let script = paths.script("Parallel_working/scripts/face_enroll.py")?;
            ResolvedLaunch {
                program: paths.python().to_path_buf(),
                args: vec![
                    script.to_string_lossy().into_owned(),
                    "--name".into(),
                    athlete.clone(),
                    "--camera".into(),
                    camera,
                    "--replace".into(),
                ],
                cwd,
                label: format!("SCAN FACE (1 cam) · {athlete}"),
                context: LaunchContext {
                    athlete: Some(athlete),
                    athlete_id: None,
                    launch_kind: LaunchKind::Maintenance,
                    drill: None,
                },
            }
        }
        LaunchRequest::FaceModelsDownload {} => {
            let script = paths.script("Parallel_working/scripts/download_face_models.py")?;
            ResolvedLaunch {
                program: paths.python().to_path_buf(),
                args: vec![script.to_string_lossy().into_owned()],
                cwd,
                label: "FACE MODEL SETUP".into(),
                context: LaunchContext {
                    athlete: None,
                    athlete_id: None,
                    launch_kind: LaunchKind::Maintenance,
                    drill: None,
                },
            }
        }
    };
    Ok(resolved)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn paths() -> AppPaths {
        AppPaths::discover().expect("repo root discoverable from the manifest dir")
    }

    fn parse(json: serde_json::Value) -> Result<LaunchRequest, serde_json::Error> {
        serde_json::from_value(json)
    }

    fn parse_raw(json: &str) -> Result<LaunchRequest, serde_json::Error> {
        serde_json::from_str(json)
    }

    fn resolve(json: serde_json::Value) -> Result<ResolvedLaunch, String> {
        let request = parse(json).map_err(|error| error.to_string())?;
        resolve_launch(&paths(), request)
    }

    #[test]
    fn exact_frontend_invoke_payloads_deserialize_without_tauri_runtime() {
        #[derive(serde::Deserialize)]
        #[serde(deny_unknown_fields)]
        struct InvokePayload {
            request: LaunchRequest,
        }

        let viewer: InvokePayload = serde_json::from_str(
            r#"{
                "request": {
                    "profile_id": "free_view_usb6",
                    "viewer": {
                        "people": 3,
                        "athlete": "Арлен",
                        "auto_orbit": true,
                        "limb_heat": true
                    }
                }
            }"#,
        )
        .unwrap();
        match viewer.request {
            LaunchRequest::FreeViewUsb6 { viewer } => {
                assert_eq!(viewer.people, Some(3));
                assert_eq!(viewer.athlete.as_deref(), Some("Арлен"));
                assert!(viewer.auto_orbit);
                assert!(viewer.limb_heat);
            }
            _ => panic!("viewer payload resolved to the wrong profile"),
        }

        let drill: InvokePayload = serde_json::from_str(
            r#"{
                "request": {
                    "profile_id": "training_drill",
                    "drill": {
                        "drill": "gk_updown",
                        "duration_s": 45
                    },
                    "athlete": "Арлен",
                    "athlete_id": "athlete-1",
                    "face_id": true,
                    "people": 2
                }
            }"#,
        )
        .unwrap();
        match drill.request {
            LaunchRequest::TrainingDrill {
                drill: TrainingDrillRequest::GkUpdown { duration_s },
                athlete,
                athlete_id,
                face_id,
                people,
            } => {
                assert_eq!(duration_s, 45.0);
                assert_eq!(athlete.as_deref(), Some("Арлен"));
                assert_eq!(athlete_id.as_deref(), Some("athlete-1"));
                assert!(face_id);
                assert_eq!(people, Some(2));
            }
            _ => panic!("drill payload resolved to the wrong profile"),
        }

        let reaction: InvokePayload = serde_json::from_str(
            r#"{
                "request": {
                    "profile_id": "training_drill",
                    "drill": {
                        "drill": "reaction_zones",
                        "rounds": 10,
                        "projector": true
                    }
                }
            }"#,
        )
        .unwrap();
        assert!(matches!(
            reaction.request,
            LaunchRequest::TrainingDrill {
                drill: TrainingDrillRequest::ReactionZones {
                    rounds: 10,
                    projector: true,
                },
                ..
            }
        ));

        let smuggled = r#"{
            "request": {
                "profile_id": "free_view_usb6",
                "program": "/bin/sh"
            }
        }"#;
        assert!(serde_json::from_str::<InvokePayload>(smuggled).is_err());

        let extra_envelope_key = r#"{
            "request": {"profile_id": "free_view_usb6"},
            "program": "/bin/sh"
        }"#;
        assert!(serde_json::from_str::<InvokePayload>(extra_envelope_key).is_err());

        let duplicate_request = r#"{
            "request": {"profile_id": "free_view_usb6"},
            "request": {"profile_id": "record_3d"}
        }"#;
        assert!(serde_json::from_str::<InvokePayload>(duplicate_request).is_err());
    }

    #[test]
    fn repo_root_is_a_real_checkout_and_scripts_stay_inside_it() {
        let paths = paths();
        for sentinel in REPO_SENTINELS {
            assert!(paths.repo_root().join(sentinel).exists());
        }
        let script = paths
            .script("Parallel_working/run_training_drill.sh")
            .unwrap();
        assert!(script.starts_with(paths.repo_root()));
    }

    #[test]
    fn a_path_escaping_the_repository_is_refused() {
        let paths = paths();
        assert!(paths.script("../../../etc/passwd").is_err());
        assert!(paths.script("Parallel_working/../../etc/hosts").is_err());
        // A directory is not a launchable script.
        assert!(paths.script("Parallel_working").is_err());
        // Absent files fail closed rather than resolving to something else.
        assert!(paths
            .script("Parallel_working/definitely_absent.sh")
            .is_err());
    }

    #[test]
    fn a_non_repository_root_is_rejected() {
        assert!(AppPaths::from_root(Path::new("/tmp")).is_err());
    }

    #[test]
    fn every_profile_resolves_to_its_own_script() {
        let cases = [
            ("free_view_usb6", "run_live_usb6_mirrored_skeleton.sh"),
            ("blm_overlay_usb6", "run_live_usb6_blm.sh"),
            ("yolo_pose_4cam", "run_live_parallel_yolopose.sh"),
            ("record_3d", "run_record_3d.sh"),
        ];
        for (profile_id, script) in cases {
            let launch = resolve(serde_json::json!({"profile_id": profile_id})).unwrap();
            assert!(
                launch.args()[0].ends_with(script),
                "{profile_id} -> {:?}",
                launch.args()
            );
            assert_eq!(launch.program(), Path::new("/bin/bash"));
            assert_eq!(launch.cwd(), paths().repo_root());
            assert!(!launch.label().is_empty());
        }
    }

    #[test]
    fn free_view_ends_with_the_degraded_camera_floor() {
        let launch = resolve(serde_json::json!({"profile_id": "free_view_usb6"})).unwrap();
        let args = launch.args();
        // Must be LAST: the wrapper's own `--min-active-cameras 6` is earlier
        // and argparse takes the last occurrence.
        assert_eq!(&args[args.len() - 2..], &["--min-active-cameras", "2"]);
    }

    #[test]
    fn training_never_lowers_the_camera_floor() {
        for drill in [
            serde_json::json!({"drill": "balance", "holds": 4}),
            serde_json::json!({
                "drill": "reaction_zones", "rounds": 10, "projector": true
            }),
        ] {
            let launch = resolve(serde_json::json!({
                "profile_id": "training_drill", "drill": drill
            }))
            .unwrap();
            assert!(
                !launch.args().iter().any(|a| a == "--min-active-cameras"),
                "drills must inherit the launcher's floor of 6: {:?}",
                launch.args()
            );
        }
    }

    #[test]
    fn reaction_zones_projector_is_a_boolean_fullscreen_capability() {
        let projected = resolve(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {
                "drill": "reaction_zones", "rounds": 10, "projector": true
            }
        }))
        .unwrap();
        assert!(projected.args().iter().any(|arg| arg == "--fullscreen"));
        assert_eq!(projected.context().drill.as_deref(), Some("reaction_zones"));

        let windowed = resolve(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {
                "drill": "reaction_zones", "rounds": 10, "projector": false
            }
        }))
        .unwrap();
        assert!(!windowed.args().iter().any(|arg| arg == "--fullscreen"));

        assert!(parse(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {
                "drill": "reaction_zones", "rounds": 10, "projector": "yes"
            }
        }))
        .is_err());
        assert!(parse(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {
                "drill": "reaction_zones", "rounds": 10,
                "projector": true, "fullscreen": "--fullscreen"
            }
        }))
        .is_err());
    }

    #[test]
    fn workload_bounds_are_accepted_at_both_ends() {
        let cases = [
            (serde_json::json!({"drill": "balance", "holds": 2}), "2"),
            (serde_json::json!({"drill": "balance", "holds": 8}), "8"),
            (serde_json::json!({"drill": "shuttle", "reps": 1}), "1"),
            (serde_json::json!({"drill": "shuttle", "reps": 6}), "6"),
            (serde_json::json!({"drill": "line_hops", "sets": 1}), "1"),
            (serde_json::json!({"drill": "line_hops", "sets": 5}), "5"),
            (
                serde_json::json!({"drill": "gk_save", "rounds": 5, "flip": false}),
                "5",
            ),
            (
                serde_json::json!({"drill": "gk_save", "rounds": 20, "flip": false}),
                "20",
            ),
            (
                serde_json::json!({
                    "drill": "reaction_zones", "rounds": 5, "projector": true
                }),
                "5",
            ),
            (
                serde_json::json!({
                    "drill": "reaction_zones", "rounds": 20, "projector": true
                }),
                "20",
            ),
        ];
        for (drill, expected) in cases {
            let launch = resolve(serde_json::json!({
                "profile_id": "training_drill", "drill": drill
            }))
            .unwrap();
            assert!(
                launch.args().contains(&expected.to_string()),
                "{expected} missing from {:?}",
                launch.args()
            );
        }
        for duration in [15.0, 120.0] {
            assert!(resolve(serde_json::json!({
                "profile_id": "training_drill",
                "drill": {"drill": "gk_updown", "duration_s": duration}
            }))
            .is_ok());
        }
    }

    #[test]
    fn zero_and_out_of_range_workloads_are_refused() {
        let bad = [
            serde_json::json!({"drill": "balance", "holds": 0}),
            serde_json::json!({"drill": "balance", "holds": 9}),
            serde_json::json!({"drill": "shuttle", "reps": 0}),
            serde_json::json!({"drill": "shuttle", "reps": 7}),
            serde_json::json!({"drill": "line_hops", "sets": 0}),
            serde_json::json!({"drill": "line_hops", "sets": 6}),
            serde_json::json!({"drill": "gk_save", "rounds": 4, "flip": false}),
            serde_json::json!({"drill": "gk_save", "rounds": 21, "flip": false}),
            serde_json::json!({
                "drill": "reaction_zones", "rounds": 4, "projector": true
            }),
            serde_json::json!({
                "drill": "reaction_zones", "rounds": 21, "projector": true
            }),
            serde_json::json!({"drill": "gk_updown", "duration_s": 14.0}),
            serde_json::json!({"drill": "gk_updown", "duration_s": 121.0}),
        ];
        for drill in bad {
            let result = resolve(serde_json::json!({
                "profile_id": "training_drill", "drill": drill
            }));
            assert!(result.is_err(), "accepted {drill:?}");
        }
    }

    #[test]
    fn a_parameter_belonging_to_another_drill_is_refused() {
        // `holds` is balance's; shuttle takes `reps`.
        assert!(parse(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {"drill": "shuttle", "holds": 4}
        }))
        .is_err());
        // Mixing both is not a way in either.
        assert!(parse(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {"drill": "balance", "holds": 4, "reps": 3}
        }))
        .is_err());
    }

    #[test]
    fn seed_cannot_be_pinned_through_a_profile() {
        // One Random drives both the corner and the cue delay, so a pinned seed
        // makes the sequence learnable and would inflate reaction times.
        assert!(parse(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {"drill": "gk_save", "rounds": 10, "flip": false, "seed": 7}
        }))
        .is_err());
        assert!(parse(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {
                "drill": "reaction_zones", "rounds": 10,
                "projector": true, "seed": 7
            }
        }))
        .is_err());
    }

    #[test]
    fn raw_program_args_and_cwd_cannot_be_smuggled_in() {
        for extra in [
            serde_json::json!({"profile_id": "free_view_usb6", "program": "/bin/sh"}),
            serde_json::json!({"profile_id": "free_view_usb6", "args": ["--shoot-enabled"]}),
            serde_json::json!({"profile_id": "free_view_usb6", "cwd": "/etc"}),
            serde_json::json!({"profile_id": "free_view_usb6", "label": "spoofed"}),
            serde_json::json!({"profile_id": "free_view_usb6", "context": {}}),
        ] {
            assert!(parse(extra.clone()).is_err(), "accepted {extra:?}");
        }
    }

    #[test]
    fn an_unknown_profile_is_refused() {
        assert!(parse(serde_json::json!({"profile_id": "shell"})).is_err());
        assert!(parse(serde_json::json!({"profile_id": "launcher_runtime"})).is_err());
    }

    #[test]
    fn adversarial_json_shapes_numbers_duplicates_and_profile_case_are_refused() {
        let malformed_or_wrong_type = [
            // Extra keys at both request and nested-object levels.
            r#"{"profile_id":"free_view_usb6","program":"/bin/sh"}"#,
            r#"{"profile_id":"free_view_usb6","viewer":{"args":["--shoot-enabled"]}}"#,
            r#"{"profile_id":"training_drill","drill":{"drill":"balance","holds":4,"seed":7}}"#,
            // A nested object cannot stand in for a scalar field.
            r#"{"profile_id":"free_view_usb6","viewer":{"athlete":{"name":"Ann"}}}"#,
            r#"{"profile_id":"training_drill","drill":{"drill":"gk_updown","duration_s":{"value":45}}}"#,
            // Strings and oversized integers cannot bypass numeric types.
            r#"{"profile_id":"free_view_usb6","viewer":{"people":"3"}}"#,
            r#"{"profile_id":"free_view_usb6","viewer":{"people":999}}"#,
            r#"{"profile_id":"training_drill","drill":{"drill":"balance","holds":4294967296}}"#,
            // JSON has no non-finite numbers; serde_json must reject them.
            r#"{"profile_id":"training_drill","drill":{"drill":"gk_updown","duration_s":NaN}}"#,
            r#"{"profile_id":"training_drill","drill":{"drill":"gk_updown","duration_s":Infinity}}"#,
            r#"{"profile_id":"training_drill","drill":{"drill":"gk_updown","duration_s":-Infinity}}"#,
            r#"{"profile_id":"training_drill","drill":{"drill":"gk_updown","duration_s":1e400}}"#,
            // Duplicate keys cannot use a last-value-wins ambiguity.
            r#"{"profile_id":"free_view_usb6","profile_id":"record_3d"}"#,
            r#"{"profile_id":"free_view_usb6","viewer":{"people":2,"people":3}}"#,
            r#"{"profile_id":"training_drill","drill":{"drill":"gk_updown","duration_s":30,"duration_s":45}}"#,
            // Profile IDs are an exact, case-sensitive enum.
            r#"{"profile_id":"FREE_VIEW_USB6"}"#,
            r#"{"profile_id":"Free_View_Usb6"}"#,
            r#"{"profile_id":"free_View_usb6"}"#,
        ];
        for raw in malformed_or_wrong_type {
            assert!(parse_raw(raw).is_err(), "accepted adversarial JSON: {raw}");
        }

        // A finite value too large for the protocol may deserialize, but the
        // semantic resolver still refuses it before session creation.
        let huge_duration = parse_raw(
            r#"{"profile_id":"training_drill","drill":{"drill":"gk_updown","duration_s":1e308}}"#,
        )
        .unwrap();
        assert!(resolve_launch(&paths(), huge_duration).is_err());
    }

    #[test]
    fn legitimate_unicode_identity_remains_supported() {
        let launch = resolve(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {"drill": "balance", "holds": 4},
            "athlete": "  Арлен Өмірбек  ",
            "athlete_id": "спортсмен-1"
        }))
        .unwrap();
        assert_eq!(launch.context().athlete.as_deref(), Some("Арлен Өмірбек"));
        assert_eq!(launch.context().athlete_id.as_deref(), Some("спортсмен-1"));
    }

    #[test]
    fn command_bound_identity_rejects_controls_options_reserved_tokens_and_huge_values() {
        let oversized = "А".repeat(129);
        let malicious = [
            "Ann\n--shoot-enabled".to_string(),
            "Ann\0hidden".to_string(),
            "--shoot-enabled".to_string(),
            "--SHOOT-ENABLED".to_string(),
            "/dev/ttyUSB0".to_string(),
            "/DEV/TTYUSB0".to_string(),
            "live_aim_test".to_string(),
            "blm_follow".to_string(),
            "launcher_runtime".to_string(),
            oversized,
        ];
        for athlete in malicious {
            for request in [
                serde_json::json!({
                    "profile_id": "free_view_usb6",
                    "viewer": {"athlete": athlete}
                }),
                serde_json::json!({
                    "profile_id": "training_drill",
                    "drill": {"drill": "balance", "holds": 4},
                    "athlete": athlete
                }),
                serde_json::json!({
                    "profile_id": "face_enroll_arena",
                    "athlete": athlete
                }),
            ] {
                assert!(
                    resolve(request.clone()).is_err(),
                    "accepted command-bound identity {athlete:?} in {request:?}"
                );
            }
        }
    }

    #[test]
    fn unicode_homoglyphs_remain_inert_identity_data() {
        // U+2212 looks like a hyphen to a person but is not the ASCII option
        // prefix. It remains one argv value and cannot become the real flag.
        let lookalike = "−−shoot-enabled";
        let launch = resolve(serde_json::json!({
            "profile_id": "free_view_usb6",
            "viewer": {"athlete": lookalike}
        }))
        .unwrap();
        assert!(launch.args().iter().any(|arg| arg == lookalike));
        assert!(!launch.args().iter().any(|arg| arg == "--shoot-enabled"));
    }

    #[test]
    fn context_only_athlete_id_rejects_controls_and_huge_values() {
        for athlete_id in ["id\nspoof".to_string(), "x".repeat(129)] {
            let request = serde_json::json!({
                "profile_id": "training_drill",
                "drill": {"drill": "balance", "holds": 4},
                "athlete_id": athlete_id
            });
            assert!(
                resolve(request.clone()).is_err(),
                "accepted invalid athlete_id in {request:?}"
            );
        }
    }

    #[test]
    fn the_blm_profile_carries_no_fire_control_or_serial_argument() {
        let launch = resolve(serde_json::json!({"profile_id": "blm_overlay_usb6"})).unwrap();
        let rendered = launch.args().join(" ");
        for forbidden in [
            "--shoot-enabled",
            "--serial-port",
            "/dev/ttyUSB",
            "live_aim_test",
            "blm_follow",
            "launcher_runtime",
            "--wheel-rpm",
        ] {
            assert!(
                !rendered.contains(forbidden),
                "{forbidden} reachable via the BLM profile: {rendered}"
            );
        }
        assert!(matches!(launch.context().launch_kind, LaunchKind::Viewer));
    }

    #[test]
    fn no_profile_can_emit_a_fire_control_argument() {
        let every = [
            serde_json::json!({"profile_id": "free_view_usb6"}),
            serde_json::json!({"profile_id": "blm_overlay_usb6"}),
            serde_json::json!({"profile_id": "yolo_pose_4cam"}),
            serde_json::json!({"profile_id": "record_3d"}),
            serde_json::json!({"profile_id": "training_drill",
                               "drill": {"drill": "gk_save", "rounds": 10, "flip": true}}),
            serde_json::json!({"profile_id": "training_drill",
                               "drill": {"drill": "reaction_zones", "rounds": 10,
                                         "projector": true}}),
            serde_json::json!({"profile_id": "face_models_download"}),
        ];
        for request in every {
            let launch = resolve(request.clone()).unwrap();
            let rendered = launch.args().join(" ");
            assert!(!rendered.contains("--shoot-enabled"), "{request:?}");
            assert!(!rendered.contains("/dev/tty"), "{request:?}");
        }
    }

    #[test]
    fn athlete_id_is_context_only_and_never_a_command_line_argument() {
        let launch = resolve(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {"drill": "balance", "holds": 4},
            "athlete": "Арлен",
            "athlete_id": "uuid-1",
            "face_id": true
        }))
        .unwrap();
        let rendered = launch.args().join(" ");
        assert!(rendered.contains("--athlete Арлен"));
        assert!(rendered.contains("--face-id"));
        // The wrapper's allowlist has no --athlete-id; identity travels in the
        // session manifest instead.
        assert!(!rendered.contains("uuid-1"), "{rendered}");
        assert_eq!(launch.context().athlete_id.as_deref(), Some("uuid-1"));
        assert_eq!(launch.context().athlete.as_deref(), Some("Арлен"));
        assert_eq!(launch.context().drill.as_deref(), Some("balance"));
    }

    #[test]
    fn reaction_zones_v1_record_uses_the_shared_typed_evidence_reader() {
        let root = std::env::temp_dir().join(format!(
            "project-cam-reaction-evidence-{}",
            uuid::Uuid::new_v4().simple()
        ));
        let training = root.join("garage_lab_combined/output/training_logs");
        std::fs::create_dir_all(&training).unwrap();
        let record = serde_json::json!({
            "schema": "project_cam.training.v1",
            "session_id": "reaction-session-typed-reader",
            "drill": "reaction_zones",
            "title": "REACTION ZONES",
            "role": "field",
            "athlete": "Арлен",
            "started": "2026-07-30T10:00:00",
            "ended": "2026-07-30T10:02:00",
            "aborted": false,
            "headline": "8/10 hits · avg 0.62 s",
            "summary": {
                "rounds_completed": 10,
                "hits_in_timeout": 8,
                "avg_reaction_s": 0.62,
                "weakest_zone": "RIGHT"
            },
            "evidence_context": {
                "protocol_id": "reaction_zones.v1",
                "applied_parameters": {
                    "rounds": 10,
                    "arena_y_mm": 3050,
                    "wall_margin_mm": 500
                },
                "protocol_parameters_fingerprint": "sha256:test"
            }
        });
        std::fs::write(training.join("sessions_index.jsonl"), format!("{record}\n")).unwrap();

        let evidence = crate::evidence::load_session_evidence(&root, None, 10, 10, None).unwrap();
        let row = evidence
            .sessions
            .iter()
            .find(|row| row.session_id == "reaction-session-typed-reader")
            .expect("reaction session missing from typed evidence");
        assert_eq!(row.drill, "reaction_zones");
        assert_eq!(
            row.evidence_context
                .as_ref()
                .and_then(|value| value.get("protocol_id"))
                .and_then(serde_json::Value::as_str),
            Some("reaction_zones.v1")
        );
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn face_id_without_a_name_is_refused_and_blank_names_do_not_count() {
        assert!(resolve(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {"drill": "balance", "holds": 4},
            "face_id": true
        }))
        .is_err());
        let launch = resolve(serde_json::json!({
            "profile_id": "training_drill",
            "drill": {"drill": "balance", "holds": 4},
            "athlete": "   "
        }))
        .unwrap();
        assert!(!launch.args().iter().any(|a| a == "--athlete"));
    }

    #[test]
    fn face_enroll_camera_must_be_an_index_or_device_node() {
        for bad in ["; rm -rf /", "--replace", "/etc/passwd", "0 --name x"] {
            assert!(
                resolve(serde_json::json!({
                    "profile_id": "face_enroll_single",
                    "athlete": "Ann", "camera": bad
                }))
                .is_err(),
                "accepted camera {bad:?}"
            );
        }
        assert!(resolve(serde_json::json!({
            "profile_id": "face_enroll_single", "athlete": "Ann", "camera": "0"
        }))
        .is_ok());
        assert!(resolve(serde_json::json!({
            "profile_id": "face_enroll_single", "athlete": "Ann", "camera": "/dev/video2"
        }))
        .is_ok());
    }

    #[test]
    fn display_command_is_repo_relative() {
        let launch = resolve(serde_json::json!({"profile_id": "record_3d"})).unwrap();
        let shown = launch.display_command();
        assert!(shown.starts_with("bash "), "{shown}");
        assert!(!shown.contains("/home/"), "{shown}");
    }

    #[test]
    fn viewer_options_replace_the_hand_built_argument_vector() {
        let launch = resolve(serde_json::json!({
            "profile_id": "free_view_usb6",
            "viewer": {"people": 3, "athlete": "Арлен", "auto_orbit": true, "limb_heat": true}
        }))
        .unwrap();
        let rendered = launch.args().join(" ");
        assert!(rendered.contains("--multi-person 3"), "{rendered}");
        assert!(
            rendered.contains("--face-id --primary-person Арлен"),
            "{rendered}"
        );
        assert!(rendered.contains("--auto-orbit"));
        assert!(rendered.contains("--limb-heat"));
        // The degraded floor still has the last word.
        let args = launch.args();
        assert_eq!(&args[args.len() - 2..], &["--min-active-cameras", "2"]);
        assert_eq!(launch.context().athlete.as_deref(), Some("Арлен"));
    }

    #[test]
    fn viewer_people_count_is_bounded_and_unknown_options_are_refused() {
        assert!(resolve(serde_json::json!({
            "profile_id": "free_view_usb6", "viewer": {"people": 0}
        }))
        .is_err());
        assert!(resolve(serde_json::json!({
            "profile_id": "free_view_usb6", "viewer": {"people": 7}
        }))
        .is_err());
        assert!(parse(serde_json::json!({
            "profile_id": "free_view_usb6", "viewer": {"extra_flag": "--shoot-enabled"}
        }))
        .is_err());
    }
}
