import { useEffect, useMemo, useRef, useState } from "react";
import {
  Power,
  ShieldAlert,
  ShieldCheck,
  Crosshair,
  Gauge,
  Flame,
  RotateCcw,
  Ruler,
  Undo2,
  Plug,
  Activity,
} from "lucide-react";
import SectionLabel from "../components/SectionLabel";
import {
  FIRE_CONFIRMATION,
  PITCH_DEFAULT_MAX_DEG,
  PITCH_DEFAULT_MIN_DEG,
  RPM_MAX,
  RPM_MIN_FIRE,
  YAW_LIMIT_DEG,
  autoSelectPort,
  fireBlockers,
  type ConsoleCommand,
  type ConsoleStatus,
  type FitKind,
  type SerialDevice,
} from "../blm";
import type { LogLine, ProcessState, RunFn } from "../App";

const inTauri = () =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** RPM passes from the measurement protocol: 500 is the lowest energy above the
 *  firmware gate and the pass that catches a mistake cheaply; 800 is the RPM every
 *  current accuracy claim rests on. */
const RPM_PRESETS = [500, 650, 800, 950];

/** Hold, do not click. A shot must cost a deliberate, sustained action. */
const FIRE_HOLD_MS = 900;

export default function LauncherView({
  run,
  processState,
  status,
  send,
  log,
}: {
  run: RunFn;
  processState: ProcessState;
  status: ConsoleStatus | null;
  send: (command: ConsoleCommand) => void;
  log: LogLine[];
}) {
  const [ports, setPorts] = useState<SerialDevice[]>([]);
  const [port, setPort] = useState("");
  const [allowFire, setAllowFire] = useState(false);
  const [roomClear, setRoomClear] = useState(false);
  const [pitch, setPitch] = useState(0);
  const [yaw, setYaw] = useState(0);
  // Starts at 0, not at a preset: the console commands 0 RPM until the operator
  // asks for more, and a slider parked on 500 read as "the wheels are set to 500".
  const [rpm, setRpm] = useState(0);
  // Entered as positive magnitudes ("how far down / how far up"), because that is
  // how the travel is measured with a hand on the barrel. Converted to a signed
  // envelope when applied.
  const [travelDown, setTravelDown] = useState("0");
  const [travelUp, setTravelUp] = useState("30");
  const [heightM, setHeightM] = useState("0.52");
  const [fitKind, setFitKind] = useState<FitKind>("linear");
  const [distance, setDistance] = useState("");
  const [holdMs, setHoldMs] = useState(0);
  const holdTimer = useRef<number | null>(null);
  const logBox = useRef<HTMLDivElement>(null);
  const logStick = useRef(true);

  const busy = processState === "starting" || processState === "running" ||
    processState === "stopping";
  const live = status !== null && (processState === "running" || processState === "starting");

  // Ports come from the backend, so a device node is a selection and never typed
  // text. Refresh whenever a process starts or ends: the launcher may have been
  // plugged in between attempts.
  useEffect(() => {
    if (!inTauri()) return;
    let cancelled = false;
    (async () => {
      const { invoke } = await import("@tauri-apps/api/core");
      try {
        const found = await invoke<SerialDevice[]>("list_serial_ports");
        if (cancelled || !Array.isArray(found)) return;
        setPorts(found);
        // Preselect the detected launcher, but never override a deliberate
        // choice that is still present — the refresh runs on every state change.
        setPort((current) => autoSelectPort(found, current));
      } catch {
        /* leave the list empty; OPEN CONSOLE stays disabled */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [processState]);

  // Room-clear is a per-session judgement: a stop, a fault or a closed console
  // must never leave a stale confirmation behind for the next one.
  useEffect(() => {
    if (!live) setRoomClear(false);
  }, [live]);

  const onLogScroll = () => {
    const el = logBox.current;
    if (el) logStick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };
  useEffect(() => {
    const el = logBox.current;
    if (el && logStick.current) el.scrollTop = el.scrollHeight;
  }, [log]);

  const selected = ports.find((device) => device.path === port);
  const latched = status?.estop_latched === true;
  // A latched ESTOP refuses every actuating command in the bridge. The controls
  // must go dead with it: they used to stay live and responsive while the machine
  // silently ignored everything, which reads as "the panel is broken".
  const canActuate = live && !latched;
  const commandedRpm = status?.wheel_rpm ?? 0;
  // The pitch envelope is LIVE state, not a constant: the bridge holds it, the
  // operator declares it, and a re-zero translates it. Taking the slider bounds from
  // here means the control can never offer an angle the bridge will clamp.
  const pitchMin = status?.pitch_min_deg ?? PITCH_DEFAULT_MIN_DEG;
  const pitchMax = status?.pitch_max_deg ?? PITCH_DEFAULT_MAX_DEG;
  const commandedPitch = status?.pitch_deg ?? 0;
  const commandedYaw = status?.yaw_deg ?? 0;

  // SET ZERO translates the safe physical endpoints into its new coordinate
  // frame. Keep the editable magnitudes in sync with that live result; otherwise
  // a later APPLY TRAVEL would silently restore stale pre-zero values.
  useEffect(() => {
    setTravelDown(String(Math.max(0, -pitchMin)));
    setTravelUp(String(Math.max(0, pitchMax)));
  }, [pitchMin, pitchMax]);

  const blockers = useMemo(() => fireBlockers(status, roomClear), [status, roomClear]);
  const canFire = live && blockers.length === 0;
  const canArm =
    live &&
    status !== null &&
    status.allow_fire &&
    !status.estop_latched &&
    roomClear &&
    status.pitch_deg !== null &&
    status.wheel_rpm >= RPM_MIN_FIRE;

  const clearHold = () => {
    if (holdTimer.current !== null) {
      window.clearInterval(holdTimer.current);
      holdTimer.current = null;
    }
    setHoldMs(0);
  };

  const beginHold = () => {
    if (!canFire || holdTimer.current !== null) return;
    const started = Date.now();
    holdTimer.current = window.setInterval(() => {
      const elapsed = Date.now() - started;
      if (elapsed >= FIRE_HOLD_MS) {
        clearHold();
        send({ command: "fire", confirm: FIRE_CONFIRMATION });
      } else {
        setHoldMs(elapsed);
      }
    }, 50);
  };

  useEffect(() => clearHold, []);
  // Releasing the gate mid-hold must abort the shot, not queue it.
  useEffect(() => {
    if (!canFire) clearHold();
  }, [canFire]);

  const openConsole = () => {
    if (!port) return;
    run({ profile_id: "blm_console", serial_port: port, allow_fire: allowFire });
  };

  // Aim NEVER commands the flywheels. The firmware takes one combined
  // `set v h wl wr`, so an aim must carry an RPM — it carries the one the console
  // ALREADY holds, not this panel's pending slider value. Sending the slider
  // value meant that nudging PITCH spun the wheels to 500: every logged command
  // read `aim <angle> 0 500` when the operator had only touched the aim.
  const sendAim = (nextPitch: number, nextYaw: number) =>
    send({
      command: "aim",
      pitch_deg: nextPitch,
      yaw_deg: nextYaw,
      wheel_rpm: commandedRpm,
    });

  // ...and the wheels never move the aim: `wheels` reuses the angles the console
  // holds, so the two axes of control stay independent in both directions.
  const sendWheels = (nextRpm: number) =>
    send({ command: "wheels", wheel_rpm: nextRpm });

  // The console owns the truth about what is commanded. `stop` zeroes the RPM and
  // `center` zeroes the angles, neither of which the operator typed here — so
  // adopt the console's values whenever they differ from what this panel last
  // sent. Without it the sliders keep displaying an aim and an RPM the machine is
  // no longer holding. A drag is unaffected: the console's values do not change
  // until the release commits, so nothing fights the pointer.
  const adopted = useRef({ pitch: 0, yaw: 0, rpm: 0 });
  useEffect(() => {
    if (!status) return;
    if (commandedPitch !== adopted.current.pitch) {
      adopted.current.pitch = commandedPitch;
      setPitch(commandedPitch);
    }
    if (commandedYaw !== adopted.current.yaw) {
      adopted.current.yaw = commandedYaw;
      setYaw(commandedYaw);
    }
    if (commandedRpm !== adopted.current.rpm) {
      adopted.current.rpm = commandedRpm;
      setRpm(commandedRpm);
    }
  }, [status, commandedPitch, commandedYaw, commandedRpm]);

  const applyLimits = () => {
    const down = Number(travelDown);
    const up = Number(travelUp);
    if (!Number.isFinite(down) || !Number.isFinite(up)) return;
    // Magnitudes in, signed envelope out. A negative "down" would silently mean
    // "the barrel cannot reach horizontal", which is not what the field asks.
    send({
      command: "limits",
      pitch_min_deg: -Math.abs(down),
      pitch_max_deg: Math.abs(up),
    });
  };

  const recordMeasurement = () => {
    const value = Number(distance);
    if (!Number.isFinite(value) || value <= 0) return;
    send({ command: "measure", rpm, landing_distance_m: value });
    setDistance("");
  };

  const runFit = () => {
    const value = Number(heightM);
    if (!Number.isFinite(value) || value <= 0) return;
    send({ command: "fit", height_m: value, kind: fitKind });
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

  return (
    <div className="h-full flex gap-[22px] px-[26px] py-[22px] overflow-hidden">
      {/* left — link, safety, telemetry */}
      <div className="w-[430px] flex-none flex flex-col gap-2 min-h-0 overflow-y-auto pr-1 pb-2">
        <SectionLabel>SERIAL LINK</SectionLabel>
        <Panel>
          <div className="flex items-center gap-2">
            <Plug size={14} className="text-white/40 flex-none" />
            <select
              value={port}
              onChange={(e) => setPort(e.target.value)}
              disabled={busy || ports.length === 0}
              className="flex-1 min-w-0 bg-black border border-white/[0.16] rounded-lg px-2.5 py-2 text-[13px] text-white outline-none focus:border-arena-yellow/60 disabled:opacity-50"
            >
              {ports.length === 0 ? (
                <option value="">no serial device found</option>
              ) : (
                ports.map((device) => (
                  <option key={device.path} value={device.path}>
                    {device.likely_launcher ? "▸ " : "   "}
                    {device.label} · {device.node}
                  </option>
                ))
              )}
            </select>
          </div>
          {selected ? (
            <p
              className={`text-[11px] leading-snug ${
                selected.likely_launcher ? "text-arena-hit" : "text-arena-missText"
              }`}
            >
              {selected.likely_launcher ? "DETECTED · " : "NOT A LAUNCHER · "}
              <span className="text-white/60">{selected.reason}</span>
              {selected.usb_id && (
                <span className="font-mono text-white/35"> [{selected.usb_id}]</span>
              )}
              {/* Detection is passive, so it must not read as a verification. The
                  two webcams on this rig expose CDC-ACM interfaces and would
                  otherwise sit in this list looking like candidates. */}
              <span className="block text-white/35">
                Identified by USB adapter, without opening the port — POLL FIRMWARE
                after connecting is what proves it is the launcher.
              </span>
              {selected.path.startsWith("/dev/serial/by-id/") && (
                <span className="block text-white/35">
                  Selected by its stable by-id link, so a replug that renumbers{" "}
                  {selected.node} does not change this choice.
                </span>
              )}
            </p>
          ) : (
            <p className="text-[11px] text-white/40 leading-snug">
              Nothing plugged in yet. The list refreshes on its own — connect the
              launcher and it appears, already selected.
            </p>
          )}
          <label
            className={`flex items-start gap-2.5 text-[12px] leading-snug ${
              busy ? "opacity-50" : "cursor-pointer"
            }`}
          >
            <input
              type="checkbox"
              checked={allowFire}
              disabled={busy}
              onChange={(e) => setAllowFire(e.target.checked)}
              className="mt-[3px] accent-arena-miss"
            />
            <span>
              <span className="font-bold text-arena-missText">ENABLE FIRE CONTROL</span>
              <span className="block text-white/45">
                Adds the arm/fire intents for this session only. Leave off for aim,
                wheels and reload — the same panel, without a shot.
              </span>
            </span>
          </label>
          <button
            onClick={openConsole}
            disabled={busy || !port}
            className="flex items-center justify-center gap-2 w-full py-3 rounded-lg font-extrabold text-[14px] tracking-wide bg-arena-yellow text-black hover:bg-arena-yellowh disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Power size={15} />
            {busy ? "CONSOLE RUNNING" : "OPEN CONSOLE"}
          </button>
          <p className="text-[10.5px] leading-snug text-white/35">
            Closing the console sends <span className="font-mono text-white/55">stop</span>{" "}
            and releases the port — including on STOP, a crash, or closing the window.
            It does not re-centre the barrel.
          </p>
        </Panel>

        <SectionLabel>SAFETY</SectionLabel>
        <div className="bg-arena-panel border border-arena-miss/40 rounded-xl p-3.5 flex flex-col gap-2.5">
          <button
            onClick={() => send({ command: "stop" })}
            disabled={!live}
            className="flex items-center justify-center gap-2.5 w-full py-4 rounded-lg font-extrabold text-[17px] tracking-[0.1em] bg-arena-miss text-black hover:brightness-110 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ShieldAlert size={19} />
            STOP
          </button>
          <div className="flex items-center gap-2">
            <StatePill
              on={status?.estop_latched === true}
              onText="ESTOP LATCHED"
              offText="not latched"
              tone="miss"
            />
            <button
              onClick={() => send({ command: "clear" })}
              disabled={!live || status?.estop_latched !== true}
              className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.16] text-[11px] font-bold tracking-wide text-white/70 hover:border-arena-yellow/60 hover:text-arena-yellow disabled:opacity-30"
            >
              <ShieldCheck size={13} />
              RELEASE LATCH
            </button>
          </div>
          <p className="text-[10.5px] leading-snug text-white/40">
            STOP latches: every actuating command is refused until the latch is
            released. Nobody downrange at any point — every shot in a calibration
            session goes into a wall or a net.
          </p>
        </div>

        <SectionLabel>TELEMETRY</SectionLabel>
        <Panel>
          <div className="grid grid-cols-2 gap-2">
            {/* Wheel L/R are MEASURED — the firmware reports real flywheel RPM.
                The angles are NOT: `info` returns the firmware's own internal
                angle, which ramps to whatever was commanded whether or not the
                barrel followed it. Measured on 2026-08-06: commanded 25 deg and
                the firmware read 25.0 deg after 1.2 s with no position feedback
                anywhere in the loop. So every angle on this panel is a command,
                and nothing here can confirm the barrel actually moved. */}
            <Metric label="WHEEL L · MEAS" value={fmt(status?.rpm_left)} unit="rpm" />
            <Metric label="WHEEL R · MEAS" value={fmt(status?.rpm_right)} unit="rpm" />
            <Metric label="RPM · CMD" value={fmt(status?.wheel_rpm)} unit="rpm" />
            <Metric label="SHOTS" value={status ? String(status.shots_fired) : "—"} />
            <Metric label="PITCH · CMD" value={fmt(status?.pitch_deg)} unit="deg" />
            <Metric label="YAW · CMD" value={fmt(status?.yaw_deg)} unit="deg" />
          </div>
          <p className="text-[10.5px] leading-snug text-white/35">
            CMD is the last commanded value. POLL FIRMWARE returns the firmware's
            own angle, which is <span className="text-white/55">open-loop</span> — it
            ramps to the commanded value whether or not the barrel followed. There is
            no position feedback in this machine, so confirm the aim by eye.
          </p>
          <button
            onClick={() => send({ command: "info" })}
            disabled={!live}
            className="flex items-center justify-center gap-1.5 w-full py-2 rounded-lg border border-white/[0.14] text-[11px] font-bold tracking-wide text-white/60 hover:text-arena-yellow hover:border-arena-yellow/50 disabled:opacity-30"
          >
            <Activity size={13} />
            POLL FIRMWARE (info)
          </button>
          {status && status.info_lines.length > 0 && (
            <div className="bg-black/60 border border-white/[0.07] rounded-lg p-2 font-mono text-[10.5px] leading-[1.7] text-white/60 max-h-[104px] overflow-y-auto">
              {status.info_lines.map((line, i) => (
                <div key={i} className="truncate">
                  {line}
                </div>
              ))}
            </div>
          )}
          {status?.last_refusal && (
            <p className="text-[11px] text-arena-missText leading-snug">
              last refusal: {status.last_refusal}
            </p>
          )}
        </Panel>
      </div>

      {/* right — aim, fire, calibration, log */}
      <div className="flex-1 min-w-0 flex flex-col gap-2 min-h-0">
        {/* Console state, pinned above the scroll region. Until it is open every
            control on this side is inert, and a slightly dimmed button is too
            quiet a signal for a panel that otherwise looks fully operable.
            A latched ESTOP takes over this strip entirely: it is the state where
            the controls move but the machine refuses, so it has to be impossible
            to miss and it carries its own release. */}
        {latched ? (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 py-2.5 rounded-lg border border-arena-miss bg-[#1a0d0c] font-mono text-[11.5px] text-arena-missText">
            <ShieldAlert size={15} className="flex-none" />
            <span className="font-bold tracking-[0.1em]">ESTOP LATCHED</span>
            <span className="text-white/55">
              aim, wheels, reload and fire are refused until you release it
            </span>
            <button
              onClick={() => send({ command: "clear" })}
              className="ml-auto flex items-center gap-1.5 px-3 py-1 rounded-md border border-arena-miss bg-arena-miss text-black font-bold tracking-wide hover:brightness-110"
            >
              <ShieldCheck size={13} />
              RELEASE LATCH
            </button>
          </div>
        ) : (
          <div
            className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 py-2 rounded-lg border font-mono text-[11.5px] ${
              live
                ? "border-arena-hit/50 bg-[#0c1a10] text-arena-hit"
                : "border-white/[0.12] bg-black/40 text-white/45"
            }`}
          >
            <span
              className={`w-[7px] h-[7px] rounded-full flex-none ${
                live ? "bg-arena-hit" : "bg-white/30"
              }`}
            />
            {live && status ? (
              <>
                <span className="font-bold tracking-[0.1em]">CONSOLE LIVE</span>
                <span className="text-white/55">{status.port}</span>
                <span
                  className={
                    status.allow_fire
                      ? "text-arena-missText font-bold"
                      : "text-white/55"
                  }
                >
                  {status.allow_fire ? "FIRE CONTROL ENABLED" : "AIM ONLY"}
                </span>
                <span className="ml-auto text-white/40">
                  shots {status.shots_fired}
                </span>
              </>
            ) : (
              <span>
                CONSOLE CLOSED — pick a port and press OPEN CONSOLE to enable these
                controls
              </span>
            )}
          </div>
        )}

        {/* The three control panels scroll as one column. They are taller than a
            short window, and with the column fixed they simply got clipped —
            pushing the MISSION LOG off the bottom edge with nothing to scroll.
            The log stays pinned below, because it is the operator's only
            feedback channel and must never be the thing that disappears. */}
        <div className="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-2">
          <SectionLabel>AIM &amp; WHEELS</SectionLabel>
          <div className="bg-arena-panel border border-arena-yellow/25 rounded-xl p-[18px] flex flex-col gap-3">
            <Slider
              icon={<Crosshair size={13} />}
              label="PITCH"
              value={pitch}
              // Bounds come from the console's declared envelope, so they follow
              // SET ZERO and TRAVEL LIMITS instead of being frozen in the UI.
              min={pitchMin}
              max={pitchMax}
              step={1}
              unit="deg"
              disabled={!canActuate}
              onChange={setPitch}
              // Only send when the value actually differs from what the console
              // holds: a click on the track with no movement used to fire off a
              // duplicate command.
              onCommit={(v) => {
                if (v !== commandedPitch) sendAim(v, yaw);
              }}
            />
            <Slider
              icon={<Crosshair size={13} />}
              label="YAW"
              value={yaw}
              min={-YAW_LIMIT_DEG}
              max={YAW_LIMIT_DEG}
              step={1}
              unit="deg"
              disabled={!canActuate}
              onChange={setYaw}
              onCommit={(v) => {
                if (v !== commandedYaw) sendAim(pitch, v);
              }}
            />
            <Slider
              icon={<Gauge size={13} />}
              label="WHEEL RPM"
              value={rpm}
              min={0}
              max={RPM_MAX}
              step={10}
              unit="rpm"
              disabled={!canActuate}
              onChange={setRpm}
              onCommit={(v) => {
                if (v !== commandedRpm) sendWheels(v);
              }}
              warn={rpm > 0 && rpm < RPM_MIN_FIRE ? `below the ${RPM_MIN_FIRE} rpm fire gate` : ""}
            />
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-bold tracking-[0.14em] text-white/40">
                PROTOCOL PASSES
              </span>
              {RPM_PRESETS.map((preset) => (
                <button
                  key={preset}
                  onClick={() => {
                    setRpm(preset);
                    sendWheels(preset);
                  }}
                  disabled={!canActuate}
                  className={`px-2.5 py-1 rounded-md border font-mono text-[11.5px] ${
                    rpm === preset
                      ? "border-arena-yellow text-arena-yellow bg-arena-yellow/[0.08]"
                      : "border-white/[0.14] text-white/60 hover:text-white"
                  } disabled:opacity-30`}
                >
                  {preset}
                </button>
              ))}
              <button
                onClick={() => {
                  setPitch(0);
                  setYaw(0);
                  sendAim(0, 0);
                }}
                disabled={!canActuate}
                className="ml-auto px-2.5 py-1 rounded-md border border-white/[0.14] text-[11px] font-bold text-white/60 hover:text-arena-yellow disabled:opacity-30"
              >
                LEVEL (0 / 0)
              </button>
            </div>
            <p className="text-[10.5px] text-white/35 leading-snug">
              The two controls are independent: moving PITCH or YAW leaves the wheels
              exactly as they are, and setting RPM leaves the aim alone. A slider is
              applied when you release it, and changing the aim clears ARM — a
              clearance judgement belongs to one specific shot.
              <span className="block mt-1 text-white/45">
                PITCH is limited to the declared travel{" "}
                <span className="font-mono text-white/70">
                  [{pitchMin}°, {pitchMax}°]
                </span>{" "}
                measured from the current zero — past it the barrel meets the ball
                feeder, and nothing in the machine measures position to warn you.
                YAW is symmetric ±{YAW_LIMIT_DEG}°.
              </span>
            </p>
          </div>

          <SectionLabel>DELIVERY</SectionLabel>
          <div className="bg-arena-panel border border-white/[0.08] rounded-xl p-[18px] flex flex-col gap-3">
            <div className="flex items-center gap-2.5">
              <button
                onClick={() => send({ command: "reload" })}
                disabled={!canActuate}
                className="flex items-center justify-center gap-2 flex-1 py-3 rounded-lg font-extrabold text-[13px] tracking-wide border border-white/[0.18] text-white hover:border-arena-yellow/60 hover:text-arena-yellow disabled:opacity-30"
              >
                <RotateCcw size={14} />
                RELOAD
              </button>
              <button
                onClick={() => send({ command: "center" })}
                disabled={!canActuate}
                title="Blind move to the firmware's zero. Only safe once SET ZERO was done at a good position."
                className="flex items-center justify-center gap-2 flex-1 py-3 rounded-lg font-extrabold text-[13px] tracking-wide border border-white/[0.18] text-white hover:border-arena-yellow/60 hover:text-arena-yellow disabled:opacity-30"
              >
                CENTER
              </button>
              {/* Moves nothing, so it stays available under a latched ESTOP — which
                  is exactly when the reference needs fixing, after an open-loop axis
                  has been driven into a stop. */}
              <button
                onClick={() => send({ command: "set_zero" })}
                disabled={!live}
                title="Adopt the barrel's current position as zero. Level it first — nothing here can measure whether it is level."
                className="flex items-center justify-center gap-2 flex-1 py-3 rounded-lg font-extrabold text-[13px] tracking-wide border border-arena-yellow/50 text-arena-yellow hover:bg-arena-yellow/[0.08] disabled:opacity-30"
              >
                <Crosshair size={14} />
                SET ZERO
              </button>
            </div>
            <p className="text-[10.5px] leading-snug text-white/35">
              SET ZERO makes the barrel's <span className="text-white/55">current</span>{" "}
              position the new zero — level it by hand first, because nothing in this
              machine measures whether it is level. Closing the console sends only{" "}
              <span className="font-mono text-white/55">stop</span>; it deliberately
              does not re-centre, because that is a blind move to a zero that may be
              inside the feeder.
            </p>

            {/* The envelope only the operator can know: how much travel remains
                below zero depends on where zero was set. Declared once and then
                enforced by the bridge — the alternative is re-deciding it on every
                slider drag, which is what jammed the barrel. */}
            <div className="flex items-end gap-2.5 flex-wrap border-t border-white/[0.07] pt-3">
              <Field
                label="PITCH TRAVEL DOWN (°)"
                value={travelDown}
                onChange={setTravelDown}
                width="w-[150px]"
                onEnter={applyLimits}
              />
              <Field
                label="PITCH TRAVEL UP (°)"
                value={travelUp}
                onChange={setTravelUp}
                width="w-[150px]"
                onEnter={applyLimits}
              />
              <button
                onClick={applyLimits}
                disabled={!live}
                className="flex items-center gap-1.5 px-3 py-2.5 rounded-lg border border-white/[0.18] text-[11.5px] font-bold text-white/80 hover:border-arena-yellow/60 hover:text-arena-yellow disabled:opacity-30"
              >
                APPLY TRAVEL
              </button>
              <span className="font-mono text-[11px] text-white/45">
                now [{pitchMin}°, {pitchMax}°]
              </span>
            </div>
            <p className="text-[10.5px] leading-snug text-white/35">
              Never force a powered axis by hand. With drive power removed, measure
              the unobstructed travel from the current zero, restore the chosen zero,
              and declare it here — the panel cannot know it, and the machine cannot
              sense a limit before hitting it. Defaults to{" "}
              <span className="font-mono text-white/55">
                [{status?.pitch_default_min_deg ?? PITCH_DEFAULT_MIN_DEG}°,{" "}
                {status?.pitch_default_max_deg ?? PITCH_DEFAULT_MAX_DEG}°]
              </span>
              . SET ZERO automatically translates the current safe endpoints into
              its new coordinates. If you moved the barrel by hand, the software
              does not know that displacement — measure and apply travel again.
            </p>

            <label
              className={`flex items-start gap-2.5 text-[12px] leading-snug ${
                live ? "cursor-pointer" : "opacity-50"
              }`}
            >
              <input
                type="checkbox"
                checked={roomClear}
                disabled={!live}
                onChange={(e) => setRoomClear(e.target.checked)}
                className="mt-[3px] accent-arena-hit"
              />
              <span>
                <span className="font-bold text-white">
                  I have checked the room — nobody is downrange
                </span>
                <span className="block text-white/45">
                  The only condition no machine can verify. Cleared automatically when
                  the console stops.
                </span>
              </span>
            </label>

            <div className="flex items-center gap-2.5">
              <button
                onClick={() => send({ command: status?.armed ? "disarm" : "arm" })}
                disabled={!live || (!status?.armed && !canArm)}
                className={`flex items-center justify-center gap-2 w-[190px] py-3.5 rounded-lg font-extrabold text-[13px] tracking-[0.08em] border ${
                  status?.armed
                    ? "border-arena-yellow bg-arena-yellow/[0.14] text-arena-yellow"
                    : "border-white/[0.18] text-white/75 hover:border-arena-yellow/60"
                } disabled:opacity-30 disabled:cursor-not-allowed`}
              >
                <ShieldCheck size={14} />
                {status?.armed
                  ? `ARMED · ${status.arm_remaining_s.toFixed(0)}s`
                  : "ARM"}
              </button>
              <button
                onPointerDown={beginHold}
                onPointerUp={clearHold}
                onPointerLeave={clearHold}
                onPointerCancel={clearHold}
                disabled={!canFire}
                className={`relative flex-1 overflow-hidden flex items-center justify-center gap-2.5 py-3.5 rounded-lg font-extrabold text-[15px] tracking-[0.1em] border ${
                  canFire
                    ? "border-arena-miss bg-arena-miss text-black"
                    : "border-arena-miss/25 bg-[#1a0d0c] text-arena-missText/40 cursor-not-allowed"
                }`}
              >
                <span
                  className="absolute inset-y-0 left-0 bg-black/25"
                  style={{ width: `${(holdMs / FIRE_HOLD_MS) * 100}%` }}
                />
                <Flame size={16} className="relative" />
                <span className="relative">
                  {holdMs > 0 ? "HOLD…" : "HOLD TO FIRE"}
                </span>
              </button>
            </div>

            {blockers.length > 0 ? (
              <p className="text-[11px] text-white/45 leading-snug">
                fire blocked: {blockers.join(" · ")}
              </p>
            ) : (
              <p className="text-[11px] text-arena-hit leading-snug">
                armed and clear — one shot, then ARM again
              </p>
            )}
          </div>

          <SectionLabel>v(RPM) CALIBRATION · METHOD A</SectionLabel>
          <div className="bg-arena-panel border border-white/[0.08] rounded-xl p-[18px] flex flex-col gap-3">
            <div className="flex items-end gap-2.5 flex-wrap">
              <Field label="BARREL HEIGHT (m)" value={heightM} onChange={setHeightM} width="w-[130px]" />
              <Field
                label={`LANDING DISTANCE (m) @ ${rpm} rpm`}
                value={distance}
                onChange={setDistance}
                width="w-[210px]"
                onEnter={recordMeasurement}
              />
              <button
                onClick={recordMeasurement}
                disabled={!live || !distance}
                className="flex items-center gap-1.5 px-3 py-2.5 rounded-lg border border-white/[0.18] text-[11.5px] font-bold text-white/80 hover:border-arena-yellow/60 hover:text-arena-yellow disabled:opacity-30"
              >
                <Ruler size={13} />
                RECORD SHOT
              </button>
              <button
                onClick={() => send({ command: "undo" })}
                disabled={!live || (status?.measurements.length ?? 0) === 0}
                className="flex items-center gap-1.5 px-3 py-2.5 rounded-lg border border-white/[0.14] text-[11.5px] font-bold text-white/55 hover:text-white disabled:opacity-30"
              >
                <Undo2 size={13} />
                UNDO
              </button>
            </div>

            <div className="flex flex-wrap gap-1.5 min-h-[26px]">
              {(status?.measurements ?? []).length === 0 ? (
                <span className="text-[11px] text-white/35">
                  no measurements yet — fire horizontally at pitch 0, then measure from
                  directly below the barrel to the first floor contact
                </span>
              ) : (
                (status?.measurements ?? []).map((m, i) => (
                  <span
                    key={i}
                    className="font-mono text-[11px] px-2 py-[3px] rounded-md border border-white/[0.14] text-white/75"
                  >
                    {m.rpm.toFixed(0)} rpm · {m.distance_m.toFixed(2)} m
                  </span>
                ))
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {(["linear", "quadratic", "interp"] as FitKind[]).map((kind) => (
                <button
                  key={kind}
                  onClick={() => setFitKind(kind)}
                  className={`px-2.5 py-1 rounded-md border font-mono text-[11px] ${
                    fitKind === kind
                      ? "border-arena-yellow text-arena-yellow bg-arena-yellow/[0.08]"
                      : "border-white/[0.14] text-white/55 hover:text-white"
                  }`}
                >
                  {kind}
                </button>
              ))}
              <button
                onClick={runFit}
                disabled={!live || (status?.measurements.length ?? 0) === 0}
                className="ml-auto px-4 py-2 rounded-lg font-extrabold text-[12px] tracking-wide bg-arena-yellow text-black hover:bg-arena-yellowh disabled:opacity-30"
              >
                WRITE v(RPM) MODEL
              </button>
            </div>
            {status?.model_summary ? (
              <p className="text-[11.5px] text-arena-hit leading-snug">
                {status.model_summary}
                <span className="block font-mono text-[10.5px] text-white/40 truncate">
                  {status.model_path}
                </span>
              </p>
            ) : (
              <p className="text-[10.5px] text-white/35 leading-snug">
                The residual is the deliverable, not a footnote: a speed without its
                spread cannot inform a clearance margin. The model clamps to the
                measured RPM range and never extrapolates.
              </p>
            )}
          </div>
        </div>

        <SectionLabel>MISSION LOG</SectionLabel>
        <div
          ref={logBox}
          onScroll={onLogScroll}
          className="flex-none h-[152px] bg-[#040404] border border-white/[0.08] rounded-xl p-3 font-mono text-[11.5px] leading-[1.8] overflow-y-auto"
        >
          {log.map((line, i) => (
            <div key={i} className={logColor(line.tone)}>
              <span className="text-white/35">{line.t}</span> {line.msg}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-arena-panel border border-white/[0.08] rounded-xl p-3.5 flex flex-col gap-2.5">
      {children}
    </div>
  );
}

function fmt(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(0);
}

function Metric({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit?: string;
}) {
  return (
    <div className="bg-black/50 border border-white/[0.07] rounded-lg px-2.5 py-1.5">
      <div className="text-[9.5px] font-bold tracking-[0.14em] text-white/35">{label}</div>
      <div className="font-mono text-[16px] text-white leading-tight">
        {value}
        {unit && <span className="text-[10px] text-white/40 ml-1">{unit}</span>}
      </div>
    </div>
  );
}

function StatePill({
  on,
  onText,
  offText,
  tone,
}: {
  on: boolean;
  onText: string;
  offText: string;
  tone: "miss" | "hit";
}) {
  const active =
    tone === "miss"
      ? "border-arena-miss text-arena-missText bg-[#1a0d0c]"
      : "border-arena-hit text-arena-hit bg-[#0c1a10]";
  return (
    <span
      className={`font-mono text-[10.5px] font-bold tracking-[0.12em] px-2.5 py-1 rounded-md border ${
        on ? active : "border-white/[0.12] text-white/40 bg-black/40"
      }`}
    >
      {on ? onText : offText}
    </span>
  );
}

function Slider({
  icon,
  label,
  value,
  min,
  max,
  step,
  unit,
  disabled,
  onChange,
  onCommit,
  warn,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  disabled: boolean;
  onChange: (v: number) => void;
  onCommit: (v: number) => void;
  warn?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="text-white/40">{icon}</span>
        <span className="text-[10px] font-bold tracking-[0.14em] text-white/45">
          {label}
        </span>
        <span className="ml-auto font-mono text-[14px] text-arena-yellow">
          {value}
          <span className="text-[10px] text-white/40 ml-1">{unit}</span>
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        // Commit on release, not on every intermediate pixel: dragging a slider
        // must not flood the firmware with dozens of aim commands.
        onPointerUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
        onKeyUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
        className="w-full accent-arena-yellow disabled:opacity-40"
      />
      {warn && <span className="text-[10.5px] text-arena-missText">{warn}</span>}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  width,
  onEnter,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  width: string;
  onEnter?: () => void;
}) {
  return (
    <label className={`flex flex-col gap-1 ${width}`}>
      <span className="text-[9.5px] font-bold tracking-[0.14em] text-white/40">
        {label}
      </span>
      <input
        value={value}
        inputMode="decimal"
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onEnter?.();
        }}
        className="bg-black border border-white/[0.16] rounded-lg px-2.5 py-2 font-mono text-[13px] text-white outline-none focus:border-arena-yellow/60"
      />
    </label>
  );
}
