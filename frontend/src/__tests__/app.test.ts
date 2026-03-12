import { describe, it, expect } from 'vitest';

describe('App module', () => {
  it('exports a default App component', async () => {
    const mod = await import('../App');
    expect(mod.default).toBeDefined();
    expect(typeof mod.default).toBe('function');
  });
});
