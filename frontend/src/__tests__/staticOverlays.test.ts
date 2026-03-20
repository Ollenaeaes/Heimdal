import { describe, it, expect } from 'vitest';
import stsZonesData from '../data/stsZones.json';
import terminalsData from '../data/terminals.json';

describe('Static Overlay Data', () => {
  describe('STS Zones', () => {
    it('imports as a valid GeoJSON FeatureCollection', () => {
      expect(stsZonesData.type).toBe('FeatureCollection');
      expect(Array.isArray(stsZonesData.features)).toBe(true);
      expect(stsZonesData.features.length).toBeGreaterThan(0);
    });

    it('each feature has name, id, and Polygon geometry', () => {
      for (const feature of stsZonesData.features) {
        expect(feature.type).toBe('Feature');
        expect(feature.properties.name).toBeDefined();
        expect(typeof feature.properties.name).toBe('string');
        expect(feature.properties.id).toBeDefined();
        expect(feature.geometry.type).toBe('Polygon');
        expect(Array.isArray(feature.geometry.coordinates)).toBe(true);
        expect(feature.geometry.coordinates[0].length).toBeGreaterThanOrEqual(4);
      }
    });

    it('contains known STS zones', () => {
      const names = stsZonesData.features.map((f) => f.properties.name);
      expect(names).toContain('Kalamata, Greece');
      expect(names).toContain('Laconian Gulf, Greece');
    });
  });

  describe('Terminals', () => {
    it('imports as a valid GeoJSON FeatureCollection', () => {
      expect(terminalsData.type).toBe('FeatureCollection');
      expect(Array.isArray(terminalsData.features)).toBe(true);
      expect(terminalsData.features.length).toBeGreaterThan(0);
    });

    it('each feature has name, id, and Point geometry', () => {
      for (const feature of terminalsData.features) {
        expect(feature.type).toBe('Feature');
        expect(feature.properties.name).toBeDefined();
        expect(typeof feature.properties.name).toBe('string');
        expect(feature.properties.id).toBeDefined();
        expect(feature.geometry.type).toBe('Point');
        expect(feature.geometry.coordinates).toHaveLength(2);
        const [lon, lat] = feature.geometry.coordinates;
        expect(lon).toBeGreaterThanOrEqual(-180);
        expect(lon).toBeLessThanOrEqual(180);
        expect(lat).toBeGreaterThanOrEqual(-90);
        expect(lat).toBeLessThanOrEqual(90);
      }
    });

    it('contains known Russian terminals', () => {
      const names = terminalsData.features.map((f) => f.properties.name);
      expect(names).toContain('Primorsk');
      expect(names).toContain('Novorossiysk');
      expect(names).toContain('Murmansk');
    });
  });

  describe('StaticOverlays component', () => {
    it('exports StaticOverlays and StaticOverlaysProps', async () => {
      const mod = await import('../components/Map/StaticOverlays');
      expect(mod.StaticOverlays).toBeDefined();
      expect(typeof mod.StaticOverlays).toBe('function');
    });
  });
});
