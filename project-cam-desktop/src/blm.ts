// The launcher console's intent vocabulary. Mirrors ConsoleCommand in
// src-tauri/src/blm.rs (contract-tested in tests/test_desktop_launcher_console.py).
//
// The UI never composes serial text and never composes the bridge's protocol
// text: it names one of these and the backend renders the line. Ranges here are
// for the WIDGETS — the backend refuses out-of-range values and the Python
// bridge clamps as a last line of defence, so a slider bug cannot become a
// different shot than the operator asked for.

export const ANGLE_LIMIT_DEG = 30;
/** The DEFAULT pitch envelope a session starts with — conservative, since no
 *  downward travel cannot jam the barrel against the ball feeder.
 *
 *  NOT a fixed limit. The collision is at a fixed physical position while the
 *  firmware's angle is measured from a zero adopted at boot or by SET ZERO, so a
 *  constant in that frame points somewhere else after every re-zero — and it
 *  deletes legitimate downward travel, since how much room is left below zero
 *  depends on where zero was set. The live envelope comes from the console
 *  status; these are only the fallback before any status arrives. */
export const PITCH_DEFAULT_MIN_DEG = 0;
export const PITCH_DEFAULT_MAX_DEG = 30;
export const YAW_LIMIT_DEG = 30;
export const RPM_MAX = 1200;
/** The firmware refuses `shoot` below this, and the bridge refuses to arm. */
export const RPM_MIN_FIRE = 400;
/** A fire request must carry exactly this word, so a stray invoke is not a shot. */
export const FIRE_CONFIRMATION = "FIRE";

export type FitKind = "linear" | "quadratic" | "interp";

export type ConsoleCommand =
  | { command: "aim"; pitch_deg: number; yaw_deg: number; wheel_rpm: number }
  | { command: "wheels"; wheel_rpm: number }
  | { command: "reload" }
  | { command: "arm" }
  | { command: "disarm" }
  | { command: "fire"; confirm: string }
  | { command: "stop" }
  | { command: "clear" }
  | { command: "center" }
  /** Adopt the barrel's current physical position as zero. Moves nothing. */
  | { command: "set_zero" }
  /** Declare the pitch travel measured from the current zero. */
  | { command: "limits"; pitch_min_deg: number; pitch_max_deg: number }
  | { command: "info" }
  | { command: "measure"; rpm: number; landing_distance_m: number }
  | { command: "undo" }
  | { command: "fit"; height_m: number; kind: FitKind };

/** A serial device the backend found, with the evidence for what it is.
 *
 *  Mirrors `SerialDevice` in src-tauri/src/launch_profiles.rs. Detection is
 *  PASSIVE — USB identity read from sysfs, no port opened — hence
 *  `likely_launcher` rather than `is_launcher`: only opening the console and
 *  polling the firmware proves what is on the other end, and the UI must not
 *  imply otherwise.
 */
export type SerialDevice = {
  /** What to launch with: a stable /dev/serial/by-id link when one exists. */
  path: string;
  /** The kernel node it currently resolves to — this is what moves on replug. */
  node: string;
  label: string;
  usb_id: string;
  likely_launcher: boolean;
  reason: string;
};

/** Pick the device to preselect, without ever overriding a deliberate choice.
 *
 *  `current` is kept whenever it is still present, so a manual override survives
 *  the periodic refresh. Otherwise the likely launcher wins — the list is already
 *  sorted with those first, so this is the first entry in practice.
 */
export function autoSelectPort(devices: SerialDevice[], current: string): string {
  if (current && devices.some((device) => device.path === current)) return current;
  const preferred = devices.find((device) => device.likely_launcher) ?? devices[0];
  return preferred?.path ?? "";
}

/** Status the bridge publishes on stdout, one line per change, prefixed so the
 *  mission log can route it out of the human-readable stream. */
export const STATUS_PREFIX = "@BLM ";

export type ConsoleStatus = {
  schema: string;
  port: string;
  connected: boolean;
  allow_fire: boolean;
  estop_latched: boolean;
  armed: boolean;
  arm_remaining_s: number;
  arm_timeout_s: number;
  pitch_deg: number | null;
  yaw_deg: number | null;
  wheel_rpm: number;
  rpm_left: number | null;
  rpm_right: number | null;
  rpm_min_fire: number;
  angle_limit_deg: number;
  /** The live envelope, in the current zero's frame. */
  pitch_min_deg: number;
  pitch_max_deg: number;
  pitch_default_min_deg: number;
  pitch_default_max_deg: number;
  yaw_limit_deg: number;
  shots_fired: number;
  last_refusal: string;
  info_lines: string[];
  measurements: { rpm: number; distance_m: number }[];
  model_path: string;
  model_summary: string;
};

/** Parse a `@BLM {...}` line. Returns null for anything else, so an ordinary log
 *  line can never be mistaken for telemetry. */
export function parseStatusLine(line: string): ConsoleStatus | null {
  if (!line.startsWith(STATUS_PREFIX)) return null;
  try {
    const parsed = JSON.parse(line.slice(STATUS_PREFIX.length));
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as ConsoleStatus;
  } catch {
    return null;
  }
}

/** Everything the operator must satisfy before a shot is even offered.
 *
 *  `roomClear` is the one condition no machine can check: the bridge enforces
 *  arm-then-fire, one shot per arm and the RPM gate, but only a person can say
 *  the room is empty. Kept here so the reason a FIRE button is disabled is
 *  always visible rather than inferred.
 */
export function fireBlockers(
  status: ConsoleStatus | null,
  roomClear: boolean
): string[] {
  const blockers: string[] = [];
  if (!status) return ["console is not running"];
  if (!status.connected) blockers.push("serial link is down");
  if (!status.allow_fire) blockers.push("console was opened without fire control");
  if (status.estop_latched) blockers.push("ESTOP latched — release it first");
  if (!roomClear) blockers.push("room-clear not confirmed");
  if (status.pitch_deg === null) blockers.push("no aim sent yet");
  if (status.wheel_rpm < RPM_MIN_FIRE)
    blockers.push(`wheels below the ${RPM_MIN_FIRE} RPM gate`);
  if (!status.armed) blockers.push("not armed");
  return blockers;
}
