import {
  SlidersHorizontal,
  Dumbbell,
  History,
  Crosshair,
  type LucideIcon,
} from "lucide-react";

export type ViewId = "CONTROL" | "TRAINING" | "SESSIONS" | "SHOTS";

const NAV: { id: ViewId; Icon: LucideIcon }[] = [
  { id: "CONTROL", Icon: SlidersHorizontal },
  { id: "TRAINING", Icon: Dumbbell },
  { id: "SESSIONS", Icon: History },
  { id: "SHOTS", Icon: Crosshair },
];

export default function Sidebar({
  view,
  setView,
}: {
  view: ViewId;
  setView: (v: ViewId) => void;
}) {
  return (
    <aside className="w-[216px] flex-none bg-[#060606] border-r border-white/[0.06] flex flex-col py-5">
      <div className="px-[22px] font-mono text-[10px] tracking-[0.22em] text-white/30 mb-3">
        MENU
      </div>
      <nav className="flex flex-col gap-1 pr-3">
        {NAV.map(({ id, Icon }) => {
          const active = view === id;
          return (
            <button
              key={id}
              onClick={() => setView(id)}
              className={`flex items-center gap-3 w-full pl-[18px] pr-4 py-2.5 rounded-r-lg text-[13px] font-bold tracking-[0.09em] text-left transition-colors border-l-[3px] ${
                active
                  ? "border-arena-yellow bg-[#101010] text-arena-yellow"
                  : "border-transparent text-white/55 hover:bg-[#101010] hover:text-white"
              }`}
            >
              <Icon size={18} strokeWidth={2} />
              {id}
            </button>
          );
        })}
      </nav>
      <div className="mt-6 px-[22px] font-mono text-[10px] leading-[1.9] tracking-[0.14em] text-white/25">
        FUTURE
        <br />
        USERS · LEVELS
        <br />
        CALENDAR · REPORTS
      </div>
      <div className="mt-auto px-[22px] font-mono text-[10px] tracking-[0.14em] text-white/25">
        v0.9 · PRE-SEASON
      </div>
    </aside>
  );
}
