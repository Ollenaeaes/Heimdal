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

const MAX_DAYS = 30;

export function AreaLookbackPanel() {
  const areaPolygon = useLookbackStore((s) => s.areaPolygon);
  const isActive = useLookbackStore((s) => s.isActive);
  const isDrawing = useLookbackStore((s) => s.isDrawing);
  const configureArea = useLookbackStore((s) => s.configureArea);
  const activate = useLookbackStore((s) => s.activate);
  const cancelDrawing = useLookbackStore((s) => s.cancelDrawing);

  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<AreaVessel[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const today = new Date().toISOString().slice(0, 10);
  const minDate = (() => {
    const d = new Date(endDate);
    d.setDate(d.getDate() - MAX_DAYS);
    return d.toISOString().slice(0, 10);
  })();

  const handleSearch = useCallback(async () => {
    if (!areaPolygon || areaPolygon.length < 3) return;

    setLoading(true);
    setError(null);
    setWarning(null);

    try {
      const start = new Date(startDate + 'T00:00:00Z');
      const end = new Date(endDate + 'T23:59:59Z');
      const polygonParam = JSON.stringify(areaPolygon);

      const params = new URLSearchParams({
        polygon: polygonParam,
        start: start.toISOString(),
        end: end.toISOString(),
      });

      const res = await fetch(`/api/vessels/area-history?${params}`);
      if (!res.ok) throw new Error(`Search failed: ${res.status}`);

      const data: AreaVessel[] = await res.json();

      if (data.length === 0) {
        setError('No vessels found in this area during the selected time range');
        setResults(null);
        return;
      }

      if (data.length >= 50) {
        setWarning(
          `${data.length}+ vessels found — showing top 50 by activity. Narrow the area or time range for better results.`,
        );
      }

      setResults(data);
      setSelected(new Set(data.map((v) => v.mmsi)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }, [areaPolygon, startDate, endDate]);

  const handleStartPlayback = useCallback(() => {
    if (!areaPolygon || selected.size === 0) return;

    const start = new Date(startDate + 'T00:00:00Z');
    const end = new Date(endDate + 'T23:59:59Z');

    configureArea(areaPolygon, [...selected], { start, end });
    activate();
    setResults(null);
  }, [areaPolygon, selected, startDate, endDate, configureArea, activate]);

  const handleCancel = useCallback(() => {
    cancelDrawing();
    setResults(null);
    setSelected(new Set());
  }, [cancelDrawing]);

  const toggleVessel = useCallback((mmsi: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(mmsi)) {
        next.delete(mmsi);
      } else {
        next.add(mmsi);
      }
      return next;
    });
  }, []);

  // Only show when polygon is drawn but playback hasn't started
  if (!areaPolygon || isActive || isDrawing) return null;

  return (
    <div
      className="fixed bottom-20 left-1/2 -translate-x-1/2 w-[380px] bg-[#111827]/95 backdrop-blur-md border border-[#1F2937] rounded-lg shadow-xl z-50"
      data-testid="area-lookback-panel"
    >
      <div className="px-4 py-3 border-b border-[#1F2937] flex items-center justify-between">
        <span className="text-sm text-gray-300 font-medium">Area Lookback</span>
        <button
          onClick={handleCancel}
          className="text-gray-400 hover:text-white text-xs"
          data-testid="area-cancel"
        >
          ✕
        </button>
      </div>

      <div className="px-4 py-3 space-y-3">
        {!results ? (
          <>
            {/* Date range */}
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-xs text-gray-500 block mb-1">Start</label>
                <input
                  type="date"
                  value={startDate}
                  min={minDate}
                  max={endDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-2 py-1 text-xs bg-[#1F2937] text-gray-300 border border-[#374151] rounded focus:border-[#3B82F6] focus:outline-none"
                  data-testid="area-start-date"
                />
              </div>
              <div className="flex-1">
                <label className="text-xs text-gray-500 block mb-1">End</label>
                <input
                  type="date"
                  value={endDate}
                  max={today}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full px-2 py-1 text-xs bg-[#1F2937] text-gray-300 border border-[#374151] rounded focus:border-[#3B82F6] focus:outline-none"
                  data-testid="area-end-date"
                />
              </div>
            </div>

            <button
              onClick={handleSearch}
              disabled={loading}
              className="w-full py-2 bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-50 text-white text-xs font-medium rounded transition-colors flex items-center justify-center gap-2"
              data-testid="area-search"
            >
              {loading && (
                <span className="animate-spin inline-block w-3 h-3 border border-white border-t-transparent rounded-full" />
              )}
              {loading ? 'Searching...' : 'Search'}
            </button>
          </>
        ) : (
          <>
            {/* Warning */}
            {warning && (
              <div className="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-1 rounded">
                {warning}
              </div>
            )}

            {/* Vessel results */}
            <div className="max-h-48 overflow-y-auto space-y-1" data-testid="area-results">
              {results.map((v) => (
                <label
                  key={v.mmsi}
                  className="flex items-center gap-2 px-2 py-1 bg-[#1F2937] rounded text-xs cursor-pointer hover:bg-[#374151]"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(v.mmsi)}
                    onChange={() => toggleVessel(v.mmsi)}
                    className="rounded border-[#374151]"
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full shrink-0"
                    style={{
                      backgroundColor: RISK_COLORS[v.risk_tier as keyof typeof RISK_COLORS] ?? '#888',
                    }}
                  />
                  <span className="text-gray-300 truncate flex-1">
                    {v.ship_name ?? `MMSI ${v.mmsi}`}
                  </span>
                  <span className="text-gray-500 shrink-0">
                    {v.position_count} pts
                  </span>
                </label>
              ))}
            </div>

            {/* Action buttons */}
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setResults(null);
                  setSelected(new Set());
                }}
                className="flex-1 py-1.5 bg-[#1F2937] hover:bg-[#374151] text-gray-300 text-xs rounded transition-colors"
              >
                Back
              </button>
              <button
                onClick={handleStartPlayback}
                disabled={selected.size === 0}
                className="flex-1 py-1.5 bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-50 text-white text-xs font-medium rounded transition-colors"
                data-testid="area-start-playback"
              >
                Start Playback ({selected.size})
              </button>
            </div>
          </>
        )}

        {error && (
          <div className="text-xs text-red-400" data-testid="area-error">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
