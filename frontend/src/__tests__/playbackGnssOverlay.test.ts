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
      // Zone detected 30min ago, expires in 2h — well within a 6h window
      makeFeature('2025-06-15T11:30:00Z', '2025-06-15T14:00:00Z'),
      // Zone detected at edge
      makeFeature('2025-06-15T12:25:00Z', '2025-06-15T13:00:00Z'),
    ];

    const result = filterZonesByTime(features, currentTime, '6h');
    expect(result).toHaveLength(2);
  });

  it('excludes zones entirely outside the window', () => {
    const features = [
      // Zone that expired well before the 6h window (half = 3h, so windowStart = 09:00)
      makeFeature('2025-06-15T04:00:00Z', '2025-06-15T06:00:00Z'),
      // Zone detected well after the 6h window (half = 3h, so windowEnd = 15:00)
      makeFeature('2025-06-15T18:00:00Z', '2025-06-15T19:00:00Z'),
    ];

    const result = filterZonesByTime(features, currentTime, '6h');
    expect(result).toHaveLength(0);
  });

  it('includes zones at exact window boundary', () => {
    // 12h window: half = 6h, so window is [06:00, 18:00]
    const features = [
      // detected_at exactly at window end
      makeFeature('2025-06-15T18:00:00Z', '2025-06-15T19:00:00Z'),
      // expires_at exactly at window start
      makeFeature('2025-06-15T04:00:00Z', '2025-06-15T06:00:00Z'),
    ];

    const result = filterZonesByTime(features, currentTime, '12h');
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

    const result = filterZonesByTime(features, currentTime, '24h');
    expect(result).toHaveLength(0);
  });

  it('window size changes affect filtering range', () => {
    const features = [
      // Zone expired 4h before current time
      // 6h window: windowStart = 09:00 -> expires 08:00 < 09:00 -> excluded
      // 12h window: windowStart = 06:00 -> expires 08:00 >= 06:00 -> included
      makeFeature('2025-06-15T06:00:00Z', '2025-06-15T08:00:00Z'),
    ];

    const result6h = filterZonesByTime(features, currentTime, '6h');
    expect(result6h).toHaveLength(0);

    const result12h = filterZonesByTime(features, currentTime, '12h');
    expect(result12h).toHaveLength(1);
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
    // 6h window, zone 30min old: ratio=0.5/6≈0.083, opacity = 1 - 0.0069 ≈ 0.993
    const opacity6h = calculateOpacityFactor('2025-06-15T11:30:00Z', currentTime, '6h');
    expect(opacity6h).toBeCloseTo(1 - (0.5 / 6) ** 2);

    // 24h window, zone 30min old: ratio=0.5/24≈0.021, opacity ≈ 0.9996
    const opacity24h = calculateOpacityFactor('2025-06-15T11:30:00Z', currentTime, '24h');
    expect(opacity24h).toBeCloseTo(1 - (0.5 / 24) ** 2);
  });
});
