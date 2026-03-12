import { describe, it, expect } from 'vitest';

describe('GlobeView module', () => {
  it('exports GlobeView component and camera constants', async () => {
    const mod = await import('../components/Globe');
    expect(mod.GlobeView).toBeDefined();
    expect(typeof mod.GlobeView).toBe('function');
    expect(mod.INITIAL_LON).toBeDefined();
    expect(mod.INITIAL_LAT).toBeDefined();
    expect(mod.INITIAL_ALT).toBeDefined();
  });

  it('has correct initial camera position constants', async () => {
    const { INITIAL_LON, INITIAL_LAT, INITIAL_ALT } = await import('../components/Globe');
    expect(INITIAL_LON).toBe(15);
    expect(INITIAL_LAT).toBe(68);
    expect(INITIAL_ALT).toBe(5_000_000);
  });
});
