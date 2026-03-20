import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createMinimapStyle } from '../components/Map/Minimap';

describe('Minimap', () => {
  const originalEnv = import.meta.env.VITE_MAPTILER_KEY;

  beforeEach(() => {
    import.meta.env.VITE_MAPTILER_KEY = 'test-key-123';
  });

  afterEach(() => {
    if (originalEnv !== undefined) {
      import.meta.env.VITE_MAPTILER_KEY = originalEnv;
    } else {
      delete import.meta.env.VITE_MAPTILER_KEY;
    }
  });

  describe('createMinimapStyle', () => {
    it('returns a valid style spec version 8', () => {
      const style = createMinimapStyle();
      expect(style.version).toBe(8);
    });

    it('includes openmaptiles vector source with key', () => {
      const style = createMinimapStyle();
      const source = style.sources.openmaptiles;
      expect(source).toBeDefined();
      expect(source.type).toBe('vector');
      expect((source as { url?: string }).url).toContain('test-key-123');
    });

    it('has a background layer', () => {
      const style = createMinimapStyle();
      const bg = style.layers.find((l) => l.id === 'background');
      expect(bg).toBeDefined();
      expect(bg!.type).toBe('background');
      expect((bg as any).paint['background-color']).toBe('#F8FAFC');
    });

    it('has a land layer with fill color', () => {
      const style = createMinimapStyle();
      const land = style.layers.find((l) => l.id === 'land');
      expect(land).toBeDefined();
      expect(land!.type).toBe('fill');
      expect((land as any).paint['fill-color']).toBe('#E2E8F0');
    });

    it('has a water layer matching background color', () => {
      const style = createMinimapStyle();
      const water = style.layers.find((l) => l.id === 'water');
      expect(water).toBeDefined();
      expect(water!.type).toBe('fill');
      expect((water as any).paint['fill-color']).toBe('#F8FAFC');
    });

    it('has exactly 3 layers (background, land, water) — no labels or roads', () => {
      const style = createMinimapStyle();
      expect(style.layers).toHaveLength(3);
      const ids = style.layers.map((l) => l.id);
      expect(ids).toEqual(['background', 'land', 'water']);
    });

    it('does not include glyphs (no labels needed)', () => {
      const style = createMinimapStyle();
      expect(style.glyphs).toBeUndefined();
    });

    it('falls back to empty string when env var is missing', () => {
      delete import.meta.env.VITE_MAPTILER_KEY;
      const style = createMinimapStyle();
      expect(style.version).toBe(8);
      expect((style.sources.openmaptiles as { url?: string }).url).toContain('key=');
    });
  });

  describe('Minimap component', () => {
    it('exports a default component', async () => {
      const mod = await import('../components/Map/Minimap');
      expect(mod.default).toBeDefined();
      expect(typeof mod.default).toBe('function');
    });
  });
});
