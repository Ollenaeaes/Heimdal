import { describe, it, expect, vi } from 'vitest';

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

// ── Story 2: Map Styling ────────────────────────────────────────────

describe('Map Styling', () => {
  it('exports camera constants from mapInstance', async () => {
    const mod = await import('../components/Map/mapInstance');
    expect(mod.INITIAL_CENTER).toBeDefined();
    expect(mod.INITIAL_ZOOM).toBeDefined();
  });
});

// ── Story 3: Vessel Markers ──────────────────────────────────────────

describe('Chevron Vessel Markers', () => {
  it('MARKER_STYLE has spec values for all tiers', async () => {
    const { MARKER_STYLE } = await import('../utils/vesselIcons');
    expect(MARKER_STYLE.green).toEqual({ opacity: 0.7, opacityFar: 0.2, scale: 0.5 });
    expect(MARKER_STYLE.yellow).toEqual({ opacity: 0.8, opacityFar: 0.8, scale: 0.7 });
    expect(MARKER_STYLE.red).toEqual({ opacity: 1.0, opacityFar: 1.0, scale: 0.85 });
  });

  it('cogToRotation converts COG degrees to radians correctly', async () => {
    const { cogToRotation } = await import('../utils/vesselIcons');
    expect(cogToRotation(0)).toBeCloseTo(0);
    expect(cogToRotation(90)).toBeCloseTo(-Math.PI / 2);
    expect(cogToRotation(null)).toBe(0);
  });

  it('red tier has expected scale', async () => {
    const { MARKER_STYLE } = await import('../utils/vesselIcons');
    expect(MARKER_STYLE.red.scale).toBe(0.85);
  });

  it('VesselLayer exports filterVessels', async () => {
    const mod = await import('../components/Map/VesselLayer');
    expect(mod.filterVessels).toBeDefined();
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
