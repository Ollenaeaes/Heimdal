import { describe, it, expect } from 'vitest';
import { buildDuplicateMmsiGeoJson } from '../components/Map/DuplicateMmsiLayer';
import { buildNetworkGeoJson } from '../components/Map/NetworkLayer';
import { buildGnssSpoofingGeoJson, severityWeight } from '../components/Map/GnssHeatmap';
import type { NetworkApiResponse } from '../components/VesselPanel/NetworkGraph';

describe('buildDuplicateMmsiGeoJson', () => {
  it('creates LineString + Point features from anomaly data with position_a/position_b', () => {
    const items = [
      {
        id: 1,
        mmsi: 123456789,
        rule_id: 'spoof_duplicate_mmsi',
        details: {
          position_a: { lat: 10, lon: 20 },
          position_b: { lat: 30, lon: 40 },
        },
      },
    ];

    const result = buildDuplicateMmsiGeoJson(items);

    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(2);

    // Line feature
    const line = result.features[0];
    expect(line.geometry.type).toBe('LineString');
    expect((line.geometry as GeoJSON.LineString).coordinates).toEqual([
      [20, 10],
      [40, 30],
    ]);
    expect(line.properties?.type).toBe('line');

    // Label feature at midpoint
    const label = result.features[1];
    expect(label.geometry.type).toBe('Point');
    expect((label.geometry as GeoJSON.Point).coordinates).toEqual([30, 20]);
    expect(label.properties?.type).toBe('label');
    expect(label.properties?.text).toBe('Duplicate MMSI');
  });

  it('uses reported/other fallback positions', () => {
    const items = [
      {
        id: 2,
        mmsi: 987654321,
        rule_id: 'spoof_duplicate_mmsi',
        details: {
          reported_lat: 5,
          reported_lon: 15,
          other_lat: 25,
          other_lon: 35,
        },
      },
    ];

    const result = buildDuplicateMmsiGeoJson(items);
    expect(result.features).toHaveLength(2);

    const line = result.features[0];
    expect((line.geometry as GeoJSON.LineString).coordinates).toEqual([
      [15, 5],
      [35, 25],
    ]);
  });

  it('returns empty FeatureCollection for empty array', () => {
    const result = buildDuplicateMmsiGeoJson([]);
    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(0);
  });

  it('skips anomalies with missing positions', () => {
    const items = [
      {
        id: 3,
        mmsi: 111222333,
        rule_id: 'spoof_duplicate_mmsi',
        details: { some_other_field: 'value' },
      },
    ];

    const result = buildDuplicateMmsiGeoJson(items);
    expect(result.features).toHaveLength(0);
  });
});

describe('buildNetworkGeoJson', () => {
  const makeVessels = () => {
    const m = new Map<number, { lat: number; lon: number }>();
    m.set(100, { lat: 10, lon: 20 });
    m.set(200, { lat: 30, lon: 40 });
    m.set(300, { lat: 50, lon: 60 });
    return m;
  };

  it('creates correct LineString features with edgeType', () => {
    const apiResponse: NetworkApiResponse = {
      mmsi: 100,
      depth: 1,
      edges: [
        {
          vessel_a_mmsi: 100,
          vessel_b_mmsi: 200,
          edge_type: 'encounter',
          confidence: 0.9,
          lat: null,
          lon: null,
          last_observed: null,
          details: {},
        },
        {
          vessel_a_mmsi: 100,
          vessel_b_mmsi: 300,
          edge_type: 'ownership',
          confidence: 0.8,
          lat: 55,
          lon: 65,
          last_observed: null,
          details: {},
        },
      ],
      vessels: {
        '100': { name: 'Test A', flag: 'PA', ship_type: 70 },
        '200': { name: 'Test B', flag: 'LR', ship_type: 80 },
        '300': { name: 'Test C', flag: 'MT', ship_type: 70 },
      },
    };

    const vessels = makeVessels();
    const { edges, nodes } = buildNetworkGeoJson(apiResponse, 100, vessels);

    expect(edges.features).toHaveLength(2);

    // Encounter edge (solid)
    const encounterEdge = edges.features[0];
    expect(encounterEdge.geometry.type).toBe('LineString');
    expect((encounterEdge.geometry as GeoJSON.LineString).coordinates).toEqual([
      [20, 10],  // selected vessel
      [40, 30],  // other vessel position (no edge lat/lon)
    ]);
    expect(encounterEdge.properties?.edgeType).toBe('encounter');
    expect(encounterEdge.properties?.dashed).toBe(false);

    // Ownership edge (dashed, uses edge lat/lon)
    const ownershipEdge = edges.features[1];
    expect((ownershipEdge.geometry as GeoJSON.LineString).coordinates).toEqual([
      [20, 10],  // selected vessel
      [65, 55],  // edge location
    ]);
    expect(ownershipEdge.properties?.edgeType).toBe('ownership');
    expect(ownershipEdge.properties?.dashed).toBe(true);

    // Node circles for connected vessels (excludes selected)
    expect(nodes.features).toHaveLength(2);
    expect(nodes.features[0].properties?.mmsi).toBe(200);
    expect(nodes.features[1].properties?.mmsi).toBe(300);
  });

  it('returns empty collections when selected vessel not found', () => {
    const apiResponse: NetworkApiResponse = {
      mmsi: 999,
      depth: 1,
      edges: [],
      vessels: {},
    };

    const vessels = new Map<number, { lat: number; lon: number }>();
    const { edges, nodes } = buildNetworkGeoJson(apiResponse, 999, vessels);

    expect(edges.features).toHaveLength(0);
    expect(nodes.features).toHaveLength(0);
  });
});

describe('buildGnssSpoofingGeoJson', () => {
  it('converts spoofing events to GeoJSON with severity weights', () => {
    const events = [
      { lat: 10, lon: 20, severity: 'critical' },
      { lat: 30, lon: 40, severity: 'low' },
    ];

    const result = buildGnssSpoofingGeoJson(events);

    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(2);

    const critical = result.features[0];
    expect((critical.geometry as GeoJSON.Point).coordinates).toEqual([20, 10]);
    expect(critical.properties?.weight).toBe(3);

    const low = result.features[1];
    expect(low.properties?.weight).toBe(0.5);
  });
});

describe('severityWeight', () => {
  it('maps severity levels to correct weights', () => {
    expect(severityWeight('critical')).toBe(3);
    expect(severityWeight('high')).toBe(2);
    expect(severityWeight('moderate')).toBe(1);
    expect(severityWeight('low')).toBe(0.5);
    expect(severityWeight('unknown')).toBe(0.5);
  });
});
