import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createMapStyle } from '../components/Map/style';

describe('createMapStyle', () => {
  const originalEnv = import.meta.env.VITE_MAPTILER_KEY;

  beforeEach(() => {
    // Ensure env var is set for tests
    import.meta.env.VITE_MAPTILER_KEY = 'test-key-123';
  });

  afterEach(() => {
    if (originalEnv !== undefined) {
      import.meta.env.VITE_MAPTILER_KEY = originalEnv;
    } else {
      delete import.meta.env.VITE_MAPTILER_KEY;
    }
  });

  it('returns a valid style spec version 8', () => {
    const style = createMapStyle();
    expect(style.version).toBe(8);
  });

  it('includes openmaptiles vector source with key', () => {
    const style = createMapStyle();
    const source = style.sources.openmaptiles;
    expect(source).toBeDefined();
    expect(source.type).toBe('vector');
    expect((source as { url?: string }).url).toContain('test-key-123');
  });

  it('includes glyphs URL with key', () => {
    const style = createMapStyle();
    expect(style.glyphs).toContain('test-key-123');
    expect(style.glyphs).toContain('api.maptiler.com/fonts');
  });

  it('has a background layer with water color #F8FAFC', () => {
    const style = createMapStyle();
    const bg = style.layers.find((l) => l.id === 'background');
    expect(bg).toBeDefined();
    expect(bg!.type).toBe('background');
    expect((bg as any).paint['background-color']).toBe('#F8FAFC');
  });

  it('has water fill matching background', () => {
    const style = createMapStyle();
    const water = style.layers.find((l) => l.id === 'water');
    expect(water).toBeDefined();
    expect((water as any).paint['fill-color']).toBe('#F8FAFC');
  });

  it('has land fill with slate-200 color', () => {
    const style = createMapStyle();
    const land = style.layers.find((l) => l.id === 'landcover');
    expect(land).toBeDefined();
    expect((land as any).paint['fill-color']).toBe('#E2E8F0');
  });

  it('has shoreline stroke with slate-400 color', () => {
    const style = createMapStyle();
    const shore = style.layers.find((l) => l.id === 'shoreline');
    expect(shore).toBeDefined();
    expect((shore as any).paint['line-color']).toBe('#94A3B8');
  });

  it('has country boundary with slate-300 color', () => {
    const style = createMapStyle();
    const boundary = style.layers.find((l) => l.id === 'boundary-country');
    expect(boundary).toBeDefined();
    expect((boundary as any).paint['line-color']).toBe('#CBD5E1');
  });

  it('has place labels with slate-600 text color', () => {
    const style = createMapStyle();
    const labels = style.layers.find((l) => l.id === 'place-labels');
    expect(labels).toBeDefined();
    expect((labels as any).paint['text-color']).toBe('#475569');
  });

  it('has industrial landuse layer with different gray', () => {
    const style = createMapStyle();
    const industrial = style.layers.find((l) => l.id === 'landuse-industrial');
    expect(industrial).toBeDefined();
    expect((industrial as any).paint['fill-color']).toBe('#D1D5DB');
  });

  it('contains all required layer types', () => {
    const style = createMapStyle();
    const layerIds = style.layers.map((l) => l.id);
    expect(layerIds).toContain('background');
    expect(layerIds).toContain('landcover');
    expect(layerIds).toContain('water');
    expect(layerIds).toContain('shoreline');
    expect(layerIds).toContain('boundary-country');
    expect(layerIds).toContain('place-labels');
    expect(layerIds).toContain('landuse-industrial');
  });

  it('falls back to empty string when env var is missing', () => {
    delete import.meta.env.VITE_MAPTILER_KEY;
    const style = createMapStyle();
    // Should not throw, just use empty key
    expect(style.version).toBe(8);
    expect((style.sources.openmaptiles as { url?: string }).url).toContain('key=');
  });
});
