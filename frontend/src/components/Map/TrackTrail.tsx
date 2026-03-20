import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';

/** AIS gap threshold in minutes */
const GAP_THRESHOLD_MINUTES = 10;

interface TrackSegment {
  coordinates: number[][];
  isGap: boolean;
  /** 0 = oldest, 1 = newest */
  recency: number;
}

/**
 * Splits track points into segments, breaking on AIS gaps (>10 min between
 * consecutive points). Each segment carries a recency value for width tapering.
 */
export function buildTrackSegments(
  points: Array<{ lat: number; lon: number; timestamp: string }>,
): TrackSegment[] {
  if (points.length < 2) return [];

  const segments: TrackSegment[] = [];
  let currentCoords: number[][] = [[points[0].lon, points[0].lat]];
  let isGap = false;

  for (let i = 1; i < points.length; i++) {
    const prevTime = new Date(points[i - 1].timestamp).getTime();
    const curTime = new Date(points[i].timestamp).getTime();
    const gapMinutes = (curTime - prevTime) / 60000;
    const hasGap = gapMinutes > GAP_THRESHOLD_MINUTES;

    if (hasGap !== isGap && currentCoords.length >= 2) {
      segments.push({
        coordinates: currentCoords,
        isGap,
        recency: i / points.length,
      });
      currentCoords = [[points[i - 1].lon, points[i - 1].lat]];
    }

    currentCoords.push([points[i].lon, points[i].lat]);
    isGap = hasGap;
  }

  if (currentCoords.length >= 2) {
    segments.push({ coordinates: currentCoords, isGap, recency: 1 });
  }

  return segments;
}

/**
 * Renders a 24-hour track trail for the currently selected vessel.
 * Solid lines for continuous AIS, dashed lines for gaps >10 min.
 * Width tapers from thin (oldest) to thick (newest).
 */
export function TrackTrail() {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);

  const { data: trackData } = useQuery({
    queryKey: ['vessel-track', selectedMmsi],
    queryFn: async () => {
      const res = await fetch(`/api/vessels/${selectedMmsi}/track?hours=24`);
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: !!selectedMmsi,
    refetchInterval: 30_000,
  });

  const geojson = useMemo(() => {
    if (!trackData?.track) return null;
    const segments = buildTrackSegments(trackData.track);
    const vessel = useVesselStore.getState().vessels.get(selectedMmsi!);
    const color =
      vessel?.riskTier === 'red'
        ? '#EF4444'
        : vessel?.riskTier === 'yellow'
          ? '#F59E0B'
          : '#60A5FA';

    return {
      type: 'FeatureCollection' as const,
      features: segments.map((seg, i) => ({
        type: 'Feature' as const,
        geometry: {
          type: 'LineString' as const,
          coordinates: seg.coordinates,
        },
        properties: {
          isGap: seg.isGap,
          recency: seg.recency,
          color,
        },
      })),
    };
  }, [trackData, selectedMmsi]);

  if (!selectedMmsi || !geojson) return null;

  return (
    <Source id="track-trail-24h" type="geojson" data={geojson}>
      <Layer
        id="track-solid"
        type="line"
        filter={['!=', ['get', 'isGap'], true]}
        paint={{
          'line-color': ['get', 'color'],
          'line-width': [
            'interpolate',
            ['linear'],
            ['get', 'recency'],
            0,
            0.5,
            1,
            2,
          ],
          'line-opacity': 0.6,
        }}
      />
      <Layer
        id="track-gap"
        type="line"
        filter={['==', ['get', 'isGap'], true]}
        paint={{
          'line-color': ['get', 'color'],
          'line-width': 1,
          'line-opacity': 0.4,
          'line-dasharray': [4, 4],
        }}
      />
    </Source>
  );
}
