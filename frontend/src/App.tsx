import { useState, useEffect, lazy, Suspense } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { SearchBar, RiskFilter, TypeFilter, TimeRangeFilter, HealthIndicator, WatchlistPanel, EquasisImport, STATS_REFETCH_INTERVAL } from './components/Controls';
import type { StatsResponse } from './components/Controls';
import { useWatchlistAlerts } from './hooks/useWatchlist';
import { useWebSocket } from './hooks/useWebSocket';
import { useOverlays } from './hooks/useOverlays';
import { useVesselStore } from './hooks/useVesselStore';
import { OverlayToggles } from './components/Globe/Overlays';
import type { OverlayToggleState } from './components/Globe/Overlays';
import type { VesselState } from './types/vessel';

const GlobeView = lazy(() => import('./components/Globe/GlobeView'));
const VesselPanel = lazy(() => import('./components/VesselPanel/VesselPanel'));

const queryClient = new QueryClient();

const DEFAULT_OVERLAYS: OverlayToggleState = {
  showStsZones: false,
  showTerminals: false,
  showEez: false,
  showSarDetections: false,
  showGfwEvents: false,
};

/** Seed the vessel store from the REST API so the globe has data immediately. */
function useVesselSnapshot() {
  const updatePositions = useVesselStore((s) => s.updatePositions);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/vessels/snapshot')
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: Array<Record<string, unknown>>) => {
        if (cancelled) return;
        const vessels: VesselState[] = data.map((d) => ({
          mmsi: d.mmsi as number,
          lat: d.lat as number,
          lon: d.lon as number,
          sog: (d.sog as number) ?? null,
          cog: (d.cog as number) ?? null,
          heading: null,
          riskTier: (d.risk_tier as VesselState['riskTier']) ?? 'green',
          riskScore: (d.risk_score as number) ?? 0,
          name: d.name as string | undefined,
          shipType: d.ship_type as number | undefined,
          timestamp: new Date().toISOString(),
        }));
        updatePositions(vessels);
      })
      .catch(() => {
        // Snapshot failed — WebSocket will populate the store instead
      });
    return () => { cancelled = true; };
  }, [updatePositions]);
}

function AppInner() {
  useWatchlistAlerts();
  useWebSocket();
  useVesselSnapshot();
  const [overlays, setOverlays] = useState<OverlayToggleState>(DEFAULT_OVERLAYS);
  useOverlays(overlays);

  const setFilter = useVesselStore((s) => s.setFilter);
  const filters = useVesselStore((s) => s.filters);

  const { data: stats } = useQuery<StatsResponse>({
    queryKey: ['stats'],
    queryFn: async () => {
      const res = await fetch('/api/stats');
      if (!res.ok) throw new Error(`Stats fetch failed: ${res.status}`);
      const raw = await res.json();
      return {
        risk_tiers: raw.vessels_by_risk_tier ?? raw.risk_tiers ?? { green: 0, yellow: 0, red: 0 },
        anomalies: raw.anomalies ?? { total_active: 0, by_severity: raw.active_anomalies_by_severity ?? {} },
        dark_ships: raw.dark_ship_candidates ?? raw.dark_ships ?? 0,
        ingestion_rate: raw.ingestion_rate ?? 0,
        total_vessels: raw.total_vessels ?? 0,
        storage_estimate_gb: raw.storage_estimate_gb ?? 0,
        gfw_events: raw.gfw_events,
      };
    },
    refetchInterval: STATS_REFETCH_INTERVAL,
  });

  const handleTierClick = (tier: string) => {
    const current = filters.riskTiers;
    if (current.has(tier) && current.size === 1) {
      // Clicking the only active filter clears it
      setFilter({ riskTiers: new Set() });
    } else {
      setFilter({ riskTiers: new Set([tier]) });
    }
  };

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <header
        className="h-10 shrink-0 flex items-center px-4 border-b border-gray-800/50 backdrop-blur-sm"
        style={{ backgroundColor: 'rgba(10, 14, 23, 0.9)' }}
      >
        {/* HEIMDAL label */}
        <h1
          className="text-gray-400 text-xs font-semibold"
          style={{ fontVariant: 'small-caps', letterSpacing: '0.05em' }}
        >
          HEIMDAL
        </h1>

        {/* Vessel count */}
        <div className="border-l border-gray-700/50 pl-3 ml-3 flex items-center">
          <span className="text-gray-500 text-xs">Vessels</span>
          <span className="font-mono text-xs text-gray-200 ml-1.5">
            {stats?.total_vessels.toLocaleString() ?? '—'}
          </span>
        </div>

        {/* Risk tier counts */}
        <div className="border-l border-gray-700/50 pl-3 ml-3 flex items-center gap-3">
          <button
            onClick={() => handleTierClick('green')}
            className={`flex items-center gap-1 text-xs hover:opacity-80 transition-opacity ${
              filters.riskTiers.has('green') ? 'ring-1 ring-green-500/50 rounded px-1 -mx-1' : ''
            }`}
            title="Filter: green tier"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <span className="font-mono text-gray-200">
              {stats?.risk_tiers.green.toLocaleString() ?? '—'}
            </span>
          </button>
          <button
            onClick={() => handleTierClick('yellow')}
            className={`flex items-center gap-1 text-xs hover:opacity-80 transition-opacity ${
              filters.riskTiers.has('yellow') ? 'ring-1 ring-yellow-500/50 rounded px-1 -mx-1' : ''
            }`}
            title="Filter: yellow tier"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
            <span className="font-mono text-gray-200">
              {stats?.risk_tiers.yellow.toLocaleString() ?? '—'}
            </span>
          </button>
          <button
            onClick={() => handleTierClick('red')}
            className={`flex items-center gap-1 text-xs hover:opacity-80 transition-opacity ${
              filters.riskTiers.has('red') ? 'ring-1 ring-red-500/50 rounded px-1 -mx-1' : ''
            }`}
            title="Filter: red tier"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
            <span className="font-mono text-gray-200">
              {stats?.risk_tiers.red.toLocaleString() ?? '—'}
            </span>
          </button>
        </div>

        {/* Ingestion rate */}
        <div className="border-l border-gray-700/50 pl-3 ml-3 flex items-center">
          <span className="text-gray-500 text-xs">Ingestion</span>
          <span className="font-mono text-xs text-gray-200 ml-1.5">
            {stats ? `${stats.ingestion_rate} pos/s` : '—'}
          </span>
        </div>

        {/* Active alerts */}
        <div className="border-l border-gray-700/50 pl-3 ml-3 flex items-center">
          <span className="text-gray-500 text-xs">Alerts</span>
          <span className="font-mono text-xs text-gray-200 ml-1.5">
            {stats?.anomalies.total_active.toLocaleString() ?? '—'}
          </span>
        </div>

        {/* WatchlistPanel & EquasisImport */}
        <div className="border-l border-gray-700/50 pl-3 ml-3 flex items-center gap-2">
          <WatchlistPanel />
          <EquasisImport />
        </div>

        {/* Health indicator — right side */}
        <div className="ml-auto">
          <HealthIndicator />
        </div>
      </header>

      <div style={{ flex: 1, position: 'relative' }}>
        <Suspense fallback={<div className="w-full h-full bg-heimdal-bg flex items-center justify-center text-gray-500">Loading globe...</div>}>
          <GlobeView showGfwEvents={overlays.showGfwEvents} showSarDetections={overlays.showSarDetections} />
        </Suspense>

        {/* Controls overlay — top-left */}
        <div className="absolute top-3 left-3 z-40 flex flex-col gap-2">
          <SearchBar />
          <div className="flex items-center gap-2">
            <RiskFilter />
            <TypeFilter />
            <TimeRangeFilter />
          </div>
        </div>

        {/* Overlay toggles — bottom-left */}
        <div className="absolute bottom-3 left-3 z-40">
          <OverlayToggles state={overlays} onChange={setOverlays} />
        </div>

        <Suspense fallback={null}>
          <VesselPanel />
        </Suspense>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  );
}
