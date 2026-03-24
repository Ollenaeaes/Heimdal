import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import type { CircleLayerSpecification } from 'maplibre-gl';

export interface GnssHeatmapProps {
  visible: boolean;
  centerTime?: Date;
  windowSize?: string; // "1h" | "3h" | "6h"
}

/**
 * Renders GNSS spoofed positions as dots on the map.
 *
 * Red dots: where GPS says the vessel is (spoofing target)
 * Cyan dots: where the vessel actually was (interference area)
 */
export function GnssHeatmap({
  visible,
  centerTime,
  windowSize = '1h',
}: GnssHeatmapProps) {
  const effectiveCenterTime = centerTime ?? new Date();

  const { data } = useQuery<GeoJSON.FeatureCollection>({
    queryKey: ['gnssPositions', effectiveCenterTime.toISOString(), windowSize],
    queryFn: async () => {
      const params = new URLSearchParams({
        center: effectiveCenterTime.toISOString(),
        window: windowSize,
      });
      const res = await fetch(`/api/gnss-positions?${params}`);
      if (!res.ok) throw new Error(`GNSS positions fetch failed: ${res.status}`);
      return res.json();
    },
    enabled: visible,
    refetchInterval: 60_000,
  });

  const spoofedPaint: CircleLayerSpecification['paint'] = {
    'circle-color': [
      'interpolate', ['linear'], ['get', 'deviation_km'],
      80, 'rgba(249,115,22,0.6)',   // orange at threshold
      200, 'rgba(239,68,68,0.8)',   // red at high deviation
      500, 'rgba(220,38,38,0.9)',   // deep red at extreme
    ],
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      3, 2,
      6, 4,
      10, 6,
    ],
    'circle-stroke-width': 0.5,
    'circle-stroke-color': 'rgba(239,68,68,0.5)',
  };

  const realPaint: CircleLayerSpecification['paint'] = {
    'circle-color': [
      'interpolate', ['linear'], ['get', 'deviation_km'],
      80, 'rgba(6,182,212,0.5)',    // light cyan at threshold
      200, 'rgba(6,182,212,0.7)',   // cyan
      500, 'rgba(14,116,144,0.9)', // teal at extreme
    ],
    'circle-radius': [
      'interpolate', ['linear'], ['zoom'],
      3, 2,
      6, 3,
      10, 5,
    ],
    'circle-stroke-width': 0.5,
    'circle-stroke-color': 'rgba(6,182,212,0.4)',
  };

  if (!visible || !data) return null;

  return (
    <Source id="gnss-positions" type="geojson" data={data}>
      {/* Spoofed positions — red dots (where GPS says vessel is) */}
      <Layer
        id="gnss-spoofed-dots"
        type="circle"
        filter={['==', ['get', 'point_type'], 'spoofed']}
        paint={spoofedPaint}
      />
      {/* Real positions — cyan dots (where vessel actually was) */}
      <Layer
        id="gnss-real-dots"
        type="circle"
        filter={['==', ['get', 'point_type'], 'real']}
        paint={realPaint}
      />
    </Source>
  );
}
