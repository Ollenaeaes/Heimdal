/**
 * Legend for GNSS interference zones (ADS-B derived) and aircraft of interest.
 */
export function GnssLegend({ visible }: { visible: boolean }) {
  if (!visible) return null;

  return (
    <div className="absolute top-1/2 -translate-y-1/2 left-4 z-[1000] bg-slate-900/90 backdrop-blur-sm rounded-lg px-3 py-2.5 border border-slate-700/50 text-xs pointer-events-auto">
      <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1.5">GNSS Interference</div>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full border border-red-500/80" style={{ background: 'rgba(239,68,68,0.35)' }} />
          <span className="text-slate-300">Severe (NACp &le; 3 / GPS lost)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full border border-amber-400/70" style={{ background: 'rgba(251,191,36,0.30)' }} />
          <span className="text-slate-300">Moderate (NACp 4-5)</span>
        </div>
      </div>
      <div className="text-[10px] text-slate-400 uppercase tracking-wider mt-2.5 mb-1.5">Aircraft</div>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full" style={{ background: '#f59e0b' }} />
          <span className="text-slate-300">Military</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full" style={{ background: '#06b6d4' }} />
          <span className="text-slate-300">Coast Guard</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full" style={{ background: '#3b82f6' }} />
          <span className="text-slate-300">Police</span>
        </div>
      </div>
      <div className="text-[9px] text-slate-500 mt-2 border-t border-slate-700/50 pt-1.5">
        Aircraft data from adsb.lol (ODbL)
      </div>
    </div>
  );
}
