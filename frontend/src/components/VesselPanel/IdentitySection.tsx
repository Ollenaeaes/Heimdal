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
    <div className="px-4 py-3 border-b border-gray-700">
      {/* Header */}
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-white truncate">
          {vessel.name ?? 'Unknown Vessel'}
        </h2>
        <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
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
            {vessel.riskTier.toUpperCase()} {vessel.riskScore}
          </span>
        </div>
      </div>

      {/* Identity grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <FieldRow label="Call Sign" value={vessel.callSign} />
        <FieldRow label="Ship Type" value={shipTypeLabel} />
        <FieldRow label="Dimensions" value={dimensions} />
        <FieldRow label="Year Built" value={vessel.yearBuilt?.toString()} />
      </div>
    </div>
  );
}

function FieldRow({
  label,
  value,
}: {
  label: string;
  value: string | undefined;
}) {
  return (
    <div>
      <dt className="text-gray-500 text-xs">{label}</dt>
      <dd className="text-gray-300">{value ?? '—'}</dd>
    </div>
  );
}
