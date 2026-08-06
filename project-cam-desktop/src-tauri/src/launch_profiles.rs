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

use serde::{Deserialize, Serialize};
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
    /// The operator console for the ball launcher — the ONLY profile that opens
    /// the serial link, and the only one with a writable stdin.
    ///
    /// It does not receive a fire-control ARGUMENT: `--allow-fire` merely makes
    /// the arm/fire intents exist in the bridge's protocol, and every shot still
    /// needs a fresh arm inside a live session. Serial writes stay in
    /// `blm_bridge.py`, which is where the clamps, the ESTOP latch and the
    /// stop-only exit path already live (`center` is deliberately opt-in).
    BlmConsole {
        /// A device node chosen from `list_serial_ports`, never free-form text.
        serial_port: String,
        #[serde(default)]
        allow_fire: bool,
    },
}

/// Device nodes an ESP32 enumerates as. Anything else is not a launcher link.
const SERIAL_PREFIXES: [&str; 2] = ["/dev/ttyUSB", "/dev/ttyACM"];

/// Stable per-device symlinks. `/dev/ttyUSB<n>` is assigned in plug order, so it
/// MOVES: the launcher was ttyUSB0 and came back as ttyUSB1 after one USB
/// re-enumeration on 2026-08-06. Selecting the by-id path instead survives that,
/// the same reason the camera config uses by-id links.
const SERIAL_BY_ID_DIR: &str = "/dev/serial/by-id";

/// USB-serial bridges that an ESP32 control board appears as. `10c4:ea60` is the
/// CP2102 on this rig's launcher; the rest are the other common bridges, listed
/// so a board swap does not silently stop being detected. `303a` is Espressif's
/// own VID, used when an ESP32-S2/S3 exposes USB directly.
const USB_SERIAL_BRIDGES: [&str; 6] = [
    "10c4:ea60", // Silicon Labs CP210x
    "1a86:7523", // WCH CH340
    "1a86:55d4", // WCH CH9102
    "0403:6001", // FTDI FT232R
    "0403:6015", // FTDI FT231X
    "067b:2303", // Prolific PL2303
];

/// A serial device offered to the operator, with the evidence for what it is.
///
/// Detection is passive — USB identity read from sysfs, no port opened — so it
/// can say "this is the adapter a launcher uses" and never "this is the
/// launcher". Only opening the console and polling the firmware proves that, and
/// the UI says so rather than implying the label is a verification.
#[derive(Clone, Debug, Serialize)]
pub struct SerialDevice {
    /// What to launch with: the stable by-id path when one exists.
    pub path: String,
    /// The kernel node it currently resolves to, shown so a moving number is
    /// visible rather than surprising.
    pub node: String,
    pub label: String,
    pub usb_id: String,
    pub likely_launcher: bool,
    pub reason: String,
}

/// Read `idVendor`/`idProduct`/`manufacturer`/`product` for a tty node by walking
/// up from its sysfs device link to the owning USB device.
fn sysfs_identity(node: &str) -> (String, String, String) {
    let unknown = (String::new(), String::new(), String::new());
    let Some(name) = Path::new(node).file_name() else {
        return unknown;
    };
    let link = Path::new("/sys/class/tty").join(name).join("device");
    let Ok(mut dir) = link.canonicalize() else {
        return unknown;
    };
    let read = |base: &Path, file: &str| {
        std::fs::read_to_string(base.join(file))
            .map(|value| value.trim().to_string())
            .unwrap_or_default()
    };
    // A tty sits one or two interface levels below the USB device that carries
    // the identity files, so walk up a bounded number of parents.
    for _ in 0..6 {
        if dir.join("idVendor").is_file() {
            let vendor = read(&dir, "idVendor");
            let product_id = read(&dir, "idProduct");
            let usb_id = if vendor.is_empty() || product_id.is_empty() {
                String::new()
            } else {
                format!("{vendor}:{product_id}")
            };
            return (usb_id, read(&dir, "manufacturer"), read(&dir, "product"));
        }
        match dir.parent() {
            Some(parent) => dir = parent.to_path_buf(),
            None => break,
        }
    }
    unknown
}

/// Classify passively. Returns (likely_launcher, reason).
fn classify(usb_id: &str, manufacturer: &str, product: &str) -> (bool, String) {
    let described = format!("{manufacturer} {product}").to_ascii_lowercase();
    // A webcam exposing a CDC-ACM interface is exactly the trap here: both
    // /dev/ttyACM nodes on this rig are `2bdf:0289 1080P USB Camera`. Never offer
    // one as a launcher, whatever else matches.
    for exclude in ["camera", "webcam", "video"] {
        if described.contains(exclude) {
            return (
                false,
                format!("USB video device ({product}) — not a launcher"),
            );
        }
    }
    if USB_SERIAL_BRIDGES.contains(&usb_id) {
        return (
            true,
            format!("{product} — the USB-serial bridge a launcher board uses"),
        );
    }
    if usb_id.starts_with("303a:") {
        return (
            true,
            format!("{product} — Espressif native USB")
                .trim()
                .to_string(),
        );
    }
    if usb_id.is_empty() {
        return (false, "no USB identity available".to_string());
    }
    (false, format!("unrecognised device {usb_id}"))
}

/// Serial devices currently present, each with its passive identification, most
/// likely launcher first. The console's picker reads this, so a port is always a
/// selection from evidence rather than typed text.
pub fn enumerate_serial_devices() -> Vec<SerialDevice> {
    let mut devices: Vec<SerialDevice> = Vec::new();
    let mut seen_nodes: Vec<String> = Vec::new();

    let mut push = |path: String, label_hint: Option<String>| {
        let Ok(node) = validated_serial_port(&path) else {
            return;
        };
        if seen_nodes.contains(&node) {
            return;
        }
        seen_nodes.push(node.clone());
        let (usb_id, manufacturer, product) = sysfs_identity(&node);
        let (likely_launcher, reason) = classify(&usb_id, &manufacturer, &product);
        let label = if !product.is_empty() {
            if manufacturer.is_empty() {
                product.clone()
            } else {
                format!("{product} ({manufacturer})")
            }
        } else {
            label_hint.unwrap_or_else(|| node.clone())
        };
        devices.push(SerialDevice {
            path,
            node,
            label,
            usb_id,
            likely_launcher,
            reason,
        });
    };

    // by-id first, so its stable path is the one offered when both are visible.
    let mut by_id: Vec<PathBuf> = std::fs::read_dir(SERIAL_BY_ID_DIR)
        .map(|entries| entries.flatten().map(|entry| entry.path()).collect())
        .unwrap_or_default();
    by_id.sort();
    for link in by_id {
        let hint = link
            .file_name()
            .map(|name| name.to_string_lossy().into_owned());
        push(link.to_string_lossy().into_owned(), hint);
    }

    // Then raw nodes, catching anything without a by-id link.
    let mut nodes: Vec<PathBuf> = std::fs::read_dir("/dev")
        .map(|entries| entries.flatten().map(|entry| entry.path()).collect())
        .unwrap_or_default();
    nodes.sort();
    for node in nodes {
        push(node.to_string_lossy().into_owned(), None);
    }

    // Stable order, launchers first. `sort_by_key` is stable, so the by-id/alpha
    // ordering above is preserved inside each group.
    devices.sort_by_key(|device| !device.likely_launcher);
    devices
}

/// The shape half of serial-port validation, kept separate from presence so it
/// is testable on a machine with no launcher attached.
///
/// This is not a path the operator composes: it must be one of the two known
/// families and digits only. `AppPaths::script`'s containment rule cannot help
/// here (a device node is outside the repo by definition), so the shape check IS
/// the boundary.
pub fn serial_port_shape(value: &str) -> Result<String, String> {
    let trimmed = value.trim();
    let describe = || {
        format!(
            "serial_port must be /dev/ttyUSB<n>, /dev/ttyACM<n> or a \
             {SERIAL_BY_ID_DIR}/<name> link, got {trimmed:?}"
        )
    };
    if let Some(name) = trimmed.strip_prefix(&format!("{SERIAL_BY_ID_DIR}/")) {
        // One path segment of ordinary characters. The link's TARGET is checked
        // by validated_serial_port, which canonicalizes first — so this only has
        // to refuse a name that could climb out of the directory.
        if name.is_empty()
            || name.len() > 200
            || name.contains('/')
            || name == "."
            || name == ".."
            || name.chars().any(char::is_control)
        {
            return Err(describe());
        }
        return Ok(trimmed.to_string());
    }
    let index = SERIAL_PREFIXES
        .iter()
        .find_map(|prefix| trimmed.strip_prefix(prefix))
        .ok_or_else(describe)?;
    if index.is_empty()
        || index.len() > 3
        || !index.chars().all(|character| character.is_ascii_digit())
    {
        return Err(describe());
    }
    Ok(trimmed.to_string())
}

/// Accept a serial device that is present, returning the kernel node it resolves
/// to. Fail-closed: a console for an absent port would open nothing and then look
/// connected.
///
/// A by-id link is canonicalized FIRST and its target re-checked against the node
/// shape — the same discipline `AppPaths::script` uses, so a symlink pointing at
/// something that is not a serial node cannot get through by having a tidy name.
pub fn validated_serial_port(value: &str) -> Result<String, String> {
    let port = serial_port_shape(value)?;
    let resolved = Path::new(&port)
        .canonicalize()
        .map_err(|_| format!("{port} is not present — is the launcher plugged in?"))?;
    let node = resolved.to_string_lossy().into_owned();
    if port.starts_with(SERIAL_BY_ID_DIR) {
        // Re-run the node half of the shape check on the resolved target.
        let index = SERIAL_PREFIXES
            .iter()
            .find_map(|prefix| node.strip_prefix(prefix))
            .ok_or_else(|| format!("{port} does not resolve to a serial device node"))?;
        if index.is_empty() || !index.chars().all(|character| character.is_ascii_digit()) {
            return Err(format!("{port} does not resolve to a serial device node"));
        }
    }
    Ok(node)
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
    /// Whether this child gets a writable stdin. Stated per profile rather than
    /// derived, because it is the difference between a process the operator can
    /// only start and stop and one they can keep sending intents to. Exactly one
    /// profile sets it, and a test pins that.
    stdin_writable: bool,
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
    pub fn stdin_writable(&self) -> bool {
        self.stdin_writable
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
                stdin_writable: false,
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
                stdin_writable: false,
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
                stdin_writable: false,
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
                stdin_writable: false,
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
                stdin_writable: false,
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
                stdin_writable: false,
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
                stdin_writable: false,
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
                stdin_writable: false,
                label: "FACE MODEL SETUP".into(),
                context: LaunchContext {
                    athlete: None,
                    athlete_id: None,
                    launch_kind: LaunchKind::Maintenance,
                    drill: None,
                },
            }
        }
        LaunchRequest::BlmConsole {
            serial_port,
            allow_fire,
        } => {
            // Launch with the path the operator selected — a by-id link when one
            // exists, because the kernel node moves on re-enumeration. Validation
            // proves it is present and resolves to a real serial node; the
            // resolved node itself is only used for identification and logging.
            let port = serial_port_shape(&serial_port)?;
            let node = validated_serial_port(&serial_port)?;
            let script = paths.script("garage_lab_combined/scripts/blm_bridge.py")?;
            let mut args = vec![
                script.to_string_lossy().into_owned(),
                "--serial-port".into(),
                port.clone(),
            ];
            if allow_fire {
                args.push("--allow-fire".into());
            }
            ResolvedLaunch {
                program: paths.python().to_path_buf(),
                args,
                cwd,
                // The one profile with a live channel: the console exists to keep
                // taking intents, unlike a viewer that is only started and stopped.
                stdin_writable: true,
                // The label names the node, not the by-id link: a 60-character
                // stable path is unreadable in a footer, and the node is what a
                // person cross-checks against `ls /dev`.
                label: format!(
                    "BLM CONSOLE · {} · {node}",
                    if allow_fire {
                        "FIRE ENABLED"
                    } else {
                        "AIM ONLY"
                    }
                ),
                context: LaunchContext {
                    athlete: None,
                    athlete_id: None,
                    launch_kind: LaunchKind::Launcher,
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

    /// Every profile EXCEPT the launcher console. Kept as a named list so adding
    /// a profile is a deliberate decision about which side of this line it is on.
    fn non_console_requests() -> Vec<serde_json::Value> {
        vec![
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
        ]
    }

    #[test]
    fn only_the_console_may_name_a_serial_port_and_nothing_may_name_shoot_enabled() {
        // NARROWED 2026-08-04, deliberately. Until the BLM console profile landed
        // this asserted that NO profile could name a serial port, and that was the
        // tripwire guarding "the desktop app does not write launcher serial". The
        // console crosses that line on purpose; every other profile must not, and
        // `--shoot-enabled` stays unreachable from ALL of them, console included —
        // firing is a runtime intent the bridge gates, never a launch argument.
        for request in non_console_requests() {
            let launch = resolve(request.clone()).unwrap();
            let rendered = launch.args().join(" ");
            assert!(!rendered.contains("--shoot-enabled"), "{request:?}");
            assert!(!rendered.contains("/dev/tty"), "{request:?}");
            assert!(
                !launch.stdin_writable(),
                "{request:?} must not get a command channel"
            );
        }

        // The console itself: a serial port yes, a fire-control flag never.
        let Some(port) = enumerate_serial_devices()
            .into_iter()
            .map(|device| device.path)
            .next()
        else {
            // No launcher attached (CI, or unplugged): the profile must then fail
            // closed rather than resolve to a console for an absent device.
            let refused = resolve(serde_json::json!({
                "profile_id": "blm_console", "serial_port": "/dev/ttyUSB0",
                "allow_fire": true
            }))
            .unwrap_err();
            assert!(refused.contains("not present"), "{refused}");
            return;
        };
        let launch = resolve(serde_json::json!({
            "profile_id": "blm_console", "serial_port": port, "allow_fire": true
        }))
        .unwrap();
        let rendered = launch.args().join(" ");
        assert!(rendered.contains(&port), "{rendered}");
        assert!(rendered.contains("--allow-fire"), "{rendered}");
        assert!(!rendered.contains("--shoot-enabled"), "{rendered}");
        assert!(launch.args()[0].ends_with("blm_bridge.py"), "{rendered}");
        assert_eq!(launch.program(), paths().python());
        assert!(launch.stdin_writable());
        assert!(matches!(launch.context().launch_kind, LaunchKind::Launcher));

        // Fire control is opt-in per launch, and absent by default.
        let aim_only = resolve(serde_json::json!({
            "profile_id": "blm_console", "serial_port": port
        }))
        .unwrap();
        assert!(!aim_only.args().join(" ").contains("--allow-fire"));
        assert!(
            aim_only.label().contains("AIM ONLY"),
            "{}",
            aim_only.label()
        );
    }

    #[test]
    fn a_serial_port_must_be_a_device_node_of_a_known_family() {
        for good in [
            "/dev/ttyUSB0",
            "/dev/ttyACM0",
            "/dev/ttyUSB12",
            " /dev/ttyACM3 ",
        ] {
            assert_eq!(serial_port_shape(good).unwrap(), good.trim(), "{good:?}");
        }
        for bad in [
            "",
            "/dev/ttyUSB",     // no index
            "/dev/ttyUSBx",    // not a number
            "/dev/ttyUSB0000", // implausibly long, so probably crafted
            "/dev/ttyS0",      // a real port family, but not an ESP32 link
            "/dev/video0",
            "/dev/ttyUSB0; rm -rf /",
            "/dev/ttyUSB0 --allow-fire",
            "/dev/ttyUSB0\nshoot",
            "../../dev/ttyUSB0",
            "/dev/../dev/ttyUSB0", // resolves to a valid node but is not the shape
            "/etc/passwd",
        ] {
            assert!(serial_port_shape(bad).is_err(), "accepted port {bad:?}");
        }
    }

    #[test]
    fn a_stable_by_id_link_is_an_acceptable_port_but_cannot_climb_out_of_its_directory() {
        // The kernel node moves: the launcher was ttyUSB0 and came back as
        // ttyUSB1 after one re-enumeration, which is why the by-id form exists.
        assert_eq!(
            serial_port_shape("/dev/serial/by-id/usb-Silicon_Labs_CP2102_0001-if00-port0").unwrap(),
            "/dev/serial/by-id/usb-Silicon_Labs_CP2102_0001-if00-port0"
        );
        for bad in [
            "/dev/serial/by-id/",
            "/dev/serial/by-id/.",
            "/dev/serial/by-id/..",
            "/dev/serial/by-id/../../etc/passwd",
            "/dev/serial/by-id/sub/dir",
            "/dev/serial/by-id/name\nshoot",
            "/dev/serial/by-path/pci-0000:00:14.0-usb-0:11.1.1:1.0-port0",
        ] {
            assert!(serial_port_shape(bad).is_err(), "accepted {bad:?}");
        }
    }

    #[test]
    fn a_by_id_link_must_resolve_to_a_serial_node() {
        // Presence and target are checked by canonicalizing FIRST, so a tidy name
        // pointing somewhere else cannot get through.
        let dir = std::env::temp_dir().join(format!(
            "project-cam-serial-{}",
            uuid::Uuid::new_v4().simple()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let decoy = dir.join("not-a-tty");
        std::fs::write(&decoy, b"x").unwrap();
        // Cannot write into /dev in a test, so exercise the resolution rule via
        // the real directory when a device is attached, and the shape rule always.
        assert!(validated_serial_port("/dev/serial/by-id/definitely-absent-link").is_err());
        let _ = std::fs::remove_dir_all(&dir);

        for device in enumerate_serial_devices() {
            // Whatever is offered must resolve to a node of a known family.
            assert!(
                device.node.starts_with("/dev/ttyUSB") || device.node.starts_with("/dev/ttyACM"),
                "{device:?}"
            );
            assert!(validated_serial_port(&device.path).is_ok(), "{device:?}");
            assert!(!device.label.is_empty(), "{device:?}");
            assert!(!device.reason.is_empty(), "{device:?}");
        }
    }

    #[test]
    fn a_usb_video_device_is_never_offered_as_a_launcher() {
        // Both /dev/ttyACM nodes on this rig are `2bdf:0289 1080P USB Camera`: a
        // webcam that exposes a CDC-ACM interface. Offering one as the launcher is
        // the exact trap this classifier exists to close.
        let (likely, reason) = classify("2bdf:0289", "SN0002", "1080P USB Camera");
        assert!(!likely, "{reason}");
        assert!(reason.contains("video"), "{reason}");
        // Even a bridge VID must lose to a camera description.
        let (likely, _) = classify("10c4:ea60", "SN0002", "USB Camera");
        assert!(!likely);
    }

    #[test]
    fn a_usb_serial_bridge_is_offered_as_the_likely_launcher_without_claiming_certainty() {
        let (likely, reason) = classify(
            "10c4:ea60",
            "Silicon Labs",
            "CP2102 USB to UART Bridge Controller",
        );
        assert!(likely);
        assert!(reason.contains("CP2102"), "{reason}");
        // The wording must stay evidential: this is the adapter a launcher uses,
        // not a verified launcher. Only polling the firmware proves that.
        assert!(
            !reason.to_lowercase().contains("is the launcher"),
            "{reason}"
        );

        for bridge in ["1a86:7523", "0403:6001", "303a:1001"] {
            assert!(classify(bridge, "", "board").0, "{bridge} not recognised");
        }
        for other in ["", "1234:5678"] {
            assert!(!classify(other, "", "").0, "{other} wrongly recognised");
        }
    }

    #[test]
    fn the_likely_launcher_sorts_first_so_the_ui_can_preselect_it() {
        let devices = enumerate_serial_devices();
        let first_other = devices.iter().position(|device| !device.likely_launcher);
        let last_launcher = devices.iter().rposition(|device| device.likely_launcher);
        if let (Some(other), Some(launcher)) = (first_other, last_launcher) {
            assert!(
                launcher < other,
                "a likely launcher must not sort after an unrecognised device: {devices:?}"
            );
        }
    }

    #[test]
    fn the_console_cannot_be_asked_to_run_something_else() {
        for smuggled in [
            serde_json::json!({"profile_id": "blm_console", "serial_port": "/dev/ttyUSB0",
                               "program": "/bin/sh"}),
            serde_json::json!({"profile_id": "blm_console", "serial_port": "/dev/ttyUSB0",
                               "args": ["--shoot-enabled"]}),
            serde_json::json!({"profile_id": "blm_console", "serial_port": "/dev/ttyUSB0",
                               "baud": 9600}),
            serde_json::json!({"profile_id": "blm_console", "serial_port": "/dev/ttyUSB0",
                               "arm_timeout_s": 100000}),
            // The port is required: no default may quietly pick a device.
            serde_json::json!({"profile_id": "blm_console"}),
        ] {
            assert!(parse(smuggled.clone()).is_err(), "accepted {smuggled:?}");
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
