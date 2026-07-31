import { useEffect, useMemo, useRef, useState } from "react";
import {
  Play,
  Hand,
  Footprints,
  Clock,
  Check,
  History,
  FlipHorizontal,
} from "lucide-react";
import SectionLabel from "../components/SectionLabel";
import { DRILLS, type Drill, type DrillRole } from "../drills";
import { drillRequest } from "../launch";
import type { SessionRow } from "../evidence";
import type { LogLine, RunFn } from "../App";

const inTauri = () =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

type Session = {
  drill: string;
  title: string;
  athlete: string;
  ended: string;
  headline: string;
  aborted: boolean;
};

const ROLES: DrillRole[] = ["GOALKEEPER", "FIELD PLAYER"];

export default function TrainingView({
  run,
  running,
  log,
  name,
  setName,
}: {
  run: RunFn;
  running: boolean;
  log: LogLine[];
  name: string;
  setName: (v: string) => void;
}) {
  const [selectedId, setSelectedId] = useState<string>(DRILLS[0].id);
  const [rounds, setRounds] = useState<number>(DRILLS[0].roundsDefault);
  const [flip, setFlip] = useState(false);
  const [enrolled, setEnrolled] = useState<string[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const logBox = useRef<HTMLDivElement>(null);
  const logStick = useRef(true);

  const drill = useMemo(
    () => DRILLS.find((d) => d.id === selectedId) ?? DRILLS[0],
    [selectedId]
  );

  const selectDrill = (d: Drill) => {
    setSelectedId(d.id);
    setRounds(d.roundsDefault);
  };

  // Log auto-follow: scroll ONLY the log container, stick to bottom only when
  // the user is already there (same contract as the CONTROL mission log).
  const onLogScroll = () => {
    const el = logBox.current;
    if (el) logStick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };
  useEffect(() => {
    const el = logBox.current;
    if (el && logStick.current) el.scrollTop = el.scrollHeight;
  }, [log]);

  // Enrolled names (canonical spelling wins) + recent sessions; refresh when a
  // process finishes — a drill may have just appended to the session index.
  useEffect(() => {
    if (!inTauri()) return;
    let cancelled = false;
    (async () => {
      const { invoke } = await import("@tauri-apps/api/core");
      try {
        const names = await invoke<string[]>("face_list_names");
        if (!cancelled && Array.isArray(names)) setEnrolled(names);
      } catch {
        /* leave empty */
      }
      try {
        // One bounded, typed reader for all evidence (see main.rs: the old
        // `training_sessions` command read the whole index unbounded and made
        // the UI parse raw JSONL). Ask for headroom, then keep drill rows only.
        const evidence = await invoke<{ sessions?: SessionRow[] }>(
          "load_session_evidence",
          { athleteFilter: null, sessionLimit: 60, shotLimit: 1 },
        );
        if (!cancelled && Array.isArray(evidence?.sessions)) {
          setSessions(
            evidence.sessions
              .filter((row) => String(row.drill ?? "").trim() !== "")
              .slice(0, 8)
              .map((row) => ({
                drill: String(row.drill ?? ""),
                title: String(row.title ?? row.drill ?? "DRILL"),
                athlete: String(row.athlete ?? ""),
                ended: String(row.ended_at ?? ""),
                headline: String(row.headline ?? ""),
                aborted: row.status === "aborted" || row.status === "failed",
              })),
          );
        }
      } catch {
        /* command absent or no evidence yet */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [running]);

  const trimmed = name.trim();
  const canonical = trimmed
    ? enrolled.find((n) => n.trim().toLowerCase() === trimmed.toLowerCase())
    : undefined;
  const isEnrolled = canonical !== undefined;
  const athlete = canonical ?? trimmed;

  const startDrill = () => {
    // A tagged semantic request, not a CLI vector: the backend maps the
    // workload onto the wrapper's legacy flag and range-checks it first.
    // Face ID only when the name is actually in the gallery — it labels the
    // primary person so logs follow the right athlete in a busy garage.
    run({
      profile_id: "training_drill",
      drill: drillRequest(drill.id, rounds, flip),
      athlete: athlete || null,
      face_id: isEnrolled,
    });
  };

  const logColor = (tone: LogLine["tone"]) =>
    tone === "sys"
      ? "text-arena-yellow"
      : tone === "cmd"
      ? "text-arena-yellowh"
      : tone === "err"
      ? "text-arena-miss"
      : tone === "out"
      ? "text-white/85"
      : "text-white/55";

  const RoleIcon = ({ role }: { role: DrillRole }) =>
    role === "GOALKEEPER" ? <Hand size={14} /> : <Footprints size={14} />;

  return (
    <div className="h-full flex gap-[22px] px-[26px] py-[22px] overflow-hidden">
      {/* left — athlete + drill catalog */}
      <div className="w-[440px] flex-none flex flex-col gap-2 min-h-0 overflow-y-auto pr-1 pb-2">
        <SectionLabel>ATHLETE</SectionLabel>
        <div className="bg-arena-panel border border-white/[0.08] rounded-xl p-3.5 flex flex-col gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={running}
            placeholder="name for the session log (optional)"
            className="w-full bg-black border border-white/[0.16] rounded-lg px-3.5 py-2.5 text-[14px] text-white outline-none focus:border-arena-yellow/60 disabled:opacity-50"
          />
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-white/40">
            {trimmed && isEnrolled ? (
              <span className="flex items-center gap-1.5 text-arena-hit font-semibold">
                <Check size={12} strokeWidth={3} /> {athlete} · Face ID will follow you
              </span>
            ) : trimmed ? (
              <span>not enrolled — logged by name only (scan on CONTROL to enable Face ID)</span>
            ) : (
              <span>anonymous session — results still recorded</span>
            )}
            {enrolled.length > 0 && !isEnrolled && (
              <span className="flex flex-wrap gap-1.5">
                {enrolled.map((n) => (
                  <button
                    key={n}
                    onClick={() => setName(n)}
                    disabled={running}
                    className="px-2 py-[2px] rounded-full border border-white/[0.14] bg-black text-white/75 hover:border-arena-yellow/60 hover:text-arena-yellow disabled:opacity-40"
                  >
                    {n}
                  </button>
                ))}
              </span>
            )}
          </div>
        </div>

        {ROLES.map((role) => (
          <div key={role} className="flex flex-col gap-2">
            <SectionLabel>{role}</SectionLabel>
            {DRILLS.filter((d) => d.role === role).map((d) => {
              const active = d.id === drill.id;
              return (
                <button
                  key={d.id}
                  onClick={() => selectDrill(d)}
                  className={`flex items-stretch gap-3.5 w-full p-3 rounded-xl text-left border transition-colors ${
                    active
                      ? "border-arena-yellow/70 bg-[#161512]"
                      : "border-white/[0.09] bg-[#0e0e0e] hover:border-arena-yellow/40 hover:bg-[#141414]"
                  }`}
                >
                  <span className={`w-1 self-stretch rounded ${active ? "bg-arena-yellow" : "bg-white/15"}`} />
                  <span
                    className={`flex items-center justify-center w-7 h-7 flex-none self-center rounded-[8px] ${
                      active ? "bg-arena-yellow text-black" : "bg-arena-yellow/10 text-arena-yellow"
                    }`}
                  >
                    <RoleIcon role={d.role} />
                  </span>
                  <span className="flex flex-col gap-[2px] min-w-0">
                    <span className={`font-bold text-[12.5px] tracking-wide ${active ? "text-arena-yellow" : "text-white"}`}>
                      {d.title}
                    </span>
                    <span className="text-[11px] text-white/50">{d.tagline}</span>
                  </span>
                  <span className="ml-auto self-center flex items-center gap-1 text-[10.5px] font-mono text-white/35">
                    <Clock size={11} />
                    {d.durationLabel}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {/* right — drill detail + sessions + log */}
      <div className="flex-1 min-w-0 flex flex-col gap-2 min-h-0">
        <SectionLabel>
          {drill.role} · {drill.title}
        </SectionLabel>
        <div className="flex-[3] min-h-0 overflow-y-auto bg-arena-panel border border-arena-yellow/25 rounded-xl p-[18px] flex flex-col gap-3.5">
          <p className="text-[12.5px] leading-relaxed text-white/75">{drill.provenance}</p>

          <div className="grid grid-cols-2 gap-3">
            <DetailList title="FLOOR SETUP" items={drill.setup} />
            <DetailList title="PROTOCOL" items={drill.protocol} />
          </div>
          <DetailList title="LIVE METRICS" items={drill.metrics} accent />

          <div className="flex items-center gap-4 pt-1">
            <span className="text-[11px] font-bold tracking-[0.12em] text-white/50 uppercase">
              {drill.roundsLabel}
            </span>
            <span className="inline-flex items-center gap-2 bg-black border border-white/[0.14] rounded-md px-2.5 py-1">
              <button
                onClick={() => setRounds((r) => Math.max(drill.roundsMin, r - drill.roundsStep))}
                disabled={running}
                className="text-white/50 hover:text-arena-yellow disabled:opacity-40 font-mono text-[15px] leading-none"
              >
                −
              </button>
              <span className="font-mono text-arena-yellow text-[15px] w-8 text-center">{rounds}</span>
              <button
                onClick={() => setRounds((r) => Math.min(drill.roundsMax, r + drill.roundsStep))}
                disabled={running}
                className="text-white/50 hover:text-arena-yellow disabled:opacity-40 font-mono text-[15px] leading-none"
              >
                +
              </button>
            </span>
            <button
              onClick={() => setFlip(!flip)}
              disabled={running}
              title="Mirror LEFT/RIGHT if the board's sides feel inverted on the mirrored rig"
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-bold tracking-wide ${
                flip
                  ? "border-arena-yellow/60 text-arena-yellow bg-arena-yellow/[0.08]"
                  : "border-white/[0.14] text-white/50 hover:text-white/80"
              } disabled:opacity-40`}
            >
              <FlipHorizontal size={13} />
              FLIP L/R
            </button>
          </div>

          <button
            onClick={startDrill}
            disabled={running}
            className="flex items-center justify-center gap-2.5 w-full py-3.5 rounded-lg font-extrabold text-[15px] tracking-wide bg-arena-yellow text-black hover:bg-arena-yellowh disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play size={16} fill="currentColor" strokeWidth={0} />
            START DRILL
          </button>
          <p className="text-[10.5px] text-white/35 leading-snug">
            Two windows open on the rig: the 3D arena view and the drill board — drag the board to the
            projector and press <span className="font-mono text-white/55">F</span> for fullscreen. Results
            log to <span className="font-mono text-white/55">output/training_logs/</span>. View-only: the
            drills read the pose stream and never actuate the launcher. Stop anytime with STOP below.
          </p>
        </div>

        <div className="flex-[2] min-h-0 grid grid-cols-2 gap-[18px]">
          <div className="flex flex-col gap-2 min-h-0">
            <SectionLabel>RECENT SESSIONS</SectionLabel>
            <div className="flex-1 min-h-0 overflow-y-auto bg-arena-panel border border-white/[0.08] rounded-xl p-3 flex flex-col gap-2">
              {sessions.length === 0 ? (
                <span className="flex items-center gap-2 text-[12px] text-white/40 p-1">
                  <History size={13} /> no logged sessions yet — finish a drill and it appears here
                </span>
              ) : (
                sessions.map((s, i) => (
                  <div key={i} className="flex items-center gap-2.5 bg-black/40 border border-white/[0.07] rounded-lg px-3 py-2">
                    <span className={`w-[7px] h-[7px] flex-none rounded-full ${s.aborted ? "bg-white/30" : "bg-arena-hit"}`} />
                    <span className="flex flex-col min-w-0">
                      <span className="text-[11.5px] font-bold text-white truncate">
                        {s.title}
                        {s.athlete && <span className="text-white/45 font-normal"> · {s.athlete}</span>}
                      </span>
                      <span className="text-[11px] text-arena-yellow/90 truncate">{s.headline}</span>
                    </span>
                    <span className="ml-auto font-mono text-[9.5px] text-white/30 flex-none">
                      {s.ended.replace("T", " ").slice(5, 16)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="flex flex-col gap-2 min-h-0">
            <SectionLabel>MISSION LOG</SectionLabel>
            <div
              ref={logBox}
              onScroll={onLogScroll}
              className="flex-1 min-h-0 bg-[#040404] border border-white/[0.08] rounded-xl p-3 font-mono text-[11.5px] leading-[1.8] overflow-y-auto"
            >
              {log.map((line, i) => (
                <div key={i} className={logColor(line.tone)}>
                  <span className="text-white/35">{line.t}</span>  {line.msg}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DetailList({ title, items, accent }: { title: string; items: string[]; accent?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className={`text-[10px] font-bold tracking-[0.14em] ${accent ? "text-arena-yellow/80" : "text-white/40"}`}>
        {title}
      </span>
      <ul className="flex flex-col gap-1">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-[11.5px] leading-snug text-white/70">
            <span className={`mt-[6px] w-1 h-1 flex-none rounded-full ${accent ? "bg-arena-yellow" : "bg-white/30"}`} />
            {it}
          </li>
        ))}
      </ul>
    </div>
  );
}
