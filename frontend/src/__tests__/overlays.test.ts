import { describe, it, expect } from 'vitest';

import stsZonesData from '../data/stsZones.json';
import terminalsData from '../data/terminals.json';
import eezData from '../data/eezBoundaries.json';

describe('Overlay data loading', () => {
  it('loads 6 STS zone polygons', () => {
    expect(stsZonesData.type).toBe('FeatureCollection');
    expect(stsZonesData.features).toHaveLength(6);
  });

  it('STS zones have correct names and polygon geometry', () => {
    const expectedNames = [
      'Kalamata, Greece',
      'Laconian Gulf, Greece',
      'Ceuta, Spain',
      'Lome, Togo',
      'South of Malta',
      'UAE/Fujairah',
    ];
    const names = stsZonesData.features.map((f) => f.properties.name);
    expect(names).toEqual(expectedNames);

    for (const feature of stsZonesData.features) {
      expect(feature.geometry.type).toBe('Polygon');
      expect(feature.geometry.coordinates).toHaveLength(1); // single ring
      expect(feature.geometry.coordinates[0].length).toBeGreaterThanOrEqual(4); // closed polygon
    }
  });

  it('loads 7 terminal point markers', () => {
    expect(terminalsData.type).toBe('FeatureCollection');
    expect(terminalsData.features).toHaveLength(7);
  });

  it('terminals have correct names and point geometry', () => {
    const expectedNames = [
      'Primorsk',
      'Ust-Luga',
      'Novorossiysk',
      'Kozmino',
      'Murmansk',
      'De-Kastri',
      'Vysotsk',
    ];
    const names = terminalsData.features.map((f) => f.properties.name);
    expect(names).toEqual(expectedNames);

    for (const feature of terminalsData.features) {
      expect(feature.geometry.type).toBe('Point');
      expect(feature.geometry.coordinates).toHaveLength(2); // [lon, lat]
    }
  });

  it('terminals are at correct coordinates', () => {
    const primorsk = terminalsData.features.find((f) => f.properties.name === 'Primorsk');
    expect(primorsk).toBeDefined();
    expect(primorsk!.geometry.coordinates).toEqual([28.67, 60.35]);

    const kozmino = terminalsData.features.find((f) => f.properties.name === 'Kozmino');
    expect(kozmino).toBeDefined();
    expect(kozmino!.geometry.coordinates).toEqual([132.89, 42.73]);
  });

  it('STS zones are at correct locations', () => {
    const kalamata = stsZonesData.features.find((f) => f.properties.id === 'sts-kalamata');
    expect(kalamata).toBeDefined();
    // Kalamata polygon should be around lon 22, lat 37 (Greece)
    const coords = kalamata!.geometry.coordinates[0];
    const lons = coords.map((c) => c[0]);
    const lats = coords.map((c) => c[1]);
    expect(Math.min(...lons)).toBeCloseTo(22.01, 1);
    expect(Math.max(...lats)).toBeCloseTo(37.05, 1);

    const fujairah = stsZonesData.features.find((f) => f.properties.id === 'sts-fujairah');
    expect(fujairah).toBeDefined();
    // Fujairah polygon should be around lon 56, lat 25 (UAE)
    const fCoords = fujairah!.geometry.coordinates[0];
    const fLons = fCoords.map((c) => c[0]);
    expect(Math.min(...fLons)).toBeCloseTo(56.23, 1);
  });

  it('loads Norwegian EEZ boundary', () => {
    expect(eezData.type).toBe('FeatureCollection');
    expect(eezData.features).toHaveLength(1);
    expect(eezData.features[0].properties.name).toBe('Norwegian EEZ');
    expect(eezData.features[0].geometry.type).toBe('LineString');
    expect(eezData.features[0].geometry.coordinates.length).toBeGreaterThan(5);
  });
});

describe('OverlayToggles component', () => {
  it('exports OverlayToggles component', async () => {
    const { OverlayToggles } = await import('../components/Map/OverlayToggles');
    expect(OverlayToggles).toBeDefined();
    expect(typeof OverlayToggles).toBe('function');
  });
});
