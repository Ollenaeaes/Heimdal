import { describe, it, expect } from 'vitest';
import { filterZonesByTime, calculateOpacityFactor } from '../components/Map/PlaybackGnssOverlay';

function makeFeature(detectedAt: string, expiresAt: string, eventType = 'spoofing'): GeoJSON.Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] },
    properties: {
      detected_at: detectedAt,
      expires_at: expiresAt,
      event_type: eventType,
      affected_count: 5,
    },
  };
}

describe('filterZonesByTime', () => {
  const currentTime = new Date('2025-06-15T12:00:00Z');

  it('includes zones that overlap the window', () => {
    const features = [
      // Zone detected 30min ago, expires in 2h — well within a 1h window
      makeFeature('2025-06-15T11:30:00Z', '2025-06-15T14:00:00Z'),
      // Zone detected at edge: detected_at <= currentTime + 30min, expires_at >= currentTime - 30min
      makeFeature('2025-06-15T12:25:00Z', '2025-06-15T13:00:00Z'),
    ];

    const result = filterZonesByTime(features, currentTime, '1h');
    expect(result).toHaveLength(2);
  });

  it('excludes zones entirely outside the window', () => {
    const features = [
      // Zone that expired 2 hours before current time (1h window half = 30min)
      makeFeature('2025-06-15T08:00:00Z', '2025-06-15T10:00:00Z'),
      // Zone detected 3 hours in the future (1h window half = 30min)
      makeFeature('2025-06-15T15:00:00Z', '2025-06-15T16:00:00Z'),
    ];

    const result = filterZonesByTime(features, currentTime, '1h');
    expect(result).toHaveLength(0);
  });

  it('includes zones at exact window boundary', () => {
    // 6h window: half = 3h, so window is [09:00, 15:00]
    const features = [
      // detected_at exactly at window end
      makeFeature('2025-06-15T15:00:00Z', '2025-06-15T16:00:00Z'),
      // expires_at exactly at window start
      makeFeature('2025-06-15T07:00:00Z', '2025-06-15T09:00:00Z'),
    ];

    const result = filterZonesByTime(features, currentTime, '6h');
    expect(result).toHaveLength(2);
  });

  it('excludes features with missing timestamps', () => {
    const features: GeoJSON.Feature[] = [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [0, 0] },
        properties: { detected_at: null, expires_at: null },
      },
    ];

    const result = filterZonesByTime(features, currentTime, '3h');
    expect(result).toHaveLength(0);
  });

  it('window size changes affect filtering range', () => {
    // Zone detected 2h ago, expires 1h from now
    // With 1h window (half = 30min): detected_at (10:00) > windowEnd (12:30)? No, 10:00 <= 12:30. expires (13:00) >= windowStart (11:30)? Yes. -> included? detected_at <= 12:30 ✓, expires >= 11:30 ✓ -> yes
    // Actually let's use a zone that's just barely inside 6h but outside 1h
    const features = [
      // Zone expired 2h before current time
      // 1h window: windowStart = 11:30 -> expires 10:00 < 11:30 -> excluded
      // 6h window: windowStart = 09:00 -> expires 10:00 >= 09:00 -> included
      makeFeature('2025-06-15T08:00:00Z', '2025-06-15T10:00:00Z'),
    ];

    const result1h = filterZonesByTime(features, currentTime, '1h');
    expect(result1h).toHaveLength(0);

    const result6h = filterZonesByTime(features, currentTime, '6h');
    expect(result6h).toHaveLength(1);
  });
});

describe('calculateOpacityFactor', () => {
  const currentTime = new Date('2025-06-15T12:00:00Z');

  it('returns 1.0 for zones detected at current time', () => {
    const opacity = calculateOpacityFactor('2025-06-15T12:00:00Z', currentTime, '6h');
    expect(opacity).toBeCloseTo(1.0);
  });

  it('returns minimum for zones at or beyond window edge', () => {
    // 6h window. Zone 6h old: ratio=1, opacity = max(0.05, 1 - 1*1) = 0.05
    const opacity = calculateOpacityFactor('2025-06-15T06:00:00Z', currentTime, '6h');
    expect(opacity).toBeCloseTo(0.05);
  });

  it('returns intermediate values for zones between center and edge (quadratic)', () => {
    // 6h window. Zone 3h old: ratio=0.5, opacity = 1 - 0.25 = 0.75
    const opacity = calculateOpacityFactor('2025-06-15T09:00:00Z', currentTime, '6h');
    expect(opacity).toBeCloseTo(0.75);
  });

  it('handles future zones (detected_at after currentTime)', () => {
    // 6h window. Zone 1h in future: ratio=1/6, opacity = 1 - (1/6)^2 ≈ 0.972
    const opacity = calculateOpacityFactor('2025-06-15T13:00:00Z', currentTime, '6h');
    expect(opacity).toBeCloseTo(1 - (1 / 6) ** 2);
  });

  it('uses correct window durations for each size', () => {
    // 1h window, zone 30min old: ratio=0.5, opacity = 1 - 0.25 = 0.75
    const opacity1h = calculateOpacityFactor('2025-06-15T11:30:00Z', currentTime, '1h');
    expect(opacity1h).toBeCloseTo(0.75);

    // 3h window, zone 30min old: ratio=0.5/3≈0.167, opacity = 1 - 0.028 ≈ 0.972
    const opacity3h = calculateOpacityFactor('2025-06-15T11:30:00Z', currentTime, '3h');
    expect(opacity3h).toBeCloseTo(1 - (0.5 / 3) ** 2);
  });
});
