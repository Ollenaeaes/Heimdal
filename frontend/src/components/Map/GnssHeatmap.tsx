import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import type { CircleLayerSpecification } from 'maplibre-gl';

export interface GnssHeatmapProps {
  visible: boolean;
  centerTime?: Date;
  windowSize?: string; // "1h" | "3h" | "6h" | "12h" | "24h" | "3d" | "7d"
}

/** Color palette for interference severity */
const SEVERITY_COLORS = {
  severe: { fill: 'rgba(239,68,68,0.30)', stroke: 'rgba(239,68,68,0.8)' },
  moderate: { fill: 'rgba(251,191,36,0.25)', stroke: 'rgba(251,191,36,0.7)' },
};

/**
 * Renders ADS-B-derived GNSS interference zones as circles on the map.
 *
 * Red: severe interference (NACp <= 3 or GPS loss)
 * Amber: moderate interference (NACp 4-5, multi-aircraft)
 *
 * Data source: ADS-B NACp degradation detection via adsb.lol
 */
export function GnssHeatmap({
  visible,
  centerTime,
  windowSize = '24h',
}: GnssHeatmapProps) {
  const effectiveCenterTime = centerTime ?? new Date();

  const { data } = useQuery<GeoJSON.FeatureCollection>({
    queryKey: ['adsbInterference', effectiveCenterTime.toISOString(), windowSize],
    queryFn: async () => {
      const params = new URLSearchParams({
        center: effectiveCenterTime.toISOString(),
        window: windowSize,
      });
      const res = await fetch(`/api/adsb/interference-zones?${params}`);
      if (!res.ok) throw new Error(`Interference zones fetch failed: ${res.status}`);
      return res.json();
    },
    enabled: visible,
    refetchInterval: 30_000,
  });

  const filteredData = useMemo(() => {
    if (!data) return null;
    return {
      ...data,
      features: data.features.filter((f) => f.geometry != null),
    };
  }, [data]);

  // Circle size based on radius_km property, scaled by zoom
  // radius_km ~8.5 for H3 res 5 cells
  const circlePaint: CircleLayerSpecification['paint'] = {
    'circle-radius': [
      'interpolate', ['exponential', 2], ['zoom'],
      3, ['*', ['get', 'radius_km'], 0.3],
      6, ['*', ['get', 'radius_km'], 1.5],
      10, ['*', ['get', 'radius_km'], 8],
    ],
    'circle-color': [
      'match', ['get', 'severity'],
      'severe', SEVERITY_COLORS.severe.fill,
      'moderate', SEVERITY_COLORS.moderate.fill,
      'rgba(251,191,36,0.2)',
    ],
    'circle-opacity': [
      'interpolate', ['linear'], ['get', 'confidence'],
      0.3, 0.2,
      0.7, 0.5,
      1.0, 0.8,
    ],
    'circle-stroke-width': [
      'case',
      ['get', 'is_active'], 2,
      1,
    ],
    'circle-stroke-color': [
      'match', ['get', 'severity'],
      'severe', SEVERITY_COLORS.severe.stroke,
      'moderate', SEVERITY_COLORS.moderate.stroke,
      'rgba(251,191,36,0.6)',
    ],
    'circle-stroke-opacity': 0.9,
    'circle-blur': 0.3,
  };

  if (!visible || !filteredData || filteredData.features.length === 0) return null;

  return (
    <Source id="adsb-interference" type="geojson" data={filteredData}>
      <Layer
        id="adsb-interference-circles"
        type="circle"
        paint={circlePaint}
      />
    </Source>
  );
}
