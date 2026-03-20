import { useEffect, useMemo, useState } from 'react';
import { Source, Layer, useMap } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';

export interface InfrastructureLayerProps {
  visible: boolean;
}

/** Color map by route_type */
export const ROUTE_TYPE_COLORS: Record<string, string> = {
  telecom_cable: '#3B82F6',
  power_cable: '#EAB308',
  gas_pipeline: '#F97316',
  oil_pipeline: '#F97316',
};

interface RouteFeature {
  type: 'Feature';
  geometry: { type: string; coordinates: number[][] };
  properties: Record<string, unknown>;
}

interface RoutesGeoJSON {
  type: string;
  features: RouteFeature[];
}

interface InfrastructureAlert {
  id: number;
  route_id: number;
  active: boolean;
  [key: string]: unknown;
}

/**
 * Process route GeoJSON data and merge alert (flagged) status into feature properties.
 * Exported for testing.
 */
export function processRouteData(
  routesData: RoutesGeoJSON,
  alerts: InfrastructureAlert[],
): RoutesGeoJSON {
  const flaggedRouteIds = new Set(
    alerts.filter((a) => a.active).map((a) => a.route_id),
  );
  return {
    ...routesData,
    features: routesData.features.map((f) => ({
      ...f,
      properties: {
        ...f.properties,
        flagged: flaggedRouteIds.has(f.properties.id as number),
      },
    })),
  };
}

/**
 * Renders subsea cables and pipelines on a MapLibre map with alert highlighting.
 * Must be rendered as a child of a react-map-gl <Map>.
 */
export function InfrastructureLayer({ visible }: InfrastructureLayerProps) {
  const { current: map } = useMap();
  const [bounds, setBounds] = useState({ west: -180, south: -90, east: 180, north: 90 });

  // Track viewport bounds for spatial queries
  useEffect(() => {
    if (!map) return;
    const updateBounds = () => {
      const b = map.getBounds();
      setBounds({
        west: b.getWest(),
        south: b.getSouth(),
        east: b.getEast(),
        north: b.getNorth(),
      });
    };
    map.on('moveend', updateBounds);
    updateBounds(); // initial
    return () => {
      map.off('moveend', updateBounds);
    };
  }, [map]);

  // Fetch infrastructure routes within viewport
  const { data: routesData } = useQuery<RoutesGeoJSON>({
    queryKey: ['infrastructure-routes', bounds],
    queryFn: async () => {
      const { west, south, east, north } = bounds;
      const res = await fetch(
        `/api/infrastructure/routes?west=${west}&south=${south}&east=${east}&north=${north}&simplify=0.001`,
      );
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: visible,
    staleTime: 30_000,
  });

  // Fetch alerts to flag routes
  const { data: alertsData } = useQuery<{ alerts: InfrastructureAlert[] }>({
    queryKey: ['infrastructure-alerts'],
    queryFn: async () => {
      const res = await fetch('/api/infrastructure/alerts');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: visible,
    refetchInterval: 30_000,
  });

  // Merge flagged status into route features
  const processedData = useMemo(() => {
    if (!routesData) return null;
    return processRouteData(routesData, alertsData?.alerts ?? []);
  }, [routesData, alertsData]);

  // Hover cursor management
  useEffect(() => {
    if (!map || !visible) return;
    const onMouseEnter = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const onMouseLeave = () => {
      map.getCanvas().style.cursor = '';
    };
    map.on('mouseenter', 'infra-routes', onMouseEnter);
    map.on('mouseleave', 'infra-routes', onMouseLeave);
    map.on('mouseenter', 'infra-routes-flagged', onMouseEnter);
    map.on('mouseleave', 'infra-routes-flagged', onMouseLeave);
    return () => {
      map.off('mouseenter', 'infra-routes', onMouseEnter);
      map.off('mouseleave', 'infra-routes', onMouseLeave);
      map.off('mouseenter', 'infra-routes-flagged', onMouseEnter);
      map.off('mouseleave', 'infra-routes-flagged', onMouseLeave);
    };
  }, [map, visible]);

  if (!visible || !processedData) return null;

  return (
    <Source id="infrastructure" type="geojson" data={processedData}>
      {/* Unflagged routes -- color by type */}
      <Layer
        id="infra-routes"
        type="line"
        filter={['!=', ['get', 'flagged'], true]}
        paint={{
          'line-color': [
            'match',
            ['get', 'route_type'],
            'telecom_cable', '#3B82F6',
            'power_cable', '#EAB308',
            'gas_pipeline', '#F97316',
            'oil_pipeline', '#F97316',
            '#6B7280',
          ],
          'line-width': 1,
          'line-opacity': 0.4,
        }}
      />
      {/* Flagged routes -- red, thicker */}
      <Layer
        id="infra-routes-flagged"
        type="line"
        filter={['==', ['get', 'flagged'], true]}
        paint={{
          'line-color': '#EF4444',
          'line-width': 3,
          'line-opacity': 0.8,
        }}
      />
    </Source>
  );
}
