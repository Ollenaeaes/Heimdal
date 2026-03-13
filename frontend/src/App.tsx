import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SearchBar, RiskFilter, TypeFilter, TimeRangeFilter, StatsBar, HealthIndicator, WatchlistPanel } from './components/Controls';
import { useWatchlistAlerts } from './hooks/useWatchlist';
import { useWebSocket } from './hooks/useWebSocket';
import { useOverlays } from './hooks/useOverlays';
import { useVesselStore } from './hooks/useVesselStore';
import { GlobeView } from './components/Globe/GlobeView';
import { OverlayToggles } from './components/Globe/Overlays';
import type { OverlayToggleState } from './components/Globe/Overlays';
import { VesselPanel } from './components/VesselPanel/VesselPanel';
import type { VesselState } from './types/vessel';

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
          sog: null,
          cog: null,
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

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <header className="h-12 shrink-0 flex items-center px-4 bg-gray-900 border-b border-gray-800 gap-4">
        <h1 className="text-white text-sm font-semibold tracking-wide">HEIMDAL</h1>
        <WatchlistPanel />
        <StatsBar />
        <div className="ml-auto">
          <HealthIndicator />
        </div>
      </header>

      <div style={{ flex: 1, position: 'relative' }}>
        <GlobeView showGfwEvents={overlays.showGfwEvents} showSarDetections={overlays.showSarDetections} />

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

        <VesselPanel />
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
