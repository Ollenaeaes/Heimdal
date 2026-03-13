import { useQuery } from '@tanstack/react-query';
import { parseISO } from 'date-fns';

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

  // Check if any service is unhealthy
  for (const [name, svc] of Object.entries(services)) {
    if (svc.status === 'unhealthy') {
      return { level: 'red', message: `${name} is unhealthy` };
    }
  }

  // Check if any service is degraded
  for (const [name, svc] of Object.entries(services)) {
    if (svc.status === 'degraded') {
      return { level: 'yellow', message: `${name} is degraded` };
    }
  }

  // Fallback: check top-level status field (legacy API shape)
  if (data.status === 'unhealthy') {
    return { level: 'red', message: 'System unhealthy' };
  }
  if (data.status === 'degraded') {
    return { level: 'yellow', message: 'System degraded' };
  }

  // Check AIS stale via services or top-level flag
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
  green: 'bg-green-500',
  yellow: 'bg-yellow-500',
  red: 'bg-red-500',
};

export function HealthIndicator() {
  const { data, isLoading, isError } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: HEALTH_REFETCH_INTERVAL,
  });

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

  return (
    <div data-testid="health-indicator" className="flex items-center gap-1.5" title={message}>
      <span
        data-testid="health-dot"
        className={`w-2 h-2 rounded-full ${DOT_COLORS[level]}`}
      />
      <span data-testid="health-message" className="text-xs text-gray-400">
        {message}
      </span>
    </div>
  );
}
