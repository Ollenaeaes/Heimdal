import type { VesselDetail } from '../../types/api';
import { useVesselStore } from '../../hooks/useVesselStore';
import {
  formatCoordinate,
  formatSpeed,
  formatCourse,
  formatTimestamp,
} from '../../utils/formatters';
import { getNavStatusLabel } from '../../utils/navStatus';
import { CollapsibleSection } from './CollapsibleSection';

interface StatusSectionProps {
  vessel: VesselDetail;
  mmsi: number;
}

export function StatusSection({ vessel, mmsi }: StatusSectionProps) {
  const live = useVesselStore((s) => s.vessels.get(mmsi));

  // Prefer live WebSocket data, fall back to API data
  const lat = live?.lat ?? (vessel as any).lat;
  const lon = live?.lon ?? (vessel as any).lon;
  const sog = live?.sog ?? vessel.sog ?? null;
  const cog = live?.cog ?? vessel.cog ?? null;
  const heading = live?.heading ?? vessel.heading ?? null;
  const destination = live?.destination ?? vessel.destination;
  const timestamp = live?.timestamp ?? vessel.lastPositionTime;
  const navStatus = live?.navStatus ?? vessel.navStatus;

  const positionStr =
    lat !== undefined && lat !== null && lon !== undefined && lon !== null
      ? `${formatCoordinate(lat, 'lat')} ${formatCoordinate(lon, 'lon')}`
      : undefined;

  return (
    <CollapsibleSection title="Status" defaultExpanded testId="status-section">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <FieldRow label="Position" value={positionStr} testId="field-position" fullWidth mono />
        <FieldRow label="Speed (SOG)" value={formatSpeed(sog)} testId="field-sog" mono />
        <FieldRow label="Course (COG)" value={formatCourse(cog)} testId="field-cog" mono />
        <FieldRow
          label="Heading"
          value={heading !== null && heading !== undefined ? `${heading}°` : '\u2014'}
          testId="field-heading"
          mono
        />
        <FieldRow
          label="Draught"
          value={vessel.draught !== undefined && vessel.draught !== null ? `${vessel.draught} m` : undefined}
          testId="field-draught"
          mono
        />
        <FieldRow label="Destination" value={destination} testId="field-destination" />
        <FieldRow
          label="Nav Status"
          value={getNavStatusLabel(navStatus)}
          testId="field-nav-status"
        />
      </div>

      {timestamp && (
        <div className="mt-1 text-xs text-gray-500 font-mono" data-testid="last-updated">
          Updated {formatTimestamp(timestamp)}
        </div>
      )}
    </CollapsibleSection>
  );
}

function FieldRow({
  label,
  value,
  testId,
  fullWidth,
  mono,
}: {
  label: string;
  value: string | undefined;
  testId?: string;
  fullWidth?: boolean;
  mono?: boolean;
}) {
  return (
    <div className={fullWidth ? 'col-span-2' : undefined} data-testid={testId}>
      <dt className="text-gray-500 text-xs">{label}</dt>
      <dd className={`text-gray-300 ${mono ? 'font-mono' : ''}`}>{value ?? '—'}</dd>
    </div>
  );
}
