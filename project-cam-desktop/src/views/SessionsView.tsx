import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import {
  EMPTY_EVIDENCE,
  loadEvidence,
  type SessionEvidence,
  type SessionRow,
} from "../evidence";

type Props = { athlete: string; evidenceRevision: number };
type Metric = { drill: string; key: string; label: string };

const METRICS: Metric[] = [
  { drill: "balance", key: "avg_sway_mm", label: "BALANCE · AVG SWAY (MM)" },
  { drill: "gk_save", key: "save_pct", label: "SAVE THE CORNERS · SAVE (%)" },
  {
    drill: "gk_save",
    key: "avg_reaction_s",
    label: "SAVE THE CORNERS · AVG REACTION (S)",
  },
  { drill: "line_hops", key: "best_rate_hz", label: "LINE HOPS · BEST RATE (HZ)" },
  { drill: "shuttle", key: "best_total_s", label: "SHUTTLE · BEST TOTAL (S)" },
  {
    drill: "gk_updown",
    key: "avg_recovery_s",
    label: "DOWN-UP · AVG RECOVERY (S)",
  },
];

function finiteMetric(row: SessionRow, key: string): number | null {
  if (!row.summary || typeof row.summary !== "object") return null;
  const value = (row.summary as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function duration(row: SessionRow): string {
  const start = Date.parse(row.started_at);
  const end = Date.parse(row.ended_at);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function displayTime(value: string): string {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : value || "—";
}

function statusTone(status: string): string {
  if (status === "complete") return "text-arena-hit";
  if (status === "aborted" || status === "failed") return "text-arena-miss";
  if (status === "running") return "text-arena-yellow";
  return "text-white/45";
}

export default function SessionsView({ athlete, evidenceRevision }: Props) {
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
  const preview = evidence.sources.find((source) =>
    source.path.startsWith("BROWSER PREVIEW")
  );
  const trend = useMemo(() => {
    for (const metric of METRICS) {
      const points = evidence.sessions
        .filter((row) => row.drill === metric.drill)
        .map((row) => ({
          timestamp: row.started_at,
          label: displayTime(row.started_at),
          value: finiteMetric(row, metric.key),
        }))
        .filter(
          (point): point is { timestamp: string; label: string; value: number } =>
            point.value !== null
        )
        .sort((left, right) => left.timestamp.localeCompare(right.timestamp));
      if (points.length >= 2) return { metric, points };
    }
    return null;
  }, [evidence.sessions]);

  const cards = [
    ["TOTAL", evidence.summary.total_sessions],
    ["COMPLETE", evidence.summary.complete_sessions],
    ["ABORTED / FAILED", evidence.summary.aborted_or_failed_sessions],
    ["PARTIAL / RUNNING", evidence.summary.partial_sessions],
  ] as const;

  return (
    <div className="px-[26px] py-[22px] pb-[30px] flex flex-col gap-4">
      <div className="flex items-baseline gap-3.5">
        <span className="font-extrabold text-[26px] tracking-tight text-white">
          SESSIONS
        </span>
        <span className="font-mono text-[12px] tracking-wide text-white/40">
          {athlete.trim() || "ALL ATHLETES"}
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

      {preview && (
        <div className="bg-arena-panel border border-white/[0.10] rounded-[10px] px-4 py-3 font-mono text-[11px] text-white/50">
          {preview.path}
        </div>
      )}
      {error && (
        <div className="bg-arena-miss/10 border border-arena-miss/35 rounded-[10px] px-4 py-3 text-[12px] text-arena-missText">
          REFRESH FAILED · {error} · showing the last successful snapshot
        </div>
      )}
      {sourceWarnings.length > 0 && (
        <div className="flex items-start gap-2.5 bg-arena-yellow/[0.07] border border-arena-yellow/25 rounded-[10px] px-4 py-3 text-[11px] text-white/60">
          <AlertTriangle size={15} className="text-arena-yellow flex-none mt-0.5" />
          <span>
            SOURCE WARNINGS · {sourceWarnings.length} source(s) were truncated,
            rejected records, or reported an error. Accepted rows remain visible.
          </span>
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        {cards.map(([label, value]) => (
          <div
            key={label}
            className="bg-arena-panel border border-white/[0.08] rounded-[13px] p-4"
          >
            <div className="font-mono text-[10px] tracking-[0.14em] text-white/45">
              {label}
            </div>
            <div className="mt-2 font-extrabold text-[32px] text-arena-yellow leading-none">
              {value}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(340px,0.65fr)] gap-3.5">
        <div className="bg-arena-panel border border-white/[0.08] rounded-[14px] overflow-hidden">
          <div className="px-5 py-3.5 font-mono text-[11px] tracking-[0.16em] text-white/50 border-b border-white/[0.08]">
            RECORDED SESSIONS · NEWEST FIRST
          </div>
          {evidence.sessions.length === 0 ? (
            <div className="px-5 py-10 text-center text-[12px] text-white/40">
              NO RECORDED SESSIONS FOR THIS FILTER
            </div>
          ) : (
            evidence.sessions.map((row) => (
              <div
                key={row.session_id}
                className="grid grid-cols-[minmax(180px,1fr)_130px_120px] gap-4 px-5 py-3 border-b border-white/[0.06] hover:bg-arena-yellow/[0.04]"
              >
                <div className="min-w-0">
                  <div className="font-bold text-[12.5px] text-white truncate">
                    {row.title || row.launch_kind.toUpperCase()}
                  </div>
                  <div className="mt-1 text-[11px] text-arena-yellow/85 truncate">
                    {row.headline || "—"}
                  </div>
                  <div className="mt-1 font-mono text-[9.5px] text-white/30 truncate">
                    {row.source_schema} · {row.session_id}
                  </div>
                </div>
                <div className="text-[11px] text-white/55">
                  <div>{row.athlete || "ANONYMOUS"}</div>
                  <div className="mt-1 font-mono text-[10px] text-white/35">
                    {displayTime(row.started_at)}
                  </div>
                </div>
                <div className="text-right">
                  <div
                    className={`font-mono text-[11px] font-bold ${statusTone(
                      row.status
                    )}`}
                  >
                    {row.status.toUpperCase()}
                  </div>
                  <div className="mt-1 font-mono text-[10px] text-white/35">
                    {duration(row)}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="bg-arena-panel border border-white/[0.08] rounded-[14px] p-5 min-h-[330px]">
          <div className="font-mono text-[11px] tracking-[0.16em] text-white/50 mb-3">
            {trend?.metric.label || "COMPARABLE DRILL TREND"}
          </div>
          {trend ? (
            <ResponsiveContainer width="100%" height={270}>
              <AreaChart
                data={trend.points}
                margin={{ top: 12, right: 10, left: -12, bottom: 10 }}
              >
                <defs>
                  <linearGradient id="session-trend-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#FFD700" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#FFD700" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                <XAxis dataKey="label" hide />
                <YAxis
                  tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#FFD700"
                  strokeWidth={2.5}
                  fill="url(#session-trend-fill)"
                  dot={{ fill: "#000", stroke: "#FFD700", strokeWidth: 2, r: 4 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[270px] flex items-center justify-center text-center font-mono text-[11px] text-white/35">
              NOT ENOUGH COMPARABLE SESSIONS
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
