import { useQuery } from '@tanstack/react-query';
import { Cartesian3 } from 'cesium';
import { getCesiumViewer } from '../Globe/cesiumViewer';
import { useVesselStore } from '../../hooks/useVesselStore';

interface InfraAlert {
  id: number;
  mmsi: number;
  vessel_name: string | null;
  risk_tier: string;
  risk_score: number;
  lat: number | null;
  lon: number | null;
  route_id: number;
  route_name: string;
  route_type: string;
  entry_time: string;
  min_speed: number | null;
  max_alignment: number | null;
}

interface InfraAlertsResponse {
  alerts: InfraAlert[];
}

interface RouteFeature {
  properties: {
    id: number;
    name: string;
    route_type: string;
    operator: string | null;
    buffer_nm: number;
  };
}

interface InfrastructureRoutesResponse {
  type: string;
  features: RouteFeature[];
}

/** Human-readable route type labels */
const ROUTE_TYPE_LABELS: Record<string, string> = {
  telecom_cable: 'Telecom Cable',
  power_cable: 'Power Cable',
  gas_pipeline: 'Gas Pipeline',
  oil_pipeline: 'Oil Pipeline',
};

/** Risk tier badge colors */
const TIER_COLORS: Record<string, string> = {
  green: 'bg-green-600',
  yellow: 'bg-yellow-500',
  red: 'bg-red-600',
};

export function InfrastructurePanel() {
  const selectVessel = useVesselStore((s) => s.selectVessel);

  const { data: routesData } = useQuery<InfrastructureRoutesResponse>({
    queryKey: ['infrastructureRoutes'],
    queryFn: () => fetch('/api/infrastructure/routes').then((r) => r.json()),
  });

  const { data: alertsData } = useQuery<InfraAlertsResponse>({
    queryKey: ['infraAlerts'],
    queryFn: () => fetch('/api/infrastructure/alerts').then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const routes = routesData?.features ?? [];
  const alerts = alertsData?.alerts ?? [];

  const handleAlertClick = (alert: InfraAlert) => {
    selectVessel(alert.mmsi);
    if (alert.lat != null && alert.lon != null) {
      const viewer = getCesiumViewer();
      if (viewer && !viewer.isDestroyed()) {
        viewer.camera.flyTo({
          destination: Cartesian3.fromDegrees(alert.lon, alert.lat, 50_000),
          duration: 1.5,
        });
      }
    }
  };

  return (
    <div
      className="bg-[#0A0E17]/90 border border-[#1F2937] rounded-lg backdrop-blur-md text-white text-xs overflow-hidden"
      data-testid="infrastructure-panel"
    >
      <div className="px-3 py-2 border-b border-[#1F2937]">
        <h3 className="text-sm font-semibold text-cyan-400">Infrastructure Protection</h3>
      </div>

      {/* Monitored Assets */}
      {routes.length > 0 && (
        <div className="px-3 py-2 border-b border-[#1F2937]">
          <div className="text-[0.65rem] text-slate-400 uppercase tracking-wider mb-1.5">
            Monitored Assets
          </div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {routes.map((r) => (
              <div key={r.properties.id} className="flex items-center justify-between">
                <span className="text-slate-200 truncate">{r.properties.name}</span>
                <span className="text-slate-500 ml-2 shrink-0">
                  {ROUTE_TYPE_LABELS[r.properties.route_type] ?? r.properties.route_type}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alert Feed */}
      <div className="px-3 py-2">
        <div className="text-[0.65rem] text-slate-400 uppercase tracking-wider mb-1.5">
          Corridor Alerts
        </div>
        {alerts.length === 0 ? (
          <div className="text-slate-500 py-2" data-testid="empty-alerts">
            No active corridor alerts
          </div>
        ) : (
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {alerts.map((alert) => (
              <button
                key={alert.id}
                onClick={() => handleAlertClick(alert)}
                className="w-full text-left px-2 py-1.5 rounded hover:bg-slate-700/50 transition-colors"
                data-testid={`infra-alert-${alert.id}`}
              >
                <div className="flex items-center gap-1.5">
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 ${TIER_COLORS[alert.risk_tier] ?? 'bg-gray-500'}`}
                  />
                  <span className="text-slate-200 truncate">
                    {alert.vessel_name ?? `MMSI ${alert.mmsi}`}
                  </span>
                  <span className="text-slate-500 ml-auto shrink-0">
                    {alert.risk_score}
                  </span>
                </div>
                <div className="text-slate-500 text-[0.6rem] mt-0.5 pl-3.5">
                  in {alert.route_name}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
