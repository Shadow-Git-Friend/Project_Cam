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
  /** No rpm by design: the wheels are stopped before a distance can be measured,
   *  so the bridge takes the RPM from the shot that was actually fired. */
  | { command: "measure"; landing_distance_m: number }
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
  /** An aim the operator actually established. `pitch_deg` alone is not that: an
   *  RPM-only change also has to state the angles, because the firmware takes one
   *  combined `set v h wl wr`. */
  aim_established: boolean;
  wheel_rpm: number;
  /** MEASURED flywheel RPM, and how old the reading is. The age is not optional
   *  decoration: the firmware stops sending while the pusher moves and a dead
   *  reader leaves the last numbers in place forever, so a frozen "0 / 0" would
   *  read as "the wheels are stopped, it is safe to walk out". `null` age means no
   *  reading has ever arrived. */
  rpm_left: number | null;
  rpm_right: number | null;
  telemetry_age_s: number | null;
  telemetry_max_age_s: number;
  /** The bridge's verdicts, NOT recomputed here. These are the same predicates its
   *  arm and fire gates use, and one safety rule must have one implementation. */
  wheels_confirmed: boolean;
  wheels_unconfirmed_reason: string;
  /** The FULL arm predicate: agreement with the command, then enough separate
   *  arrivals, then enough span between them. `wheels_confirmed` alone is
   *  necessary but not sufficient — a panel showing only that would look ready
   *  while ARM refuses. `wheels_in_band_s` is the span the SAMPLES cover, so it
   *  never grows while nothing is arriving. */
  wheels_stable: boolean;
  wheels_unstable_reason: string;
  wheels_sample_count: number;
  wheels_stable_min_samples: number;
  wheels_in_band_s: number;
  wheels_band_rpm: number;
  wheels_stable_required_s: number;
  rpm_spread_max: number;
  /** Whether the MACHINE says the flywheels are stopped: commanded zero, a fresh
   *  reading, and both wheels under the threshold. */
  safe_to_approach: boolean;
  rpm_safe_approach: number;
  /** A reload since the last shot — bookkeeping the console is entitled to. */
  loaded: boolean;
  /** What the last poll's ball switch said. Inferred polarity, so it informs and
   *  never gates; `null` until a poll has been seen. */
  ball_present: boolean | null;
  info_age_s: number | null;
  rpm_min_fire: number;
  angle_limit_deg: number;
  /** The live envelope, in the current zero's frame. */
  pitch_min_deg: number;
  pitch_max_deg: number;
  pitch_default_min_deg: number;
  pitch_default_max_deg: number;
  yaw_limit_deg: number;
  /** Shots the FIRMWARE confirmed, not `shoot` commands written. */
  shots_fired: number;
  shot_ack_timeout_s: number;
  /** A `shoot` that reached the port and has not yet been acknowledged by the
   *  firmware's front limit. While this is non-null the outcome is unknown: no
   *  shot exists, no distance may be recorded, and every command that could
   *  change the physical outcome is refused. `timed_out` means the bridge gave
   *  up and latched STOP — that state is not clearable from the panel. */
  fire_request: {
    request_seq: number;
    rpm: number;
    rpm_left_pre_fire: number;
    rpm_right_pre_fire: number;
    rpm_pre_fire_sample_age_s: number;
    confirmation_age_s: number;
    timed_out: boolean;
  } | null;
  /** The CONFIRMED shot waiting for its landing distance, carrying the RPM
   *  commanded when it was taken. Null when nothing is outstanding, which is
   *  when RECORD SHOT has nothing to attach to.
   *
   *  The RPM pair says `pre_fire` because that is what it is: the firmware gates
   *  telemetry on STATE_IDLE and is in STATE_SHOOTING for the whole
   *  acknowledgement window, so no reading contemporaneous with the shot can
   *  exist. Its age travels with it for the same reason. */
  pending_shot: {
    rpm: number;
    seq: number;
    request_seq: number;
    rpm_left_pre_fire: number;
    rpm_right_pre_fire: number;
    rpm_pre_fire_sample_age_s: number;
  } | null;
  last_refusal: string;
  info_lines: string[];
  measurements: { rpm: number; distance_m: number; shot_seq: number }[];
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
  if (!status.aim_established) blockers.push("no aim sent yet");
  if (status.wheel_rpm < RPM_MIN_FIRE)
    blockers.push(`wheels commanded below the ${RPM_MIN_FIRE} RPM gate`);
  // The commanded RPM says what was asked for; only these two say what happened.
  if (!status.loaded) blockers.push("no reload since the last shot");
  if (!status.wheels_confirmed)
    blockers.push(status.wheels_unconfirmed_reason || "flywheels not confirmed");
  if (!status.armed) blockers.push("not armed");
  return blockers;
}

/** One named step, so the per-shot cycle is on screen instead of on paper.
 *
 *  The cycle is not incidental: firmware `reload` homes both aim axes AND zeroes
 *  the wheel targets, and a shot consumes the arm — so RPM and ARM genuinely have
 *  to be re-established for every single shot. That surprised the operator on the
 *  first pass, which is the tell that the sequence needed to be shown rather than
 *  remembered.
 *
 *  Every branch reads a field the BRIDGE computed. This function orders and names
 *  them; it never decides a safety question of its own.
 */
export type CycleStep = {
  key: string;
  title: string;
  detail: string;
  tone: "idle" | "ask" | "wait" | "ready" | "danger";
};

export function cycleStep(
  status: ConsoleStatus | null,
  roomClear: boolean
): CycleStep {
  if (!status || !status.connected)
    return {
      key: "closed",
      title: "OPEN THE CONSOLE",
      detail: "Pick the launcher port and press OPEN CONSOLE.",
      tone: "idle",
    };
  if (status.estop_latched)
    return {
      key: "latched",
      title: "RELEASE THE LATCH",
      detail: "Every actuating command is refused until the ESTOP latch is released.",
      tone: "danger",
    };

  // A fired shot outranks everything else: the ball is on the floor and the only
  // way to walk out to it is through a confirmed spin-down.
  if (status.pending_shot) {
    const shot = status.pending_shot;
    if (status.wheel_rpm !== 0)
      return {
        key: "spin_down",
        title: "SET RPM TO 0",
        detail: `Shot ${shot.seq} is on the floor. Nobody may walk downrange until the wheels are commanded to zero.`,
        tone: "danger",
      };
    if (!status.safe_to_approach)
      return {
        key: "spinning_down",
        title: "DO NOT APPROACH",
        detail:
          status.telemetry_age_s === null ||
          status.telemetry_age_s > status.telemetry_max_age_s
            ? "The flywheel reading is stale, so the console cannot tell whether they have stopped. Do not use it as permission."
            : `Waiting for both wheels below ${status.rpm_safe_approach} rpm.`,
        tone: "danger",
      };
    return {
      key: "measure",
      title: `MEASURE SHOT ${shot.seq}`,
      detail: `Wheels confirmed stopped. Measure from directly below the barrel to the first floor contact, then RECORD SHOT at ${shot.rpm} rpm.`,
      tone: "ask",
    };
  }

  if (!status.loaded)
    return {
      key: "reload",
      title: "RELOAD",
      detail:
        "Reload also homes the aim and zeroes the wheels, so it comes first — everything after it is set against a known state.",
      tone: "ask",
    };
  if (!status.aim_established)
    return {
      key: "aim",
      title: "SET THE AIM",
      detail: "Commit PITCH and YAW. An RPM-only change does not count as an aim.",
      tone: "ask",
    };
  if (status.wheel_rpm < RPM_MIN_FIRE)
    return {
      key: "spin_up",
      title: "COMMAND THE PASS RPM",
      detail: `The reload zeroed the wheels. Pick the pass RPM — at least ${RPM_MIN_FIRE} to clear the firmware gate.`,
      tone: "ask",
    };
  if (!status.wheels_confirmed)
    return {
      key: "unconfirmed",
      title: "WHEELS NOT CONFIRMED",
      detail: status.wheels_unconfirmed_reason,
      tone: "wait",
    };
  if (status.wheels_in_band_s < status.wheels_stable_required_s)
    return {
      key: "stabilising",
      title: "CONFIRMING THE WHEELS",
      detail: `Held ${status.wheels_in_band_s.toFixed(1)} s of the ${status.wheels_stable_required_s.toFixed(1)} s required inside ±${status.wheels_band_rpm} rpm.`,
      tone: "wait",
    };
  if (!status.allow_fire)
    return {
      key: "aim_only",
      title: "AIM ONLY",
      detail:
        "This console was opened without fire control. Reopen it with ENABLE FIRE CONTROL to arm.",
      tone: "idle",
    };
  if (!roomClear)
    return {
      key: "room",
      title: "CONFIRM THE ROOM",
      detail: "The one condition no machine can check. Nobody downrange.",
      tone: "ask",
    };
  if (!status.armed)
    return {
      key: "arm",
      title: "ARM",
      detail: `Wheels confirmed for ${status.wheels_in_band_s.toFixed(1)} s. The arm lasts ${status.arm_timeout_s} s and one shot consumes it.`,
      tone: "ready",
    };
  return {
    key: "fire",
    title: "HOLD TO FIRE",
    detail: `Armed for ${status.arm_remaining_s.toFixed(0)} s more. Start the slow-motion capture first.`,
    tone: "ready",
  };
}
