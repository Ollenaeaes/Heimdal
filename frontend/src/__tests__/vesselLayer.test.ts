import { describe, it, expect, vi } from 'vitest';
import type { VesselState } from '../types/vessel';

// Mock react-map-gl/maplibre to prevent maplibre-gl from loading
vi.mock('react-map-gl/maplibre', () => ({
  Source: vi.fn(() => null),
  Layer: vi.fn(() => null),
  useMap: vi.fn(() => ({ current: null })),
}));

import { buildVesselGeoJson, buildSpeedVectors } from '../components/Map/VesselLayer';

function makeVessel(overrides: Partial<VesselState> & { mmsi: number }): VesselState {
  return {
    lat: 59.0,
    lon: 10.0,
    sog: 12,
    cog: 180,
    heading: 180,
    riskTier: 'green',
    riskScore: 0,
    timestamp: '2025-01-15T12:00:00Z',
    ...overrides,
  };
}

describe('buildVesselGeoJson', () => {
  it('produces correct FeatureCollection from vessel array', () => {
    const vessels = [
      makeVessel({ mmsi: 123456789, lat: 60, lon: 5, riskTier: 'yellow', name: 'NORDIC STAR' }),
      makeVessel({ mmsi: 987654321, lat: 58, lon: 11, riskTier: 'red', name: 'DARK RUNNER' }),
    ];
    const result = buildVesselGeoJson(vessels, new Set(), new Set());

    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(2);

    const f0 = result.features[0];
    expect(f0.type).toBe('Feature');
    expect(f0.geometry.type).toBe('Point');
    expect(f0.geometry.coordinates).toEqual([5, 60]);
    expect(f0.properties.mmsi).toBe(123456789);

    const f1 = result.features[1];
    expect(f1.geometry.coordinates).toEqual([11, 58]);
    expect(f1.properties.mmsi).toBe(987654321);
  });

  it('features have correct properties including heading and isMoving', () => {
    const vessels = [
      makeVessel({ mmsi: 111, riskTier: 'red', cog: 45, heading: 50, sog: 10, name: 'VESSEL A' }),
    ];
    const watchedMmsis = new Set([111]);
    const spoofedMmsis = new Set<number>();

    const result = buildVesselGeoJson(vessels, watchedMmsis, spoofedMmsis);
    const props = result.features[0].properties;

    expect(props.mmsi).toBe(111);
    expect(props.riskTier).toBe('red');
    expect(props.riskScore).toBe(100);
    expect(props.cog).toBe(45);
    expect(props.heading).toBe(50);
    expect(props.sog).toBe(10);
    expect(props.shipName).toBe('VESSEL A');
    expect(props.isWatchlisted).toBe(true);
    expect(props.isSpoofed).toBe(false);
    expect(props.isMoving).toBe(true);
  });

  it('green vessels get riskScore 0, yellow 50, red 100, blacklisted 150', () => {
    const vessels = [
      makeVessel({ mmsi: 1, riskTier: 'green' }),
      makeVessel({ mmsi: 2, riskTier: 'yellow' }),
      makeVessel({ mmsi: 3, riskTier: 'red' }),
      makeVessel({ mmsi: 4, riskTier: 'blacklisted' }),
    ];
    const result = buildVesselGeoJson(vessels, new Set(), new Set());

    expect(result.features[0].properties.riskScore).toBe(0);
    expect(result.features[1].properties.riskScore).toBe(50);
    expect(result.features[2].properties.riskScore).toBe(100);
    expect(result.features[3].properties.riskScore).toBe(150);
  });

  it('empty vessel array produces empty FeatureCollection', () => {
    const result = buildVesselGeoJson([], new Set(), new Set());

    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(0);
  });

  it('marks spoofed vessels correctly', () => {
    const vessels = [
      makeVessel({ mmsi: 555, riskTier: 'yellow', name: 'SPOOFED ONE' }),
      makeVessel({ mmsi: 666, riskTier: 'green', name: 'CLEAN VESSEL' }),
    ];
    const result = buildVesselGeoJson(vessels, new Set(), new Set([555]));

    expect(result.features[0].properties.isSpoofed).toBe(true);
    expect(result.features[1].properties.isSpoofed).toBe(false);
  });

  it('uses MMSI fallback when vessel has no name', () => {
    const vessels = [makeVessel({ mmsi: 999 })];
    const result = buildVesselGeoJson(vessels, new Set(), new Set());

    expect(result.features[0].properties.shipName).toBe('MMSI 999');
  });

  it('stationary vessels have isMoving=false', () => {
    const vessels = [makeVessel({ mmsi: 111, sog: 0 })];
    const result = buildVesselGeoJson(vessels, new Set(), new Set());

    expect(result.features[0].properties.isMoving).toBe(false);
  });

  it('includes vessel dimensions', () => {
    const vessels = [makeVessel({ mmsi: 111, length: 200, width: 32 })];
    const result = buildVesselGeoJson(vessels, new Set(), new Set());

    expect(result.features[0].properties.vesselLength).toBe(200);
    expect(result.features[0].properties.vesselWidth).toBe(32);
  });
});

describe('buildSpeedVectors', () => {
  it('generates vectors for moving vessels', () => {
    const vessels = [
      makeVessel({ mmsi: 1, sog: 12, cog: 90 }),
    ];
    const result = buildSpeedVectors(vessels);

    expect(result.features).toHaveLength(1);
    expect(result.features[0].geometry.type).toBe('LineString');
    expect(result.features[0].geometry.coordinates).toHaveLength(2);
    // End point should be east of start (cog=90)
    expect(result.features[0].geometry.coordinates[1][0]).toBeGreaterThan(
      result.features[0].geometry.coordinates[0][0]
    );
  });

  it('skips stationary vessels', () => {
    const vessels = [
      makeVessel({ mmsi: 1, sog: 0, cog: 90 }),
    ];
    const result = buildSpeedVectors(vessels);
    expect(result.features).toHaveLength(0);
  });

  it('skips vessels with null cog', () => {
    const vessels = [
      makeVessel({ mmsi: 1, sog: 12, cog: null }),
    ];
    const result = buildSpeedVectors(vessels);
    expect(result.features).toHaveLength(0);
  });
});
