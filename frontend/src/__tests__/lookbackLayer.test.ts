import { describe, it, expect } from 'vitest';
import { interpolatePosition } from '../components/Map/LookbackLayer';
import type { TrackPoint } from '../types/api';

function makeTrackPoint(
  timestamp: string,
  lat: number,
  lon: number,
  sog: number | null = 10,
  cog: number | null = 90,
): TrackPoint {
  return { timestamp, lat, lon, sog, cog, heading: null };
}

describe('interpolatePosition', () => {
  it('returns null for empty track', () => {
    expect(interpolatePosition([], Date.now())).toBeNull();
  });

  it('returns the single point for a one-point track', () => {
    const track = [makeTrackPoint('2024-01-01T00:00:00Z', 60, 25)];
    const result = interpolatePosition(track, new Date('2024-01-01T00:00:00Z').getTime());
    expect(result).toEqual({ lat: 60, lon: 25, cog: 90, sog: 10 });
  });

  it('returns first point when target time is before first point', () => {
    const track = [
      makeTrackPoint('2024-01-01T01:00:00Z', 60, 25),
      makeTrackPoint('2024-01-01T02:00:00Z', 61, 26),
    ];
    const result = interpolatePosition(track, new Date('2024-01-01T00:00:00Z').getTime());
    expect(result).toEqual({ lat: 60, lon: 25, cog: 90, sog: 10 });
  });

  it('returns last point when target time is after last point', () => {
    const track = [
      makeTrackPoint('2024-01-01T01:00:00Z', 60, 25),
      makeTrackPoint('2024-01-01T02:00:00Z', 61, 26),
    ];
    const result = interpolatePosition(track, new Date('2024-01-01T03:00:00Z').getTime());
    expect(result).toEqual({ lat: 61, lon: 26, cog: 90, sog: 10 });
  });

  it('interpolates correctly at the midpoint between two points', () => {
    const track = [
      makeTrackPoint('2024-01-01T00:00:00Z', 60, 20, 10, 90),
      makeTrackPoint('2024-01-01T02:00:00Z', 62, 24, 14, 180),
    ];
    // Midpoint = 1 hour in
    const targetMs = new Date('2024-01-01T01:00:00Z').getTime();
    const result = interpolatePosition(track, targetMs);
    expect(result).not.toBeNull();
    expect(result!.lat).toBeCloseTo(61, 5);
    expect(result!.lon).toBeCloseTo(22, 5);
    expect(result!.sog).toBeCloseTo(12, 5);
    // cog takes the "after" point's value
    expect(result!.cog).toBe(180);
  });

  it('interpolates at 25% through a multi-point track', () => {
    const track = [
      makeTrackPoint('2024-01-01T00:00:00Z', 0, 0, 0, 0),
      makeTrackPoint('2024-01-01T01:00:00Z', 10, 10, 10, 90),
      makeTrackPoint('2024-01-01T02:00:00Z', 20, 20, 20, 180),
      makeTrackPoint('2024-01-01T03:00:00Z', 30, 30, 30, 270),
    ];
    // 30 minutes in — between point 0 and point 1
    const targetMs = new Date('2024-01-01T00:30:00Z').getTime();
    const result = interpolatePosition(track, targetMs);
    expect(result).not.toBeNull();
    expect(result!.lat).toBeCloseTo(5, 5);
    expect(result!.lon).toBeCloseTo(5, 5);
    expect(result!.sog).toBeCloseTo(5, 5);
  });

  it('handles null sog values', () => {
    const track = [
      makeTrackPoint('2024-01-01T00:00:00Z', 60, 20, null, 90),
      makeTrackPoint('2024-01-01T02:00:00Z', 62, 24, 14, 180),
    ];
    const targetMs = new Date('2024-01-01T01:00:00Z').getTime();
    const result = interpolatePosition(track, targetMs);
    expect(result).not.toBeNull();
    // When one sog is null, should return the "after" point's sog
    expect(result!.sog).toBe(14);
  });
});
