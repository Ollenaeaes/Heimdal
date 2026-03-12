import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GlobeView } from './components/Globe';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="h-screen w-screen flex flex-col overflow-hidden bg-gray-950">
        {/* Top bar — thin header for future stats/health indicators */}
        <header className="h-12 shrink-0 flex items-center px-4 bg-gray-900 border-b border-gray-800">
          <h1 className="text-white text-sm font-semibold tracking-wide">HEIMDAL</h1>
        </header>

        {/* Main content: globe fills remaining space */}
        <main className="flex-1 relative">
          <GlobeView />

          {/* Right panel slot — hidden by default, for future vessel detail panel */}
          <div
            id="vessel-panel-slot"
            className="hidden fixed right-0 top-12 bottom-0 w-[420px] bg-gray-900 border-l border-gray-800"
          />
        </main>
      </div>
    </QueryClientProvider>
  );
}
