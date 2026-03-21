import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';

/** AIS gap threshold in minutes */
const GAP_THRESHOLD_MINUTES = 10;

/** Track history in hours */
const TRACK_HOURS = 12;

/**
 * Speed color scale (knots) — blue to cyan to green to yellow to red.
 * Works on any risk-tier vessel since it uses a separate palette from risk colors.
 */
const SPEED_COLORS = [
  { speed: 0, color: '#6366F1' },    // indigo — stationary/drifting
  { speed: 2, color: '#3B82F6' },    // blue — slow
  { speed: 5, color: '#06B6D4' },    // cyan — moderate
  { speed: 10, color: '#22C55E' },   // green — normal
  { speed: 15, color: '#EAB308' },   // yellow — fast
  { speed: 20, color: '#F97316' },   // orange — very fast
  { speed: 25, color: '#EF4444' },   // red — extreme
];

export interface TrackPoint {
  lat: number;
  lon: number;
  timestamp: string;
  sog?: number | null;
  cog?: number | null;
}

interface TrackLineSegment {
  coordinates: number[][];
  speed: number; // average SOG for the segment
  isGap: boolean;
}

/**
 * Splits track points into short segments, each colored by speed.
 * Breaks on AIS gaps (>10 min). Each segment is a pair of consecutive points.
 */
export function buildSpeedSegments(points: TrackPoint[]): TrackLineSegment[] {
  if (points.length < 2) return [];

  const segments: TrackLineSegment[] = [];

  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    const prevTime = new Date(prev.timestamp).getTime();
    const curTime = new Date(cur.timestamp).getTime();
    const gapMinutes = (curTime - prevTime) / 60000;
    const isGap = gapMinutes > GAP_THRESHOLD_MINUTES;

    const speed = ((prev.sog ?? 0) + (cur.sog ?? 0)) / 2;

    segments.push({
      coordinates: [
        [prev.lon, prev.lat],
        [cur.lon, cur.lat],
      ],
      speed,
      isGap,
    });
  }

  return segments;
}

/** Map a speed value to a hex color using the speed color scale. */
function speedToColor(sog: number): string {
  if (sog <= SPEED_COLORS[0].speed) return SPEED_COLORS[0].color;
  for (let i = 1; i < SPEED_COLORS.length; i++) {
    if (sog <= SPEED_COLORS[i].speed) {
      return SPEED_COLORS[i].color;
    }
  }
  return SPEED_COLORS[SPEED_COLORS.length - 1].color;
}

/**
 * Renders a 12-hour track trail for the currently selected vessel.
 * Color-coded by speed (knots). Dashed lines for AIS gaps >10 min.
 */
export function TrackTrail() {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);

  const { data: trackData } = useQuery<TrackPoint[]>({
    queryKey: ['vessel-track', selectedMmsi],
    queryFn: async () => {
      const res = await fetch(`/api/vessels/${selectedMmsi}/track?hours=${TRACK_HOURS}`);
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: !!selectedMmsi,
    refetchInterval: 30_000,
  });

  const geojson = useMemo(() => {
    if (!trackData || !Array.isArray(trackData) || trackData.length < 2) return null;

    const segments = buildSpeedSegments(trackData);

    return {
      type: 'FeatureCollection' as const,
      features: segments.map((seg) => ({
        type: 'Feature' as const,
        geometry: {
          type: 'LineString' as const,
          coordinates: seg.coordinates,
        },
        properties: {
          isGap: seg.isGap,
          speed: seg.speed,
          color: speedToColor(seg.speed),
        },
      })),
    };
  }, [trackData]);

  if (!selectedMmsi || !geojson) return null;

  return (
    <Source id="track-trail-24h" type="geojson" data={geojson}>
      <Layer
        id="track-solid"
        type="line"
        filter={['!=', ['get', 'isGap'], true]}
        paint={{
          'line-color': ['get', 'color'],
          'line-width': 2.5,
          'line-opacity': 0.8,
        }}
      />
      <Layer
        id="track-gap"
        type="line"
        filter={['==', ['get', 'isGap'], true]}
        paint={{
          'line-color': '#6366F1',
          'line-width': 1,
          'line-opacity': 0.4,
          'line-dasharray': [4, 4],
        }}
      />
    </Source>
  );
}

export { SPEED_COLORS };
