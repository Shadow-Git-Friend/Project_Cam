export default function Topbar() {
  return (
    <header className="flex items-center px-[26px] py-4 bg-arena-bg">
      <div className="w-[38px] h-[38px] rounded-[9px] bg-arena-yellow text-black flex items-center justify-center font-extrabold text-[15px] tracking-wide">
        PC
      </div>
      <div className="ml-3.5 flex items-baseline gap-2.5">
        <span className="font-extrabold text-[22px] tracking-tight text-white">PROJECT CAM</span>
        <span className="font-extrabold text-[22px] tracking-tight text-arena-yellow">
          ARENA CONTROL CENTER
        </span>
      </div>
      <div className="ml-auto text-right font-mono text-[10.5px] tracking-wider text-white/40 leading-relaxed">
        GARAGE ARENA · ALMATY
        <br />
        LOCAL · MULTI-VIEW · 3D
      </div>
    </header>
  );
}
