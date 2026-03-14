import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useVesselStore } from '../../hooks/useVesselStore';
import { getCesiumViewer } from '../Globe/cesiumViewer';
import { Cartesian3 } from 'cesium';
import type { VesselState } from '../../types/vessel';
import { RISK_COLORS } from '../../utils/riskColors';

/**
 * Detect search type from the input term.
 * - 9 digits → MMSI
 * - 7 digits → IMO
 * - otherwise → name search
 */
export function detectSearchType(term: string): 'mmsi' | 'imo' | 'name' {
  const trimmed = term.trim();
  if (/^\d{9}$/.test(trimmed)) return 'mmsi';
  if (/^\d{7}$/.test(trimmed)) return 'imo';
  return 'name';
}

/** Custom hook for debouncing a string value. */
export function useDebounce(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

interface SearchResult {
  mmsi: number;
  name?: string;
  riskTier: VesselState['riskTier'];
  lat: number;
  lon: number;
}

const MAX_RESULTS = 10;

export function SearchBar() {
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const vessels = useVesselStore((s) => s.vessels);

  const debouncedTerm = useDebounce(term, 200);

  // Search the local vessel store
  const results: SearchResult[] = useMemo(() => {
    const q = debouncedTerm.trim().toLowerCase();
    if (!q) return [];

    const searchType = detectSearchType(debouncedTerm);
    const matches: SearchResult[] = [];

    // Direct MMSI lookup
    if (searchType === 'mmsi') {
      const mmsi = parseInt(q, 10);
      const v = vessels.get(mmsi);
      if (v) {
        matches.push({ mmsi: v.mmsi, name: v.name, riskTier: v.riskTier, lat: v.lat, lon: v.lon });
      }
      return matches;
    }

    for (const v of vessels.values()) {
      if (matches.length >= MAX_RESULTS) break;

      if (searchType === 'imo') {
        // IMO search — check if MMSI contains the term (rough heuristic)
        if (String(v.mmsi).includes(q)) {
          matches.push({ mmsi: v.mmsi, name: v.name, riskTier: v.riskTier, lat: v.lat, lon: v.lon });
        }
      } else {
        // Name search
        const name = v.name?.toLowerCase() ?? '';
        const mmsiStr = String(v.mmsi);
        if (name.includes(q) || mmsiStr.includes(q)) {
          matches.push({ mmsi: v.mmsi, name: v.name, riskTier: v.riskTier, lat: v.lat, lon: v.lon });
        }
      }
    }
    return matches;
  }, [debouncedTerm, vessels]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleSelect = useCallback(
    (result: SearchResult) => {
      selectVessel(result.mmsi);
      setTerm('');
      setOpen(false);

      // Pan the map to the vessel
      const viewer = getCesiumViewer();
      if (viewer) {
        viewer.camera.flyTo({
          destination: Cartesian3.fromDegrees(result.lon, result.lat, 50_000),
          duration: 1.5,
        });
      }
    },
    [selectVessel],
  );

  // Allow Enter to select the first (or only) result
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && results.length > 0) {
        e.preventDefault();
        handleSelect(results[0]);
      }
      if (e.key === 'Escape') {
        setOpen(false);
      }
    },
    [results, handleSelect],
  );

  const searchType = detectSearchType(term);
  const placeholder = 'Search vessels (name, MMSI, IMO)...';

  return (
    <div ref={wrapperRef} className="relative w-72" data-testid="search-bar">
      <input
        type="text"
        value={term}
        onChange={(e) => {
          setTerm(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className="w-full px-3 py-2 rounded bg-[#111827]/80 text-white text-[0.8rem]
                   placeholder-gray-400 border border-[#1F2937] focus:border-[#3B82F6]
                   focus:outline-none backdrop-blur-md font-[Inter,sans-serif]"
        aria-label="Search vessels"
      />
      {term.trim() && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">
          {searchType === 'mmsi' ? 'MMSI' : searchType === 'imo' ? 'IMO' : 'Name'}
        </span>
      )}

      {open && results.length > 0 && (
        <ul
          className="absolute top-full left-0 right-0 mt-1 rounded bg-[#111827]/95
                     border border-[#1F2937] shadow-lg backdrop-blur-md max-h-60 overflow-y-auto z-50"
          data-testid="search-results"
        >
          {results.map((r) => (
            <li key={r.mmsi}>
              <button
                type="button"
                onClick={() => handleSelect(r)}
                className="w-full px-3 py-2 text-left text-[0.8rem] text-white hover:bg-[#1F2937]/60
                           flex items-center gap-2 transition-colors"
                data-testid="search-result-item"
              >
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: RISK_COLORS[r.riskTier] ?? '#888' }}
                />
                <span className="truncate">{r.name ?? `MMSI ${r.mmsi}`}</span>
                <span className="ml-auto text-xs text-gray-400">{r.mmsi}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
