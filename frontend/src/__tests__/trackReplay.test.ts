import { describe, it, expect } from 'vitest';
import { detectAisGaps } from '../hooks/useTrackReplay';
import type { TrackPoint } from '../types/api';

// ─── Story 2: Track Replay ─────────────────────────────────────────

function makeTrackPoint(
  timestamp: string,
  lat: number,
  lon: number,
  sog: number | null = 12.5,
  cog: number | null = 180,
  heading: number | null = 178
): TrackPoint {
  return { timestamp, lat, lon, sog, cog, heading };
}

describe('detectAisGaps', () => {
  it('detects no gaps when points are closely spaced', () => {
    const track: TrackPoint[] = [
      makeTrackPoint('2026-03-10T12:00:00Z', 68.0, 15.0),
      makeTrackPoint('2026-03-10T13:00:00Z', 68.1, 15.1),
      makeTrackPoint('2026-03-10T14:00:00Z', 68.2, 15.2),
      makeTrackPoint('2026-03-10T15:00:00Z', 68.3, 15.3),
    ];
    const gaps = detectAisGaps(track);
    expect(gaps).toHaveLength(0);
  });

  it('detects a gap of 8 hours', () => {
    const track: TrackPoint[] = [
      makeTrackPoint('2026-03-10T12:00:00Z', 68.0, 15.0),
      makeTrackPoint('2026-03-10T13:00:00Z', 68.1, 15.1),
      makeTrackPoint('2026-03-10T21:00:00Z', 68.5, 15.5), // 8h gap
      makeTrackPoint('2026-03-10T22:00:00Z', 68.6, 15.6),
    ];
    const gaps = detectAisGaps(track);
    expect(gaps).toHaveLength(1);
    expect(gaps[0].startIndex).toBe(1);
    expect(gaps[0].endIndex).toBe(2);
    expect(gaps[0].gapHours).toBe(8);
  });

  it('detects multiple gaps', () => {
    const track: TrackPoint[] = [
      makeTrackPoint('2026-03-10T00:00:00Z', 68.0, 15.0),
      makeTrackPoint('2026-03-10T08:00:00Z', 68.1, 15.1), // 8h gap
      makeTrackPoint('2026-03-10T09:00:00Z', 68.2, 15.2),
      makeTrackPoint('2026-03-10T22:00:00Z', 68.3, 15.3), // 13h gap
      makeTrackPoint('2026-03-10T23:00:00Z', 68.4, 15.4),
    ];
    const gaps = detectAisGaps(track);
    expect(gaps).toHaveLength(2);
    expect(gaps[0].gapHours).toBe(8);
    expect(gaps[1].gapHours).toBe(13);
  });

  it('returns empty array for empty track', () => {
    expect(detectAisGaps([])).toHaveLength(0);
  });

  it('returns empty array for single point track', () => {
    const track = [makeTrackPoint('2026-03-10T12:00:00Z', 68.0, 15.0)];
    expect(detectAisGaps(track)).toHaveLength(0);
  });

  it('does not flag 5h gap (below 6h threshold)', () => {
    const track: TrackPoint[] = [
      makeTrackPoint('2026-03-10T12:00:00Z', 68.0, 15.0),
      makeTrackPoint('2026-03-10T17:00:00Z', 68.1, 15.1), // 5h — below threshold
    ];
    expect(detectAisGaps(track)).toHaveLength(0);
  });

  it('flags exactly 6h gap (at threshold)', () => {
    const track: TrackPoint[] = [
      makeTrackPoint('2026-03-10T12:00:00Z', 68.0, 15.0),
      makeTrackPoint('2026-03-10T18:00:00Z', 68.1, 15.1), // 6h — at threshold
    ];
    expect(detectAisGaps(track)).toHaveLength(1);
  });

  it('gap segment contains correct timestamps', () => {
    const track: TrackPoint[] = [
      makeTrackPoint('2026-03-10T10:00:00Z', 68.0, 15.0),
      makeTrackPoint('2026-03-10T20:00:00Z', 68.5, 15.5), // 10h gap
    ];
    const gaps = detectAisGaps(track);
    expect(gaps[0].startTime).toBe('2026-03-10T10:00:00Z');
    expect(gaps[0].endTime).toBe('2026-03-10T20:00:00Z');
  });
});

describe('TrackReplay component exports', () => {
  it('exports TrackReplay component', async () => {
    const mod = await import('../components/VesselPanel/TrackReplay');
    expect(mod.TrackReplay).toBeDefined();
    expect(typeof mod.TrackReplay).toBe('function');
  });
});

describe('useTrackReplay hook exports', () => {
  it('exports useTrackReplay hook', async () => {
    const mod = await import('../hooks/useTrackReplay');
    expect(mod.useTrackReplay).toBeDefined();
    expect(typeof mod.useTrackReplay).toBe('function');
  });

  it('exports detectAisGaps function', async () => {
    const mod = await import('../hooks/useTrackReplay');
    expect(mod.detectAisGaps).toBeDefined();
    expect(typeof mod.detectAisGaps).toBe('function');
  });
});

describe('ReplayOverlay component exports', () => {
  it('exports ReplayOverlay component', async () => {
    const mod = await import('../components/Globe/ReplayOverlay');
    expect(mod.ReplayOverlay).toBeDefined();
    expect(typeof mod.ReplayOverlay).toBe('function');
  });
});

describe('ReplayStore exports', () => {
  it('exports useReplayStore', async () => {
    const mod = await import('../hooks/useReplayStore');
    expect(mod.useReplayStore).toBeDefined();
    expect(typeof mod.useReplayStore).toBe('function');
  });

  it('replay store defaults to inactive', async () => {
    const { useReplayStore } = await import('../hooks/useReplayStore');
    const state = useReplayStore.getState();
    expect(state.isActive).toBe(false);
    expect(state.track).toBeNull();
    expect(state.currentIndex).toBe(0);
    expect(state.aisGaps).toEqual([]);
  });

  it('setReplayState updates the store', async () => {
    const { useReplayStore } = await import('../hooks/useReplayStore');
    const mockTrack: TrackPoint[] = [
      makeTrackPoint('2026-03-10T12:00:00Z', 68.0, 15.0),
      makeTrackPoint('2026-03-10T13:00:00Z', 68.1, 15.1),
    ];

    useReplayStore.getState().setReplayState({
      isActive: true,
      track: mockTrack,
      currentIndex: 1,
      aisGaps: [],
    });

    const state = useReplayStore.getState();
    expect(state.isActive).toBe(true);
    expect(state.track).toEqual(mockTrack);
    expect(state.currentIndex).toBe(1);

    // Clean up
    useReplayStore.getState().clearReplay();
  });

  it('clearReplay resets to defaults', async () => {
    const { useReplayStore } = await import('../hooks/useReplayStore');
    useReplayStore.getState().setReplayState({
      isActive: true,
      track: [makeTrackPoint('2026-03-10T12:00:00Z', 68.0, 15.0)],
      currentIndex: 5,
      aisGaps: [],
    });

    useReplayStore.getState().clearReplay();

    const state = useReplayStore.getState();
    expect(state.isActive).toBe(false);
    expect(state.track).toBeNull();
    expect(state.currentIndex).toBe(0);
  });
});

describe('Track replay timeline calculations', () => {
  it('progress is 0 at start of track', () => {
    const trackLength = 100;
    const currentIndex = 0;
    const progress = trackLength > 1 ? (currentIndex / (trackLength - 1)) * 100 : 0;
    expect(progress).toBe(0);
  });

  it('progress is 100 at end of track', () => {
    const trackLength = 100;
    const currentIndex = 99;
    const progress = trackLength > 1 ? (currentIndex / (trackLength - 1)) * 100 : 0;
    expect(progress).toBe(100);
  });

  it('progress is ~50 at midpoint', () => {
    const trackLength = 101;
    const currentIndex = 50;
    const progress = trackLength > 1 ? (currentIndex / (trackLength - 1)) * 100 : 0;
    expect(progress).toBe(50);
  });

  it('progress is 0 for single-point track', () => {
    const trackLength = 1;
    const currentIndex = 0;
    const progress = trackLength > 1 ? (currentIndex / (trackLength - 1)) * 100 : 0;
    expect(progress).toBe(0);
  });
});
