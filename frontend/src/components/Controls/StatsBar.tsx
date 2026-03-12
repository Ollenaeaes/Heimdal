import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

export interface StatsResponse {
  risk_tiers: { green: number; yellow: number; red: number };
  anomalies: { total_active: number; by_severity: Record<string, number> };
  dark_ships: number;
  ingestion_rate: number;
  total_vessels: number;
  storage_estimate_gb: number;
  gfw_events?: { by_type: Record<string, number> };
}

async function fetchStats(): Promise<StatsResponse> {
  const res = await fetch('/api/stats');
  if (!res.ok) throw new Error(`Stats fetch failed: ${res.status}`);
  return res.json();
}

export const STATS_REFETCH_INTERVAL = 30_000;

function calcPercent(value: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((value / total) * 100);
}

export function StatsBar() {
  const [expanded, setExpanded] = useState(false);
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

  const totalRisk = data.risk_tiers.green + data.risk_tiers.yellow + data.risk_tiers.red;

  return (
    <div data-testid="stats-bar" className="relative">
      {/* Compact chip view */}
      <button
        data-testid="stats-toggle"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 flex-wrap cursor-pointer hover:opacity-80 transition-opacity"
        aria-expanded={expanded}
        aria-label="Toggle detailed stats"
      >
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
        <span className="text-gray-500 text-xs ml-1">{expanded ? '\u25B2' : '\u25BC'}</span>
      </button>

      {/* Expanded detail panel */}
      {expanded && (
        <div
          data-testid="stats-expanded"
          className="absolute top-full left-0 mt-1 w-[480px] bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50 p-4 space-y-4"
        >
          {/* Risk Tier Distribution */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
              Risk Tier Distribution
            </h4>
            <BarRow
              label="Green"
              value={data.risk_tiers.green}
              percent={calcPercent(data.risk_tiers.green, totalRisk)}
              color="#27AE60"
              testId="bar-green"
            />
            <BarRow
              label="Yellow"
              value={data.risk_tiers.yellow}
              percent={calcPercent(data.risk_tiers.yellow, totalRisk)}
              color="#D4820C"
              testId="bar-yellow"
            />
            <BarRow
              label="Red"
              value={data.risk_tiers.red}
              percent={calcPercent(data.risk_tiers.red, totalRisk)}
              color="#C0392B"
              testId="bar-red"
            />
          </div>

          {/* Anomalies by Severity */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
              Active Anomalies by Severity
            </h4>
            {Object.entries(data.anomalies.by_severity).length > 0 ? (
              Object.entries(data.anomalies.by_severity).map(([severity, count]) => {
                const severityColors: Record<string, string> = {
                  critical: '#7F1D1D',
                  high: '#DC2626',
                  moderate: '#D4820C',
                  low: '#6B7280',
                };
                return (
                  <BarRow
                    key={severity}
                    label={severity.charAt(0).toUpperCase() + severity.slice(1)}
                    value={count}
                    percent={calcPercent(count, data.anomalies.total_active)}
                    color={severityColors[severity] ?? '#6B7280'}
                    testId={`bar-severity-${severity}`}
                  />
                );
              })
            ) : (
              <span className="text-xs text-gray-500">No active anomalies</span>
            )}
          </div>

          {/* GFW Events by Type */}
          {data.gfw_events && Object.keys(data.gfw_events.by_type).length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                GFW Events by Type
              </h4>
              {(() => {
                const totalGfw = Object.values(data.gfw_events!.by_type).reduce((s, v) => s + v, 0);
                const gfwColors: Record<string, string> = {
                  ENCOUNTER: '#D4820C',
                  LOITERING: '#7F1D1D',
                  AIS_DISABLING: '#DC2626',
                  PORT_VISIT: '#3B82F6',
                };
                return Object.entries(data.gfw_events!.by_type).map(([type, count]) => (
                  <BarRow
                    key={type}
                    label={type.replace(/_/g, ' ')}
                    value={count}
                    percent={calcPercent(count, totalGfw)}
                    color={gfwColors[type] ?? '#6B7280'}
                    testId={`bar-gfw-${type.toLowerCase()}`}
                  />
                ));
              })()}
            </div>
          )}

          {/* Additional Stats */}
          <div className="grid grid-cols-3 gap-3 pt-2 border-t border-gray-700">
            <StatCard
              label="Dark Ships"
              value={data.dark_ships.toLocaleString()}
              testId="stat-dark-ships"
            />
            <StatCard
              label="Ingestion Rate"
              value={`${data.ingestion_rate} pos/sec`}
              testId="stat-ingestion-detail"
            />
            <StatCard
              label="Storage"
              value={`${data.storage_estimate_gb.toFixed(1)} GB`}
              testId="stat-storage"
            />
          </div>
        </div>
      )}
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

function BarRow({
  label,
  value,
  percent,
  color,
  testId,
}: {
  label: string;
  value: number;
  percent: number;
  color: string;
  testId: string;
}) {
  return (
    <div data-testid={testId} className="flex items-center gap-2 mb-1.5">
      <span className="text-xs text-gray-400 w-20 shrink-0">{label}</span>
      <div className="flex-1 h-3 bg-gray-800 rounded overflow-hidden">
        <div
          className="h-full rounded transition-all duration-300"
          style={{ width: `${percent}%`, backgroundColor: color }}
          data-testid={`${testId}-fill`}
        />
      </div>
      <span className="text-xs text-gray-300 w-16 text-right shrink-0">
        {value.toLocaleString()} ({percent}%)
      </span>
    </div>
  );
}

function StatCard({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId: string;
}) {
  return (
    <div data-testid={testId} className="bg-gray-800 rounded p-2 text-center">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className="text-sm font-medium text-gray-200">{value}</div>
    </div>
  );
}
