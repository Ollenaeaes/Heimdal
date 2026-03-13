import { describe, it, expect, beforeEach } from 'vitest';
import {
  useWatchlistStore,
  formatRiskChangeNotification,
  formatAnomalyNotification,
  getVesselName,
} from '../hooks/useWatchlist';
import type { AlertEvent } from '../hooks/useWatchlist';
import { useVesselStore } from '../hooks/useVesselStore';
import type { VesselState } from '../types/vessel';

const makeVessel = (overrides: Partial<VesselState> = {}): VesselState => ({
  mmsi: 211000001,
  lat: 54.32,
  lon: 10.15,
  sog: 11.2,
  cog: 270,
  heading: 268,
  riskTier: 'green',
  riskScore: 12,
  name: 'Baltic Explorer',
  timestamp: '2025-06-10T08:30:00Z',
  ...overrides,
});

describe('useWatchlistStore', () => {
  beforeEach(() => {
    useWatchlistStore.setState({ watchedMmsis: new Set() });
  });

  it('initializes with empty set', () => {
    const state = useWatchlistStore.getState();
    expect(state.watchedMmsis.size).toBe(0);
  });

  it('setWatchlist replaces the entire set', () => {
    useWatchlistStore.getState().setWatchlist([111111111, 222222222, 333333333]);
    const state = useWatchlistStore.getState();
    expect(state.watchedMmsis.size).toBe(3);
    expect(state.watchedMmsis.has(111111111)).toBe(true);
    expect(state.watchedMmsis.has(222222222)).toBe(true);
    expect(state.watchedMmsis.has(333333333)).toBe(true);
  });

  it('setWatchlist with empty array clears the set', () => {
    useWatchlistStore.getState().setWatchlist([111111111]);
    useWatchlistStore.getState().setWatchlist([]);
    expect(useWatchlistStore.getState().watchedMmsis.size).toBe(0);
  });

  it('addToWatchlist adds a single MMSI', () => {
    useWatchlistStore.getState().addToWatchlist(444444444);
    expect(useWatchlistStore.getState().watchedMmsis.has(444444444)).toBe(true);
    expect(useWatchlistStore.getState().watchedMmsis.size).toBe(1);
  });

  it('addToWatchlist is idempotent', () => {
    useWatchlistStore.getState().addToWatchlist(444444444);
    useWatchlistStore.getState().addToWatchlist(444444444);
    expect(useWatchlistStore.getState().watchedMmsis.size).toBe(1);
  });

  it('removeFromWatchlist removes a single MMSI', () => {
    useWatchlistStore.getState().setWatchlist([111111111, 222222222]);
    useWatchlistStore.getState().removeFromWatchlist(111111111);
    const state = useWatchlistStore.getState();
    expect(state.watchedMmsis.size).toBe(1);
    expect(state.watchedMmsis.has(111111111)).toBe(false);
    expect(state.watchedMmsis.has(222222222)).toBe(true);
  });

  it('removeFromWatchlist is safe for non-existent MMSI', () => {
    useWatchlistStore.getState().setWatchlist([111111111]);
    useWatchlistStore.getState().removeFromWatchlist(999999999);
    expect(useWatchlistStore.getState().watchedMmsis.size).toBe(1);
  });

  it('isWatched returns true for watched MMSIs', () => {
    useWatchlistStore.getState().setWatchlist([111111111, 222222222]);
    expect(useWatchlistStore.getState().isWatched(111111111)).toBe(true);
    expect(useWatchlistStore.getState().isWatched(222222222)).toBe(true);
  });

  it('isWatched returns false for unwatched MMSIs', () => {
    useWatchlistStore.getState().setWatchlist([111111111]);
    expect(useWatchlistStore.getState().isWatched(999999999)).toBe(false);
  });
});

describe('optimistic updates', () => {
  beforeEach(() => {
    useWatchlistStore.setState({ watchedMmsis: new Set() });
  });

  it('add updates set immediately', () => {
    const store = useWatchlistStore.getState();
    store.addToWatchlist(555555555);
    // The set is updated synchronously — this simulates what the mutation onMutate does
    expect(useWatchlistStore.getState().watchedMmsis.has(555555555)).toBe(true);
  });

  it('remove updates set immediately', () => {
    useWatchlistStore.getState().setWatchlist([555555555, 666666666]);
    useWatchlistStore.getState().removeFromWatchlist(555555555);
    expect(useWatchlistStore.getState().watchedMmsis.has(555555555)).toBe(false);
    // Other entries unaffected
    expect(useWatchlistStore.getState().watchedMmsis.has(666666666)).toBe(true);
  });
});

describe('alert filtering', () => {
  beforeEach(() => {
    useWatchlistStore.setState({ watchedMmsis: new Set() });
  });

  it('only watchlisted MMSIs should trigger notifications', () => {
    useWatchlistStore.getState().setWatchlist([111111111, 222222222]);

    // Watched MMSI — should trigger
    expect(useWatchlistStore.getState().isWatched(111111111)).toBe(true);
    // Not watched — should not trigger
    expect(useWatchlistStore.getState().isWatched(999999999)).toBe(false);
  });

  it('non-watchlisted MMSIs are ignored', () => {
    useWatchlistStore.getState().setWatchlist([111111111]);

    const unwatchedMmsis = [222222222, 333333333, 444444444];
    for (const mmsi of unwatchedMmsis) {
      expect(useWatchlistStore.getState().isWatched(mmsi)).toBe(false);
    }
  });
});

describe('notification message formatting', () => {
  it('formats risk_change notification correctly', () => {
    const event: AlertEvent = {
      type: 'risk_change',
      mmsi: 211000001,
      old_tier: 'green',
      new_tier: 'red',
      score: 85,
      trigger_rule: 'dark_activity',
      timestamp: '2025-06-10T09:00:00Z',
    };

    const result = formatRiskChangeNotification('Baltic Explorer', event);
    expect(result.title).toBe('Risk Change: Baltic Explorer');
    expect(result.body).toBe('green → red (dark_activity)');
  });

  it('formats anomaly notification correctly', () => {
    const event: AlertEvent = {
      type: 'anomaly',
      mmsi: 211000001,
      rule_id: 'AIS_GAP',
      severity: 'high',
      points: 30,
      details: 'AIS signal lost for 6 hours',
      timestamp: '2025-06-10T09:15:00Z',
    };

    const result = formatAnomalyNotification('Baltic Explorer', event);
    expect(result.title).toBe('New Anomaly: Baltic Explorer');
    expect(result.body).toBe('AIS_GAP (high)');
  });

  it('handles missing vessel name in risk_change', () => {
    const event: AlertEvent = {
      type: 'risk_change',
      mmsi: 999999999,
      old_tier: 'yellow',
      new_tier: 'red',
      trigger_rule: 'sanctions_proximity',
      timestamp: '2025-06-10T10:00:00Z',
    };

    const result = formatRiskChangeNotification('MMSI 999999999', event);
    expect(result.title).toBe('Risk Change: MMSI 999999999');
  });

  it('handles missing vessel name in anomaly', () => {
    const event: AlertEvent = {
      type: 'anomaly',
      mmsi: 888888888,
      rule_id: 'SPEED_ANOMALY',
      severity: 'medium',
      timestamp: '2025-06-10T10:30:00Z',
    };

    const result = formatAnomalyNotification('MMSI 888888888', event);
    expect(result.title).toBe('New Anomaly: MMSI 888888888');
  });
});

describe('vessel name lookup', () => {
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

  it('returns vessel name when available', () => {
    const vessel = makeVessel({ mmsi: 211000001, name: 'Baltic Explorer' });
    useVesselStore.getState().updatePosition(vessel);

    const name = getVesselName(211000001);
    expect(name).toBe('Baltic Explorer');
  });

  it('falls back to MMSI when vessel not in store', () => {
    const name = getVesselName(999999999);
    expect(name).toBe('MMSI 999999999');
  });

  it('falls back to MMSI when vessel has no name', () => {
    const vessel = makeVessel({ mmsi: 211000002, name: undefined });
    useVesselStore.getState().updatePosition(vessel);

    const name = getVesselName(211000002);
    expect(name).toBe('MMSI 211000002');
  });
});
