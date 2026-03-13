import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { VesselState } from '../types/vessel';

// Mock Cesium before imports
vi.mock('cesium', () => ({
  Cartesian3: {
    fromDegrees: vi.fn((lon: number, lat: number, alt?: number) => ({
      x: lon,
      y: lat,
      z: alt ?? 0,
    })),
    UNIT_Z: { x: 0, y: 0, z: 1 },
  },
  ConstantProperty: vi.fn((val: unknown) => ({ value: val })),
  CallbackProperty: vi.fn((cb: () => unknown) => ({ callback: cb })),
  NearFarScalar: vi.fn(
    (near: number, nearVal: number, far: number, farVal: number) => ({
      near,
      nearValue: nearVal,
      far,
      farValue: farVal,
    }),
  ),
  Ion: { defaultAccessToken: '' },
  MaterialProperty: {},
  Color: {
    fromCssColorString: vi.fn((css: string) => ({ css })),
  },
}));

vi.mock('resium', () => ({
  Entity: vi.fn(({ children }: { children?: unknown }) => children),
  BillboardGraphics: vi.fn(() => null),
  useCesium: vi.fn(() => ({ viewer: null })),
  Viewer: vi.fn(({ children }: { children?: unknown }) => children),
  CameraFlyTo: vi.fn(() => null),
}));

import { useVesselStore } from '../hooks/useVesselStore';
import { MARKER_STYLE, cogToRotation } from '../utils/vesselIcons';

// We test filterVessels directly since it's exported
import { filterVessels } from '../components/Globe/VesselMarkers';

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
  it('green tier has opacity 0.4 and scale 0.6', () => {
    expect(MARKER_STYLE.green).toEqual({ opacity: 0.4, scale: 0.6 });
  });

  it('yellow tier has opacity 0.9 and scale 0.8', () => {
    expect(MARKER_STYLE.yellow).toEqual({ opacity: 0.9, scale: 0.8 });
  });

  it('red tier has opacity 1.0 and scale 1.0', () => {
    expect(MARKER_STYLE.red).toEqual({ opacity: 1.0, scale: 1.0 });
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

describe('VesselMarkers component', () => {
  it('exports VesselMarkers as a function', async () => {
    const mod = await import('../components/Globe/VesselMarkers');
    expect(mod.VesselMarkers).toBeDefined();
    expect(typeof mod.VesselMarkers).toBe('function');
  });

  it('exports filterVessels utility', async () => {
    const mod = await import('../components/Globe/VesselMarkers');
    expect(mod.filterVessels).toBeDefined();
    expect(typeof mod.filterVessels).toBe('function');
  });
});
