import { useMemo, useState } from 'react';
import { CustomDataSource, Entity, PolylineGraphics, PointGraphics, LabelGraphics } from 'resium';
import { Cartesian3, Color, Cartesian2, LabelStyle, VerticalOrigin, NearFarScalar } from 'cesium';
import { useQuery } from '@tanstack/react-query';

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

/** Human-readable labels for route types */
export const ROUTE_TYPE_LABELS: Record<string, string> = {
  telecom_cable: 'Telecom Cable',
  power_cable: 'Power Cable',
  gas_pipeline: 'Gas Pipeline',
  oil_pipeline: 'Oil Pipeline',
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

interface InfrastructureAlert {
  id: number;
  mmsi: number;
  vessel_name: string;
  risk_tier: string;
  risk_score: number;
  lat: number;
  lon: number;
  route_id: number;
  route_name: string;
  route_type: string;
  entry_time: string;
  exit_time: string | null;
  duration_minutes: number | null;
  min_speed: number | null;
  max_alignment: number | null;
  active: boolean;
  details: Record<string, unknown>;
}

function getPointMarkerPixelSize(routeType: string): number {
  return routeType.includes('cable') ? 8 : 10;
}

function formatTimeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/**
 * Renders infrastructure routes as polylines, with alert-based halos
 * from actual infrastructure_events (not raw proximity).
 */
export function InfrastructureOverlay({ visible }: InfrastructureOverlayProps) {
  const { data } = useQuery<InfrastructureRoutesResponse>({
    queryKey: ['infrastructureRoutes'],
    queryFn: () => fetch('/api/infrastructure/routes').then((r) => r.json()),
    enabled: visible,
  });

  const { data: alertsData } = useQuery<{ alerts: InfrastructureAlert[] }>({
    queryKey: ['infrastructureAlerts'],
    queryFn: () => fetch('/api/infrastructure/alerts').then((r) => r.json()),
    enabled: visible,
    refetchInterval: 30_000,
  });

  const features = data?.features ?? [];
  const alerts = alertsData?.alerts ?? [];

  // Group alerts by route_id for quick lookup
  const alertsByRoute = useMemo(() => {
    const map = new Map<number, InfrastructureAlert[]>();
    for (const a of alerts) {
      const existing = map.get(a.route_id) ?? [];
      existing.push(a);
      map.set(a.route_id, existing);
    }
    return map;
  }, [alerts]);

  // Set of route IDs that have active alerts
  const alertedRouteIds = useMemo(() => {
    return new Set(alerts.map((a) => a.route_id));
  }, [alerts]);

  // Extract point features from route endpoints
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

  if (!visible) return null;

  return (
    <>
      <CustomDataSource name="infrastructure-routes">
        {/* Route polylines */}
        {features.map((f) => {
          const coords = f.geometry.coordinates;
          const positions = coords.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat));
          const colorHex = ROUTE_TYPE_COLORS[f.properties.route_type] ?? '#3B82F6';
          const hasAlert = alertedRouteIds.has(f.properties.id);
          const color = Color.fromCssColorString(colorHex);
          const typeLabel = ROUTE_TYPE_LABELS[f.properties.route_type] ?? f.properties.route_type;
          const routeName = f.properties.name || 'Unknown';

          // Build description with alert info if flagged
          const routeAlerts = alertsByRoute.get(f.properties.id) ?? [];
          let description = `<b>${routeName}</b><br/>Type: ${typeLabel}`;
          if (f.properties.operator) {
            description += `<br/>Operator: ${f.properties.operator}`;
          }
          if (routeAlerts.length > 0) {
            description += `<br/><br/><b style="color:#EF4444;">Alerts (${routeAlerts.length})</b><br/>`;
            for (const a of routeAlerts) {
              const status = a.active ? '<span style="color:#EF4444;">ACTIVE</span>' : `ended ${formatTimeAgo(a.exit_time!)}`;
              description += `<div style="margin:4px 0;padding:4px;border-left:3px solid ${a.risk_tier === 'red' ? '#EF4444' : '#EAB308'};padding-left:8px;">`;
              description += `<b>${a.vessel_name?.trim() || `MMSI ${a.mmsi}`}</b> (${a.risk_tier.toUpperCase()})`;
              description += `<br/>Entry: ${new Date(a.entry_time).toUTCString()}`;
              description += `<br/>Status: ${status}`;
              if (a.duration_minutes != null) {
                description += `<br/>Duration: ${Math.round(a.duration_minutes)}min`;
              }
              if (a.min_speed != null) {
                description += `<br/>Min Speed: ${a.min_speed.toFixed(1)} kn`;
              }
              if (a.max_alignment != null) {
                description += `<br/>Max Alignment: ${a.max_alignment.toFixed(0)}°`;
              }
              description += `</div>`;
            }
          }

          // Midpoint for label
          const midIdx = Math.floor(coords.length / 2);
          const midPos = Cartesian3.fromDegrees(coords[midIdx][0], coords[midIdx][1]);

          return (
            <Entity
              key={`route-${f.properties.id}`}
              id={`infra-route-${f.properties.id}`}
              name={routeName}
              description={description}
              position={midPos}
            >
              <PolylineGraphics
                positions={positions}
                width={hasAlert ? 4 : 2}
                material={hasAlert ? Color.fromCssColorString('#EF4444').withAlpha(0.8) : color}
              />
              <LabelGraphics
                text={routeName}
                font="11px Inter, sans-serif"
                fillColor={Color.fromCssColorString(colorHex)}
                style={LabelStyle.FILL_AND_OUTLINE}
                outlineColor={Color.BLACK}
                outlineWidth={2}
                verticalOrigin={VerticalOrigin.CENTER}
                pixelOffset={new Cartesian2(0, -8)}
                scaleByDistance={new NearFarScalar(5e4, 1.0, 5e6, 0)}
                translucencyByDistance={new NearFarScalar(5e4, 1.0, 2e6, 0)}
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
            <Entity
              key={pt.id}
              id={`infra-point-${pt.id}`}
              position={position}
              name={`${pt.name} (${pt.isStart ? 'Landing A' : 'Landing B'})`}
              description={`<b>${pt.name}</b><br/>Type: ${ROUTE_TYPE_LABELS[pt.routeType] ?? pt.routeType}`}
            >
              <PointGraphics
                pixelSize={pixelSize}
                color={color}
                outlineColor={Color.WHITE}
                outlineWidth={1}
              />
            </Entity>
          );
        })}
      </CustomDataSource>
    </>
  );
}
