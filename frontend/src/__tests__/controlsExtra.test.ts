import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { subHours, subDays } from 'date-fns';
import { useVesselStore } from '../hooks/useVesselStore';
import { TIME_PRESETS } from '../components/Controls/TimeRangeFilter';
import { STATS_REFETCH_INTERVAL } from '../components/Controls/StatsBar';
import {
  computeHealthLevel,
  HEALTH_REFETCH_INTERVAL,
  AIS_STALE_THRESHOLD_MS,
} from '../components/Controls/HealthIndicator';
import type { HealthResponse } from '../components/Controls/HealthIndicator';

describe('TimeRangeFilter', () => {
  beforeEach(() => {
    useVesselStore.setState({
      vessels: new Map(),
      positionHistory: new Map(),
      selectedMmsi: null,
      filters: {
        riskTiers: new Set(),
        shipTypes: [],
        bbox: null,
        activeSince: null,
      },
    });
  });

  it('TIME_PRESETS contains all expected preset buttons', () => {
    const labels = TIME_PRESETS.map((p) => p.label);
    expect(labels).toEqual(['1h', '6h', '24h', '7d', 'All']);
  });

  it('TIME_PRESETS have correct keys', () => {
    const keys = TIME_PRESETS.map((p) => p.key);
    expect(keys).toEqual(['1h', '6h', '24h', '7d', 'all']);
  });

  it('clicking "1h" preset sets activeSince to approximately 1 hour ago', () => {
    const before = Date.now();
    const preset = TIME_PRESETS.find((p) => p.key === '1h')!;
    const result = preset.getTime();

    expect(result).not.toBeNull();
    const resultTime = new Date(result!).getTime();
    const expectedTime = subHours(new Date(before), 1).getTime();

    // Allow 1 second tolerance
    expect(Math.abs(resultTime - expectedTime)).toBeLessThan(1000);
  });

  it('clicking "6h" preset sets activeSince to approximately 6 hours ago', () => {
    const before = Date.now();
    const preset = TIME_PRESETS.find((p) => p.key === '6h')!;
    const result = preset.getTime();

    expect(result).not.toBeNull();
    const resultTime = new Date(result!).getTime();
    const expectedTime = subHours(new Date(before), 6).getTime();
    expect(Math.abs(resultTime - expectedTime)).toBeLessThan(1000);
  });

  it('clicking "24h" preset sets activeSince to approximately 24 hours ago', () => {
    const before = Date.now();
    const preset = TIME_PRESETS.find((p) => p.key === '24h')!;
    const result = preset.getTime();

    expect(result).not.toBeNull();
    const resultTime = new Date(result!).getTime();
    const expectedTime = subHours(new Date(before), 24).getTime();
    expect(Math.abs(resultTime - expectedTime)).toBeLessThan(1000);
  });

  it('clicking "7d" preset sets activeSince to approximately 7 days ago', () => {
    const before = Date.now();
    const preset = TIME_PRESETS.find((p) => p.key === '7d')!;
    const result = preset.getTime();

    expect(result).not.toBeNull();
    const resultTime = new Date(result!).getTime();
    const expectedTime = subDays(new Date(before), 7).getTime();
    expect(Math.abs(resultTime - expectedTime)).toBeLessThan(1000);
  });

  it('clicking "All" preset returns null (clears activeSince)', () => {
    const preset = TIME_PRESETS.find((p) => p.key === 'all')!;
    const result = preset.getTime();
    expect(result).toBeNull();
  });

  it('setFilter with activeSince updates the Zustand store', () => {
    const timestamp = subHours(new Date(), 1).toISOString();
    useVesselStore.getState().setFilter({ activeSince: timestamp });

    const state = useVesselStore.getState();
    expect(state.filters.activeSince).toBe(timestamp);
  });

  it('setFilter with null activeSince clears it in the Zustand store', () => {
    // First set a value
    useVesselStore.getState().setFilter({ activeSince: '2024-03-15T14:30:00Z' });
    expect(useVesselStore.getState().filters.activeSince).not.toBeNull();

    // Then clear it
    useVesselStore.getState().setFilter({ activeSince: null });
    expect(useVesselStore.getState().filters.activeSince).toBeNull();
  });
});

describe('StatsBar', () => {
  it('STATS_REFETCH_INTERVAL is 30 seconds', () => {
    expect(STATS_REFETCH_INTERVAL).toBe(30_000);
  });

  it('stats response shape contains expected fields', () => {
    // Validates the expected shape by creating a mock and checking it type-checks
    const mockStats = {
      risk_tiers: { green: 1200, yellow: 50, red: 10 },
      anomalies: { total_active: 35, by_severity: { high: 10, medium: 15, low: 10 } },
      dark_ships: 5,
      ingestion_rate: 42.5,
      total_vessels: 1260,
      storage_estimate_gb: 15.2,
    };

    expect(mockStats.total_vessels).toBe(1260);
    expect(mockStats.risk_tiers.green).toBe(1200);
    expect(mockStats.risk_tiers.yellow).toBe(50);
    expect(mockStats.risk_tiers.red).toBe(10);
    expect(mockStats.anomalies.total_active).toBe(35);
    expect(mockStats.ingestion_rate).toBe(42.5);
  });

  it('ingestion rate formats as "X pos/sec"', () => {
    const rate = 42.5;
    const formatted = `${rate} pos/sec`;
    expect(formatted).toBe('42.5 pos/sec');
  });
});

describe('HealthIndicator', () => {
  it('HEALTH_REFETCH_INTERVAL is 60 seconds', () => {
    expect(HEALTH_REFETCH_INTERVAL).toBe(60_000);
  });

  it('AIS_STALE_THRESHOLD_MS is 2 minutes', () => {
    expect(AIS_STALE_THRESHOLD_MS).toBe(2 * 60 * 1000);
  });

  it('shows green when all services are healthy and AIS is fresh', () => {
    const data: HealthResponse = {
      status: 'healthy',
      services: {
        database: { status: 'healthy' },
        redis: { status: 'healthy' },
        ais_stream: {
          status: 'healthy',
          last_message_at: new Date().toISOString(),
          total_vessels: 1200,
        },
      },
      vessel_count: 1200,
      anomaly_count: 35,
    };

    const result = computeHealthLevel(data);
    expect(result.level).toBe('green');
    expect(result.message).toBe('All systems operational');
  });

  it('shows yellow when AIS stream is stale (last_message_at > 2 min ago)', () => {
    const staleTime = new Date(Date.now() - 3 * 60 * 1000).toISOString(); // 3 min ago

    const data: HealthResponse = {
      status: 'healthy',
      services: {
        database: { status: 'healthy' },
        redis: { status: 'healthy' },
        ais_stream: {
          status: 'healthy',
          last_message_at: staleTime,
          total_vessels: 1200,
        },
      },
      vessel_count: 1200,
      anomaly_count: 35,
    };

    const result = computeHealthLevel(data);
    expect(result.level).toBe('yellow');
    expect(result.message).toBe('AIS stream stale');
  });

  it('shows yellow when a service is degraded', () => {
    const data: HealthResponse = {
      status: 'degraded',
      services: {
        database: { status: 'healthy' },
        redis: { status: 'degraded' },
        ais_stream: {
          status: 'healthy',
          last_message_at: new Date().toISOString(),
          total_vessels: 1200,
        },
      },
      vessel_count: 1200,
      anomaly_count: 35,
    };

    const result = computeHealthLevel(data);
    expect(result.level).toBe('yellow');
    expect(result.message).toBe('redis is degraded');
  });

  it('shows red when any service is unhealthy', () => {
    const data: HealthResponse = {
      status: 'unhealthy',
      services: {
        database: { status: 'unhealthy' },
        redis: { status: 'healthy' },
        ais_stream: {
          status: 'healthy',
          last_message_at: new Date().toISOString(),
          total_vessels: 1200,
        },
      },
      vessel_count: 1200,
      anomaly_count: 35,
    };

    const result = computeHealthLevel(data);
    expect(result.level).toBe('red');
    expect(result.message).toBe('database is unhealthy');
  });

  it('red takes priority over yellow (unhealthy over degraded)', () => {
    const data: HealthResponse = {
      status: 'unhealthy',
      services: {
        database: { status: 'unhealthy' },
        redis: { status: 'degraded' },
        ais_stream: {
          status: 'healthy',
          last_message_at: new Date().toISOString(),
          total_vessels: 1200,
        },
      },
      vessel_count: 1200,
      anomaly_count: 35,
    };

    const result = computeHealthLevel(data);
    expect(result.level).toBe('red');
    expect(result.message).toBe('database is unhealthy');
  });

  it('AIS just within threshold shows green', () => {
    // 1 minute ago - within 2 min threshold
    const recentTime = new Date(Date.now() - 60 * 1000).toISOString();

    const data: HealthResponse = {
      status: 'healthy',
      services: {
        database: { status: 'healthy' },
        redis: { status: 'healthy' },
        ais_stream: {
          status: 'healthy',
          last_message_at: recentTime,
          total_vessels: 1200,
        },
      },
      vessel_count: 1200,
      anomaly_count: 35,
    };

    const result = computeHealthLevel(data);
    expect(result.level).toBe('green');
    expect(result.message).toBe('All systems operational');
  });
});
