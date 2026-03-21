import { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { parseISO, formatDistanceToNow } from 'date-fns';

export interface ServiceHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  last_message_at?: string;
  total_vessels?: number;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  services: Record<string, ServiceHealth>;
  vessel_count: number;
  anomaly_count: number;
}

async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/api/health');
  if (!res.ok) throw new Error(`Health fetch failed: ${res.status}`);
  return res.json();
}

export const HEALTH_REFETCH_INTERVAL = 60_000;
export const AIS_STALE_THRESHOLD_MS = 2 * 60 * 1000; // 2 minutes

export type HealthLevel = 'green' | 'yellow' | 'red';

export function computeHealthLevel(data: HealthResponse): { level: HealthLevel; message: string } {
  const services = data.services ?? {};

  for (const [name, svc] of Object.entries(services)) {
    if (svc.status === 'unhealthy') {
      return { level: 'red', message: `${name} is unhealthy` };
    }
  }

  for (const [name, svc] of Object.entries(services)) {
    if (svc.status === 'degraded') {
      return { level: 'yellow', message: `${name} is degraded` };
    }
  }

  if (data.status === 'unhealthy') {
    return { level: 'red', message: 'System unhealthy' };
  }
  if (data.status === 'degraded') {
    return { level: 'yellow', message: 'System degraded' };
  }

  const ais = services.ais_stream;
  if (ais?.last_message_at) {
    const lastMsg = parseISO(ais.last_message_at).getTime();
    const age = Date.now() - lastMsg;
    if (age > AIS_STALE_THRESHOLD_MS) {
      return { level: 'yellow', message: 'AIS stream stale' };
    }
  } else if ('ais_connected' in data && !(data as Record<string, unknown>).ais_connected) {
    return { level: 'yellow', message: 'AIS stream disconnected' };
  }

  return { level: 'green', message: 'All systems operational' };
}

const DOT_COLORS: Record<HealthLevel, string> = {
  green: 'bg-[#22C55E]',
  yellow: 'bg-[#F59E0B]',
  red: 'bg-[#EF4444]',
};

const STATUS_DOT: Record<string, string> = {
  healthy: '#22C55E',
  degraded: '#F59E0B',
  unhealthy: '#EF4444',
};

function formatLastSeen(iso?: string): string {
  if (!iso) return 'unknown';
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return 'unknown';
  }
}

export function HealthIndicator() {
  const [showDetails, setShowDetails] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data, isLoading, isError } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: HEALTH_REFETCH_INTERVAL,
  });

  // Close dropdown on outside click
  useEffect(() => {
    if (!showDetails) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setShowDetails(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showDetails]);

  if (isLoading) {
    return (
      <div data-testid="health-indicator" className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-gray-500 animate-pulse" />
        <span className="text-xs text-gray-500">Checking...</span>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div data-testid="health-indicator" className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-red-500" />
        <span className="text-xs text-red-400">Health check failed</span>
      </div>
    );
  }

  const { level, message } = computeHealthLevel(data);
  const services = data.services ?? {};
  const isClickable = level !== 'green' || Object.keys(services).length > 0;

  return (
    <div ref={ref} className="relative">
      <button
        data-testid="health-indicator"
        onClick={() => isClickable && setShowDetails(!showDetails)}
        className={`flex items-center gap-1.5 ${isClickable ? 'cursor-pointer hover:opacity-80' : ''}`}
        title={message}
      >
        <span
          data-testid="health-dot"
          className={`w-2 h-2 rounded-full ${DOT_COLORS[level]}`}
        />
        <span data-testid="health-message" className="text-xs text-gray-400">
          {message}
        </span>
      </button>

      {/* Detail dropdown */}
      {showDetails && (
        <div className="absolute right-0 top-full mt-1 w-64 bg-[#111827] border border-[#1F2937] rounded shadow-lg z-50">
          <div className="px-3 py-2 border-b border-[#1F2937]">
            <div className="text-[0.65rem] font-medium uppercase tracking-wider text-slate-500">
              System Health
            </div>
          </div>
          {Object.keys(services).length > 0 ? (
            <div className="px-3 py-2 flex flex-col gap-2">
              {Object.entries(services).map(([name, svc]) => (
                <div key={name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: STATUS_DOT[svc.status] ?? '#6B7280' }}
                    />
                    <span className="text-[0.7rem] text-slate-300">{name.replace(/_/g, ' ')}</span>
                  </div>
                  <div className="text-[0.6rem] text-slate-500 font-mono">
                    {svc.status !== 'healthy' && svc.last_message_at
                      ? `last seen ${formatLastSeen(svc.last_message_at)}`
                      : svc.status}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="px-3 py-2">
              <div className="flex items-center justify-between">
                <span className="text-[0.7rem] text-slate-300">Overall</span>
                <span className="text-[0.6rem] font-mono" style={{ color: STATUS_DOT[data.status] }}>
                  {data.status}
                </span>
              </div>
            </div>
          )}
          <div className="px-3 py-1.5 border-t border-[#1F2937] text-[0.6rem] text-slate-600">
            {data.vessel_count.toLocaleString()} vessels tracked
          </div>
        </div>
      )}
    </div>
  );
}
