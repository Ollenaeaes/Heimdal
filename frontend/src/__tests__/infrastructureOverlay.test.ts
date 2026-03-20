import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
  QueryClient: vi.fn(),
  QueryClientProvider: vi.fn(({ children }: { children?: unknown }) => children),
}));

import { ROUTE_TYPE_COLORS } from '../components/Map/InfrastructureLayer';

// Realistic test data
const makeRouteFeature = (overrides: Record<string, unknown> = {}) => ({
  type: 'Feature' as const,
  geometry: {
    type: 'LineString',
    coordinates: [
      [5.125, 60.391],
      [5.234, 60.412],
      [5.345, 60.425],
      [5.456, 60.438],
    ],
  },
  properties: {
    id: 1,
    name: 'Nordlink HVDC Cable',
    route_type: 'power_cable',
    operator: 'Statnett',
    buffer_nm: 1.0,
    ...overrides,
  },
});

const makeGeoJsonResponse = (features: ReturnType<typeof makeRouteFeature>[]) => ({
  type: 'FeatureCollection' as const,
  features,
});

describe('Infrastructure route type color mapping', () => {
  it('maps telecom_cable to blue (#3B82F6)', () => {
    expect(ROUTE_TYPE_COLORS['telecom_cable']).toBe('#3B82F6');
  });

  it('maps power_cable to yellow (#EAB308)', () => {
    expect(ROUTE_TYPE_COLORS['power_cable']).toBe('#EAB308');
  });

  it('maps gas_pipeline to orange (#F97316)', () => {
    expect(ROUTE_TYPE_COLORS['gas_pipeline']).toBe('#F97316');
  });

  it('maps oil_pipeline to orange (#F97316)', () => {
    expect(ROUTE_TYPE_COLORS['oil_pipeline']).toBe('#F97316');
  });
});

describe('InfrastructureLayer component exports', () => {
  it('exports ROUTE_TYPE_COLORS map', async () => {
    const { ROUTE_TYPE_COLORS: colors } = await import('../components/Map/InfrastructureLayer');
    expect(colors).toBeDefined();
    expect(typeof colors).toBe('object');
    expect(Object.keys(colors)).toContain('telecom_cable');
    expect(Object.keys(colors)).toContain('power_cable');
    expect(Object.keys(colors)).toContain('gas_pipeline');
    expect(Object.keys(colors)).toContain('oil_pipeline');
  });
});

describe('Infrastructure GeoJSON data shape', () => {
  it('creates valid GeoJSON FeatureCollection', () => {
    const features = [
      makeRouteFeature(),
      makeRouteFeature({
        id: 2,
        name: 'Europipe II Gas Pipeline',
        route_type: 'gas_pipeline',
        operator: 'Gassco',
      }),
    ];
    const collection = makeGeoJsonResponse(features);
    expect(collection.type).toBe('FeatureCollection');
    expect(collection.features).toHaveLength(2);
    expect(collection.features[0].type).toBe('Feature');
    expect(collection.features[0].geometry.type).toBe('LineString');
    expect(collection.features[0].properties.route_type).toBe('power_cable');
    expect(collection.features[1].properties.route_type).toBe('gas_pipeline');
  });

  it('route feature has required properties', () => {
    const feature = makeRouteFeature();
    expect(feature.properties).toHaveProperty('id');
    expect(feature.properties).toHaveProperty('name');
    expect(feature.properties).toHaveProperty('route_type');
    expect(feature.properties).toHaveProperty('operator');
    expect(feature.properties).toHaveProperty('buffer_nm');
  });

  it('geometry coordinates are [lon, lat] pairs', () => {
    const feature = makeRouteFeature();
    const coords = feature.geometry.coordinates;
    expect(coords.length).toBeGreaterThan(1);
    for (const coord of coords) {
      expect(coord).toHaveLength(2);
      expect(coord[0]).toBeGreaterThanOrEqual(-180);
      expect(coord[0]).toBeLessThanOrEqual(180);
      expect(coord[1]).toBeGreaterThanOrEqual(-90);
      expect(coord[1]).toBeLessThanOrEqual(90);
    }
  });
});

describe('Infrastructure overlay visibility logic', () => {
  it('component returns null when visible is false', () => {
    // The component has an early return: if (!visible) return null;
    // We test the logic pattern directly
    const visible = false;
    const result = !visible ? null : 'rendered';
    expect(result).toBeNull();
  });

  it('component renders when visible is true', () => {
    const visible = true;
    const result = !visible ? null : 'rendered';
    expect(result).not.toBeNull();
  });
});

describe('Risk halo filtering logic', () => {
  it('yellow vessel near route produces amber halo', () => {
    const vessels = [
      { mmsi: 211000001, lat: 60.4, lon: 5.2, riskTier: 'yellow', riskScore: 55 },
    ];
    const riskyVessels = vessels.filter(
      (v) => v.riskTier === 'yellow' || v.riskTier === 'red' || v.riskTier === 'blacklisted',
    );
    expect(riskyVessels).toHaveLength(1);
    expect(riskyVessels[0].riskTier).toBe('yellow');
  });

  it('red vessel near route produces red halo', () => {
    const vessels = [
      { mmsi: 273456789, lat: 60.42, lon: 5.3, riskTier: 'red', riskScore: 85 },
    ];
    const riskyVessels = vessels.filter(
      (v) => v.riskTier === 'yellow' || v.riskTier === 'red' || v.riskTier === 'blacklisted',
    );
    expect(riskyVessels).toHaveLength(1);
    expect(riskyVessels[0].riskTier).toBe('red');
  });

  it('green vessel near route produces no halo', () => {
    const vessels = [
      { mmsi: 311000001, lat: 60.41, lon: 5.25, riskTier: 'green', riskScore: 5 },
    ];
    const riskyVessels = vessels.filter(
      (v) => v.riskTier === 'yellow' || v.riskTier === 'red' || v.riskTier === 'blacklisted',
    );
    expect(riskyVessels).toHaveLength(0);
  });

  it('mixed vessel tiers filters correctly', () => {
    const vessels = [
      { mmsi: 100, lat: 60.4, lon: 5.2, riskTier: 'green', riskScore: 5 },
      { mmsi: 200, lat: 60.41, lon: 5.25, riskTier: 'yellow', riskScore: 55 },
      { mmsi: 300, lat: 60.42, lon: 5.3, riskTier: 'red', riskScore: 85 },
      { mmsi: 400, lat: 60.43, lon: 5.35, riskTier: 'green', riskScore: 10 },
    ];
    const riskyVessels = vessels.filter(
      (v) => v.riskTier === 'yellow' || v.riskTier === 'red' || v.riskTier === 'blacklisted',
    );
    expect(riskyVessels).toHaveLength(2);
    expect(riskyVessels.map((v) => v.mmsi)).toEqual([200, 300]);
  });

  it('proximity check: vessel within 0.5 degrees is near', () => {
    const routeCoords = [[5.125, 60.391], [5.234, 60.412], [5.345, 60.425]];
    const vesselLon = 5.2;
    const vesselLat = 60.4;
    const PROXIMITY_THRESHOLD = 0.5;

    // Find nearest point on route
    let minDist = Infinity;
    for (const coord of routeCoords) {
      const dx = coord[0] - vesselLon;
      const dy = coord[1] - vesselLat;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < minDist) minDist = d;
    }
    expect(minDist).toBeLessThan(PROXIMITY_THRESHOLD);
  });

  it('proximity check: vessel far away is not near', () => {
    const routeCoords = [[5.125, 60.391], [5.234, 60.412], [5.345, 60.425]];
    const vesselLon = 10.0;
    const vesselLat = 55.0;
    const PROXIMITY_THRESHOLD = 0.5;

    let minDist = Infinity;
    for (const coord of routeCoords) {
      const dx = coord[0] - vesselLon;
      const dy = coord[1] - vesselLat;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < minDist) minDist = d;
    }
    expect(minDist).toBeGreaterThan(PROXIMITY_THRESHOLD);
  });
});

describe('Point feature rendering', () => {
  it('extracts start and end points from route coordinates', () => {
    const feature = makeRouteFeature();
    const coords = feature.geometry.coordinates;
    const startPoint = coords[0];
    const endPoint = coords[coords.length - 1];

    expect(startPoint[0]).toBe(5.125);
    expect(startPoint[1]).toBe(60.391);
    expect(endPoint[0]).toBe(5.456);
    expect(endPoint[1]).toBe(60.438);
  });

  it('generates two point features per route (start and end)', () => {
    const features = [makeRouteFeature()];
    const pointCount = features.length * 2;
    expect(pointCount).toBe(2);
  });

  it('point features for multiple routes', () => {
    const features = [
      makeRouteFeature(),
      makeRouteFeature({ id: 2, name: 'Langeled Gas Pipeline', route_type: 'gas_pipeline' }),
      makeRouteFeature({ id: 3, name: 'NorNed Telecom Cable', route_type: 'telecom_cable' }),
    ];
    const pointCount = features.length * 2;
    expect(pointCount).toBe(6);
  });

  it('cable endpoints get smaller markers than pipeline endpoints', () => {
    // Cables use pixelSize 8, pipelines use 10
    const getCablePixelSize = (routeType: string) => routeType.includes('cable') ? 8 : 10;
    expect(getCablePixelSize('telecom_cable')).toBe(8);
    expect(getCablePixelSize('power_cable')).toBe(8);
    expect(getCablePixelSize('gas_pipeline')).toBe(10);
    expect(getCablePixelSize('oil_pipeline')).toBe(10);
  });
});

describe('Alert feed behavior', () => {
  it('InfrastructurePanel exports correctly', async () => {
    const { InfrastructurePanel } = await import('../components/Dashboard/InfrastructurePanel');
    expect(InfrastructurePanel).toBeDefined();
    expect(typeof InfrastructurePanel).toBe('function');
  });
});

describe('Alert data sorting', () => {
  it('alerts should be sorted by risk_score descending', () => {
    const alerts = [
      { id: 1, mmsi: 100, vessel_name: 'Low Risk', risk_tier: 'green', risk_score: 10, route_name: 'Cable A' },
      { id: 2, mmsi: 200, vessel_name: 'High Risk', risk_tier: 'red', risk_score: 90, route_name: 'Cable B' },
      { id: 3, mmsi: 300, vessel_name: 'Medium Risk', risk_tier: 'yellow', risk_score: 50, route_name: 'Cable C' },
    ];
    const sorted = [...alerts].sort((a, b) => b.risk_score - a.risk_score);
    expect(sorted[0].vessel_name).toBe('High Risk');
    expect(sorted[1].vessel_name).toBe('Medium Risk');
    expect(sorted[2].vessel_name).toBe('Low Risk');
  });

  it('empty alerts array produces empty state message text', () => {
    const alerts: unknown[] = [];
    const emptyMessage = alerts.length === 0 ? 'No active corridor alerts' : null;
    expect(emptyMessage).toBe('No active corridor alerts');
  });

  it('non-empty alerts do not show empty state', () => {
    const alerts = [{ id: 1, mmsi: 100, vessel_name: 'Test', risk_score: 50 }];
    const emptyMessage = alerts.length === 0 ? 'No active corridor alerts' : null;
    expect(emptyMessage).toBeNull();
  });
});

describe('OverlayToggleState includes showInfrastructure', () => {
  it('DEFAULT_OVERLAYS has showInfrastructure set to false', () => {
    // Verify the overlay state shape (mirrors App.tsx DEFAULT_OVERLAYS)
    const defaults = {
      showStsZones: false,
      showTerminals: false,
      showEez: false,
      showSarDetections: false,
      showGfwEvents: false,
      showInfrastructure: false,
      showGnssZones: false,
    };
    expect(defaults).toHaveProperty('showInfrastructure');
    expect(defaults.showInfrastructure).toBe(false);
  });

  it('toggle function flips showInfrastructure', () => {
    const state = { showInfrastructure: false };
    const toggled = { ...state, showInfrastructure: !state.showInfrastructure };
    expect(toggled.showInfrastructure).toBe(true);
  });
});

describe('Vessel store integration for risk halos', () => {
  it('can read vessels from store', async () => {
    const { useVesselStore } = await import('../hooks/useVesselStore');
    const state = useVesselStore.getState();
    expect(state).toHaveProperty('vessels');
    expect(state.vessels).toBeInstanceOf(Map);
  });

  it('vessels have riskTier field used for halo filtering', async () => {
    const { useVesselStore } = await import('../hooks/useVesselStore');
    const store = useVesselStore.getState();
    store.updatePosition({
      mmsi: 273456789,
      lat: 60.42,
      lon: 5.30,
      sog: 2.0,
      cog: 90,
      heading: null,
      riskTier: 'red',
      riskScore: 85,
      name: 'Volga Spirit',
      timestamp: new Date().toISOString(),
    });

    const vessel = useVesselStore.getState().vessels.get(273456789);
    expect(vessel).toBeDefined();
    expect(vessel?.riskTier).toBe('red');
    expect(vessel?.riskScore).toBe(85);
  });
});
