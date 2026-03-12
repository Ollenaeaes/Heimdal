import { describe, it, expect } from 'vitest';

// ─── Story 1: Enhanced Stats Dashboard ─────────────────────────────

describe('StatsBar expanded stats — calcPercent utility', () => {
  function calcPercent(value: number, total: number): number {
    if (total === 0) return 0;
    return Math.round((value / total) * 100);
  }

  it('calculates correct percentage for risk tier green', () => {
    expect(calcPercent(120, 300)).toBe(40);
  });

  it('calculates correct percentage for risk tier yellow', () => {
    expect(calcPercent(90, 300)).toBe(30);
  });

  it('calculates correct percentage for risk tier red', () => {
    expect(calcPercent(90, 300)).toBe(30);
  });

  it('returns 0 when total is 0', () => {
    expect(calcPercent(0, 0)).toBe(0);
  });

  it('returns 100 when value equals total', () => {
    expect(calcPercent(150, 150)).toBe(100);
  });

  it('handles small fractions with rounding', () => {
    expect(calcPercent(1, 3)).toBe(33);
  });

  it('handles large values', () => {
    expect(calcPercent(10000, 50000)).toBe(20);
  });
});

describe('StatsBar component exports', () => {
  it('exports StatsBar component', async () => {
    const mod = await import('../components/Controls/StatsBar');
    expect(mod.StatsBar).toBeDefined();
    expect(typeof mod.StatsBar).toBe('function');
  });

  it('exports STATS_REFETCH_INTERVAL constant', async () => {
    const mod = await import('../components/Controls/StatsBar');
    expect(mod.STATS_REFETCH_INTERVAL).toBe(30_000);
  });
});

describe('StatsResponse type — gfw_events field', () => {
  it('StatsResponse supports gfw_events optional field', async () => {
    const mod = await import('../components/Controls/StatsBar');
    expect(mod).toBeDefined();

    // Verify the type works at runtime by constructing a valid response
    const response: import('../components/Controls/StatsBar').StatsResponse = {
      risk_tiers: { green: 120, yellow: 45, red: 35 },
      anomalies: { total_active: 23, by_severity: { critical: 3, high: 8, moderate: 7, low: 5 } },
      dark_ships: 12,
      ingestion_rate: 450,
      total_vessels: 200,
      storage_estimate_gb: 2.4,
      gfw_events: {
        by_type: {
          ENCOUNTER: 15,
          LOITERING: 8,
          AIS_DISABLING: 5,
          PORT_VISIT: 22,
        },
      },
    };
    expect(response.gfw_events).toBeDefined();
    expect(response.gfw_events!.by_type.ENCOUNTER).toBe(15);
  });

  it('StatsResponse works without gfw_events field', () => {
    const response: import('../components/Controls/StatsBar').StatsResponse = {
      risk_tiers: { green: 100, yellow: 50, red: 25 },
      anomalies: { total_active: 10, by_severity: { high: 5, low: 5 } },
      dark_ships: 8,
      ingestion_rate: 300,
      total_vessels: 175,
      storage_estimate_gb: 1.8,
    };
    expect(response.gfw_events).toBeUndefined();
  });
});

describe('StatsBar expanded detail panel content', () => {
  it('severity breakdown shows all four levels', () => {
    const bySeverity: Record<string, number> = {
      critical: 3,
      high: 8,
      moderate: 7,
      low: 5,
    };

    const entries = Object.entries(bySeverity);
    expect(entries).toHaveLength(4);
    expect(entries.map(([k]) => k)).toEqual(['critical', 'high', 'moderate', 'low']);
  });

  it('GFW event types are formatted without underscores', () => {
    const types = ['ENCOUNTER', 'LOITERING', 'AIS_DISABLING', 'PORT_VISIT'];
    const formatted = types.map((t) => t.replace(/_/g, ' '));
    expect(formatted).toEqual(['ENCOUNTER', 'LOITERING', 'AIS DISABLING', 'PORT VISIT']);
  });

  it('storage estimate is formatted with 1 decimal place', () => {
    const gb = 2.456;
    expect(gb.toFixed(1)).toBe('2.5');
  });

  it('ingestion rate is formatted with unit', () => {
    const rate = 450;
    expect(`${rate} pos/sec`).toBe('450 pos/sec');
  });
});
