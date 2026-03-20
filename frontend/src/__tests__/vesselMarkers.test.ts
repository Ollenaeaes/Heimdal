import { describe, it, expect, beforeEach } from 'vitest';
import type { VesselState } from '../types/vessel';

import { useVesselStore } from '../hooks/useVesselStore';
import { MARKER_STYLE, cogToRotation } from '../utils/vesselIcons';

// filterVessels now lives in Map/VesselLayer
import { filterVessels } from '../components/Map/VesselLayer';

const makeVessel = (overrides: Partial<VesselState> = {}): VesselState => ({
  mmsi: 123456789,
  lat: 60.35,
  lon: 28.67,
  sog: 12.5,
  cog: 180.0,
  heading: 179,
  riskTier: 'green',
  riskScore: 15,
  name: 'Nordic Carrier',
  timestamp: '2024-03-15T14:30:00Z',
  shipType: 70,
  ...overrides,
});

describe('MARKER_STYLE', () => {
  it('green tier has correct style', () => {
    expect(MARKER_STYLE.green).toEqual({ opacity: 0.7, opacityFar: 0.2, scale: 0.5 });
  });

  it('yellow tier has correct style', () => {
    expect(MARKER_STYLE.yellow).toEqual({ opacity: 0.8, opacityFar: 0.8, scale: 0.7 });
  });

  it('red tier has correct style', () => {
    expect(MARKER_STYLE.red).toEqual({ opacity: 1.0, opacityFar: 1.0, scale: 0.85 });
  });
});

describe('cogToRotation', () => {
  it('converts 0 degrees (north) to 0 radians', () => {
    expect(cogToRotation(0)).toBeCloseTo(0);
  });

  it('converts 90 degrees (east) to -PI/2 radians', () => {
    expect(cogToRotation(90)).toBeCloseTo(-Math.PI / 2);
  });

  it('converts 180 degrees (south) to -PI radians', () => {
    expect(cogToRotation(180)).toBeCloseTo(-Math.PI);
  });

  it('converts 270 degrees (west) to -3PI/2 radians', () => {
    expect(cogToRotation(270)).toBeCloseTo(-1.5 * Math.PI);
  });

  it('returns 0 for null COG', () => {
    expect(cogToRotation(null)).toBe(0);
  });
});

describe('filterVessels', () => {
  const emptyFilters = {
    riskTiers: new Set<string>(),
    shipTypes: [] as number[],
    activeSince: null as string | null,
    darkShipsOnly: false,
    showGfwEventTypes: [] as string[],
  };

  it('returns all vessels when no filters are active', () => {
    const vessels = new Map<number, VesselState>([
      [1, makeVessel({ mmsi: 1, riskTier: 'green' })],
      [2, makeVessel({ mmsi: 2, riskTier: 'yellow' })],
      [3, makeVessel({ mmsi: 3, riskTier: 'red' })],
    ]);

    const result = filterVessels(vessels, emptyFilters);
    expect(result).toHaveLength(3);
  });

  it('filters by risk tier', () => {
    const vessels = new Map<number, VesselState>([
      [1, makeVessel({ mmsi: 1, riskTier: 'green' })],
      [2, makeVessel({ mmsi: 2, riskTier: 'yellow' })],
      [3, makeVessel({ mmsi: 3, riskTier: 'red' })],
    ]);

    const result = filterVessels(vessels, {
      ...emptyFilters,
      riskTiers: new Set(['red', 'yellow']),
    });
    expect(result).toHaveLength(2);
    expect(result.map((v) => v.riskTier)).toEqual(
      expect.arrayContaining(['red', 'yellow']),
    );
    expect(result.map((v) => v.riskTier)).not.toContain('green');
  });

  it('filters by ship type', () => {
    const vessels = new Map<number, VesselState>([
      [1, makeVessel({ mmsi: 1, shipType: 70 })],
      [2, makeVessel({ mmsi: 2, shipType: 80 })],
      [3, makeVessel({ mmsi: 3, shipType: 70 })],
    ]);

    const result = filterVessels(vessels, {
      ...emptyFilters,
      shipTypes: [80],
    });
    expect(result).toHaveLength(1);
    expect(result[0].mmsi).toBe(2);
  });

  it('filters by activeSince timestamp', () => {
    const vessels = new Map<number, VesselState>([
      [1, makeVessel({ mmsi: 1, timestamp: '2024-03-15T10:00:00Z' })],
      [2, makeVessel({ mmsi: 2, timestamp: '2024-03-15T16:00:00Z' })],
    ]);

    const result = filterVessels(vessels, {
      ...emptyFilters,
      activeSince: '2024-03-15T12:00:00Z',
    });
    expect(result).toHaveLength(1);
    expect(result[0].mmsi).toBe(2);
  });

  it('combines multiple filters', () => {
    const vessels = new Map<number, VesselState>([
      [1, makeVessel({ mmsi: 1, riskTier: 'red', shipType: 70, timestamp: '2024-03-15T16:00:00Z' })],
      [2, makeVessel({ mmsi: 2, riskTier: 'red', shipType: 80, timestamp: '2024-03-15T16:00:00Z' })],
      [3, makeVessel({ mmsi: 3, riskTier: 'green', shipType: 70, timestamp: '2024-03-15T16:00:00Z' })],
      [4, makeVessel({ mmsi: 4, riskTier: 'red', shipType: 70, timestamp: '2024-03-15T08:00:00Z' })],
    ]);

    const result = filterVessels(vessels, {
      riskTiers: new Set(['red']),
      shipTypes: [70],
      activeSince: '2024-03-15T12:00:00Z',
    });
    expect(result).toHaveLength(1);
    expect(result[0].mmsi).toBe(1);
  });

  it('includes vessels with undefined shipType when shipType filter is active', () => {
    const vessels = new Map<number, VesselState>([
      [1, makeVessel({ mmsi: 1, shipType: undefined })],
      [2, makeVessel({ mmsi: 2, shipType: 80 })],
    ]);

    const result = filterVessels(vessels, {
      ...emptyFilters,
      shipTypes: [70],
    });
    // Vessel without shipType should pass through since we can't classify it
    expect(result).toHaveLength(1);
    expect(result[0].mmsi).toBe(1);
  });
});

describe('selectVessel integration', () => {
  beforeEach(() => {
    useVesselStore.setState({
      vessels: new Map(),
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
  });

  it('selectVessel sets the selected MMSI in the store', () => {
    useVesselStore.getState().selectVessel(123456789);
    expect(useVesselStore.getState().selectedMmsi).toBe(123456789);
  });

  it('selectVessel with null clears the selection', () => {
    useVesselStore.getState().selectVessel(123456789);
    useVesselStore.getState().selectVessel(null);
    expect(useVesselStore.getState().selectedMmsi).toBeNull();
  });
});
