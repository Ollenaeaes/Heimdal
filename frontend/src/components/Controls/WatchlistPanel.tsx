import { useState, useRef, useEffect } from 'react';
import { useWatchlistStore, useWatchlistQuery } from '../../hooks/useWatchlist';
import { useVesselStore } from '../../hooks/useVesselStore';

const RISK_DOT_COLORS: Record<string, string> = {
  green: 'bg-green-500',
  yellow: 'bg-yellow-500',
  red: 'bg-red-500',
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

  return (
    <div ref={panelRef} className="relative">
      <button
        data-testid="watchlist-toggle"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
          isOpen
            ? 'bg-blue-600 text-white'
            : 'bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white'
        } border border-gray-700`}
      >
        <span className="text-sm">⊙</span>
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
          className="absolute top-full left-0 mt-1.5 w-72 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden"
        >
          <div className="px-3 py-2 border-b border-gray-700">
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
            <div className="max-h-64 overflow-y-auto">
              {watchedVessels.map((v) => (
                <button
                  key={v.mmsi}
                  onClick={() => {
                    selectVessel(v.mmsi);
                    setIsOpen(false);
                  }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-gray-700/50 transition-colors text-left"
                >
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 ${RISK_DOT_COLORS[v.riskTier] ?? 'bg-gray-500'}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-200 truncate">{v.name}</p>
                    {v.timestamp && (
                      <p className="text-[10px] text-gray-500">{formatTimeAgo(v.timestamp)}</p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
