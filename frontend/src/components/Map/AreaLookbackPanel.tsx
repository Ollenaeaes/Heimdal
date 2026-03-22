import { useState, useCallback } from 'react';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { RISK_COLORS } from '../../utils/riskColors';

interface AreaVessel {
  mmsi: number;
  ship_name: string | null;
  flag_state: string | null;
  risk_tier: string;
  position_count: number;
}

/**
 * AreaLookbackPanel appears after a polygon is drawn for area lookback.
 * Shows date range picker, searches for vessels in the area, and lets the user
 * select vessels to play back.
 */
export function AreaLookbackPanel() {
  const areaPolygon = useLookbackStore((s) => s.areaPolygon);
  const isDrawing = useLookbackStore((s) => s.isDrawing);
  const isActive = useLookbackStore((s) => s.isActive);
  const configureArea = useLookbackStore((s) => s.configureArea);
  const activate = useLookbackStore((s) => s.activate);
  const cancelDrawing = useLookbackStore((s) => s.cancelDrawing);

  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 16);
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 16));

  const [results, setResults] = useState<AreaVessel[]>([]);
  const [selectedMmsis, setSelectedMmsis] = useState<Set<number>>(new Set());
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(async () => {
    if (!areaPolygon) return;

    setIsSearching(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        polygon: JSON.stringify(areaPolygon),
        start: new Date(startDate + ':00Z').toISOString(),
        end: new Date(endDate + ':00Z').toISOString(),
      });

      const res = await fetch(`/api/vessels/area-history?${params}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(body.detail ?? `Search failed: ${res.status}`);
      }

      const data: AreaVessel[] = await res.json();
      setResults(data);
      setHasSearched(true);
      // Auto-select all found vessels (up to 20 for playback)
      setSelectedMmsis(new Set(data.slice(0, 20).map((v) => v.mmsi)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setIsSearching(false);
    }
  }, [areaPolygon, startDate, endDate]);

  const toggleVessel = useCallback((mmsi: number) => {
    setSelectedMmsis((prev) => {
      const next = new Set(prev);
      if (next.has(mmsi)) {
        next.delete(mmsi);
      } else {
        next.add(mmsi);
      }
      return next;
    });
  }, []);

  const handleStartPlayback = useCallback(() => {
    if (!areaPolygon || selectedMmsis.size === 0) return;
    const start = new Date(startDate + ':00Z');
    const end = new Date(endDate + ':00Z');
    configureArea(areaPolygon, [...selectedMmsis], { start, end });
    activate();
  }, [areaPolygon, selectedMmsis, startDate, endDate, configureArea, activate]);

  const handleClose = useCallback(() => {
    cancelDrawing();
    setResults([]);
    setSelectedMmsis(new Set());
    setHasSearched(false);
    setError(null);
  }, [cancelDrawing]);

  // Only show when polygon is drawn but lookback is not yet active
  if (!areaPolygon || isDrawing || isActive) return null;

  const today = new Date().toISOString().slice(0, 16);

  return (
    <div
      className="absolute top-3 right-16 z-50 w-80 rounded-lg shadow-xl border border-slate-700/50 overflow-hidden"
      style={{ backgroundColor: 'rgba(10, 14, 23, 0.95)' }}
      data-testid="area-lookback-panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/50">
        <h3 className="text-xs font-semibold text-slate-300">Area Lookback</h3>
        <button
          onClick={handleClose}
          className="text-slate-500 hover:text-red-400 transition-colors"
          aria-label="Close area lookback"
          data-testid="area-lookback-close"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="p-3 space-y-3">
        {/* Date range */}
        <div className="flex gap-2">
          <div className="flex-1 min-w-0">
            <label className="text-[0.65rem] text-slate-500 block mb-1">Start</label>
            <input
              type="datetime-local"
              value={startDate}
              max={endDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-2 py-1 text-xs bg-[#1F2937] text-gray-300 border border-[#374151] rounded focus:border-blue-500 focus:outline-none"
              data-testid="area-lookback-start"
            />
          </div>
          <div className="flex-1 min-w-0">
            <label className="text-[0.65rem] text-slate-500 block mb-1">End</label>
            <input
              type="datetime-local"
              value={endDate}
              max={today}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full px-2 py-1 text-xs bg-[#1F2937] text-gray-300 border border-[#374151] rounded focus:border-blue-500 focus:outline-none"
              data-testid="area-lookback-end"
            />
          </div>
        </div>

        {/* Search button */}
        <button
          onClick={handleSearch}
          disabled={isSearching}
          className="w-full py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 disabled:cursor-wait text-white text-xs font-medium rounded transition-colors"
          data-testid="area-lookback-search"
        >
          {isSearching ? 'Searching...' : 'Search Area'}
        </button>

        {/* Error */}
        {error && (
          <p className="text-xs text-red-400" data-testid="area-lookback-error">
            {error}
          </p>
        )}

        {/* Results */}
        {hasSearched && !error && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[0.65rem] text-slate-500">
                {results.length} vessel{results.length !== 1 ? 's' : ''} found
              </span>
              {results.length > 0 && (
                <button
                  onClick={() =>
                    setSelectedMmsis((prev) =>
                      prev.size === results.length
                        ? new Set()
                        : new Set(results.map((v) => v.mmsi)),
                    )
                  }
                  className="text-[0.65rem] text-blue-400 hover:text-blue-300"
                >
                  {selectedMmsis.size === results.length ? 'Deselect all' : 'Select all'}
                </button>
              )}
            </div>

            {results.length > 0 && (
              <div className="max-h-48 overflow-y-auto space-y-0.5" data-testid="area-lookback-results">
                {results.map((v) => (
                  <label
                    key={v.mmsi}
                    className="flex items-center gap-2 px-2 py-1 rounded text-xs cursor-pointer hover:bg-slate-800/50"
                  >
                    <input
                      type="checkbox"
                      checked={selectedMmsis.has(v.mmsi)}
                      onChange={() => toggleVessel(v.mmsi)}
                      className="rounded border-slate-600"
                    />
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: RISK_COLORS[v.risk_tier] ?? '#888' }}
                    />
                    <span className="text-slate-300 truncate flex-1">
                      {v.ship_name ?? `MMSI ${v.mmsi}`}
                    </span>
                    <span className="text-slate-500 text-[0.6rem] shrink-0">
                      {v.position_count} pts
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Start playback */}
        {hasSearched && selectedMmsis.size > 0 && (
          <button
            onClick={handleStartPlayback}
            className="w-full py-1.5 bg-green-600 hover:bg-green-700 text-white text-xs font-medium rounded transition-colors"
            data-testid="area-lookback-start-playback"
          >
            Start Playback ({selectedMmsis.size} vessel{selectedMmsis.size !== 1 ? 's' : ''})
          </button>
        )}
      </div>
    </div>
  );
}
