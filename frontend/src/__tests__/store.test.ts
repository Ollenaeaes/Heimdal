import { describe, it, expect, beforeEach } from 'vitest';
import { useVesselStore } from '../hooks/useVesselStore';
import type { VesselState } from '../types/vessel';

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
  ...overrides,
});

describe('useVesselStore', () => {
  beforeEach(() => {
    // Reset the store between tests
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
  });

  it('initializes with empty state', () => {
    const state = useVesselStore.getState();
    expect(state.vessels.size).toBe(0);
    expect(state.selectedMmsi).toBeNull();
    expect(state.filters.riskTiers.size).toBe(0);
    expect(state.filters.shipTypes).toEqual([]);
    expect(state.filters.bbox).toBeNull();
    expect(state.filters.activeSince).toBeNull();
  });

  it('updatePosition correctly adds a vessel', () => {
    const vessel = makeVessel();
    useVesselStore.getState().updatePosition(vessel);

    const state = useVesselStore.getState();
    expect(state.vessels.size).toBe(1);
    expect(state.vessels.get(123456789)).toEqual(vessel);
  });

  it('updatePosition correctly updates an existing vessel', () => {
    const vessel = makeVessel();
    useVesselStore.getState().updatePosition(vessel);

    const updated = makeVessel({ lat: 61.0, sog: 8.0, riskTier: 'yellow' });
    useVesselStore.getState().updatePosition(updated);

    const state = useVesselStore.getState();
    expect(state.vessels.size).toBe(1);
    expect(state.vessels.get(123456789)!.lat).toBe(61.0);
    expect(state.vessels.get(123456789)!.sog).toBe(8.0);
    expect(state.vessels.get(123456789)!.riskTier).toBe('yellow');
  });

  it('selectVessel sets selectedMmsi', () => {
    useVesselStore.getState().selectVessel(987654321);
    expect(useVesselStore.getState().selectedMmsi).toBe(987654321);

    useVesselStore.getState().selectVessel(null);
    expect(useVesselStore.getState().selectedMmsi).toBeNull();
  });

  it('setFilter merges partial filter updates', () => {
    useVesselStore.getState().setFilter({ shipTypes: [70, 80] });
    expect(useVesselStore.getState().filters.shipTypes).toEqual([70, 80]);
    // Other filters remain unchanged
    expect(useVesselStore.getState().filters.bbox).toBeNull();
  });
});
