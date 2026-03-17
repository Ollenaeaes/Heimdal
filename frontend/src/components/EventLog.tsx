import { useState, useMemo, useCallback } from 'react';
import { Cartesian3 } from 'cesium';
import { getCesiumViewer } from './Globe/cesiumViewer';
import { useVesselStore } from '../hooks/useVesselStore';
import { useLookbackStore } from '../hooks/useLookbackStore';
import { useAlertStream, type AlertEvent } from '../hooks/useAlertStream';

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#EF4444',
  high: '#F97316',
  moderate: '#EAB308',
  low: '#6B7280',
};

const RULE_LABELS: Record<string, string> = {
  ais_gap: 'AIS gap detected',
  sts_proximity: 'STS zone proximity',
  dark_rendezvous: 'Dark rendezvous detected',
  sanctions_corridor: 'Sanctions corridor transit',
  draft_change: 'Significant draft change',
  destination_change: 'Destination changed',
  speed_anomaly: 'Speed anomaly',
  flag_change: 'Flag change detected',
  encounter: 'Vessel encounter',
  loitering: 'Loitering detected',
  port_visit: 'Port visit',
};

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '—';
  }
}

export default function EventLog() {
  const { events } = useAlertStream();
  const [open, setOpen] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<Set<string>>(
    new Set(['critical', 'high', 'moderate', 'low']),
  );

  const vessels = useVesselStore((s) => s.vessels);
  const selectVessel = useVesselStore((s) => s.selectVessel);

  const toggleSeverity = useCallback((sev: string) => {
    setSeverityFilter((prev) => {
      const next = new Set(prev);
      if (next.has(sev)) {
        next.delete(sev);
      } else {
        next.add(sev);
      }
      return next;
    });
  }, []);

  const filtered = useMemo(
    () => events.filter((e) => severityFilter.has(e.severity)),
    [events, severityFilter],
  );

  const handleFlyTo = useCallback(
    (event: AlertEvent) => {
      const vessel = vessels.get(event.mmsi);
      const lat = event.lat ?? vessel?.lat;
      const lon = event.lon ?? vessel?.lon;

      if (lat != null && lon != null) {
        const viewer = getCesiumViewer();
        if (viewer) {
          viewer.camera.flyTo({
            destination: Cartesian3.fromDegrees(lon, lat, 50_000),
            duration: 1.5,
          });
        }
      }
      selectVessel(event.mmsi);
    },
    [vessels, selectVessel],
  );

  const lookbackActive = useLookbackStore((s) => s.isActive);
  const activeCount = events.filter((e) => e.severity === 'critical' || e.severity === 'high').length;

  return (
    <div className={`absolute left-0 right-0 z-30 ${lookbackActive ? 'bottom-[60px]' : 'bottom-0'}`}>
      {/* Toggle bar */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1 text-xs text-slate-300 bg-slate-800/90 border-t border-slate-700/50 hover:bg-slate-700/90 backdrop-blur-sm w-full"
      >
        <span className="text-[0.65rem]">{open ? '▼' : '▲'}</span>
        <span className="font-medium">Event Log</span>
        {activeCount > 0 && (
          <span className="ml-1 px-1.5 py-0.5 rounded-full text-[0.6rem] font-mono bg-red-500/20 text-red-400">
            {activeCount}
          </span>
        )}
        <span className="text-slate-500 text-[0.65rem] ml-auto">
          {filtered.length} events
        </span>
      </button>

      {/* Event log panel */}
      {open && (
        <div
          className="bg-slate-800/95 backdrop-blur-sm border-t border-slate-700/50"
          style={{ height: 200 }}
        >
          {/* Severity filter toggles */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-slate-700/30">
            {(['critical', 'high', 'moderate', 'low'] as const).map((sev) => (
              <button
                key={sev}
                onClick={() => toggleSeverity(sev)}
                className={`px-2 py-0.5 rounded text-[0.65rem] font-medium uppercase transition-colors ${
                  severityFilter.has(sev)
                    ? 'text-white'
                    : 'text-slate-600 opacity-50'
                }`}
                style={{
                  backgroundColor: severityFilter.has(sev)
                    ? `${SEVERITY_COLORS[sev]}22`
                    : 'transparent',
                  color: severityFilter.has(sev)
                    ? SEVERITY_COLORS[sev]
                    : undefined,
                }}
              >
                {sev}
              </button>
            ))}
          </div>

          {/* Scrollable event list */}
          <div className="overflow-y-auto" style={{ height: 'calc(200px - 36px)' }}>
            {filtered.length === 0 ? (
              <div className="flex items-center justify-center h-full text-slate-500 text-xs">
                No events
              </div>
            ) : (
              filtered.map((event, idx) => (
                <div
                  key={event.id ?? `${event.mmsi}-${event.timestamp}-${idx}`}
                  className="flex items-center gap-2 px-3 py-1 hover:bg-slate-700/30 text-[0.7rem] border-b border-slate-700/10"
                >
                  {/* Timestamp */}
                  <span className="shrink-0 font-mono text-slate-500 w-16">
                    {formatTime(event.timestamp)}
                  </span>

                  {/* Severity badge */}
                  <span
                    className="shrink-0 w-16 text-center font-mono font-medium uppercase text-[0.6rem] rounded px-1 py-0.5"
                    style={{
                      color: SEVERITY_COLORS[event.severity],
                      backgroundColor: `${SEVERITY_COLORS[event.severity]}15`,
                    }}
                  >
                    {event.severity}
                  </span>

                  {/* Vessel name */}
                  <span className="shrink-0 text-slate-200 font-medium truncate w-36">
                    {event.vesselName ?? `MMSI ${event.mmsi}`}
                  </span>

                  {/* Rule description */}
                  <span className="text-slate-400 truncate flex-1">
                    {RULE_LABELS[event.ruleId] ?? event.ruleId}
                  </span>

                  {/* Fly to button */}
                  <button
                    onClick={() => handleFlyTo(event)}
                    className="shrink-0 text-[0.6rem] text-blue-400 hover:text-blue-300 font-medium"
                  >
                    → Fly to
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
