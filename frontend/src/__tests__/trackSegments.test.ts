import { describe, it, expect } from 'vitest';
import { buildSpeedSegments, type TrackPoint } from '../components/Map/TrackTrail';

describe('buildSpeedSegments (MapLibre TrackTrail)', () => {
  const makePoints = (
    timestamps: number[],
    sog = 10,
    baseLon = 28.0,
    baseLat = 60.0,
  ): TrackPoint[] =>
    timestamps.map((t, i) => ({
      lon: baseLon + i * 0.01,
      lat: baseLat + i * 0.01,
      timestamp: new Date(t).toISOString(),
      sog,
    }));

  it('returns empty array for empty input', () => {
    expect(buildSpeedSegments([])).toEqual([]);
  });

  it('returns empty array for a single point', () => {
    const points = makePoints([1000]);
    expect(buildSpeedSegments(points)).toEqual([]);
  });

  it('creates one segment per pair of consecutive points', () => {
    const base = Date.UTC(2024, 2, 15, 14, 0, 0);
    const points = makePoints([
      base,
      base + 5 * 60000,
      base + 10 * 60000,
    ]);

    const segments = buildSpeedSegments(points);
    expect(segments.length).toBe(2); // 3 points = 2 segments
    expect(segments[0].isGap).toBe(false);
    expect(segments[0].coordinates.length).toBe(2);
  });

  it('marks gaps >10 minutes', () => {
    const base = Date.UTC(2024, 2, 15, 14, 0, 0);
    const points = makePoints([
      base,
      base + 5 * 60000,   // 5 min — no gap
      base + 25 * 60000,  // 20 min — GAP
      base + 30 * 60000,  // 5 min — no gap
    ]);

    const segments = buildSpeedSegments(points);
    expect(segments.length).toBe(3);
    expect(segments[0].isGap).toBe(false);
    expect(segments[1].isGap).toBe(true);
    expect(segments[2].isGap).toBe(false);
  });

  it('computes average speed per segment', () => {
    const base = Date.UTC(2024, 2, 15, 14, 0, 0);
    const points: TrackPoint[] = [
      { lon: 28.0, lat: 60.0, timestamp: new Date(base).toISOString(), sog: 10 },
      { lon: 28.01, lat: 60.01, timestamp: new Date(base + 5 * 60000).toISOString(), sog: 20 },
    ];

    const segments = buildSpeedSegments(points);
    expect(segments[0].speed).toBe(15); // average of 10 and 20
  });

  it('handles null sog as 0', () => {
    const base = Date.UTC(2024, 2, 15, 14, 0, 0);
    const points: TrackPoint[] = [
      { lon: 28.0, lat: 60.0, timestamp: new Date(base).toISOString(), sog: null },
      { lon: 28.01, lat: 60.01, timestamp: new Date(base + 5 * 60000).toISOString(), sog: 10 },
    ];

    const segments = buildSpeedSegments(points);
    expect(segments[0].speed).toBe(5); // average of 0 and 10
  });
});
