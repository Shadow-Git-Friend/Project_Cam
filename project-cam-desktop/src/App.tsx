import { useCallback, useEffect, useRef, useState } from "react";
import { Square } from "lucide-react";
import Topbar from "./components/Topbar";
import Sidebar, { type ViewId } from "./components/Sidebar";
import ControlView from "./views/ControlView";
import TrainingView from "./views/TrainingView";
import LauncherView from "./views/LauncherView";
import SessionsView from "./views/SessionsView";
import ShotsView from "./views/ShotsView";
import type { LaunchRequest, LaunchReceipt } from "./launch";
import { parseStatusLine, type ConsoleCommand, type ConsoleStatus } from "./blm";

export type LogLine = { t: string; msg: string; tone: "sys" | "cmd" | "dim" | "out" | "err" };
export type ProcessState = "idle" | "starting" | "running" | "stopping" | "faulted";

// LaunchContext is no longer a frontend concept: the backend derives it from
// the profile, so the UI cannot claim a launch_kind the launch is not.

// Launches go through the Rust backend by NAME. The frontend cannot supply a
// program, arguments or a working directory: it names a profile and passes
// semantic parameters, and the backend resolves everything else (and runs the
// child in its own process group so stop reaps the whole tree).
export type RunFn = (request: LaunchRequest) => void;

const nowClock = () => new Date().toTimeString().slice(0, 8);

const inTauri = () =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

const isBusyState = (state: ProcessState) =>
  state === "starting" || state === "running" || state === "stopping";

function ProcessFooter({
  state,
  command,
  onStop,
}: {
  state: ProcessState;
  command: string;
  onStop: () => void;
}) {
  const busy = isBusyState(state);
  const canStop = isBusyState(state);
  const statusTone =
    state === "faulted"
      ? "text-arena-missText bg-[#1a0d0c] border-arena-miss/60"
      : busy
        ? "text-black bg-arena-yellow border-arena-yellow"
        : "text-white/55 bg-[#141414] border-white/10";

  return (
    <footer className="flex items-center gap-3.5 bg-[#0a0a0a] border-t border-white/[0.08] px-[18px] py-2.5">
      <span
        className={`font-mono text-[12px] font-bold tracking-[0.12em] px-3 py-1.5 rounded-md border ${statusTone}`}
      >
        {state.toUpperCase()}
      </span>
      <div className="flex-1 bg-black border border-white/[0.12] rounded-lg px-3 py-2 font-mono text-[12px] text-white/50 truncate">
        {command ||
          (state === "faulted" ? "last pipeline exited with an error" : "no active pipeline")}
      </div>
      <button
        onClick={onStop}
        disabled={!canStop}
        className={`flex items-center gap-2 px-[18px] py-2.5 rounded-lg font-extrabold text-[12px] tracking-[0.08em] border transition-[filter] ${
          canStop
            ? "border-arena-miss bg-arena-miss text-black hover:brightness-110"
            : "border-arena-miss/30 bg-[#1a0d0c] text-arena-missText/45 cursor-not-allowed"
        }`}
      >
        <Square size={12} fill="currentColor" strokeWidth={0} />
        STOP
      </button>
    </footer>
  );
}

export default function App() {
  const [view, setView] = useState<ViewId>("CONTROL");
  const [processState, setProcessState] = useState<ProcessState>("idle");
  const [command, setCommand] = useState("");
  const [evidenceRevision, setEvidenceRevision] = useState(0);
  const processStateRef = useRef<ProcessState>("idle");
  // Athlete name is shared between CONTROL and TRAINING so the identity
  // follows the user across views (enrollment, Face ID, session logs).
  const [name, setName] = useState("");
  // Launcher telemetry arrives on the same stdout stream as the log, tagged so
  // it can be routed out of it. Null whenever no console is publishing, which is
  // what every gate in the LAUNCHER view reads as "not live".
  const [blmStatus, setBlmStatus] = useState<ConsoleStatus | null>(null);
  const [log, setLog] = useState<LogLine[]>([
    { t: nowClock(), msg: "Project Cam control center ready", tone: "sys" },
    { t: nowClock(), msg: "launches resolve to backend profiles", tone: "dim" },
  ]);

  const append = (msg: string, tone: LogLine["tone"]) =>
    // cap the buffer so a long-running pipeline can't grow it without bound
    setLog((l) => [...l, { t: nowClock(), msg, tone }].slice(-500));

  const applyProcessState = useCallback((next: ProcessState) => {
    const previous = processStateRef.current;
    processStateRef.current = next;
    setProcessState(next);
    if (
      previous !== next &&
      isBusyState(previous) &&
      (next === "idle" || next === "faulted")
    ) {
      setCommand("");
      setEvidenceRevision((revision) => revision + 1);
    }
  }, []);

  const refreshProcessState = useCallback(async () => {
    if (!inTauri()) return "idle" as ProcessState;
    const { invoke } = await import("@tauri-apps/api/core");
    const next = await invoke<ProcessState>("pipeline_state");
    applyProcessState(next);
    return next;
  }, [applyProcessState]);

  const busy = isBusyState(processState);

  // Wire the backend log/exit events once.
  const bootMsg = useRef(false);
  useEffect(() => {
    if (!inTauri()) {
      if (!bootMsg.current) {
        bootMsg.current = true;
        append("browser preview — launch buttons need the desktop app (./run.sh)", "dim");
      }
      return;
    }
    let unlistenLog: (() => void) | undefined;
    let unlistenExit: (() => void) | undefined;
    (async () => {
      const { listen } = await import("@tauri-apps/api/event");
      unlistenLog = await listen<{ line: string; stream: string }>("pipeline-log", (e) => {
        const { line, stream } = e.payload;
        // A tagged status line is telemetry, not log text: showing raw JSON in
        // the mission log would bury the operator's own messages.
        const status = parseStatusLine(line);
        if (status) {
          setBlmStatus(status);
          return;
        }
        append(line, stream === "err" ? "err" : stream === "sys" ? "sys" : "out");
      });
      unlistenExit = await listen<{ code: number; label: string }>("pipeline-exit", (e) => {
        const { code, label } = e.payload;
        // The console is gone, so its last status must not linger as a live one.
        setBlmStatus(null);
        append(
          `${label} exited with code ${code}`,
          code === 0 || code === 130 || code === -2 ? "sys" : "err"
        );
        void refreshProcessState();
      });
    })().catch((err) => {
      // If event permissions are missing (capabilities), say so loudly instead
      // of silently losing all pipeline output + exit notifications.
      append(`event listeners failed: ${String(err)}`, "err");
    });
    return () => {
      unlistenLog?.();
      unlistenExit?.();
    };
  }, [refreshProcessState]);

  // Reconciliation is unconditional: Rust owns all transitions, and polling
  // repairs a lost event whether the terminal state is Idle or Faulted.
  useEffect(() => {
    if (!inTauri()) return;
    const reconcile = () => void refreshProcessState().catch(() => {});
    reconcile();
    const timer = window.setInterval(reconcile, 1000);
    return () => window.clearInterval(timer);
  }, [refreshProcessState]);

  const run: RunFn = (request) => {
    if (busy) {
      append("A process is already running; stop it first.", "err");
      return;
    }
    append(`LAUNCH ${request.profile_id}`, "cmd");
    if (!inTauri()) {
      append("(browser preview — not actually spawned)", "dim");
      return;
    }
    (async () => {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        // The receipt carries the backend's own label and command text, so the
        // log stays informative without the UI knowing any path.
        const receipt = await invoke<LaunchReceipt>("launch_profile", { request });
        setCommand(receipt.command);
        append(`${receipt.label} · session ${receipt.session_id}`, "sys");
        await refreshProcessState();
      } catch (err) {
        append(String(err), "err");
        await refreshProcessState().catch(() => {});
      }
    })();
  };

  // One typed intent to the running launcher console. The UI cannot write serial
  // and cannot write the bridge's protocol text: Rust renders the line and the
  // bridge applies the gates (arm expiry, auto-disarm after a shot, ESTOP latch).
  const sendLauncher = (command: ConsoleCommand) => {
    if (!inTauri()) {
      append(`(browser preview — ${command.command} not sent)`, "dim");
      return;
    }
    (async () => {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke<string>("send_launcher_command", { command });
      } catch (err) {
        append(String(err), "err");
      }
    })();
  };

  const stop = () => {
    if (!busy) return;
    if (!inTauri()) {
      setCommand("");
      return;
    }
    (async () => {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        const signalled = await invoke<boolean>("stop_process");
        if (!signalled) {
          append("nothing running — reconciling state", "dim");
        } else {
          append("stopping…", "sys");
        }
        await refreshProcessState();
      } catch (err) {
        append(String(err), "err");
        await refreshProcessState().catch(() => {});
      }
    })();
  };

  return (
    <div
      className="h-screen w-screen bg-arena-bg flex flex-col overflow-hidden"
      data-evidence-revision={evidenceRevision}
      data-process-state={processState}
    >
      <Topbar />
      <div className="h-0.5 bg-gradient-to-r from-arena-yellow to-arena-yellow/10" />
      <div className="flex flex-1 min-h-0">
        <Sidebar view={view} setView={setView} />
        {/* CONTROL and TRAINING manage their own scrolling (only their inner
            panels scroll); the data views scroll as whole pages. */}
        <main
          className={`flex-1 min-w-0 bg-arena-bg ${
            view === "CONTROL" || view === "TRAINING" || view === "LAUNCHER"
              ? "overflow-hidden"
              : "overflow-y-auto"
          }`}
        >
          {view === "CONTROL" && (
            <ControlView run={run} running={busy} log={log} name={name} setName={setName} />
          )}
          {view === "TRAINING" && (
            <TrainingView run={run} running={busy} log={log} name={name} setName={setName} />
          )}
          {view === "LAUNCHER" && (
            <LauncherView
              run={run}
              processState={processState}
              status={blmStatus}
              send={sendLauncher}
              log={log}
            />
          )}
          {view === "SESSIONS" && (
            <SessionsView athlete={name} evidenceRevision={evidenceRevision} />
          )}
          {view === "SHOTS" && (
            <ShotsView athlete={name} evidenceRevision={evidenceRevision} />
          )}
        </main>
      </div>
      <ProcessFooter state={processState} command={command} onStop={stop} />
    </div>
  );
}
