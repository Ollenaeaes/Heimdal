import { describe, it, expect, vi } from 'vitest';

// Mock Cesium before imports
vi.mock('cesium', () => ({
  Cartesian3: {
    fromDegrees: vi.fn((lon: number, lat: number, alt?: number) => ({
      x: lon,
      y: lat,
      z: alt ?? 0,
    })),
    UNIT_Z: { x: 0, y: 0, z: 1 },
  },
  ConstantProperty: vi.fn((val: unknown) => ({ value: val })),
  CallbackProperty: vi.fn((cb: () => unknown) => ({ callback: cb })),
  NearFarScalar: vi.fn(
    (near: number, nearVal: number, far: number, farVal: number) => ({
      near,
      nearValue: nearVal,
      far,
      farValue: farVal,
    }),
  ),
  EntityCluster: vi.fn(),
  Color: {
    fromCssColorString: vi.fn((css: string) => ({ css })),
  },
  Ion: { defaultAccessToken: '' },
  MaterialProperty: {},
}));

vi.mock('resium', () => ({
  Entity: vi.fn(({ children }: { children?: unknown }) => children),
  BillboardGraphics: vi.fn(() => null),
  CustomDataSource: vi.fn(({ children }: { children?: unknown }) => children),
  useCesium: vi.fn(() => ({ viewer: null })),
  Viewer: vi.fn(({ children }: { children?: unknown }) => children),
  CameraFlyTo: vi.fn(() => null),
}));

import { getHighestRiskTier, CLUSTER_PIXEL_RANGE } from '../components/Globe/VesselCluster';
import type { RiskTier } from '../utils/riskColors';

describe('CLUSTER_PIXEL_RANGE', () => {
  it('uses 50 pixels as the cluster threshold', () => {
    expect(CLUSTER_PIXEL_RANGE).toBe(50);
  });
});

describe('getHighestRiskTier', () => {
  it('returns green for empty array', () => {
    expect(getHighestRiskTier([])).toBe('green');
  });

  it('returns green when all vessels are green', () => {
    expect(getHighestRiskTier(['green', 'green', 'green'])).toBe('green');
  });

  it('returns yellow when highest is yellow', () => {
    expect(getHighestRiskTier(['green', 'yellow'])).toBe('yellow');
  });

  it('returns red when any vessel is red', () => {
    expect(getHighestRiskTier(['green', 'red'])).toBe('red');
  });

  it('returns red when mixed green, yellow, red', () => {
    expect(getHighestRiskTier(['green', 'yellow', 'red'])).toBe('red');
  });

  it('returns yellow for yellow-only cluster', () => {
    expect(getHighestRiskTier(['yellow', 'yellow'])).toBe('yellow');
  });

  it('returns red for red-only cluster', () => {
    expect(getHighestRiskTier(['red', 'red', 'red'])).toBe('red');
  });

  it('returns red when green and red are present (no yellow)', () => {
    const tiers: RiskTier[] = ['green', 'green', 'red'];
    expect(getHighestRiskTier(tiers)).toBe('red');
  });
});

describe('VesselCluster component', () => {
  it('exports VesselCluster as a function', async () => {
    const mod = await import('../components/Globe/VesselCluster');
    expect(mod.VesselCluster).toBeDefined();
    expect(typeof mod.VesselCluster).toBe('function');
  });
});
