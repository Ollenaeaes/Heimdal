import type { VesselDetail } from '../../types/api';
import { useVesselStore } from '../../hooks/useVesselStore';
import {
  formatCoordinate,
  formatSpeed,
  formatCourse,
  formatTimestamp,
} from '../../utils/formatters';
import { getNavStatusLabel } from '../../utils/navStatus';

interface StatusSectionProps {
  vessel: VesselDetail;
  mmsi: number;
}

export function StatusSection({ vessel, mmsi }: StatusSectionProps) {
  const live = useVesselStore((s) => s.vessels.get(mmsi));

  // Prefer live WebSocket data, fall back to API data
  const lat = live?.lat ?? (vessel as any).lat;
  const lon = live?.lon ?? (vessel as any).lon;
  const sog = live?.sog ?? (vessel as any).sog ?? null;
  const cog = live?.cog ?? (vessel as any).cog ?? null;
  const heading = live?.heading ?? (vessel as any).heading ?? null;
  const destination = live?.destination ?? vessel.destination;
  const timestamp = live?.timestamp ?? (vessel as any).timestamp;
  const navStatus = (live as any)?.navStatus ?? (vessel as any).navStatus;

  const positionStr =
    lat !== undefined && lat !== null && lon !== undefined && lon !== null
      ? `${formatCoordinate(lat, 'lat')} ${formatCoordinate(lon, 'lon')}`
      : undefined;

  return (
    <div className="px-4 py-3 border-b border-gray-700" data-testid="status-section">
      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Status
      </h3>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <FieldRow label="Position" value={positionStr} testId="field-position" fullWidth />
        <FieldRow label="Speed (SOG)" value={formatSpeed(sog)} testId="field-sog" />
        <FieldRow label="Course (COG)" value={formatCourse(cog)} testId="field-cog" />
        <FieldRow
          label="Heading"
          value={heading !== null && heading !== undefined ? `${heading}°` : '—'}
          testId="field-heading"
        />
        <FieldRow
          label="Draught"
          value={vessel.draught !== undefined && vessel.draught !== null ? `${vessel.draught} m` : undefined}
          testId="field-draught"
        />
        <FieldRow label="Destination" value={destination} testId="field-destination" />
        <FieldRow
          label="Nav Status"
          value={getNavStatusLabel(navStatus)}
          testId="field-nav-status"
        />
      </div>

      {timestamp && (
        <div className="mt-2 text-xs text-gray-500" data-testid="last-updated">
          Updated {formatTimestamp(timestamp)}
        </div>
      )}
    </div>
  );
}

function FieldRow({
  label,
  value,
  testId,
  fullWidth,
}: {
  label: string;
  value: string | undefined;
  testId?: string;
  fullWidth?: boolean;
}) {
  return (
    <div className={fullWidth ? 'col-span-2' : undefined} data-testid={testId}>
      <dt className="text-gray-500 text-xs">{label}</dt>
      <dd className="text-gray-300">{value ?? '—'}</dd>
    </div>
  );
}
