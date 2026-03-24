/**
 * Legend for GNSS interference zone colors.
 */
export function GnssLegend({ visible }: { visible: boolean }) {
  if (!visible) return null;

  return (
    <div className="absolute top-16 left-4 z-[1000] bg-slate-900/90 backdrop-blur-sm rounded-lg px-3 py-2.5 border border-slate-700/50 text-xs pointer-events-auto">
      <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1.5">GNSS Zones</div>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-sm border border-red-500/70" style={{ background: 'rgba(239,68,68,0.35)' }} />
          <span className="text-slate-300">Spoofing target</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-sm border border-purple-500/65" style={{ background: 'rgba(168,85,247,0.30)' }} />
          <span className="text-slate-300">Jamming</span>
        </div>
      </div>
    </div>
  );
}
