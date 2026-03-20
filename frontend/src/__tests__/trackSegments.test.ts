import { describe, it, expect } from 'vitest';
import { buildTrackSegments } from '../components/Map/TrackTrail';

describe('buildTrackSegments (MapLibre TrackTrail)', () => {
  const makePoints = (
    timestamps: number[],
    baseLon = 28.0,
    baseLat = 60.0,
  ) =>
    timestamps.map((t, i) => ({
      lon: baseLon + i * 0.01,
      lat: baseLat + i * 0.01,
      timestamp: new Date(t).toISOString(),
    }));

  it('returns empty array for empty input', () => {
    expect(buildTrackSegments([])).toEqual([]);
  });

  it('returns empty array for a single point', () => {
    const points = makePoints([1000]);
    expect(buildTrackSegments(points)).toEqual([]);
  });

  it('keeps consecutive points as one segment when no gaps', () => {
    const base = Date.UTC(2024, 2, 15, 14, 0, 0);
    // 5 points, 5 minutes apart (no gap)
    const points = makePoints([
      base,
      base + 5 * 60000,
      base + 10 * 60000,
      base + 15 * 60000,
      base + 20 * 60000,
    ]);

    const segments = buildTrackSegments(points);
    expect(segments.length).toBe(1);
    expect(segments[0].isGap).toBe(false);
    expect(segments[0].coordinates.length).toBe(5);
  });

  it('splits on gaps >10 minutes', () => {
    const base = Date.UTC(2024, 2, 15, 14, 0, 0);
    const points = makePoints([
      base,
      base + 5 * 60000, // 5 min — no gap
      base + 10 * 60000, // 5 min — no gap
      base + 25 * 60000, // 15 min — GAP
      base + 30 * 60000, // 5 min — no gap
    ]);

    const segments = buildTrackSegments(points);
    // Should have: solid segment, gap segment, solid segment
    expect(segments.length).toBe(3);
    expect(segments[0].isGap).toBe(false);
    expect(segments[1].isGap).toBe(true);
    expect(segments[2].isGap).toBe(false);
  });

  it('marks gap segments correctly', () => {
    const base = Date.UTC(2024, 2, 15, 14, 0, 0);
    // All points 15 minutes apart — all gaps
    const points = makePoints([
      base,
      base + 15 * 60000,
      base + 30 * 60000,
      base + 45 * 60000,
    ]);

    const segments = buildTrackSegments(points);
    // All gaps, so one gap segment
    expect(segments.length).toBe(1);
    expect(segments[0].isGap).toBe(true);
    expect(segments[0].coordinates.length).toBe(4);
  });

  it('has recency values between 0 and 1', () => {
    const base = Date.UTC(2024, 2, 15, 14, 0, 0);
    const points = makePoints([
      base,
      base + 5 * 60000,
      base + 10 * 60000,
      base + 25 * 60000, // gap
      base + 30 * 60000,
      base + 35 * 60000,
    ]);

    const segments = buildTrackSegments(points);
    for (const seg of segments) {
      expect(seg.recency).toBeGreaterThanOrEqual(0);
      expect(seg.recency).toBeLessThanOrEqual(1);
    }
    // The last segment should have recency = 1
    expect(segments[segments.length - 1].recency).toBe(1);
  });
});
