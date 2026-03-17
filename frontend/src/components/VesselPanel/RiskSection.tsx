import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { VesselDetail } from '../../types/api';
import type { AnomalyEvent } from '../../types/anomaly';
import { getRuleName } from '../../utils/ruleNames';
import { SEVERITY_COLORS } from '../../utils/severityColors';
import { formatTimestamp } from '../../utils/formatters';
import { CollapsibleSection } from './CollapsibleSection';

interface RiskSectionProps {
  vessel: VesselDetail;
}

const SCORE_CAP = 200;

/** Human-readable labels for common anomaly detail keys. */
const DETAIL_LABELS: Record<string, string> = {
  reason: 'Reason',
  reported_flag: 'Reported flag',
  mmsi_derived_flag: 'MMSI-derived flag',
  mid: 'MID',
  flags: 'Flags seen',
  flag_count: 'Flag count',
  current_flag: 'Current flag',
  confidence: 'Confidence',
  matched_field: 'Matched by',
  match_type: 'Match type',
  program: 'Program',
  entity_id: 'Entity ID',
  destination: 'Destination',
  avg_speed_knots: 'Avg speed (kn)',
  duration_hours: 'Duration (hrs)',
  position_count: 'Positions',
};

/**
 * Deduplicate anomalies: keep only the most recent entry per rule_id.
 * The backend should prevent duplicates going forward, but older data
 * may still have them.
 */
function deduplicateByRule(anomalies: AnomalyEvent[]): AnomalyEvent[] {
  const seen = new Map<string, AnomalyEvent>();
  for (const a of anomalies) {
    const existing = seen.get(a.ruleId);
    if (!existing || new Date(a.timestamp) > new Date(existing.timestamp)) {
      seen.set(a.ruleId, a);
    }
  }
  return Array.from(seen.values());
}

export function RiskSection({ vessel }: RiskSectionProps) {
  const fillPercent = Math.min((vessel.riskScore / SCORE_CAP) * 100, 100);
  const unresolvedAnomalies = (vessel.anomalies ?? []).filter(
    (a) => !a.resolved
  );
  const deduplicated = deduplicateByRule(unresolvedAnomalies);

  return (
    <CollapsibleSection title="Risk" defaultExpanded testId="risk-section">
      {/* Score bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-400 uppercase tracking-wide">
            Risk Score
          </span>
          <span
            className="text-sm font-semibold text-white"
            data-testid="risk-score-value"
          >
            {vessel.riskScore}
          </span>
        </div>
        <div
          className="h-2 w-full rounded-full overflow-hidden"
          style={{ background: '#374151' }}
          data-testid="risk-score-bar"
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${fillPercent}%`,
              background:
                'linear-gradient(to right, #22C55E, #F59E0B, #EF4444)',
            }}
            data-testid="risk-score-fill"
          />
        </div>
        <div className="flex justify-between mt-0.5 text-[10px] text-gray-500">
          <span>0</span>
          <span>100</span>
          <span>200+</span>
        </div>
        <NetworkScoreLine vessel={vessel} />
      </div>

      {/* Anomaly list — deduplicated by rule */}
      {deduplicated.length > 0 && (
        <div className="space-y-2" data-testid="anomaly-list">
          <span className="text-xs text-gray-400 uppercase tracking-wide">
            Score Breakdown ({deduplicated.length})
          </span>
          {deduplicated.map((anomaly) => (
            <AnomalyCard key={anomaly.ruleId} anomaly={anomaly} />
          ))}
        </div>
      )}
    </CollapsibleSection>
  );
}

/** Format a detail value for display. Primitives render as-is; arrays
 *  of objects (like findings) get flattened to their key fields. */
function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
    return String(value);
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'object' && item !== null) {
          // For findings: show reason or check + severity
          const r = (item as Record<string, unknown>).reason ?? (item as Record<string, unknown>).check;
          const s = (item as Record<string, unknown>).severity;
          return r ? `${r}${s ? ` (${s})` : ''}` : JSON.stringify(item);
        }
        return String(item);
      })
      .join(', ');
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function NetworkScoreLine({ vessel }: { vessel: VesselDetail }) {
  const hasNetwork = (vessel.networkScore ?? 0) > 0;

  const { data: networkData } = useQuery<{ vessels: Record<string, unknown> }>({
    queryKey: ['vesselNetwork', vessel.mmsi, 1],
    queryFn: () =>
      fetch(`/api/vessels/${vessel.mmsi}/network?depth=1`).then((r) => r.json()),
    enabled: hasNetwork,
  });

  const connectedCount = networkData
    ? Math.max(0, Object.keys(networkData.vessels).length - 1)
    : 0;

  return (
    <div className="flex items-center gap-2 mt-2 text-xs" data-testid="network-score-line">
      <span className="text-gray-400">Network:</span>
      <span className="text-gray-200 font-mono" data-testid="network-score-value">
        {hasNetwork
          ? `${vessel.networkScore} pts · Connected to ${connectedCount} vessels`
          : 'No connections'}
      </span>
    </div>
  );
}

function AnomalyCard({ anomaly }: { anomaly: AnomalyEvent }) {
  const [expanded, setExpanded] = useState(false);
  const severityColor = SEVERITY_COLORS[anomaly.severity];

  const detailEntries = Object.entries(anomaly.details).filter(
    ([, v]) => v !== null && v !== undefined && v !== ''
  );

  return (
    <div
      className="border-l-4 bg-[#111827] border border-[#1F2937] p-2 rounded-r cursor-pointer select-none"
      onClick={() => setExpanded(!expanded)}
      style={{ borderLeftColor: severityColor }}
      data-testid="anomaly-card"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-200" data-testid="anomaly-rule-name">
          {getRuleName(anomaly.ruleId)}
        </span>
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold text-gray-300" data-testid="anomaly-points">
            +{anomaly.points}
          </span>
          <span
            className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase text-white"
            style={{ backgroundColor: severityColor }}
            data-testid="anomaly-severity-badge"
          >
            {anomaly.severity}
          </span>
        </div>
      </div>

      {/* Collapsed: one-line summary */}
      {!expanded && detailEntries.length > 0 && (
        <p className="text-xs text-gray-500 truncate">
          {detailEntries
            .slice(0, 3)
            .map(([k, v]) => `${DETAIL_LABELS[k] ?? k}: ${formatDetailValue(v)}`)
            .join(' · ')}
        </p>
      )}

      {/* Expanded: full detail table */}
      {expanded && (
        <div className="mt-2 space-y-1">
          {detailEntries.map(([key, value]) => (
            <div key={key} className="flex justify-between text-xs">
              <span className="text-gray-500">{DETAIL_LABELS[key] ?? key}</span>
              <span className="text-gray-300 text-right ml-2 break-all">
                {formatDetailValue(value)}
              </span>
            </div>
          ))}
          <div className="text-[10px] text-gray-600 pt-1">
            {formatTimestamp(anomaly.timestamp)}
          </div>
        </div>
      )}
    </div>
  );
}
