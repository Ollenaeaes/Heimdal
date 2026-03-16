import { useState, useRef, useEffect } from 'react';
import { useWatchlistStore, useWatchlistQuery, useWatchlistMutations } from '../../hooks/useWatchlist';
import { useVesselStore } from '../../hooks/useVesselStore';

const RISK_DOT_COLORS: Record<string, string> = {
  green: 'bg-[#22C55E]',
  yellow: 'bg-[#F59E0B]',
  red: 'bg-[#EF4444]',
};

const RISK_TIER_LABELS: Record<string, string> = {
  green: 'Low',
  yellow: 'Medium',
  red: 'High',
};

function formatTimeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function WatchlistPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const watchedMmsis = useWatchlistStore((s) => s.watchedMmsis);
  const vessels = useVesselStore((s) => s.vessels);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const { removeMutation } = useWatchlistMutations();

  // Fetch watchlist on mount
  useWatchlistQuery();

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isOpen]);

  const watchedVessels = Array.from(watchedMmsis).map((mmsi) => {
    const vessel = vessels.get(mmsi);
    return {
      mmsi,
      name: vessel?.name ?? `MMSI ${mmsi}`,
      riskTier: vessel?.riskTier ?? 'green',
      timestamp: vessel?.timestamp,
    };
  });

  const handleRemove = (e: React.MouseEvent, mmsi: number) => {
    e.stopPropagation();
    removeMutation.mutate({ mmsi });
  };

  return (
    <div ref={panelRef} className="relative">
      <button
        data-testid="watchlist-toggle"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
          isOpen
            ? 'bg-[#3B82F6] text-white'
            : 'bg-[#111827] text-gray-300 hover:bg-[#1F2937] hover:text-white'
        } border border-[#1F2937]`}
      >
        <span className="text-sm">{'\u2299'}</span>
        Watchlist
        {watchedMmsis.size > 0 && (
          <span className="ml-1 bg-blue-500/30 text-blue-300 rounded-full px-1.5 text-[10px]">
            {watchedMmsis.size}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          data-testid="watchlist-panel"
          className="absolute top-full left-0 mt-1.5 w-80 bg-[#111827] border border-[#1F2937] rounded shadow-xl z-50 overflow-hidden backdrop-blur-md"
        >
          <div className="px-3 py-2 border-b border-[#1F2937]">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
              Watched Vessels
            </h3>
          </div>

          {watchedVessels.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <p className="text-gray-500 text-xs">
                No vessels watched. Click a vessel and press Watch to start.
              </p>
            </div>
          ) : (
            <div className="max-h-72 overflow-y-auto">
              {watchedVessels.map((v) => (
                <div
                  key={v.mmsi}
                  className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-[#1F2937]/50 transition-colors group"
                >
                  <button
                    onClick={() => {
                      selectVessel(v.mmsi);
                      setIsOpen(false);
                    }}
                    className="flex items-center gap-2.5 min-w-0 flex-1 text-left"
                  >
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${RISK_DOT_COLORS[v.riskTier] ?? 'bg-gray-500'}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-gray-200 truncate">{v.name}</p>
                      <div className="flex items-center gap-2 text-[10px] text-gray-500">
                        <span className="font-mono">{v.mmsi}</span>
                        <span>{RISK_TIER_LABELS[v.riskTier] ?? v.riskTier} risk</span>
                        {v.timestamp && (
                          <>
                            <span>{'\u00B7'}</span>
                            <span>{formatTimeAgo(v.timestamp)}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={(e) => handleRemove(e, v.mmsi)}
                    className="shrink-0 opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all text-xs p-1"
                    aria-label={`Remove ${v.name} from watchlist`}
                    title="Remove from watchlist"
                  >
                    {'\u2715'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
