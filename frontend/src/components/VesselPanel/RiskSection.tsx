import type { VesselDetail } from '../../types/api';
import type { AnomalyEvent } from '../../types/anomaly';
import { getRuleName } from '../../utils/ruleNames';
import { SEVERITY_COLORS } from '../../utils/severityColors';
import { formatTimestamp } from '../../utils/formatters';

interface RiskSectionProps {
  vessel: VesselDetail;
}

const SCORE_CAP = 200;

export function RiskSection({ vessel }: RiskSectionProps) {
  const fillPercent = Math.min((vessel.riskScore / SCORE_CAP) * 100, 100);
  const unresolvedAnomalies = (vessel.anomalies ?? []).filter(
    (a) => !a.resolved
  );

  return (
    <div className="px-4 py-3 border-b border-gray-700" data-testid="risk-section">
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
                'linear-gradient(to right, #27AE60, #D4820C, #C0392B)',
            }}
            data-testid="risk-score-fill"
          />
        </div>
        <div className="flex justify-between mt-0.5 text-[10px] text-gray-500">
          <span>0</span>
          <span>100</span>
          <span>200+</span>
        </div>
      </div>

      {/* Anomaly list */}
      {unresolvedAnomalies.length > 0 && (
        <div className="space-y-2" data-testid="anomaly-list">
          <span className="text-xs text-gray-400 uppercase tracking-wide">
            Active Anomalies ({unresolvedAnomalies.length})
          </span>
          {unresolvedAnomalies.map((anomaly) => (
            <AnomalyCard key={anomaly.id} anomaly={anomaly} />
          ))}
        </div>
      )}
    </div>
  );
}

function AnomalyCard({ anomaly }: { anomaly: AnomalyEvent }) {
  const severityColor = SEVERITY_COLORS[anomaly.severity];
  const detailsSummary = Object.entries(anomaly.details)
    .map(([k, v]) => `${k}: ${v}`)
    .join(', ');

  return (
    <div
      className="rounded-md border border-gray-700 bg-gray-800 p-2"
      data-testid="anomaly-card"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-200" data-testid="anomaly-rule-name">
          {getRuleName(anomaly.ruleId)}
        </span>
        <span
          className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase text-white"
          style={{ backgroundColor: severityColor }}
          data-testid="anomaly-severity-badge"
        >
          {anomaly.severity}
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <span data-testid="anomaly-points">+{anomaly.points} pts</span>
        <span data-testid="anomaly-timestamp">{formatTimestamp(anomaly.timestamp)}</span>
      </div>
      {detailsSummary && (
        <p className="mt-1 text-xs text-gray-500 truncate" data-testid="anomaly-details">
          {detailsSummary}
        </p>
      )}
    </div>
  );
}
