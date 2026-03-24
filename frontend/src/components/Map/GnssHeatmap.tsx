import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import type { FillLayerSpecification, LineLayerSpecification } from 'maplibre-gl';

export interface GnssHeatmapProps {
  visible: boolean;
  centerTime?: Date;
  windowSize?: string; // "6h" | "12h" | "24h" | "3d" | "7d"
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

/**
 * @deprecated Use the new polygon-based GNSS zone API instead.
 * Convert spoofing events to GeoJSON FeatureCollection (legacy point-based format).
 */
export function buildGnssSpoofingGeoJson(
  events: { lat: number; lon: number; severity: string }[],
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

/** Parse a window size string like "6h", "24h", "3d", "7d" into hours. */
function parseWindowHours(windowSize: string): number {
  const match = windowSize.match(/^(\d+)(h|d)$/);
  if (!match) return 24;
  const value = parseInt(match[1], 10);
  const unit = match[2];
  return unit === 'd' ? value * 24 : value;
}

/** Add opacity_factor to each feature based on age relative to the time window. */
function addTemporalFade(
  geojson: GeoJSON.FeatureCollection,
  centerTime: Date,
  windowHours: number,
): GeoJSON.FeatureCollection {
  const centerMs = centerTime.getTime();

  return {
    type: 'FeatureCollection',
    features: geojson.features.map((feature) => {
      const detectedAt = feature.properties?.detected_at;
      if (!detectedAt) {
        return {
          ...feature,
          properties: { ...feature.properties, opacity_factor: 1 },
        };
      }

      const ageMs = centerMs - new Date(detectedAt).getTime();
      const ageHours = ageMs / 3_600_000;
      const opacityFactor = Math.max(0.2, 1 - ageHours / windowHours);

      return {
        ...feature,
        properties: { ...feature.properties, opacity_factor: opacityFactor },
      };
    }),
  };
}

/**
 * Renders GNSS interference zones as filled polygons with color intensity
 * based on affected_count, event_type, and temporal fade.
 *
 * Spoofing zones use a red/orange spectrum, jamming zones use purple/blue.
 * Opacity decreases for older zones within the time window.
 */
export function GnssHeatmap({
  visible,
  centerTime,
  windowSize = '24h',
}: GnssHeatmapProps) {
  const effectiveCenterTime = centerTime ?? new Date();
  const windowHours = parseWindowHours(windowSize);

  const { data: rawData } = useQuery<GeoJSON.FeatureCollection>({
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

  const data = useMemo(() => {
    if (!rawData) return null;
    return addTemporalFade(rawData, effectiveCenterTime, windowHours);
  }, [rawData, effectiveCenterTime, windowHours]);

  const fillPaint: FillLayerSpecification['paint'] = {
    'fill-color': [
      'case',
      ['==', ['get', 'event_type'], 'jamming'],
      // Jamming: purple/blue spectrum based on affected_count
      [
        'interpolate', ['linear'], ['get', 'affected_count'],
        1, 'rgba(147,51,234,0.3)',
        15, 'rgba(99,102,241,0.8)',
      ],
      // Spoofing (default): red/orange spectrum based on affected_count
      [
        'interpolate', ['linear'], ['get', 'affected_count'],
        1, 'rgba(249,115,22,0.3)',
        15, 'rgba(239,68,68,0.8)',
      ],
    ],
    'fill-opacity': ['get', 'opacity_factor'],
  };

  const linePaint: LineLayerSpecification['paint'] = {
    'line-color': [
      'case',
      ['==', ['get', 'event_type'], 'jamming'],
      'rgba(99,102,241,0.9)',
      'rgba(239,68,68,0.9)',
    ],
    'line-width': 1,
  };

  if (!visible || !data) return null;

  return (
    <Source id="gnss-zones" type="geojson" data={data}>
      <Layer
        id="gnss-zones-fill"
        type="fill"
        paint={fillPaint}
      />
      <Layer
        id="gnss-zones-outline"
        type="line"
        paint={linePaint}
      />
    </Source>
  );
}
