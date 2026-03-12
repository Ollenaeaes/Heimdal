import { useQuery } from '@tanstack/react-query';

export interface StatsResponse {
  risk_tiers: { green: number; yellow: number; red: number };
  anomalies: { total_active: number; by_severity: Record<string, number> };
  dark_ships: number;
  ingestion_rate: number;
  total_vessels: number;
  storage_estimate_gb: number;
}

async function fetchStats(): Promise<StatsResponse> {
  const res = await fetch('/api/stats');
  if (!res.ok) throw new Error(`Stats fetch failed: ${res.status}`);
  return res.json();
}

export const STATS_REFETCH_INTERVAL = 30_000;

export function StatsBar() {
  const { data, isLoading, isError } = useQuery<StatsResponse>({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: STATS_REFETCH_INTERVAL,
  });

  if (isLoading) {
    return (
      <div data-testid="stats-bar" className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Loading stats...</span>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div data-testid="stats-bar" className="flex items-center gap-2">
        <span className="text-xs text-red-400">Stats unavailable</span>
      </div>
    );
  }

  return (
    <div data-testid="stats-bar" className="flex items-center gap-2 flex-wrap">
      <Chip label="Vessels" value={data.total_vessels.toLocaleString()} testId="stat-total-vessels" />
      <Chip
        label="Green"
        value={data.risk_tiers.green.toLocaleString()}
        testId="stat-green"
        dotColor="bg-green-500"
      />
      <Chip
        label="Yellow"
        value={data.risk_tiers.yellow.toLocaleString()}
        testId="stat-yellow"
        dotColor="bg-yellow-500"
      />
      <Chip
        label="Red"
        value={data.risk_tiers.red.toLocaleString()}
        testId="stat-red"
        dotColor="bg-red-500"
      />
      <Chip
        label="Anomalies"
        value={data.anomalies.total_active.toLocaleString()}
        testId="stat-anomalies"
      />
      <Chip
        label="Ingestion"
        value={`${data.ingestion_rate} pos/sec`}
        testId="stat-ingestion"
      />
    </div>
  );
}

function Chip({
  label,
  value,
  testId,
  dotColor,
}: {
  label: string;
  value: string;
  testId: string;
  dotColor?: string;
}) {
  return (
    <span
      data-testid={testId}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-800 text-xs text-gray-300"
    >
      {dotColor && <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />}
      <span className="text-gray-500">{label}:</span>
      <span className="font-medium text-gray-200">{value}</span>
    </span>
  );
}
