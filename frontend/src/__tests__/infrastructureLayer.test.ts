import { describe, it, expect } from 'vitest';
import { processRouteData, ROUTE_TYPE_COLORS } from '../components/Map/InfrastructureLayer';

const makeRouteFeature = (overrides: Record<string, unknown> = {}) => ({
  type: 'Feature' as const,
  geometry: {
    type: 'LineString',
    coordinates: [
      [5.125, 60.391],
      [5.234, 60.412],
      [5.345, 60.425],
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

const makeAlert = (overrides: Record<string, unknown> = {}) => ({
  id: 1,
  route_id: 1,
  active: true,
  mmsi: 273456789,
  vessel_name: 'Volga Spirit',
  risk_tier: 'red',
  risk_score: 85,
  ...overrides,
});

describe('processRouteData', () => {
  it('correctly flags routes with active alerts', () => {
    const routesData = {
      type: 'FeatureCollection',
      features: [
        makeRouteFeature({ id: 1, name: 'Nordlink HVDC Cable' }),
        makeRouteFeature({ id: 2, name: 'Europipe II Gas Pipeline', route_type: 'gas_pipeline' }),
        makeRouteFeature({ id: 3, name: 'NorNed Telecom Cable', route_type: 'telecom_cable' }),
      ],
    };
    const alerts = [
      makeAlert({ id: 1, route_id: 1, active: true }),
      makeAlert({ id: 2, route_id: 3, active: true }),
    ];

    const result = processRouteData(routesData, alerts);

    expect(result.features[0].properties.flagged).toBe(true);
    expect(result.features[1].properties.flagged).toBe(false);
    expect(result.features[2].properties.flagged).toBe(true);
  });

  it('handles empty alerts array', () => {
    const routesData = {
      type: 'FeatureCollection',
      features: [
        makeRouteFeature({ id: 1 }),
        makeRouteFeature({ id: 2 }),
      ],
    };

    const result = processRouteData(routesData, []);

    expect(result.features[0].properties.flagged).toBe(false);
    expect(result.features[1].properties.flagged).toBe(false);
  });

  it('preserves original properties', () => {
    const routesData = {
      type: 'FeatureCollection',
      features: [
        makeRouteFeature({
          id: 1,
          name: 'Nordlink HVDC Cable',
          route_type: 'power_cable',
          operator: 'Statnett',
          buffer_nm: 1.0,
        }),
      ],
    };

    const result = processRouteData(routesData, []);

    expect(result.features[0].properties.id).toBe(1);
    expect(result.features[0].properties.name).toBe('Nordlink HVDC Cable');
    expect(result.features[0].properties.route_type).toBe('power_cable');
    expect(result.features[0].properties.operator).toBe('Statnett');
    expect(result.features[0].properties.buffer_nm).toBe(1.0);
    expect(result.features[0].properties.flagged).toBe(false);
  });

  it('only flags routes with active alerts, not inactive ones', () => {
    const routesData = {
      type: 'FeatureCollection',
      features: [
        makeRouteFeature({ id: 1 }),
        makeRouteFeature({ id: 2 }),
      ],
    };
    const alerts = [
      makeAlert({ id: 1, route_id: 1, active: true }),
      makeAlert({ id: 2, route_id: 2, active: false }),
    ];

    const result = processRouteData(routesData, alerts);

    expect(result.features[0].properties.flagged).toBe(true);
    expect(result.features[1].properties.flagged).toBe(false);
  });

  it('preserves the FeatureCollection type and structure', () => {
    const routesData = {
      type: 'FeatureCollection',
      features: [makeRouteFeature()],
    };

    const result = processRouteData(routesData, []);

    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(1);
    expect(result.features[0].type).toBe('Feature');
    expect(result.features[0].geometry.type).toBe('LineString');
  });

  it('does not mutate original routesData', () => {
    const routesData = {
      type: 'FeatureCollection',
      features: [makeRouteFeature({ id: 1 })],
    };
    const originalProps = { ...routesData.features[0].properties };

    processRouteData(routesData, [makeAlert({ route_id: 1, active: true })]);

    expect(routesData.features[0].properties).toEqual(originalProps);
    expect(routesData.features[0].properties).not.toHaveProperty('flagged');
  });
});

describe('ROUTE_TYPE_COLORS', () => {
  it('maps telecom_cable to blue', () => {
    expect(ROUTE_TYPE_COLORS['telecom_cable']).toBe('#3B82F6');
  });

  it('maps power_cable to yellow', () => {
    expect(ROUTE_TYPE_COLORS['power_cable']).toBe('#EAB308');
  });

  it('maps gas_pipeline to orange', () => {
    expect(ROUTE_TYPE_COLORS['gas_pipeline']).toBe('#F97316');
  });

  it('maps oil_pipeline to orange', () => {
    expect(ROUTE_TYPE_COLORS['oil_pipeline']).toBe('#F97316');
  });
});
