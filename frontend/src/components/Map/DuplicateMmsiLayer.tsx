import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';

export interface DuplicateMmsiLayerProps {
  visible: boolean;
}

interface DuplicateAnomalyItem {
  id: number;
  mmsi: number;
  rule_id: string;
  details: {
    reported_lat?: number;
    reported_lon?: number;
    other_lat?: number;
    other_lon?: number;
    position_a?: { lat: number; lon: number };
    position_b?: { lat: number; lon: number };
    [key: string]: unknown;
  };
}

interface AnomalyResponse {
  items: DuplicateAnomalyItem[];
  total: number;
}

/**
 * Extract the two positions from a duplicate MMSI anomaly's details.
 * Returns null if positions cannot be determined.
 */
function extractPositions(
  details: DuplicateAnomalyItem['details'],
): { posA: { lat: number; lon: number }; posB: { lat: number; lon: number } } | null {
  if (details.position_a && details.position_b) {
    return { posA: details.position_a, posB: details.position_b };
  }
  if (
    details.reported_lat != null &&
    details.reported_lon != null &&
    details.other_lat != null &&
    details.other_lon != null
  ) {
    return {
      posA: { lat: details.reported_lat, lon: details.reported_lon },
      posB: { lat: details.other_lat, lon: details.other_lon },
    };
  }
  return null;
}

/** Convert duplicate MMSI anomalies to GeoJSON. Exported for tests. */
export function buildDuplicateMmsiGeoJson(
  items: DuplicateAnomalyItem[],
): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];

  for (const anomaly of items) {
    const positions = extractPositions(anomaly.details);
    if (!positions) continue;

    const { posA, posB } = positions;

    // Line between positions
    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [posA.lon, posA.lat],
          [posB.lon, posB.lat],
        ],
      },
      properties: { type: 'line', anomalyId: anomaly.id },
    });

    // Label at midpoint
    features.push({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [
          (posA.lon + posB.lon) / 2,
          (posA.lat + posB.lat) / 2,
        ],
      },
      properties: { type: 'label', text: 'Duplicate MMSI', anomalyId: anomaly.id },
    });
  }

  return { type: 'FeatureCollection', features };
}

/**
 * Renders dashed lines between duplicate MMSI position pairs on a MapLibre map.
 */
export function DuplicateMmsiLayer({ visible }: DuplicateMmsiLayerProps) {
  const { data } = useQuery<AnomalyResponse>({
    queryKey: ['duplicateMmsi'],
    queryFn: async () => {
      const res = await fetch('/api/anomalies?rule_id=spoof_duplicate_mmsi&resolved=false&per_page=1000');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: visible,
    refetchInterval: 60_000,
  });

  const geojson = useMemo(() => {
    if (!data?.items) return null;
    return buildDuplicateMmsiGeoJson(data.items);
  }, [data]);

  if (!visible || !geojson) return null;

  return (
    <Source id="duplicate-mmsi" type="geojson" data={geojson}>
      <Layer
        id="dup-mmsi-lines"
        type="line"
        filter={['==', ['get', 'type'], 'line']}
        paint={{
          'line-color': '#EF4444',
          'line-width': 2,
          'line-dasharray': [4, 4],
        }}
      />
      <Layer
        id="dup-mmsi-labels"
        type="symbol"
        filter={['==', ['get', 'type'], 'label']}
        layout={{
          'text-field': ['get', 'text'],
          'text-size': 10,
          'text-font': ['Open Sans Regular'],
        }}
        paint={{
          'text-color': '#EF4444',
          'text-halo-color': '#000',
          'text-halo-width': 1,
        }}
      />
    </Source>
  );
}
