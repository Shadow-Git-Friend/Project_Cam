// Launch requests. Mirrors LaunchRequest in src-tauri/src/launch_profiles.rs
// (field names are contract-tested in tests/test_desktop_launch_profiles.py).
//
// The frontend names a profile and supplies semantic parameters only. It has no
// way to express a program path, an argument vector or a working directory:
// those are produced by the Rust resolver, which is the whole point. The
// backend also rejects unknown fields, so an accidental extra key is a loud
// error rather than a silently ignored one.

export type TrainingDrillRequest =
  | { drill: "balance"; holds: number }
  | { drill: "shuttle"; reps: number }
  | { drill: "line_hops"; sets: number }
  | { drill: "gk_save"; rounds: number; flip: boolean }
  | { drill: "gk_updown"; duration_s: number }
  | { drill: "reaction_zones"; rounds: number; projector: boolean }
  | { drill: "cmj"; jumps: number }
  | { drill: "hop_symmetry"; hops_per_leg: number }
  | { drill: "reactive_cut"; reps: number; projector: boolean };

export type LaunchRequest =
  | { profile_id: "free_view_usb6" }
  | { profile_id: "blm_overlay_usb6" }
  | { profile_id: "yolo_pose_4cam" }
  | { profile_id: "record_3d" }
  | {
      profile_id: "training_drill";
      drill: TrainingDrillRequest;
      athlete?: string | null;
      /** Stable identity for the manifest; never a command-line argument. */
      athlete_id?: string | null;
      face_id?: boolean;
      people?: number | null;
    }
  | { profile_id: "face_enroll_arena"; athlete: string }
  | { profile_id: "face_enroll_single"; athlete: string; camera: string }
  | { profile_id: "face_models_download" }
  /** The launcher console — the only profile that opens the serial link and the
   *  only one with a live command channel. `serial_port` must be a node chosen
   *  from `list_serial_ports`; `allow_fire` only makes the arm/fire intents
   *  exist, and every shot still needs a fresh arm inside the session. */
  | { profile_id: "blm_console"; serial_port: string; allow_fire?: boolean };

export type ProfileId = LaunchRequest["profile_id"];

/** Drills whose request carries `projector` (a fullscreen board). Every other
 *  drill has no such field, so the toggle must not be offered for them. */
export const PROJECTOR_DRILLS = ["reaction_zones", "reactive_cut"] as const;

export function supportsProjector(drillId: string): boolean {
  return (PROJECTOR_DRILLS as readonly string[]).includes(drillId);
}

/** The backend decides label and command text; it returns them for the log. */
export type LaunchReceipt = {
  session_id: string;
  session_dir: string;
  label: string;
  command: string;
};

/** Build the drill-specific half of a training request from a catalog entry.
 *
 * `projector` is fullscreen for the two projector drills. It is off by default
 * because a fullscreen board covers the 3D arena view, which the operator wants
 * beside it on a single-monitor rig; on a real projector the coach turns it on.
 */
export function drillRequest(
  drillId: string,
  workload: number,
  flip: boolean,
  projector = false
): TrainingDrillRequest {
  switch (drillId) {
    case "balance":
      return { drill: "balance", holds: workload };
    case "shuttle":
      return { drill: "shuttle", reps: workload };
    case "line_hops":
      return { drill: "line_hops", sets: workload };
    case "gk_save":
      return { drill: "gk_save", rounds: workload, flip };
    case "gk_updown":
      return { drill: "gk_updown", duration_s: workload };
    case "cmj":
      return { drill: "cmj", jumps: workload };
    case "hop_symmetry":
      return { drill: "hop_symmetry", hops_per_leg: workload };
    case "reactive_cut":
      return { drill: "reactive_cut", reps: workload, projector };
    case "reaction_zones":
      return { drill: "reaction_zones", rounds: workload, projector };
    default:
      throw new Error(`unknown drill ${drillId}`);
  }
}
