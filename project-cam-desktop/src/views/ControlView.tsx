import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Play,
  ScanFace,
  Check,
  ChevronRight,
  Users,
  Download,
  CircleDot,
  Circle,
} from "lucide-react";
import SectionLabel from "../components/SectionLabel";
import type { LaunchRequest } from "../launch";
import {
  LAUNCHES,
  UNKNOWN_READINESS,
  type Launch,
  type Readiness,
} from "../data";
import type { LogLine, RunFn } from "../App";

const inTauri = () =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

// The guided "START TRAINING" button launches the recommended cinematic viewer
// (view-only — never actuates the launcher).
const RECOMMENDED = LAUNCHES[0];

export default function ControlView({
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
  const [camera, setCamera] = useState("0");
  const [people, setPeople] = useState(4);
  const [orbit, setOrbit] = useState(false);
  const [heat, setHeat] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [enrolled, setEnrolled] = useState<string[]>([]);
  const [readiness, setReadiness] = useState<Readiness[]>(UNKNOWN_READINESS);
  const logBox = useRef<HTMLDivElement>(null);
  const logStick = useRef(true);

  // Auto-follow new log lines by scrolling ONLY the log container (never
  // scrollIntoView — that scrolls every ancestor and dragged the whole page).
  // If the user scrolls up to read, stay put until they return to the bottom.
  const onLogScroll = () => {
    const el = logBox.current;
    if (el) logStick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };

  useEffect(() => {
    const el = logBox.current;
    if (el && logStick.current) el.scrollTop = el.scrollHeight;
  }, [log]);

  // Live readiness + who is enrolled. Refresh on mount and whenever a process
  // finishes (a scan may have just added the current athlete to the gallery).
  useEffect(() => {
    if (!inTauri()) return;
    let cancelled = false;
    (async () => {
      const { invoke } = await import("@tauri-apps/api/core");
      try {
        const r = await invoke<Readiness[]>("check_readiness");
        if (!cancelled && Array.isArray(r) && r.length) setReadiness(r);
      } catch {
        if (!cancelled) {
          setReadiness(
            UNKNOWN_READINESS.map((item) => ({
              ...item,
              status: "CHECK FAILED",
              ready: false,
            }))
          );
        }
      }
      try {
        const names = await invoke<string[]>("face_list_names");
        if (!cancelled && Array.isArray(names)) setEnrolled(names);
      } catch {
        /* leave list empty */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [running]);

  const trimmed = name.trim();
  // The gallery's exact spelling wins: recognition labels come from the
  // gallery, so "арлен"/"Arlen" typed here must not fork a second identity.
  const canonical = trimmed
    ? enrolled.find((n) => n.trim().toLowerCase() === trimmed.toLowerCase())
    : undefined;
  const isEnrolled = canonical !== undefined;
  const athlete = canonical ?? trimmed;

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

  // Shared viewer options — the guided Start and every advanced launch card use
  // them, so Face ID + your name follow you everywhere. These are semantic
  // fields the backend validates; the frontend no longer builds a CLI vector.
  const viewerOptions = () => ({
    people,
    athlete: trimmed ? athlete : null,
    auto_orbit: orbit,
    limb_heat: heat,
  });

  const startTraining = () =>
    run({ profile_id: RECOMMENDED.profile_id, viewer: viewerOptions() } as LaunchRequest);
  const launchCard = (launch: Launch) =>
    run({ profile_id: launch.profile_id, viewer: viewerOptions() } as LaunchRequest);

  // Arena scan: open ALL cameras and capture while the athlete turns 360°.
  const scanFace = () => {
    if (!trimmed) return;
    run({ profile_id: "face_enroll_arena", athlete });
  };

  // Fallback: single webcam close-up (Advanced), e.g. a laptop/desk cam.
  const scanFaceSingle = () => {
    if (!trimmed) return;
    run({
      profile_id: "face_enroll_single",
      athlete,
      camera: camera.trim() || "0",
    });
  };

  const downloadModels = () => run({ profile_id: "face_models_download" });

  const step = (delta: number) => setPeople((p) => Math.min(6, Math.max(1, p + delta)));

  return (
    <div className="h-full flex gap-[22px] px-[26px] py-[22px] overflow-hidden">
      {/* left column — the guided flow; scrolls on its own when ADVANCED is open */}
      <div className="w-[470px] flex-none flex flex-col gap-2 min-h-0 overflow-y-auto pr-1 pb-2">
        <SectionLabel>START TRAINING</SectionLabel>
        <div className="bg-arena-panel border border-arena-yellow/25 rounded-xl p-[18px] flex flex-col gap-[18px]">
          {/* STEP 1 — name */}
          <div className="flex flex-col gap-2">
            <StepTag n={1}>YOUR NAME</StepTag>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={running}
              placeholder="e.g. Arlen"
              className="w-full bg-black border border-white/[0.16] rounded-lg px-3.5 py-2.5 text-[15px] text-white outline-none focus:border-arena-yellow/60 disabled:opacity-50"
            />
            {enrolled.length > 0 && !isEnrolled && (
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-white/40">
                <span>already enrolled — tap to use:</span>
                {enrolled.map((n) => (
                  <button
                    key={n}
                    onClick={() => setName(n)}
                    disabled={running}
                    className="px-2.5 py-[3px] rounded-full border border-white/[0.14] bg-black text-white/75 hover:border-arena-yellow/60 hover:text-arena-yellow disabled:opacity-40"
                  >
                    {n}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* STEP 2 — face scan */}
          <div className="flex flex-col gap-2">
            <StepTag n={2}>SCAN YOUR FACE <span className="text-white/35 font-normal normal-case">· once</span></StepTag>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                {!trimmed ? (
                  <span className="flex items-center gap-2 text-[12.5px] text-white/45">
                    <Circle size={13} /> enter your name first
                  </span>
                ) : isEnrolled ? (
                  <span className="flex items-center gap-2 text-[12.5px] text-arena-hit font-semibold">
                    <Check size={14} strokeWidth={3} /> {athlete} is enrolled
                  </span>
                ) : (
                  <span className="flex items-center gap-2 text-[12.5px] text-white/60">
                    <CircleDot size={13} className="text-arena-yellow" /> {trimmed} not enrolled yet
                  </span>
                )}
              </div>
              <button
                onClick={scanFace}
                disabled={running || !trimmed}
                className="flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold text-[12px] tracking-wide border border-arena-yellow/50 text-arena-yellow bg-arena-yellow/[0.06] hover:bg-arena-yellow/[0.14] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ScanFace size={15} />
                {isEnrolled ? "RE-SCAN" : "SCAN MY FACE"}
              </button>
            </div>
            <p className="text-[11px] text-white/40 leading-snug">
              Stand in the arena and <span className="text-white/70">slowly turn a full circle</span>. A 6-camera
              preview opens and every camera that sees your face records it — it's fine if some see nothing. It
              finishes when the bar fills; press <span className="font-mono text-white/60">Q</span> to finish early.
            </p>
          </div>

          {/* STEP 3 — go */}
          <div className="flex flex-col gap-2.5">
            <StepTag n={3}>GO</StepTag>
            <button
              onClick={startTraining}
              disabled={running || !trimmed}
              className="flex items-center justify-center gap-2.5 w-full py-3.5 rounded-lg font-extrabold text-[15px] tracking-wide bg-arena-yellow text-black hover:bg-arena-yellowh disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Play size={16} fill="currentColor" strokeWidth={0} />
              START TRAINING
            </button>
            <div className="flex items-center justify-between text-[12px] text-white/50">
              <span className="flex items-center gap-1.5">
                <Users size={13} className="text-white/40" /> tracks up to
                <span className="inline-flex items-center gap-1.5 bg-black border border-white/[0.14] rounded-md px-2 py-[2px] ml-1">
                  <button
                    onClick={() => step(-1)}
                    disabled={running}
                    className="text-white/50 hover:text-arena-yellow disabled:opacity-40 font-mono leading-none text-[13px]"
                  >
                    −
                  </button>
                  <span className="font-mono text-arena-yellow text-[13px] w-3 text-center">{people}</span>
                  <button
                    onClick={() => step(1)}
                    disabled={running}
                    className="text-white/50 hover:text-arena-yellow disabled:opacity-40 font-mono leading-none text-[13px]"
                  >
                    +
                  </button>
                </span>
                people
              </span>
              <span className={trimmed ? "text-arena-hit" : "text-white/40"}>
                Face ID {trimmed ? "ON" : "off (no name)"}
              </span>
            </div>
          </div>
        </div>

        {/* Advanced — collapsed by default */}
        <button
          onClick={() => setAdvanced(!advanced)}
          className="flex items-center gap-2 mt-2 px-1 py-1.5 text-[11px] font-bold tracking-[0.12em] text-white/45 hover:text-white/75"
        >
          <ChevronRight size={14} className={`transition-transform ${advanced ? "rotate-90" : ""}`} />
          ADVANCED OPTIONS
        </button>

        {advanced && (
          <div className="flex flex-col gap-2 pl-1">
            <SectionLabel>CHOOSE A SPECIFIC VIEW</SectionLabel>
            {LAUNCHES.map((l) => (
              <button
                key={l.title}
                onClick={() => launchCard(l)}
                disabled={running}
                className={`flex items-stretch gap-3.5 w-full p-3 rounded-xl bg-[#0e0e0e] border transition-colors ${
                  running ? "opacity-45 cursor-not-allowed" : "hover:border-arena-yellow/55 hover:bg-[#161616]"
                } ${l.danger ? "border-arena-miss/40" : "border-white/[0.09]"}`}
              >
                <span className={`w-1 self-stretch rounded ${l.danger ? "bg-arena-miss" : "bg-arena-yellow"}`} />
                <span className="flex items-center justify-center w-6 h-6 flex-none rounded-[6px] bg-arena-yellow/10 text-arena-yellow">
                  <Play size={11} fill="currentColor" strokeWidth={0} />
                </span>
                <span className="flex flex-col gap-[2px] text-left min-w-0">
                  <span className="font-bold text-[12.5px] tracking-wide text-white">{l.title}</span>
                  <span className="text-[11px] text-white/50">{l.desc}</span>
                </span>
              </button>
            ))}

            <SectionLabel>OPTIONS</SectionLabel>
            <div className="bg-arena-panel border border-white/[0.08] rounded-xl p-4 flex flex-col gap-[11px]">
              <Toggle label="Auto-orbit 3D camera" checked={orbit} onToggle={() => setOrbit(!orbit)} disabled={running} />
              <Toggle label="Limb speed heat" checked={heat} onToggle={() => setHeat(!heat)} disabled={running} />
              <div className="flex items-center gap-3 pt-0.5">
                <span className="text-[12.5px] text-white/50 w-28">Single-cam scan</span>
                <input
                  value={camera}
                  onChange={(e) => setCamera(e.target.value)}
                  disabled={running}
                  title="Camera index for the single-camera fallback scan"
                  className="w-16 bg-black border border-white/[0.14] rounded-md px-2.5 py-1.5 font-mono text-[13px] text-white outline-none focus:border-arena-yellow/50 disabled:opacity-50"
                />
                <button
                  onClick={scanFaceSingle}
                  disabled={running || !trimmed}
                  title="Enroll from one webcam close-up instead of the arena cameras"
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold text-[11px] tracking-wide border border-white/[0.16] text-white/70 hover:text-white hover:border-arena-yellow/40 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <ScanFace size={13} />
                  SCAN 1 CAM
                </button>
              </div>
            </div>

            <SectionLabel>MANAGE FACES</SectionLabel>
            <div className="bg-arena-panel border border-white/[0.08] rounded-xl p-4 flex flex-col gap-3">
              <div className="flex flex-wrap gap-2">
                {enrolled.length === 0 ? (
                  <span className="text-[12px] text-white/40">Gallery is empty — nobody enrolled yet.</span>
                ) : (
                  enrolled.map((n) => (
                    <span
                      key={n}
                      className="flex items-center gap-1.5 bg-black border border-white/[0.14] rounded-full px-3 py-1 text-[12px] text-white/85"
                    >
                      <Check size={12} className="text-arena-hit" strokeWidth={3} />
                      {n}
                    </span>
                  ))
                )}
              </div>
              <button
                onClick={downloadModels}
                disabled={running}
                className="flex items-center gap-2 self-start bg-[#141414] border border-white/[0.12] rounded-lg px-3.5 py-2 font-bold text-[11px] tracking-wide text-white/70 hover:text-white hover:border-arena-yellow/40 disabled:opacity-45"
              >
                <Download size={13} />
                RE-DOWNLOAD FACE MODELS
              </button>
              <p className="text-[10.5px] text-white/35 leading-snug">
                Face labels are identification hints only — not liveness/anti-spoof authentication, and never a
                fire-authorization signal.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* right column — fills the viewport; only the MISSION LOG box scrolls */}
      <div className="flex-1 min-w-0 flex flex-col gap-2 min-h-0">
        <SectionLabel>LOCAL FILE / DEVICE CHECKS</SectionLabel>
        <p className="text-[10px] text-white/35 leading-snug">
          Presence checks only — not camera, model, GPU, launcher, or E-stop readiness.
        </p>
        <div className="grid grid-cols-4 gap-2.5">
          {readiness.map((r) => (
            <div key={r.label} className="bg-arena-panel border border-white/[0.08] rounded-[11px] p-3 flex flex-col gap-2">
              <div className="flex items-center gap-1.5">
                <span
                  className={`w-[7px] h-[7px] rounded-full ${r.ready ? "bg-arena-yellow" : "bg-white/30"}`}
                  style={{ boxShadow: r.ready ? "0 0 8px #FFD700" : "none" }}
                />
                <span className="font-mono text-[9.5px] tracking-[0.1em] text-white/45">{r.label}</span>
              </div>
              <span className={`font-bold text-[13px] tracking-wide ${r.ready ? "text-arena-yellow" : "text-white/45"}`}>
                {r.status}
              </span>
            </div>
          ))}
        </div>

        <SectionLabel>MISSION LOG</SectionLabel>
        <div
          ref={logBox}
          onScroll={onLogScroll}
          className="flex-1 min-h-0 bg-[#040404] border border-white/[0.08] rounded-xl p-4 font-mono text-[12.5px] leading-[1.85] overflow-y-auto"
        >
          {log.map((line, i) => (
            <div key={i} className={logColor(line.tone)}>
              <span className="text-white/35">{line.t}</span>  {line.msg}
            </div>
          ))}
          <div className="text-arena-yellow">
            &gt;
            <span className="log-cursor inline-block w-2 h-[15px] bg-arena-yellow ml-1 align-[-2px]" />
          </div>
        </div>
      </div>
    </div>
  );
}

function StepTag({ n, children }: { n: number; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex items-center justify-center w-[18px] h-[18px] rounded-full bg-arena-yellow text-black font-bold text-[11px]">
        {n}
      </span>
      <span className="font-bold text-[11px] tracking-[0.12em] text-white/70 uppercase">{children}</span>
    </div>
  );
}

function Toggle({
  label,
  checked,
  onToggle,
  disabled,
}: {
  label: string;
  checked: boolean;
  onToggle: () => void;
  disabled?: boolean;
}) {
  return (
    <div
      onClick={disabled ? undefined : onToggle}
      className={`flex items-center gap-3 ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
    >
      <span
        className={`w-[18px] h-[18px] flex-none rounded-[5px] flex items-center justify-center border-[1.5px] ${
          checked ? "bg-arena-yellow border-arena-yellow" : "border-white/25"
        }`}
      >
        {checked && <Check size={12} strokeWidth={3.5} className="text-black" />}
      </span>
      <span className="text-[13px] text-white/85">{label}</span>
    </div>
  );
}
