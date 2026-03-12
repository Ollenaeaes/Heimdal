import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { VesselState } from '../../types/vessel';

const RISK_COLORS: Record<string, string> = {
  green: '#27AE60',
  yellow: '#D4820C',
  red: '#C0392B',
};

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

async function fetchSearchResults(term: string): Promise<SearchResult[]> {
  if (!term.trim()) return [];
  const res = await fetch(`/api/vessels?search=${encodeURIComponent(term)}&per_page=10`);
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  const data = await res.json();
  // API returns { data: VesselState[] } or VesselState[]
  const vessels: VesselState[] = Array.isArray(data) ? data : data.data ?? [];
  return vessels.map((v) => ({
    mmsi: v.mmsi,
    name: v.name,
    riskTier: v.riskTier,
    lat: v.lat,
    lon: v.lon,
  }));
}

export function SearchBar() {
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const selectVessel = useVesselStore((s) => s.selectVessel);

  const debouncedTerm = useDebounce(term, 300);

  const { data: results = [] } = useQuery({
    queryKey: ['vesselSearch', debouncedTerm],
    queryFn: () => fetchSearchResults(debouncedTerm),
    enabled: debouncedTerm.trim().length > 0,
    staleTime: 10_000,
  });

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

  const handleSelect = (result: SearchResult) => {
    selectVessel(result.mmsi);
    setTerm('');
    setOpen(false);
  };

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
        placeholder={placeholder}
        className="w-full px-3 py-2 rounded-lg bg-gray-800/80 text-white text-sm
                   placeholder-gray-400 border border-gray-700 focus:border-blue-500
                   focus:outline-none backdrop-blur-sm"
        aria-label="Search vessels"
      />
      {term.trim() && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">
          {searchType === 'mmsi' ? 'MMSI' : searchType === 'imo' ? 'IMO' : 'Name'}
        </span>
      )}

      {open && results.length > 0 && (
        <ul
          className="absolute top-full left-0 right-0 mt-1 rounded-lg bg-gray-800/95
                     border border-gray-700 shadow-lg backdrop-blur-sm max-h-60 overflow-y-auto z-50"
          data-testid="search-results"
        >
          {results.map((r) => (
            <li key={r.mmsi}>
              <button
                type="button"
                onClick={() => handleSelect(r)}
                className="w-full px-3 py-2 text-left text-sm text-white hover:bg-gray-700/60
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
