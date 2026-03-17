import { useState, useMemo, useCallback } from 'react';
import { useVesselStore } from '../../hooks/useVesselStore';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { CollapsibleSection } from './CollapsibleSection';
import { RISK_COLORS } from '../../utils/riskColors';
import type { VesselState } from '../../types/vessel';

const MAX_VESSELS = 5;
const MAX_DAYS = 30;

interface LookbackSectionProps {
  mmsi: number;
}

export function LookbackSection({ mmsi }: LookbackSectionProps) {
  const isActive = useLookbackStore((s) => s.isActive);
  const configure = useLookbackStore((s) => s.configure);
  const activate = useLookbackStore((s) => s.activate);

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedMmsis, setSelectedMmsis] = useState<number[]>([mmsi]);
  const [showNetwork, setShowNetwork] = useState(false);
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));

  const vessels = useVesselStore((s) => s.vessels);

  // Search results from vessel store
  const searchResults = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    if (!q) return [];
    const results: VesselState[] = [];
    for (const v of vessels.values()) {
      if (results.length >= 8) break;
      if (selectedMmsis.includes(v.mmsi)) continue;
      const name = v.name?.toLowerCase() ?? '';
      const mmsiStr = String(v.mmsi);
      if (name.includes(q) || mmsiStr.includes(q)) {
        results.push(v);
      }
    }
    return results;
  }, [searchTerm, vessels, selectedMmsis]);

  const addVessel = useCallback(
    (vesselMmsi: number) => {
      if (selectedMmsis.length >= MAX_VESSELS) return;
      if (selectedMmsis.includes(vesselMmsi)) return;
      setSelectedMmsis((prev) => [...prev, vesselMmsi]);
      setSearchTerm('');
    },
    [selectedMmsis],
  );

  const removeVessel = useCallback(
    (vesselMmsi: number) => {
      if (vesselMmsi === mmsi) return; // Can't remove the primary vessel
      setSelectedMmsis((prev) => prev.filter((m) => m !== vesselMmsi));
    },
    [mmsi],
  );

  const handleStartPlayback = useCallback(() => {
    const start = new Date(startDate + 'T00:00:00Z');
    const end = new Date(endDate + 'T23:59:59Z');

    // Clamp to max 30 days
    const minStart = new Date(end);
    minStart.setDate(minStart.getDate() - MAX_DAYS);
    const clampedStart = start < minStart ? minStart : start;

    configure({
      vessels: selectedMmsis,
      dateRange: { start: clampedStart, end },
      showNetwork,
    });
    activate();
  }, [startDate, endDate, selectedMmsis, showNetwork, configure, activate]);

  // Compute clamped min date (30 days before endDate)
  const minDate = useMemo(() => {
    const d = new Date(endDate);
    d.setDate(d.getDate() - MAX_DAYS);
    return d.toISOString().slice(0, 10);
  }, [endDate]);

  const today = new Date().toISOString().slice(0, 10);

  if (isActive) return null; // Don't show config when active — timeline bar takes over

  return (
    <CollapsibleSection title="Lookback" testId="lookback-section">
      <div className="space-y-3">
          {/* Date range picker */}
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
                data-testid="lookback-start-date"
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
                data-testid="lookback-end-date"
              />
            </div>
          </div>

          {/* Vessel search */}
          <div>
            <label className="text-xs text-gray-500 block mb-1">
              Add Vessels ({selectedMmsis.length}/{MAX_VESSELS})
            </label>
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              disabled={selectedMmsis.length >= MAX_VESSELS}
              placeholder={
                selectedMmsis.length >= MAX_VESSELS
                  ? 'Max 5 vessels'
                  : 'Search by name or MMSI...'
              }
              className="w-full px-2 py-1 text-xs bg-[#1F2937] text-gray-300 border border-[#374151] rounded focus:border-[#3B82F6] focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="lookback-vessel-search"
            />

            {/* Search results dropdown */}
            {searchResults.length > 0 && (
              <div className="mt-1 bg-[#1F2937] border border-[#374151] rounded max-h-32 overflow-y-auto">
                {searchResults.map((v) => (
                  <button
                    key={v.mmsi}
                    onClick={() => addVessel(v.mmsi)}
                    className="w-full px-2 py-1 text-left text-xs text-gray-300 hover:bg-[#374151] flex items-center gap-1"
                    data-testid="lookback-search-result"
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: RISK_COLORS[v.riskTier] ?? '#888' }}
                    />
                    <span className="truncate">{v.name ?? `MMSI ${v.mmsi}`}</span>
                    <span className="ml-auto text-gray-500">{v.mmsi}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Selected vessels list */}
          <div className="space-y-1" data-testid="lookback-vessel-list">
            {selectedMmsis.map((m) => {
              const v = vessels.get(m);
              return (
                <div
                  key={m}
                  className="flex items-center justify-between px-2 py-1 bg-[#1F2937] rounded text-xs"
                >
                  <div className="flex items-center gap-1">
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: RISK_COLORS[v?.riskTier ?? 'green'] ?? '#888' }}
                    />
                    <span className="text-gray-300 truncate">
                      {v?.name ?? `MMSI ${m}`}
                    </span>
                    {m === mmsi && (
                      <span className="text-gray-500 text-[0.65rem]">(primary)</span>
                    )}
                  </div>
                  {m !== mmsi && (
                    <button
                      onClick={() => removeVessel(m)}
                      className="text-gray-500 hover:text-red-400 ml-1"
                      aria-label={`Remove vessel ${m}`}
                      data-testid={`lookback-remove-${m}`}
                    >
                      ✕
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {/* Show network toggle */}
          <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={showNetwork}
              onChange={(e) => setShowNetwork(e.target.checked)}
              className="rounded border-[#374151]"
              data-testid="lookback-show-network"
            />
            Show network connections
          </label>

          {/* Start playback button */}
          <button
            onClick={handleStartPlayback}
            className="w-full py-2 bg-[#3B82F6] hover:bg-[#2563EB] text-white text-xs font-medium rounded transition-colors"
            data-testid="lookback-start"
          >
            Start Playback
          </button>
        </div>
    </CollapsibleSection>
  );
}
