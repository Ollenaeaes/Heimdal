import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import type { FillLayerSpecification, LineLayerSpecification } from 'maplibre-gl';

export interface GnssHeatmapProps {
  visible: boolean;
  centerTime?: Date;
  windowSize?: string; // "6h" | "12h" | "24h" | "3d" | "7d"
}

/** Color palette for zone types */
const ZONE_COLORS = {
  spoofing: { fill: 'rgba(239,68,68,0.25)', stroke: 'rgba(239,68,68,0.7)' },
  interference_area: { fill: 'rgba(6,182,212,0.20)', stroke: 'rgba(6,182,212,0.6)' },
  jamming: { fill: 'rgba(168,85,247,0.22)', stroke: 'rgba(168,85,247,0.65)' },
};

/**
 * Renders GNSS interference zones as filled polygons on the map.
 *
 * Red/orange: spoofing target zones (where GPS positions get dragged to)
 * Cyan/blue:  interference area zones (where vessels physically were)
 * Purple:     jamming zones (GPS loss causing cardinal-direction jumps)
 */
export function GnssHeatmap({
  visible,
  centerTime,
  windowSize = '24h',
}: GnssHeatmapProps) {
  const effectiveCenterTime = centerTime ?? new Date();

  const { data } = useQuery<GeoJSON.FeatureCollection>({
    queryKey: ['gnssZones', effectiveCenterTime.toISOString(), windowSize],
    queryFn: async () => {
      const params = new URLSearchParams({
        center: effectiveCenterTime.toISOString(),
        window: windowSize,
      });
      const res = await fetch(`/api/gnss-zones?${params}`);
      if (!res.ok) throw new Error(`GNSS zones fetch failed: ${res.status}`);
      return res.json();
    },
    enabled: visible,
    refetchInterval: 60_000,
  });

  // Filter out features with null geometry
  const filteredData = useMemo(() => {
    if (!data) return null;
    return {
      ...data,
      features: data.features.filter((f) => f.geometry != null),
    };
  }, [data]);

  // Fill paint — color by event_type
  const fillPaint: FillLayerSpecification['paint'] = {
    'fill-color': [
      'match', ['get', 'event_type'],
      'spoofing', ZONE_COLORS.spoofing.fill,
      'interference_area', ZONE_COLORS.interference_area.fill,
      'jamming', ZONE_COLORS.jamming.fill,
      'rgba(239,68,68,0.2)', // fallback
    ],
    'fill-opacity': 0.8,
  };

  // Stroke paint — color by event_type
  const linePaint: LineLayerSpecification['paint'] = {
    'line-color': [
      'match', ['get', 'event_type'],
      'spoofing', ZONE_COLORS.spoofing.stroke,
      'interference_area', ZONE_COLORS.interference_area.stroke,
      'jamming', ZONE_COLORS.jamming.stroke,
      'rgba(239,68,68,0.6)', // fallback
    ],
    'line-width': 1.5,
    'line-opacity': 0.9,
  };

  if (!visible || !filteredData || filteredData.features.length === 0) return null;

  return (
    <Source id="gnss-zones" type="geojson" data={filteredData}>
      {/* Zone polygons — filled */}
      <Layer
        id="gnss-zone-fill"
        type="fill"
        paint={fillPaint}
      />
      {/* Zone outlines */}
      <Layer
        id="gnss-zone-outline"
        type="line"
        paint={linePaint}
      />
    </Source>
  );
}
