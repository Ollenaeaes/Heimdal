import { useEffect, useMemo, useRef } from 'react';
import { Cartesian3, Color, GeoJsonDataSource, Entity as CesiumEntity } from 'cesium';
import { useQuery } from '@tanstack/react-query';
import { getCesiumViewer } from './cesiumViewer';

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

interface InfrastructureAlert {
  id: number;
  mmsi: number;
  vessel_name: string;
  risk_tier: string;
  risk_score: number;
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

function formatTimeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/**
 * Renders infrastructure routes using a single GeoJsonDataSource for performance.
 * Unflagged routes are very subtle (low opacity, thin).
 * Flagged routes (with infrastructure_events) are highlighted red.
 */
export function InfrastructureOverlay({ visible }: InfrastructureOverlayProps) {
  const dataSourceRef = useRef<GeoJsonDataSource | null>(null);

  const { data: routesData } = useQuery<{ type: string; features: any[] }>({
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

  const alertedRouteIds = useMemo(() => {
    return new Set((alertsData?.alerts ?? []).map((a) => a.route_id));
  }, [alertsData]);

  const alertsByRoute = useMemo(() => {
    const map = new Map<number, InfrastructureAlert[]>();
    for (const a of (alertsData?.alerts ?? [])) {
      const existing = map.get(a.route_id) ?? [];
      existing.push(a);
      map.set(a.route_id, existing);
    }
    return map;
  }, [alertsData]);

  // Load/update the GeoJSON data source
  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed() || !routesData) return;

    // Remove old data source
    if (dataSourceRef.current) {
      viewer.dataSources.remove(dataSourceRef.current, true);
      dataSourceRef.current = null;
    }

    if (!visible) return;

    const ds = new GeoJsonDataSource('infrastructure');

    ds.load(routesData, {
      stroke: Color.fromCssColorString('#3B82F6').withAlpha(0.15),
      strokeWidth: 1,
      clampToGround: true,
    }).then(() => {
      if (viewer.isDestroyed()) return;

      // Style each entity based on route_type and alert status
      const entities = ds.entities.values;
      for (const entity of entities) {
        const props = entity.properties;
        if (!props) continue;

        const routeType = props.route_type?.getValue?.() ?? '';
        const routeId = props.id?.getValue?.() ?? 0;
        const routeName = props.name?.getValue?.() ?? 'Unknown';
        const isAlerting = alertedRouteIds.has(routeId);
        const colorHex = ROUTE_TYPE_COLORS[routeType] ?? '#3B82F6';
        const typeLabel = ROUTE_TYPE_LABELS[routeType] ?? routeType;

        // Set entity ID for hover detection
        entity.id = `infra-route-${routeId}`;
        entity.name = routeName;

        // Build description
        let desc = `<b>${routeName}</b><br/>Type: ${typeLabel}`;
        const operator = props.operator?.getValue?.();
        if (operator) desc += `<br/>Operator: ${operator}`;

        const routeAlerts = alertsByRoute.get(routeId) ?? [];
        if (routeAlerts.length > 0) {
          desc += `<br/><br/><b style="color:#EF4444;">Alerts (${routeAlerts.length})</b>`;
          for (const a of routeAlerts) {
            const status = a.active ? '<span style="color:#EF4444;">ACTIVE</span>' : `ended ${formatTimeAgo(a.exit_time!)}`;
            desc += `<div style="margin:4px 0;padding:4px;border-left:3px solid ${a.risk_tier === 'red' ? '#EF4444' : '#EAB308'};padding-left:8px;">`;
            desc += `<b>${a.vessel_name?.trim() || `MMSI ${a.mmsi}`}</b> (${a.risk_tier.toUpperCase()})`;
            desc += `<br/>Entry: ${new Date(a.entry_time).toUTCString()}`;
            desc += `<br/>Status: ${status}`;
            if (a.duration_minutes != null) desc += `<br/>Duration: ${Math.round(a.duration_minutes)}min`;
            if (a.min_speed != null) desc += `<br/>Min Speed: ${a.min_speed.toFixed(1)} kn`;
            desc += `</div>`;
          }
        }

        entity.description = desc as any;

        // Style the polyline
        if (entity.polyline) {
          if (isAlerting) {
            entity.polyline.material = Color.fromCssColorString('#EF4444').withAlpha(0.8) as any;
            entity.polyline.width = 3 as any;
          } else {
            entity.polyline.material = Color.fromCssColorString(colorHex).withAlpha(0.15) as any;
            entity.polyline.width = 1 as any;
          }
        }

        // Hide point markers from GeoJSON (endpoints) — too many, not useful
        if (entity.billboard) {
          entity.billboard.show = false as any;
        }
        if (entity.point) {
          entity.point.show = false as any;
        }
        // Hide auto-generated labels
        if (entity.label) {
          entity.label.show = false as any;
        }
      }

      viewer.dataSources.add(ds);
      dataSourceRef.current = ds;
    });

    return () => {
      if (dataSourceRef.current && viewer && !viewer.isDestroyed()) {
        viewer.dataSources.remove(dataSourceRef.current, true);
        dataSourceRef.current = null;
      }
    };
  }, [routesData, visible, alertedRouteIds, alertsByRoute]);

  // Hide/show when visibility toggles
  useEffect(() => {
    if (dataSourceRef.current) {
      dataSourceRef.current.show = visible;
    }
  }, [visible]);

  return null; // All rendering handled via Cesium dataSources directly
}
