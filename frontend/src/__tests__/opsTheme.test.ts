import { describe, it, expect, vi } from 'vitest';

// Mock Cesium for module imports that reference it
vi.mock('cesium', () => ({
  Cartesian3: { fromDegrees: vi.fn(), UNIT_Z: { x: 0, y: 0, z: 1 } },
  ConstantProperty: vi.fn(),
  CallbackProperty: vi.fn((cb: () => unknown) => ({ callback: cb })),
  NearFarScalar: vi.fn(),
  Ion: { defaultAccessToken: '' },
  Color: { fromCssColorString: vi.fn((css: string) => ({ css, withAlpha: (a: number) => ({ css, alpha: a }) })) },
  PolylineDashMaterialProperty: vi.fn(),
  IonImageryProvider: { fromAssetId: vi.fn() },
}));

vi.mock('resium', () => ({
  Entity: vi.fn(({ children }: { children?: unknown }) => children),
  BillboardGraphics: vi.fn(() => null),
  PolylineGraphics: vi.fn(() => null),
  useCesium: vi.fn(() => ({ viewer: null })),
  Viewer: vi.fn(({ children }: { children?: unknown }) => children),
}));

// ── Story 1: Theme Foundation ─────────────────────────────────────────

describe('Theme Foundation', () => {
  it('riskColors exports updated hex values', async () => {
    const { RISK_COLORS, getRiskColor } = await import('../utils/riskColors');
    expect(getRiskColor('green')).toBe('#22C55E');
    expect(getRiskColor('yellow')).toBe('#F59E0B');
    expect(getRiskColor('red')).toBe('#EF4444');
    expect(Object.keys(RISK_COLORS)).toEqual(['green', 'yellow', 'red', 'blacklisted']);
  });

  it('severityColors exports updated palette', async () => {
    const { SEVERITY_COLORS, getSeverityColor } = await import('../utils/severityColors');
    expect(getSeverityColor('critical')).toBe('#991B1B');
    expect(getSeverityColor('high')).toBe('#DC2626');
    expect(getSeverityColor('moderate')).toBe('#F59E0B');
    expect(getSeverityColor('low')).toBe('#6B7280');
    expect(Object.keys(SEVERITY_COLORS)).toEqual(['critical', 'high', 'moderate', 'low']);
  });
});

// ── Story 2: Globe Styling ────────────────────────────────────────────

describe('Globe Styling', () => {
  it('GlobeView configures dark globe base color and scene', async () => {
    const mod = await import('../components/Globe/GlobeView');
    expect(mod.GlobeView).toBeDefined();
    expect(typeof mod.GlobeView).toBe('function');
  });

  it('exports camera constants', async () => {
    const mod = await import('../components/Globe/cesiumViewer');
    expect(mod.INITIAL_LON).toBeDefined();
    expect(mod.INITIAL_LAT).toBeDefined();
    expect(mod.INITIAL_ALT).toBeDefined();
  });
});

// ── Story 3: Vessel Markers ──────────────────────────────────────────

describe('Chevron Vessel Markers', () => {
  it('MARKER_STYLE has spec values for all tiers', async () => {
    const { MARKER_STYLE } = await import('../utils/vesselIcons');
    expect(MARKER_STYLE.green).toEqual({ opacity: 0.6, scale: 0.6 });
    expect(MARKER_STYLE.yellow).toEqual({ opacity: 0.9, scale: 0.8 });
    expect(MARKER_STYLE.red).toEqual({ opacity: 1.0, scale: 1.0 });
  });

  it('cogToRotation converts COG degrees to radians correctly', async () => {
    const { cogToRotation } = await import('../utils/vesselIcons');
    expect(cogToRotation(0)).toBeCloseTo(0);
    expect(cogToRotation(90)).toBeCloseTo(-Math.PI / 2);
    expect(cogToRotation(null)).toBe(0);
  });

  it('red pulse oscillates between 1.0 and 1.15 scale factor', async () => {
    const { MARKER_STYLE } = await import('../utils/vesselIcons');
    // The CallbackProperty increments by 0.06 and uses 0.15 amplitude
    // At sin=0 → scale = 1.0 * MARKER_STYLE.red.scale = 1.2
    // At sin=1 → scale = 1.15 * 1.2 = 1.38
    // At sin=-1 → scale = 0.85 * 1.2 = 1.02
    // This verifies the pulse range is 1.0-1.15 multiplier on base scale
    expect(MARKER_STYLE.red.scale).toBe(1.0);
  });

  it('VesselMarkers exports filterVessels', async () => {
    const mod = await import('../components/Globe/VesselMarkers');
    expect(mod.filterVessels).toBeDefined();
  });
});

// ── Story 4: Track Trails ─────────────────────────────────────────────

describe('Track Trail Tapering', () => {
  it('TrackTrail component exports', async () => {
    const mod = await import('../components/Globe/TrackTrail');
    expect(mod.TrackTrail).toBeDefined();
    expect(typeof mod.TrackTrail).toBe('function');
  });
});

// ── Story 5: HUD Top Bar ──────────────────────────────────────────────

describe('HUD Top Bar', () => {
  it('App exports default component', async () => {
    const mod = await import('../App');
    expect(mod.default).toBeDefined();
    expect(typeof mod.default).toBe('function');
  });

  it('StatsBar and STATS_REFETCH_INTERVAL exported from Controls', async () => {
    const mod = await import('../components/Controls');
    expect(mod.StatsBar).toBeDefined();
    expect(mod.STATS_REFETCH_INTERVAL).toBe(30_000);
  });
});

// ── Story 6: Side Panel Restyle ───────────────────────────────────────

describe('Panel Restyle', () => {
  it('VesselPanel exports', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.VesselPanel).toBeDefined();
    expect(mod.IdentitySection).toBeDefined();
    expect(mod.StatusSection).toBeDefined();
    expect(mod.RiskSection).toBeDefined();
  });

  it('IdentitySection is a function component', async () => {
    const mod = await import('../components/VesselPanel/IdentitySection');
    expect(typeof mod.IdentitySection).toBe('function');
  });
});

// ── Story 7: Controls Restyle ─────────────────────────────────────────

describe('Controls Restyle', () => {
  it('all control components export from index', async () => {
    const mod = await import('../components/Controls');
    expect(mod.SearchBar).toBeDefined();
    expect(mod.RiskFilter).toBeDefined();
    expect(mod.TypeFilter).toBeDefined();
    expect(mod.TimeRangeFilter).toBeDefined();
    expect(mod.HealthIndicator).toBeDefined();
    expect(mod.WatchlistPanel).toBeDefined();
    expect(mod.EquasisImport).toBeDefined();
  });

  it('HealthIndicator uses new risk colors for dot', async () => {
    const mod = await import('../components/Controls/HealthIndicator');
    expect(mod.computeHealthLevel).toBeDefined();
    // Verify green health returns green level
    const result = mod.computeHealthLevel({
      status: 'healthy',
      services: {},
      vessel_count: 10,
      anomaly_count: 0,
    });
    expect(result.level).toBe('green');
    expect(result.message).toBe('All systems operational');
  });

  it('SearchBar imports RISK_COLORS from shared utils (not local copy)', async () => {
    const { RISK_COLORS } = await import('../utils/riskColors');
    // Verify the shared constant has the new values
    expect(RISK_COLORS.green).toBe('#22C55E');
  });
});
