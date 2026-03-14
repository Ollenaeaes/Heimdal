import type { VesselDetail } from '../../types/api';
import { getShipTypeLabel } from '../../utils/shipTypes';
import { countryCodeToFlagEmoji } from '../../utils/flagEmoji';
import { RISK_COLORS } from '../../utils/riskColors';

interface IdentitySectionProps {
  vessel: VesselDetail;
}

export function IdentitySection({ vessel }: IdentitySectionProps) {
  const flagEmoji = countryCodeToFlagEmoji(vessel.flagCountry);
  const riskColor = RISK_COLORS[vessel.riskTier];
  const shipTypeLabel = getShipTypeLabel(vessel.shipType);
  const dimensions =
    vessel.length && vessel.width
      ? `${vessel.length} x ${vessel.width} m`
      : undefined;

  return (
    <div className="px-3 py-2 border-b border-[#1F2937]">
      {/* Header */}
      <div className="mb-2">
        <h2 className="text-[1.25rem] font-semibold text-white truncate" style={{ fontFamily: 'Inter, sans-serif' }}>
          {vessel.name ?? 'Unknown Vessel'}
        </h2>
        <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 font-mono">
          {vessel.imo && <span>IMO {vessel.imo}</span>}
          <span>MMSI {vessel.mmsi}</span>
          {vessel.flagCountry && (
            <span>
              {flagEmoji} {vessel.flagCountry}
            </span>
          )}
        </div>
        <div className="mt-2">
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-white"
            style={{ backgroundColor: riskColor }}
            data-testid="risk-badge"
          >
            ● {vessel.riskTier.toUpperCase()} — {vessel.riskScore}pts
          </span>
        </div>
      </div>

      {/* Identity — inline layout */}
      <div className="text-xs text-gray-400 space-y-0.5">
        <div>
          Flag: <span className="text-gray-300">{vessel.flagCountry ?? '—'}</span>
          {shipTypeLabel && <> | Type: <span className="text-gray-300">{shipTypeLabel}</span></>}
        </div>
        <div>
          Call Sign: <span className="text-gray-300">{vessel.callSign ?? '—'}</span>
          {dimensions && <> | Dimensions: <span className="text-gray-300">{dimensions}</span></>}
        </div>
        {vessel.yearBuilt && (
          <div>
            Year Built: <span className="text-gray-300">{vessel.yearBuilt}</span>
          </div>
        )}
      </div>
    </div>
  );
}
