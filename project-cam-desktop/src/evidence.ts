/** Raw comparability facts recorded with a session — never a verdict.
 *
 * Whether a session may seed a baseline is decided by the versioned comparison
 * policy from these numbers, so there is deliberately no `quality_class` and no
 * `baseline_eligible` here: changing a threshold must be re-applicable to
 * history instead of grandfathering whatever was true on the recording day.
 *
 * Every field is optional. A session produced by a viewer without
 * `--udp-capture-context` carries no claim rather than an invented one.
 */
export type SessionEvidenceContext = {
  /** Protocol identity, e.g. "balance.v1". */
  protocol_id?: string;
  /** Semantic workload actually applied, read back off the built drill. */
  applied_parameters?: Record<string, number | boolean | string>;
  /** Hash over protocol_id + applied parameters; the baseline comparison key. */
  protocol_parameters_fingerprint?: string;

  context_schema?: string;
  /** Camera ROLES, not /dev/videoN: a role is stable across replug. */
  configured_camera_roles?: string[];
  opened_camera_roles?: string[];
  /** Hash of the calibration actually loaded; a change starts a new epoch. */
  calibration_fingerprint?: string;
  /** Share of packets in which each configured role was open. NOT that role's
   *  contribution to triangulation — an open camera can still deliver junk. */
  camera_open_ratio_by_role?: Record<string, number>;
  /** Share of packets that carried at least one tracked joint. */
  pose_valid_frame_ratio?: number;
  median_reported_joint_cameras?: number | null;
  packets_observed?: number;
  /** gk_save only: a pinned seed makes the cue sequence learnable, so such a
   *  session must not feed a reaction-time baseline. */
  seed_pinned?: boolean;
};

export type SessionRow = {
  session_id: string;
  source_schema: string;
  source_path: string;
  athlete: string;
  /** Stable identity; null for historical sessions that were never linked.
   *  The display name is editable and is never the join key. */
  athlete_id: string | null;
  launch_kind: string;
  drill: string;
  title: string;
  started_at: string;
  ended_at: string;
  status: string;
  headline: string;
  summary: unknown;
  evidence_context: SessionEvidenceContext | null;
  warnings: string[];
};

export type ShotRow = {
  session_id: string;
  sequence: number;
  timestamp: string;
  target: string;
  wheel_left_rpm: number | null;
  wheel_right_rpm: number | null;
  speed_mps: number | null;
  speed_calibrated: boolean;
  pitch_deg: number | null;
  yaw_deg: number | null;
  state: string;
  outcome: string;
  block_reason: string;
  source_schema: string;
  source_path: string;
  warnings: string[];
};

export type SourceStatus = {
  path: string;
  accepted: number;
  rejected: number;
  truncated: boolean;
  error: string;
};

export type EvidenceSummary = {
  total_sessions: number;
  complete_sessions: number;
  aborted_or_failed_sessions: number;
  partial_sessions: number;
  launched_attempts: number;
  blocked_attempts: number;
};

export type SessionEvidence = {
  generated_at: string;
  sessions: SessionRow[];
  shots: ShotRow[];
  summary: EvidenceSummary;
  sources: SourceStatus[];
};

export const EMPTY_EVIDENCE: SessionEvidence = {
  generated_at: "",
  sessions: [],
  shots: [],
  summary: {
    total_sessions: 0,
    complete_sessions: 0,
    aborted_or_failed_sessions: 0,
    partial_sessions: 0,
    launched_attempts: 0,
    blocked_attempts: 0,
  },
  sources: [],
};

export async function loadEvidence(
  athleteFilter?: string
): Promise<SessionEvidence> {
  if (
    typeof window === "undefined" ||
    !("__TAURI_INTERNALS__" in window)
  ) {
    return {
      ...EMPTY_EVIDENCE,
      sources: [
        {
          path: "BROWSER PREVIEW · NO LOCAL DATA ACCESS",
          accepted: 0,
          rejected: 0,
          truncated: false,
          error: "",
        },
      ],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<SessionEvidence>("load_session_evidence", {
        athleteFilter: athleteFilter?.trim() || null,
    sessionLimit: 100,
    shotLimit: 500,
  });
}
