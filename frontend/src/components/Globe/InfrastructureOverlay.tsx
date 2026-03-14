import { useMemo } from 'react';
import { CustomDataSource, Entity, PolylineGraphics, PointGraphics } from 'resium';
import { Cartesian3, Color } from 'cesium';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';

export interface InfrastructureOverlayProps {
  visible: boolean;
}

/** Color map by route_type */
export const ROUTE_TYPE_COLORS: Record<string, string> = {
  telecom_cable: '#3B82F6',
  power_cable: '#EAB308',
  gas_pipeline: '#F97316',
  oil_pipeline: '#F97316',
};

/** Risk halo colors by vessel tier */
const RISK_HALO_COLORS: Record<string, Color> = {
  yellow: Color.fromCssColorString('rgba(234, 179, 8, 0.4)'),
  red: Color.fromCssColorString('rgba(239, 68, 68, 0.5)'),
};

interface RouteFeature {
  type: 'Feature';
  geometry: {
    type: string;
    coordinates: number[][];
  };
  properties: {
    id: number;
    name: string;
    route_type: string;
    operator: string | null;
    buffer_nm: number;
  };
}

interface InfrastructureRoutesResponse {
  type: 'FeatureCollection';
  features: RouteFeature[];
}

/**
 * Determine the point type from metadata (landing_station or platform).
 * For now, we check the route_type and geometry type.
 */
function getPointMarkerPixelSize(routeType: string): number {
  return routeType.includes('cable') ? 8 : 10;
}

/**
 * Find the nearest point on a route to a given vessel position.
 * Returns the closest coordinate pair [lon, lat].
 */
function findNearestSegment(
  coords: number[][],
  vesselLon: number,
  vesselLat: number,
): { nearIdx: number; dist: number } {
  let minDist = Infinity;
  let nearIdx = 0;
  for (let i = 0; i < coords.length; i++) {
    const dx = coords[i][0] - vesselLon;
    const dy = coords[i][1] - vesselLat;
    const d = dx * dx + dy * dy;
    if (d < minDist) {
      minDist = d;
      nearIdx = i;
    }
  }
  return { nearIdx, dist: Math.sqrt(minDist) };
}

/**
 * Extract a small segment of route coordinates around an index.
 */
function extractSegment(coords: number[][], centerIdx: number, radius: number): number[][] {
  const start = Math.max(0, centerIdx - radius);
  const end = Math.min(coords.length - 1, centerIdx + radius);
  return coords.slice(start, end + 1);
}

/**
 * Renders infrastructure routes (cables, pipelines) as polylines on the globe.
 * Also renders risk halos for yellow/red vessels near routes and
 * point features at route endpoints (landing stations / platforms).
 */
export function InfrastructureOverlay({ visible }: InfrastructureOverlayProps) {
  const vessels = useVesselStore((s) => s.vessels);

  const { data } = useQuery<InfrastructureRoutesResponse>({
    queryKey: ['infrastructureRoutes'],
    queryFn: () => fetch('/api/infrastructure/routes').then((r) => r.json()),
    enabled: visible,
  });

  const features = data?.features ?? [];

  // Extract point features from route endpoints (first and last coordinate)
  const pointFeatures = useMemo(() => {
    if (!features.length) return [];
    const points: Array<{
      id: string;
      lon: number;
      lat: number;
      name: string;
      routeType: string;
      isStart: boolean;
    }> = [];
    for (const f of features) {
      const coords = f.geometry.coordinates;
      if (coords.length >= 2) {
        points.push({
          id: `${f.properties.id}-start`,
          lon: coords[0][0],
          lat: coords[0][1],
          name: f.properties.name,
          routeType: f.properties.route_type,
          isStart: true,
        });
        points.push({
          id: `${f.properties.id}-end`,
          lon: coords[coords.length - 1][0],
          lat: coords[coords.length - 1][1],
          name: f.properties.name,
          routeType: f.properties.route_type,
          isStart: false,
        });
      }
    }
    return points;
  }, [features]);

  // Compute risk halos: yellow/red vessels near infrastructure routes
  const riskHalos = useMemo(() => {
    if (!features.length) return [];
    const halos: Array<{
      id: string;
      positions: Cartesian3[];
      color: Color;
    }> = [];

    const vesselArray = Array.from(vessels.values());
    const riskyVessels = vesselArray.filter(
      (v) => v.riskTier === 'yellow' || v.riskTier === 'red',
    );

    if (!riskyVessels.length) return [];

    // For each route, check if any risky vessel is nearby (within ~0.5 deg approx)
    const PROXIMITY_THRESHOLD = 0.5; // degrees, rough approximation
    for (const f of features) {
      const coords = f.geometry.coordinates;
      for (const vessel of riskyVessels) {
        const { nearIdx, dist } = findNearestSegment(coords, vessel.lon, vessel.lat);
        if (dist < PROXIMITY_THRESHOLD) {
          const segmentCoords = extractSegment(coords, nearIdx, 3);
          const positions = segmentCoords.map(([lon, lat]) =>
            Cartesian3.fromDegrees(lon, lat),
          );
          const haloColor = RISK_HALO_COLORS[vessel.riskTier];
          if (haloColor) {
            halos.push({
              id: `halo-${f.properties.id}-${vessel.mmsi}`,
              positions,
              color: haloColor,
            });
          }
        }
      }
    }
    return halos;
  }, [features, vessels]);

  if (!visible) return null;

  return (
    <>
      <CustomDataSource name="infrastructure-routes">
        {/* Route polylines */}
        {features.map((f) => {
          const coords = f.geometry.coordinates;
          const positions = coords.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat));
          const colorHex = ROUTE_TYPE_COLORS[f.properties.route_type] ?? '#3B82F6';
          const color = Color.fromCssColorString(colorHex);
          return (
            <Entity key={`route-${f.properties.id}`} id={`infra-route-${f.properties.id}`}>
              <PolylineGraphics
                positions={positions}
                width={2}
                material={color}
              />
            </Entity>
          );
        })}

        {/* Point features at route endpoints */}
        {pointFeatures.map((pt) => {
          const position = Cartesian3.fromDegrees(pt.lon, pt.lat);
          const colorHex = ROUTE_TYPE_COLORS[pt.routeType] ?? '#3B82F6';
          const color = Color.fromCssColorString(colorHex);
          const pixelSize = getPointMarkerPixelSize(pt.routeType);
          return (
            <Entity key={pt.id} id={`infra-point-${pt.id}`} position={position}>
              <PointGraphics
                pixelSize={pixelSize}
                color={color}
                outlineColor={Color.WHITE}
                outlineWidth={1}
              />
            </Entity>
          );
        })}

        {/* Risk halos */}
        {riskHalos.map((halo) => (
          <Entity key={halo.id} id={`infra-${halo.id}`}>
            <PolylineGraphics
              positions={halo.positions}
              width={8}
              material={halo.color}
            />
          </Entity>
        ))}
      </CustomDataSource>
    </>
  );
}
