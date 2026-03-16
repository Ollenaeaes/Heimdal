import { describe, it, expect, beforeEach } from 'vitest';
import { useVesselStore } from '../hooks/useVesselStore';
import { detectSearchType, useDebounce } from '../components/Controls/SearchBar';
import { computeTierCounts } from '../components/Controls/RiskFilter';

function resetStore() {
  useVesselStore.setState({
    vessels: new Map(),
    positionHistory: new Map(),
    selectedMmsi: null,
    filters: {
      riskTiers: new Set(),
      shipTypes: [],
      bbox: null,
      activeSince: null,
      darkShipsOnly: false,
      showGfwEventTypes: [],
    },
  });
}

// ─── Story 1: Search Bar ────────────────────────────────────────────

describe('SearchBar — detectSearchType', () => {
  it('detects 9-digit number as MMSI', () => {
    expect(detectSearchType('123456789')).toBe('mmsi');
  });

  it('detects 7-digit number as IMO', () => {
    expect(detectSearchType('1234567')).toBe('imo');
  });

  it('detects text as name search', () => {
    expect(detectSearchType('Nordic Carrier')).toBe('name');
  });

  it('detects partial numbers as name search', () => {
    expect(detectSearchType('12345')).toBe('name');
  });

  it('handles whitespace-padded input', () => {
    expect(detectSearchType('  123456789  ')).toBe('mmsi');
    expect(detectSearchType('  1234567  ')).toBe('imo');
  });

  it('treats 10-digit number as name (not MMSI)', () => {
    expect(detectSearchType('1234567890')).toBe('name');
  });
});

describe('SearchBar — useDebounce export exists', () => {
  it('useDebounce is exported as a function', () => {
    expect(typeof useDebounce).toBe('function');
  });
});

describe('SearchBar — clicking result sets selectedMmsi', () => {
  beforeEach(resetStore);

  it('selectVessel sets selectedMmsi when called (simulating result click)', () => {
    const { selectVessel } = useVesselStore.getState();
    selectVessel(987654321);
    expect(useVesselStore.getState().selectedMmsi).toBe(987654321);
  });
});

// ─── Story 2: Risk Tier Filter ──────────────────────────────────────

describe('RiskFilter — computeTierCounts', () => {
  it('counts vessels per risk tier', () => {
    const vessels = new Map<number, { riskTier: string }>([
      [1, { riskTier: 'green' }],
      [2, { riskTier: 'green' }],
      [3, { riskTier: 'yellow' }],
      [4, { riskTier: 'red' }],
      [5, { riskTier: 'red' }],
      [6, { riskTier: 'red' }],
    ]);
    const counts = computeTierCounts(vessels);
    expect(counts).toEqual({ green: 2, yellow: 1, red: 3, blacklisted: 0 });
  });

  it('returns zeroes for empty vessel map', () => {
    const counts = computeTierCounts(new Map());
    expect(counts).toEqual({ green: 0, yellow: 0, red: 0, blacklisted: 0 });
  });
});

describe('RiskFilter — toggling updates store', () => {
  beforeEach(resetStore);

  it('toggling a tier adds it to riskTiers filter', () => {
    const { setFilter } = useVesselStore.getState();
    const next = new Set(['red']);
    setFilter({ riskTiers: next });
    expect(useVesselStore.getState().filters.riskTiers).toEqual(new Set(['red']));
  });

  it('toggling a tier off removes it from riskTiers filter', () => {
    // Start with red and yellow active
    useVesselStore.getState().setFilter({ riskTiers: new Set(['red', 'yellow']) });
    // Toggle yellow off
    const current = useVesselStore.getState().filters.riskTiers;
    const next = new Set(current);
    next.delete('yellow');
    useVesselStore.getState().setFilter({ riskTiers: next });

    expect(useVesselStore.getState().filters.riskTiers).toEqual(new Set(['red']));
  });

  it('empty riskTiers means no filter (all visible)', () => {
    const { filters } = useVesselStore.getState();
    expect(filters.riskTiers.size).toBe(0);
  });
});

// ─── Story 3: Vessel Type Filter ────────────────────────────────────

describe('TypeFilter — store integration', () => {
  beforeEach(resetStore);

  it('selecting "Tankers" sets shipTypes to codes 80-89', () => {
    const expected = [80, 81, 82, 83, 84, 85, 86, 87, 88, 89];
    useVesselStore.getState().setFilter({ shipTypes: expected });
    expect(useVesselStore.getState().filters.shipTypes).toEqual(expected);
  });

  it('selecting "All Types" clears shipTypes filter', () => {
    // Set some types first
    useVesselStore.getState().setFilter({ shipTypes: [70, 71, 72] });
    expect(useVesselStore.getState().filters.shipTypes.length).toBe(3);

    // Clear (All Types)
    useVesselStore.getState().setFilter({ shipTypes: [] });
    expect(useVesselStore.getState().filters.shipTypes).toEqual([]);
  });

  it('selecting "Cargo" sets shipTypes to codes 70-79', () => {
    const expected = [70, 71, 72, 73, 74, 75, 76, 77, 78, 79];
    useVesselStore.getState().setFilter({ shipTypes: expected });
    expect(useVesselStore.getState().filters.shipTypes).toEqual(expected);
  });

  it('selecting "Passenger" sets shipTypes to codes 60-69', () => {
    const expected = [60, 61, 62, 63, 64, 65, 66, 67, 68, 69];
    useVesselStore.getState().setFilter({ shipTypes: expected });
    expect(useVesselStore.getState().filters.shipTypes).toEqual(expected);
  });

  it('setFilter does not overwrite other filter fields', () => {
    useVesselStore.getState().setFilter({ riskTiers: new Set(['red']) });
    useVesselStore.getState().setFilter({ shipTypes: [80, 81] });

    const filters = useVesselStore.getState().filters;
    expect(filters.riskTiers).toEqual(new Set(['red']));
    expect(filters.shipTypes).toEqual([80, 81]);
  });
});
