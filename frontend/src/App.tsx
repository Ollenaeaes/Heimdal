import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GlobeView } from './components/Globe';
import { VesselPanel } from './components/VesselPanel';
import { SearchBar, RiskFilter, TypeFilter, TimeRangeFilter, StatsBar, HealthIndicator } from './components/Controls';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="h-screen w-screen flex flex-col overflow-hidden bg-gray-950">
        {/* Top bar with stats and health */}
        <header className="h-12 shrink-0 flex items-center px-4 bg-gray-900 border-b border-gray-800 gap-4">
          <h1 className="text-white text-sm font-semibold tracking-wide">HEIMDAL</h1>
          <StatsBar />
          <div className="ml-auto">
            <HealthIndicator />
          </div>
        </header>

        {/* Main content: globe fills remaining space */}
        <main className="flex-1 relative">
          <GlobeView />

          {/* Controls overlay — top-left */}
          <div className="absolute top-3 left-3 z-40 flex flex-col gap-2">
            <SearchBar />
            <div className="flex items-center gap-2">
              <RiskFilter />
              <TypeFilter />
              <TimeRangeFilter />
            </div>
          </div>

          <VesselPanel />
        </main>
      </div>
    </QueryClientProvider>
  );
}
