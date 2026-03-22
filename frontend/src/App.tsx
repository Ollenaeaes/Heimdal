import { useState, useEffect, lazy, Suspense } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { SearchBar, RiskFilter, TypeFilter, TimeRangeFilter, HealthIndicator, WatchlistPanel, EquasisImport, STATS_REFETCH_INTERVAL } from './components/Controls';
import type { StatsResponse } from './components/Controls';
import { useWatchlistAlerts } from './hooks/useWatchlist';
import { usePositionPolling } from './hooks/usePositionPolling';
import { useViewportGreenVessels } from './hooks/useViewportGreenVessels';
import { useVesselStore } from './hooks/useVesselStore';
import { OverlayToggles } from './components/Map/OverlayToggles';
import { AreaLookbackButton } from './components/Map/AreaLookbackButton';
import { AreaLookbackPanel } from './components/Map/AreaLookbackPanel';
import Minimap from './components/Map/Minimap';
import { TrackLegend } from './components/Map/TrackLegend';
import type { OverlayToggleState } from './components/Map/OverlayToggles';
import type { VesselState } from './types/vessel';

const MapView = lazy(() => import('./components/Map/MapView'));
const VesselPanel = lazy(() => import('./components/VesselPanel/VesselPanel'));
const EventLog = lazy(() => import('./components/EventLog'));

const queryClient = new QueryClient();

const DEFAULT_OVERLAYS: OverlayToggleState = {
  showStsZones: false,
  showTerminals: false,
  showEez: false,
  showSeaBorders: false,
  showSeaBordersEez: true,
  showSeaBorders12nm: true,
  showSarDetections: false,
  showGfwEvents: false,
  showInfrastructure: false,
  showGnssZones: false,
  showNetwork: false,
};

/** Refresh interval for snapshot — keep in sync with STATS_REFETCH_INTERVAL (30s). */
const SNAPSHOT_REFETCH_MS = 30_000;

/** Parse snapshot API response into VesselState[]. */
function parseSnapshotData(data: Array<Record<string, unknown>>): VesselState[] {
  return data.map((d) => ({
    mmsi: d.mmsi as number,
    lat: d.lat as number,
    lon: d.lon as number,
    sog: (d.sog as number) ?? null,
    cog: (d.cog as number) ?? null,
    heading: (d.heading as number) ?? null,
    riskTier: (d.risk_tier as VesselState['riskTier']) ?? 'green',
    riskScore: (d.risk_score as number) ?? 0,
    name: d.name as string | undefined,
    shipType: d.ship_type as number | undefined,
    timestamp: new Date().toISOString(),
    length: (d.length as number) ?? null,
    width: (d.width as number) ?? null,
  }));
}

/**
 * Seed the vessel store with yellow/red/blacklisted vessels globally.
 * Green vessels are loaded separately by useViewportGreenVessels.
 */
function useVesselSnapshot() {
  const updatePositions = useVesselStore((s) => s.updatePositions);

  useEffect(() => {
    let cancelled = false;

    function fetchSnapshot() {
      fetch('/api/vessels/snapshot?risk_tiers=yellow,red,blacklisted')
        .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
        .then((data: Array<Record<string, unknown>>) => {
          if (cancelled) return;
          updatePositions(parseSnapshotData(data));
        })
        .catch(() => {});
    }

    fetchSnapshot();
    const timer = setInterval(fetchSnapshot, SNAPSHOT_REFETCH_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [updatePositions]);
}

function AppInner() {
  useWatchlistAlerts();
  usePositionPolling();
  useVesselSnapshot();
  useViewportGreenVessels();
  const [overlays, setOverlays] = useState<OverlayToggleState>(DEFAULT_OVERLAYS);
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
      setFilter({ riskTiers: new Set() });
    } else {
      setFilter({ riskTiers: new Set([tier]) });
    }
  };

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* HUD Bar — thin, semi-transparent, status line per visual theme spec */}
      <header
        className="h-9 shrink-0 flex items-center px-4 border-b border-[#1F2937]"
        style={{ backgroundColor: 'rgba(10, 14, 23, 0.92)' }}
      >
        {/* HEIMDAL wordmark */}
        <h1
          className="text-slate-400 text-xs font-semibold tracking-wider"
        >
          HEIMDAL
        </h1>

        {/* Vessel count */}
        <div className="border-l border-slate-700/50 pl-3 ml-3 flex items-center">
          <span className="text-slate-500 text-[0.7rem]">Vessels</span>
          <span className="font-mono text-[0.7rem] text-slate-200 ml-1.5">
            {stats?.total_vessels.toLocaleString() ?? '—'}
          </span>
        </div>

        {/* Risk tier counts — clickable filter shortcuts */}
        <div className="border-l border-slate-700/50 pl-3 ml-3 flex items-center gap-3">
          <button
            onClick={() => handleTierClick('green')}
            className={`flex items-center gap-1 text-[0.7rem] hover:opacity-80 transition-opacity ${
              filters.riskTiers.has('green') ? 'ring-1 ring-green-500/50 rounded px-1 -mx-1' : ''
            }`}
            title="Filter: green tier"
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#22C55E' }} />
            <span className="font-mono text-slate-200">
              {stats?.risk_tiers.green.toLocaleString() ?? '—'}
            </span>
          </button>
          <button
            onClick={() => handleTierClick('yellow')}
            className={`flex items-center gap-1 text-[0.7rem] hover:opacity-80 transition-opacity ${
              filters.riskTiers.has('yellow') ? 'ring-1 ring-yellow-500/50 rounded px-1 -mx-1' : ''
            }`}
            title="Filter: yellow tier"
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#EAB308' }} />
            <span className="font-mono text-slate-200">
              {stats?.risk_tiers.yellow.toLocaleString() ?? '—'}
            </span>
          </button>
          <button
            onClick={() => handleTierClick('red')}
            className={`flex items-center gap-1 text-[0.7rem] hover:opacity-80 transition-opacity ${
              filters.riskTiers.has('red') ? 'ring-1 ring-red-500/50 rounded px-1 -mx-1' : ''
            }`}
            title="Filter: red tier"
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#EF4444' }} />
            <span className="font-mono text-slate-200">
              {stats?.risk_tiers.red.toLocaleString() ?? '—'}
            </span>
          </button>
        </div>

        {/* Ingestion rate */}
        <div className="border-l border-slate-700/50 pl-3 ml-3 flex items-center">
          <span className="text-slate-500 text-[0.7rem]">Ingestion</span>
          <span className="font-mono text-[0.7rem] text-slate-200 ml-1.5">
            {stats ? `${stats.ingestion_rate} pos/s` : '—'}
          </span>
        </div>

        {/* Active alerts */}
        <div className="border-l border-slate-700/50 pl-3 ml-3 flex items-center">
          <span className="text-slate-500 text-[0.7rem]">Alerts</span>
          <span className="font-mono text-[0.7rem] text-slate-200 ml-1.5">
            {stats?.anomalies.total_active.toLocaleString() ?? '—'}
          </span>
        </div>

        {/* WatchlistPanel & EquasisImport */}
        <div className="border-l border-slate-700/50 pl-3 ml-3 flex items-center gap-2">
          <WatchlistPanel />
          <EquasisImport />
        </div>

        {/* Health indicator — right side */}
        <div className="ml-auto">
          <HealthIndicator />
        </div>
      </header>

      <div style={{ flex: 1, position: 'relative' }}>
        <Suspense fallback={<div className="w-full h-full bg-slate-900 flex items-center justify-center text-slate-500">Loading map...</div>}>
          <MapView
            showGfwEvents={overlays.showGfwEvents}
            showSarDetections={overlays.showSarDetections}
            showInfrastructure={overlays.showInfrastructure}
            showGnssZones={overlays.showGnssZones}
            showNetwork={overlays.showNetwork}
            showStsZones={overlays.showStsZones}
            showTerminals={overlays.showTerminals}
            showSeaBorders={overlays.showSeaBorders}
            showSeaBordersEez={overlays.showSeaBordersEez}
            showSeaBorders12nm={overlays.showSeaBorders12nm}
          />
        </Suspense>

        {/* Left side layer control panel */}
        <div className="absolute top-3 left-3 z-40 flex flex-col gap-2" style={{ maxHeight: 'calc(100vh - 80px)' }}>
          {/* Search */}
          <SearchBar />

          {/* Filters */}
          <div className="flex items-center gap-2">
            <RiskFilter />
            <TypeFilter />
            <TimeRangeFilter />
            <AreaLookbackButton />
          </div>

          {/* Layer toggles — self-collapsing */}
          <OverlayToggles state={overlays} onChange={setOverlays} />
        </div>

        <TrackLegend />
        <AreaLookbackPanel />
        <Minimap />

        <Suspense fallback={null}>
          <VesselPanel />
        </Suspense>

        <Suspense fallback={null}>
          <EventLog />
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
