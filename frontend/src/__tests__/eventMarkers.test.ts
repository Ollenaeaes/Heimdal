import { describe, it, expect } from 'vitest';
import { buildGfwEventsGeoJson } from '../components/Map/GfwEventLayer';
import { buildSarGeoJson } from '../components/Map/SarDetectionLayer';

// ---- GFW Events ----

describe('buildGfwEventsGeoJson', () => {
  const sampleEvents = [
    {
      id: 'evt-1',
      type: 'ENCOUNTER',
      startTime: '2025-01-01T00:00:00Z',
      endTime: '2025-01-01T02:00:00Z',
      lat: 10.5,
      lon: 20.5,
      vesselMmsi: 123456789,
      vesselName: 'Nordic Star',
      encounterPartnerMmsi: 987654321,
      encounterPartnerName: 'Pacific Wanderer',
      portName: null,
      durationHours: 2.0,
    },
    {
      id: 'evt-2',
      type: 'LOITERING',
      startTime: '2025-01-02T00:00:00Z',
      endTime: null,
      lat: 15.0,
      lon: 25.0,
      vesselMmsi: 111222333,
      vesselName: 'Sea Breeze',
      encounterPartnerMmsi: null,
      encounterPartnerName: null,
      portName: null,
      durationHours: 8.5,
    },
    {
      id: 'evt-3',
      type: 'AIS_DISABLING',
      startTime: '2025-01-03T00:00:00Z',
      endTime: '2025-01-03T12:00:00Z',
      lat: -5.0,
      lon: 40.0,
      vesselMmsi: 444555666,
      vesselName: 'Shadow Runner',
      encounterPartnerMmsi: null,
      encounterPartnerName: null,
      portName: null,
      durationHours: 12.0,
    },
    {
      id: 'evt-4',
      type: 'PORT_VISIT',
      startTime: '2025-01-04T00:00:00Z',
      endTime: '2025-01-04T06:00:00Z',
      lat: 1.3,
      lon: 103.8,
      vesselMmsi: 777888999,
      vesselName: 'Coastal Trader',
      encounterPartnerMmsi: null,
      encounterPartnerName: null,
      portName: 'Singapore',
      durationHours: 6.0,
    },
  ];

  it('filters by event type', () => {
    const result = buildGfwEventsGeoJson(sampleEvents, ['ENCOUNTER', 'LOITERING']);
    expect(result.features).toHaveLength(2);
    expect(result.features[0].properties.type).toBe('ENCOUNTER');
    expect(result.features[1].properties.type).toBe('LOITERING');
  });

  it('produces correct GeoJSON structure', () => {
    const result = buildGfwEventsGeoJson(sampleEvents, ['ENCOUNTER']);
    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(1);

    const feature = result.features[0];
    expect(feature.type).toBe('Feature');
    expect(feature.geometry.type).toBe('Point');
    expect(feature.geometry.coordinates).toEqual([20.5, 10.5]);
    expect(feature.properties.id).toBe('evt-1');
    expect(feature.properties.type).toBe('ENCOUNTER');
    expect(feature.properties.start).toBe('2025-01-01T00:00:00Z');
    expect(feature.properties.end).toBe('2025-01-01T02:00:00Z');
    expect(feature.properties.duration_hours).toBe(2.0);
    expect(feature.properties.mmsi).toBe(123456789);
    expect(feature.properties.vessel_name).toBe('Nordic Star');
  });

  it('returns empty FeatureCollection for empty array', () => {
    const result = buildGfwEventsGeoJson([], ['ENCOUNTER']);
    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(0);
  });

  it('returns empty FeatureCollection when no types match', () => {
    const result = buildGfwEventsGeoJson(sampleEvents, []);
    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(0);
  });

  it('includes all types when all are selected', () => {
    const result = buildGfwEventsGeoJson(sampleEvents, [
      'ENCOUNTER',
      'LOITERING',
      'AIS_DISABLING',
      'PORT_VISIT',
    ]);
    expect(result.features).toHaveLength(4);
  });
});

// ---- SAR Detections ----

describe('buildSarGeoJson', () => {
  const sampleDetections = [
    {
      id: 'sar-1',
      detectedAt: '2025-01-01T10:00:00Z',
      lat: 12.0,
      lon: 45.0,
      estimatedLength: 85,
      isDark: true,
      matchingScore: null,
      fishingScore: 0.8,
      matchedMmsi: null,
      matchedVesselName: null,
    },
    {
      id: 'sar-2',
      detectedAt: '2025-01-01T11:00:00Z',
      lat: 13.0,
      lon: 46.0,
      estimatedLength: 120,
      isDark: false,
      matchingScore: 0.92,
      fishingScore: 0.1,
      matchedMmsi: 222333444,
      matchedVesselName: 'Atlantic Carrier',
    },
    {
      id: 'sar-3',
      detectedAt: '2025-01-01T12:00:00Z',
      lat: 14.0,
      lon: 47.0,
      estimatedLength: null,
      isDark: true,
      matchingScore: null,
      fishingScore: null,
      matchedMmsi: null,
      matchedVesselName: null,
    },
  ];

  it('filters dark-only when flag is set', () => {
    const result = buildSarGeoJson(sampleDetections, true);
    expect(result.features).toHaveLength(2);
    expect(result.features.every((f: any) => f.properties.is_dark === true)).toBe(true);
  });

  it('includes all when darkOnly is false', () => {
    const result = buildSarGeoJson(sampleDetections, false);
    expect(result.features).toHaveLength(3);
  });

  it('produces correct GeoJSON structure', () => {
    const result = buildSarGeoJson(sampleDetections, false);
    expect(result.type).toBe('FeatureCollection');

    const feature = result.features[1];
    expect(feature.type).toBe('Feature');
    expect(feature.geometry.type).toBe('Point');
    expect(feature.geometry.coordinates).toEqual([46.0, 13.0]);
    expect(feature.properties.id).toBe('sar-2');
    expect(feature.properties.is_dark).toBe(false);
    expect(feature.properties.length_m).toBe(120);
    expect(feature.properties.matching_score).toBe(0.92);
    expect(feature.properties.fishing_score).toBe(0.1);
  });

  it('returns empty FeatureCollection for empty array', () => {
    const result = buildSarGeoJson([], false);
    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(0);
  });

  it('returns empty FeatureCollection when all are non-dark and darkOnly is true', () => {
    const nonDarkOnly = [sampleDetections[1]]; // only the matched one
    const result = buildSarGeoJson(nonDarkOnly, true);
    expect(result.type).toBe('FeatureCollection');
    expect(result.features).toHaveLength(0);
  });
});
