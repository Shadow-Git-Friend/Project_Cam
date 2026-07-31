import { Square } from "lucide-react";

export default function Footer({
  running,
  command,
  onStop,
}: {
  running: boolean;
  command: string;
  onStop: () => void;
}) {
  return (
    <footer className="flex items-center gap-3.5 bg-[#0a0a0a] border-t border-white/[0.08] px-[18px] py-2.5">
      <span
        className={`font-mono text-[12px] font-bold tracking-[0.12em] px-3 py-1.5 rounded-md border ${
          running
            ? "text-black bg-arena-yellow border-arena-yellow"
            : "text-white/55 bg-[#141414] border-white/10"
        }`}
      >
        {running ? "RUNNING" : "IDLE"}
      </span>
      <div className="flex-1 bg-black border border-white/[0.12] rounded-lg px-3 py-2 font-mono text-[12px] text-white/50 truncate">
        {command || "no active pipeline"}
      </div>
      <button
        onClick={onStop}
        className={`flex items-center gap-2 px-[18px] py-2.5 rounded-lg font-extrabold text-[12px] tracking-[0.08em] border transition-[filter] hover:brightness-110 ${
          running
            ? "border-arena-miss bg-arena-miss text-black"
            : "border-arena-miss/40 bg-[#1a0d0c] text-arena-missText"
        }`}
      >
        <Square size={12} fill="currentColor" strokeWidth={0} />
        STOP
      </button>
    </footer>
  );
}
