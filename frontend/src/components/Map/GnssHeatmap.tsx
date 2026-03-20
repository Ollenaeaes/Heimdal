import { useState, useCallback } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import { SpoofingTimeControls } from '../Globe/SpoofingTimeControls';

export interface GnssHeatmapProps {
  visible: boolean;
}

interface SpoofingPoint {
  lat: number;
  lon: number;
  severity: string;
}

/** Severity to heatmap weight mapping. Exported for tests. */
export function severityWeight(severity: string): number {
  switch (severity) {
    case 'critical': return 3;
    case 'high': return 2;
    case 'moderate': return 1;
    default: return 0.5;
  }
}

/** Convert spoofing events to GeoJSON FeatureCollection. Exported for tests. */
export function buildGnssSpoofingGeoJson(
  events: SpoofingPoint[],
): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: events.map((e) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [e.lon, e.lat] },
      properties: {
        severity: e.severity,
        weight: severityWeight(e.severity),
      },
    })),
  };
}

/**
 * Renders GNSS spoofing events as a native MapLibre heatmap layer.
 * Includes time preset buttons and a timeline scrubber.
 */
export function GnssHeatmap({ visible }: GnssHeatmapProps) {
  const [timeRange, setTimeRange] = useState<{ start: Date; end: Date }>(() => {
    const now = new Date();
    return { start: new Date(now.getTime() - 24 * 3600_000), end: now };
  });

  const handleTimeRangeChange = useCallback((start: Date, end: Date) => {
    setTimeRange({ start, end });
  }, []);

  const { data } = useQuery<GeoJSON.FeatureCollection>({
    queryKey: ['gnssSpoofingEvents', timeRange.start.toISOString(), timeRange.end.toISOString()],
    queryFn: async () => {
      const params = `?start=${timeRange.start.toISOString()}&end=${timeRange.end.toISOString()}`;
      const res = await fetch(`/api/gnss-spoofing-events${params}`);
      if (!res.ok) throw new Error(`${res.status}`);
      const json = await res.json();
      const points: SpoofingPoint[] = json.points ?? json;
      return buildGnssSpoofingGeoJson(points);
    },
    enabled: visible,
    refetchInterval: 60_000,
  });

  return (
    <>
      {visible && data && (
        <Source id="gnss-heatmap" type="geojson" data={data}>
          <Layer
            id="gnss-heatmap-layer"
            type="heatmap"
            paint={{
              'heatmap-weight': ['get', 'weight'],
              'heatmap-intensity': 1,
              'heatmap-radius': 30,
              'heatmap-opacity': 0.6,
              'heatmap-color': [
                'interpolate', ['linear'], ['heatmap-density'],
                0, 'rgba(0,0,0,0)',
                0.2, '#FEF08A',
                0.5, '#F97316',
                0.8, '#EF4444',
                1, '#DC2626',
              ],
            }}
          />
        </Source>
      )}
      <SpoofingTimeControls visible={visible} onTimeRangeChange={handleTimeRangeChange} />
    </>
  );
}
