import { describe, it, expect, beforeEach } from 'vitest';
import { useVesselStore, MAX_HISTORY_PER_VESSEL } from '../hooks/useVesselStore';
import type { VesselState } from '../types/vessel';
import { buildTrailColors, filterHistoryByAge } from '../components/Globe/TrackTrails';
import type { PositionHistoryEntry } from '../hooks/useVesselStore';

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

describe('Position history in useVesselStore', () => {
  beforeEach(() => {
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

  it('appends position history when updatePosition is called', () => {
    const vessel = makeVessel();
    useVesselStore.getState().updatePosition(vessel);

    const history = useVesselStore.getState().positionHistory.get(123456789);
    expect(history).toBeDefined();
    expect(history!.length).toBe(1);
    expect(history![0]).toEqual({
      lat: 60.35,
      lon: 28.67,
      timestamp: '2024-03-15T14:30:00Z',
    });
  });

  it('appends multiple positions for the same vessel', () => {
    useVesselStore.getState().updatePosition(makeVessel({ lat: 60.0, timestamp: '2024-03-15T14:00:00Z' }));
    useVesselStore.getState().updatePosition(makeVessel({ lat: 60.5, timestamp: '2024-03-15T14:15:00Z' }));
    useVesselStore.getState().updatePosition(makeVessel({ lat: 61.0, timestamp: '2024-03-15T14:30:00Z' }));

    const history = useVesselStore.getState().positionHistory.get(123456789);
    expect(history!.length).toBe(3);
    expect(history![0].lat).toBe(60.0);
    expect(history![1].lat).toBe(60.5);
    expect(history![2].lat).toBe(61.0);
  });

  it('caps history at MAX_HISTORY_PER_VESSEL', () => {
    // Fill beyond the cap
    for (let i = 0; i < MAX_HISTORY_PER_VESSEL + 50; i++) {
      useVesselStore.getState().updatePosition(
        makeVessel({
          lat: 60 + i * 0.001,
          timestamp: new Date(Date.UTC(2024, 2, 15, 14, 0, i)).toISOString(),
        }),
      );
    }

    const history = useVesselStore.getState().positionHistory.get(123456789);
    expect(history!.length).toBe(MAX_HISTORY_PER_VESSEL);
    // The oldest entries should have been dropped — the last entry is the most recent
    const lastEntry = history![history!.length - 1];
    expect(lastEntry.lat).toBeCloseTo(60 + (MAX_HISTORY_PER_VESSEL + 49) * 0.001, 5);
  });

  it('maintains separate history per vessel', () => {
    useVesselStore.getState().updatePosition(makeVessel({ mmsi: 111, lat: 60.0 }));
    useVesselStore.getState().updatePosition(makeVessel({ mmsi: 222, lat: 65.0 }));
    useVesselStore.getState().updatePosition(makeVessel({ mmsi: 111, lat: 60.5 }));

    const history111 = useVesselStore.getState().positionHistory.get(111);
    const history222 = useVesselStore.getState().positionHistory.get(222);
    expect(history111!.length).toBe(2);
    expect(history222!.length).toBe(1);
  });

  it('clearOldPositions prunes entries older than maxAgeMs', () => {
    const now = Date.now();
    // Add an old position (2 hours ago) and a recent one (5 minutes ago)
    useVesselStore.getState().updatePosition(
      makeVessel({ timestamp: new Date(now - 2 * 60 * 60 * 1000).toISOString() }),
    );
    useVesselStore.getState().updatePosition(
      makeVessel({ lat: 61.0, timestamp: new Date(now - 5 * 60 * 1000).toISOString() }),
    );

    // Prune anything older than 1 hour
    useVesselStore.getState().clearOldPositions(60 * 60 * 1000);

    const history = useVesselStore.getState().positionHistory.get(123456789);
    expect(history!.length).toBe(1);
    expect(history![0].lat).toBe(61.0);
  });

  it('clearOldPositions removes vessel key when all entries are old', () => {
    const now = Date.now();
    useVesselStore.getState().updatePosition(
      makeVessel({ timestamp: new Date(now - 3 * 60 * 60 * 1000).toISOString() }),
    );

    useVesselStore.getState().clearOldPositions(60 * 60 * 1000);

    const history = useVesselStore.getState().positionHistory;
    expect(history.has(123456789)).toBe(false);
  });

  it('updatePosition still correctly updates the vessels map', () => {
    // Ensure existing vessel store behavior is preserved
    const vessel = makeVessel();
    useVesselStore.getState().updatePosition(vessel);

    const state = useVesselStore.getState();
    expect(state.vessels.size).toBe(1);
    expect(state.vessels.get(123456789)).toEqual(vessel);
  });
});

describe('TrackTrails helpers', () => {
  describe('buildTrailColors', () => {
    it('returns colors matching the risk tier', () => {
      const greens = buildTrailColors('green', 5);
      expect(greens.length).toBe(5);
      // Last color (newest) should have full opacity
      expect(greens[4].alpha).toBeCloseTo(1.0);
      // First color (oldest) should be transparent
      expect(greens[0].alpha).toBeCloseTo(0.0);
    });

    it('returns correct colors for red tier', () => {
      const reds = buildTrailColors('red', 3);
      expect(reds.length).toBe(3);
      // Red channel should dominate (C0392B => r=192/255)
      expect(reds[2].red).toBeCloseTo(0xC0 / 255, 1);
    });

    it('handles single point with full opacity', () => {
      const colors = buildTrailColors('yellow', 1);
      expect(colors.length).toBe(1);
      expect(colors[0].alpha).toBeCloseTo(1.0);
    });
  });

  describe('filterHistoryByAge', () => {
    it('filters out entries older than maxAgeHours', () => {
      const now = new Date('2024-03-15T15:00:00Z').getTime();
      const entries: PositionHistoryEntry[] = [
        { lat: 60.0, lon: 28.0, timestamp: new Date(now - 2 * 3600000).toISOString() }, // 2h old
        { lat: 60.5, lon: 28.5, timestamp: new Date(now - 30 * 60000).toISOString() },  // 30min old
        { lat: 61.0, lon: 29.0, timestamp: new Date(now).toISOString() },                // newest
      ];

      const filtered = filterHistoryByAge(entries, 1);
      expect(filtered.length).toBe(2);
      expect(filtered[0].lat).toBe(60.5);
      expect(filtered[1].lat).toBe(61.0);
    });

    it('returns empty array for empty input', () => {
      expect(filterHistoryByAge([], 1)).toEqual([]);
    });

    it('returns all entries when none are older than maxAgeHours', () => {
      const now = new Date('2024-03-15T15:00:00Z').getTime();
      const entries: PositionHistoryEntry[] = [
        { lat: 60.0, lon: 28.0, timestamp: new Date(now - 10 * 60000).toISOString() },
        { lat: 60.5, lon: 28.5, timestamp: new Date(now).toISOString() },
      ];

      const filtered = filterHistoryByAge(entries, 1);
      expect(filtered.length).toBe(2);
    });
  });
});
