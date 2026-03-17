import { useQuery } from '@tanstack/react-query';
import { formatTimestampAbsolute } from '../../utils/formatters';
import type { AnomalyEvent } from '../../types/anomaly';
import type { TrackPoint } from '../../types/api';
import { CollapsibleSection } from './CollapsibleSection';

interface VoyageTimelineProps {
  mmsi: number;
  anomalies: AnomalyEvent[];
  onFlyTo?: (lat: number, lon: number, timestamp: string) => void;
}

type MarkerColor = 'red' | 'amber' | 'blue' | 'gray';

function getMarkerColor(ruleId: string): MarkerColor {
  if (ruleId.includes('ais_gap') || ruleId.includes('ais_disabling')) return 'red';
  if (ruleId.includes('sts') || ruleId.includes('encounter') || ruleId.includes('loitering')) return 'amber';
  if (ruleId.includes('port')) return 'blue';
  return 'gray';
}

const MARKER_CSS: Record<MarkerColor, string> = {
  red: 'bg-red-500',
  amber: 'bg-amber-500',
  blue: 'bg-blue-500',
  gray: 'bg-gray-500',
};

async function fetchTrack(mmsi: number, start: string): Promise<TrackPoint[]> {
  const res = await fetch(`/api/vessels/${mmsi}/track?start=${start}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch track for ${mmsi}: ${res.status}`);
  }
  return res.json() as Promise<TrackPoint[]>;
}

function getDayLabels(): { label: string; position: number }[] {
  const now = new Date();
  const labels: { label: string; position: number }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const pct = ((6 - i) / 6) * 100;
    labels.push({
      label: d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
      position: pct,
    });
  }
  return labels;
}

function getTimelinePosition(timestamp: string): number {
  const now = Date.now();
  const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
  const start = now - sevenDaysMs;
  const ts = new Date(timestamp).getTime();
  const pct = ((ts - start) / sevenDaysMs) * 100;
  return Math.max(0, Math.min(100, pct));
}

export function VoyageTimeline({ mmsi, anomalies, onFlyTo }: VoyageTimelineProps) {
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

  const { data: track, isLoading } = useQuery<TrackPoint[]>({
    queryKey: ['vessel-track', mmsi],
    queryFn: () => fetchTrack(mmsi, sevenDaysAgo),
  });

  const dayLabels = getDayLabels();

  const handleMarkerClick = (anomaly: AnomalyEvent) => {
    const details = anomaly.details as Record<string, unknown>;
    const lat = (details?.lat as number) ?? null;
    const lon = (details?.lon as number) ?? null;
    if (lat !== null && lon !== null && onFlyTo) {
      onFlyTo(lat, lon, anomaly.timestamp);
    }
  };

  return (
    <CollapsibleSection title="Voyage Timeline" testId="voyage-timeline">
      {isLoading ? (
        <div className="text-xs text-gray-500">Loading track data...</div>
      ) : !track || track.length === 0 ? (
        <div className="text-xs text-gray-500">No track data available</div>
      ) : (
        <div className="overflow-x-auto" data-testid="timeline-scroll-container">
          <div className="relative min-w-[600px] h-20">
            {/* Day labels */}
            <div className="absolute top-0 left-0 right-0 flex justify-between text-xs text-gray-500">
              {dayLabels.map((d) => (
                <span key={d.label} style={{ left: `${d.position}%` }} className="absolute">
                  {d.label}
                </span>
              ))}
            </div>

            {/* Track line */}
            <div className="absolute top-8 left-0 right-0 h-0.5 bg-gray-600" data-testid="track-line" />

            {/* Event markers */}
            {anomalies.map((anomaly) => {
              const pos = getTimelinePosition(anomaly.timestamp);
              const color = getMarkerColor(anomaly.ruleId);
              return (
                <button
                  key={anomaly.id}
                  className={`absolute top-6 w-3 h-3 rounded-full ${MARKER_CSS[color]} cursor-pointer hover:ring-2 hover:ring-white transition-all group`}
                  style={{ left: `${pos}%`, transform: 'translateX(-50%)' }}
                  data-testid={`timeline-marker-${color}`}
                  data-rule-id={anomaly.ruleId}
                  onClick={() => handleMarkerClick(anomaly)}
                  title={anomaly.ruleId}
                >
                  <span className="absolute bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap bg-gray-800 text-gray-300 text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity">
                    {anomaly.ruleId}
                    <br />
                    {formatTimestampAbsolute(anomaly.timestamp)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </CollapsibleSection>
  );
}
