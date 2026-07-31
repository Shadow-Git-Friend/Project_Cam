import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import {
  EMPTY_EVIDENCE,
  loadEvidence,
  type SessionEvidence,
  type ShotRow,
} from "../evidence";

type Props = { athlete: string; evidenceRevision: number };

const GRID =
  "grid-cols-[minmax(150px,0.9fr)_132px_minmax(120px,0.8fr)_105px_minmax(150px,1fr)_110px_95px_minmax(170px,1.2fr)]";

function finite(value: number | null): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function timeLabel(value: string): string {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : value || "—";
}

function rpmLabel(shot: ShotRow): string {
  const left = finite(shot.wheel_left_rpm) ? Math.round(shot.wheel_left_rpm) : null;
  const right = finite(shot.wheel_right_rpm) ? Math.round(shot.wheel_right_rpm) : null;
  if (left === null && right === null) return "—";
  return `${left ?? "—"} / ${right ?? "—"}`;
}

function speedLabel(shot: ShotRow): string {
  if (finite(shot.speed_mps)) {
    const value = `${shot.speed_mps.toFixed(1)} m/s`;
    return shot.speed_calibrated ? value : `${value} · UNCALIBRATED`;
  }
  if (finite(shot.wheel_left_rpm) || finite(shot.wheel_right_rpm)) {
    return "UNCALIBRATED";
  }
  return "—";
}

function angleLabel(shot: ShotRow): string {
  if (!finite(shot.pitch_deg) && !finite(shot.yaw_deg)) return "—";
  const pitch = finite(shot.pitch_deg) ? `${shot.pitch_deg.toFixed(1)}°` : "—";
  const yaw = finite(shot.yaw_deg) ? `${shot.yaw_deg.toFixed(1)}°` : "—";
  return `${pitch} / ${yaw}`;
}

function resultLabel(shot: ShotRow): string {
  if (shot.state === "blocked") {
    return `BLOCKED · ${shot.block_reason || "reason unavailable"}`;
  }
  if (shot.state !== "launched") return "STATE UNKNOWN";
  if (shot.outcome === "hit") return "HIT";
  if (shot.outcome === "miss") return "MISS";
  if (shot.outcome === "invalid") return "INVALID";
  return "OUTCOME UNKNOWN";
}

function resultTone(shot: ShotRow): string {
  if (shot.state === "blocked" || shot.outcome === "miss") return "text-arena-miss";
  if (shot.state === "launched" && shot.outcome === "hit") return "text-arena-hit";
  return "text-white/50";
}

export default function ShotsView({ athlete, evidenceRevision }: Props) {
  const [evidence, setEvidence] = useState<SessionEvidence>(EMPTY_EVIDENCE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadEvidence(athlete)
      .then((next) => {
        if (cancelled) return;
        setEvidence(next);
        setError("");
      })
      .catch((reason) => {
        if (!cancelled) setError(String(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [athlete, evidenceRevision, refreshToken]);

  const sourceWarnings = evidence.sources.filter(
    (source) => source.rejected > 0 || source.truncated || Boolean(source.error)
  );

  return (
    <div className="px-[26px] py-[22px] pb-[30px] flex flex-col gap-3.5">
      <div className="flex items-baseline gap-3.5">
        <span className="font-extrabold text-[26px] tracking-tight text-white">
          SHOTS
        </span>
        <span className="font-mono text-[12px] tracking-wide text-white/40">
          {athlete.trim() || "ALL ATHLETES"} · {evidence.summary.launched_attempts} LAUNCHED ·{" "}
          {evidence.summary.blocked_attempts} BLOCKED
        </span>
        <button
          onClick={() => setRefreshToken((value) => value + 1)}
          disabled={loading}
          className="ml-auto flex items-center gap-1.5 bg-[#141414] border border-white/[0.12] rounded-lg px-3.5 py-2 font-bold text-[11px] tracking-wide text-arena-yellow hover:border-arena-yellow/50 disabled:opacity-40"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          {loading ? "LOADING" : "REFRESH"}
        </button>
      </div>

      {error && (
        <div className="bg-arena-miss/10 border border-arena-miss/35 rounded-[10px] px-4 py-3 text-[12px] text-arena-missText">
          REFRESH FAILED · {error} · showing the last successful snapshot
        </div>
      )}
      {sourceWarnings.length > 0 && (
        <div className="flex items-start gap-2.5 bg-arena-yellow/[0.07] border border-arena-yellow/25 rounded-[10px] px-4 py-3 text-[11px] text-white/60">
          <AlertTriangle size={15} className="text-arena-yellow flex-none mt-0.5" />
          SOURCE WARNINGS · corrupt or truncated rows were rejected; accepted attempts
          remain visible.
        </div>
      )}

      <div className="bg-arena-panel border border-white/[0.08] rounded-[14px] overflow-x-auto">
        <div className={`grid ${GRID} min-w-[1120px] gap-x-3 px-5 py-3 border-b border-white/[0.08] font-mono text-[9.5px] font-bold tracking-[0.10em] text-arena-yellow`}>
          <span>SESSION</span>
          <span>TIME</span>
          <span>TARGET</span>
          <span>RPM L / R</span>
          <span>SPEED</span>
          <span>PITCH / YAW</span>
          <span>STATE</span>
          <span>OUTCOME / REASON</span>
        </div>
        {evidence.shots.length === 0 ? (
          <div className="min-w-[1120px] px-5 py-12 text-center text-[12px] text-white/40">
            NO EXPLICIT LAUNCH OR BLOCK EVIDENCE FOR THIS FILTER
          </div>
        ) : (
          evidence.shots.map((shot) => (
            <div
              key={`${shot.session_id}-${shot.sequence}-${shot.timestamp}`}
              className={`grid ${GRID} min-w-[1120px] gap-x-3 px-5 py-3 border-b border-white/[0.05] font-mono text-[11px] items-center hover:bg-arena-yellow/[0.04]`}
            >
              <span className="truncate text-white/55" title={shot.session_id}>
                {shot.session_id}
              </span>
              <span className="text-white/45">{timeLabel(shot.timestamp)}</span>
              <span className="truncate text-white/80">{shot.target || "—"}</span>
              <span className="text-white/70">{rpmLabel(shot)}</span>
              <span className={shot.speed_calibrated ? "text-white/80" : "text-arena-yellow/75"}>
                {speedLabel(shot)}
              </span>
              <span className="text-white/70">{angleLabel(shot)}</span>
              <span
                className={
                  shot.state === "blocked"
                    ? "font-bold text-arena-miss"
                    : shot.state === "launched"
                    ? "font-bold text-arena-yellow"
                    : "font-bold text-white/40"
                }
              >
                {shot.state.toUpperCase()}
              </span>
              <span className={`font-bold truncate ${resultTone(shot)}`}>
                {resultLabel(shot)}
              </span>
            </div>
          ))
        )}
      </div>
      <p className="font-mono text-[10px] leading-relaxed text-white/30">
        RPM is a command value. m/s is labelled calibrated only when the source carries
        explicit calibration evidence. Missing outcome evidence remains unknown.
      </p>
    </div>
  );
}
