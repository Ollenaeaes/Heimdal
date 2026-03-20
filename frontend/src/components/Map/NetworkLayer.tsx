import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { NetworkApiResponse } from '../VesselPanel/NetworkGraph';

export interface NetworkLayerProps {
  visible: boolean;
}

/** Edge types that render with dashed lines. */
const DASHED_EDGE_TYPES = new Set(['proximity', 'ownership']);

/** Edge type to line color mapping. */
const EDGE_TYPE_COLORS: Record<string, string> = {
  encounter: '#FFFFFF',
  proximity: '#6B7280',
  port_visit: '#06B6D4',
  ownership: '#9333EA',
};

interface NetworkEdgeFeature {
  lon1: number;
  lat1: number;
  lon2: number;
  lat2: number;
  edgeType: string;
}

/** Convert network API response into GeoJSON for edges and nodes. Exported for tests. */
export function buildNetworkGeoJson(
  data: NetworkApiResponse,
  selectedMmsi: number,
  vessels: Map<number, { lat: number; lon: number }>,
): { edges: GeoJSON.FeatureCollection; nodes: GeoJSON.FeatureCollection } {
  const edgeFeatures: GeoJSON.Feature[] = [];
  const nodeFeatures: GeoJSON.Feature[] = [];
  const selectedVessel = vessels.get(selectedMmsi);

  if (!selectedVessel || !data.edges) {
    return {
      edges: { type: 'FeatureCollection', features: [] },
      nodes: { type: 'FeatureCollection', features: [] },
    };
  }

  for (const edge of data.edges) {
    const otherMmsi = edge.vessel_a_mmsi === selectedMmsi
      ? edge.vessel_b_mmsi
      : edge.vessel_a_mmsi;
    const otherVessel = vessels.get(otherMmsi);

    let endLon: number | undefined;
    let endLat: number | undefined;

    if (edge.lat != null && edge.lon != null) {
      endLat = edge.lat;
      endLon = edge.lon;
    } else if (otherVessel) {
      endLat = otherVessel.lat;
      endLon = otherVessel.lon;
    }

    if (endLat == null || endLon == null) continue;

    const dashed = DASHED_EDGE_TYPES.has(edge.edge_type);

    edgeFeatures.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [selectedVessel.lon, selectedVessel.lat],
          [endLon, endLat],
        ],
      },
      properties: {
        edgeType: edge.edge_type,
        dashed,
      },
    });
  }

  // Node circles for connected vessels
  if (data.vessels) {
    for (const key of Object.keys(data.vessels)) {
      const vMmsi = Number(key);
      if (vMmsi === selectedMmsi) continue;
      const vesselPos = vessels.get(vMmsi);
      if (vesselPos) {
        nodeFeatures.push({
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [vesselPos.lon, vesselPos.lat],
          },
          properties: { mmsi: vMmsi },
        });
      }
    }
  }

  return {
    edges: { type: 'FeatureCollection', features: edgeFeatures },
    nodes: { type: 'FeatureCollection', features: nodeFeatures },
  };
}

/**
 * Renders vessel network connections on a MapLibre map.
 * Shows edges between the selected vessel and its network connections,
 * with styling based on edge type.
 */
export function NetworkLayer({ visible }: NetworkLayerProps) {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const vessels = useVesselStore((s) => s.vessels);

  const enabled = visible && selectedMmsi !== null;

  const { data } = useQuery<NetworkApiResponse>({
    queryKey: ['vesselNetwork', selectedMmsi, 1],
    queryFn: async () => {
      const res = await fetch(`/api/vessels/${selectedMmsi}/network?depth=1`);
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled,
  });

  const { edgeGeoJson, nodeGeoJson } = useMemo(() => {
    if (!data || !selectedMmsi) {
      return {
        edgeGeoJson: null,
        nodeGeoJson: null,
      };
    }
    const { edges, nodes } = buildNetworkGeoJson(data, selectedMmsi, vessels);
    return { edgeGeoJson: edges, nodeGeoJson: nodes };
  }, [data, selectedMmsi, vessels]);

  if (!visible || !selectedMmsi || !edgeGeoJson) return null;

  return (
    <>
      {/* Edge lines */}
      <Source id="network-edges" type="geojson" data={edgeGeoJson}>
        {/* Solid edges (encounter, port_visit) */}
        <Layer
          id="network-edges-solid"
          type="line"
          filter={['==', ['get', 'dashed'], false]}
          paint={{
            'line-color': ['match', ['get', 'edgeType'],
              'encounter', '#FFFFFF',
              'port_visit', '#06B6D4',
              '#6B7280',
            ],
            'line-width': 1.5,
          }}
        />
        {/* Dashed edges (proximity, ownership) */}
        <Layer
          id="network-edges-dashed"
          type="line"
          filter={['==', ['get', 'dashed'], true]}
          paint={{
            'line-color': ['match', ['get', 'edgeType'],
              'proximity', '#6B7280',
              'ownership', '#9333EA',
              '#6B7280',
            ],
            'line-width': 1.5,
            'line-dasharray': [4, 4],
          }}
        />
      </Source>

      {/* Node circles */}
      {nodeGeoJson && (
        <Source id="network-nodes" type="geojson" data={nodeGeoJson}>
          <Layer
            id="network-nodes-circles"
            type="circle"
            paint={{
              'circle-radius': 5,
              'circle-color': '#9333EA',
              'circle-opacity': 0.6,
              'circle-stroke-width': 1,
              'circle-stroke-color': '#FFFFFF',
            }}
          />
        </Source>
      )}
    </>
  );
}
