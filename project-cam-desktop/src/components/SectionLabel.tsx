export default function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 mb-1.5 mt-3.5 first:mt-0.5">
      <span className="w-[3px] h-3.5 bg-arena-yellow rounded-sm" />
      <span className="font-mono text-[11px] tracking-[0.18em] text-white/55">{children}</span>
    </div>
  );
}
