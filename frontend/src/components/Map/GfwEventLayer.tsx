import { useEffect, useMemo, useState, useCallback } from 'react';
import { Source, Layer, Popup, useMap } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { GfwEventType } from '../../types/api';

export interface GfwEventLayerProps {
  visible: boolean;
}

/** Human-readable labels for GFW event types */
const EVENT_TYPE_LABELS: Record<GfwEventType, string> = {
  ENCOUNTER: 'Encounter',
  LOITERING: 'Loitering',
  AIS_DISABLING: 'AIS Disabling',
  PORT_VISIT: 'Port Visit',
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  ENCOUNTER: 'text-orange-400',
  LOITERING: 'text-yellow-400',
  AIS_DISABLING: 'text-red-400',
  PORT_VISIT: 'text-blue-400',
};

const RISK_TIER_COLORS: Record<string, string> = {
  green: 'text-green-400',
  yellow: 'text-yellow-400',
  red: 'text-red-400',
  blacklisted: 'text-red-300',
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

function formatDuration(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  if (hours < 24) return `${hours.toFixed(1)} hrs`;
  const days = Math.floor(hours / 24);
  const remainingHours = Math.round(hours % 24);
  return `${days}d ${remainingHours}h`;
}

interface GfwEventFeatureProperties {
  id: string;
  type: string;
  start: string;
  end: string | null;
  duration_hours: number | null;
  mmsi: number | null;
  vessel_name: string | null;
  vessel_flag: string | null;
  vessel_type: string | null;
  vessel_risk_tier: string | null;
  encounter_partner_mmsi: number | null;
  encounter_partner_name: string | null;
  encounter_partner_flag: string | null;
  port_name: string | null;
}

/**
 * Build a GeoJSON FeatureCollection from GFW events, filtering by enabled event types.
 * Exported for testing.
 */
export function buildGfwEventsGeoJson(events: any[], showTypes: string[]) {
  const typeSet = new Set(showTypes);
  const features = (events || [])
    .filter((e: any) => typeSet.has(e.type))
    .map((e: any) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [e.lon, e.lat] },
      properties: {
        id: e.id,
        type: e.type,
        start: e.startTime,
        end: e.endTime,
        duration_hours: e.durationHours,
        mmsi: e.vesselMmsi,
        vessel_name: e.vesselName,
        vessel_flag: e.vesselFlag,
        vessel_type: e.vesselType,
        vessel_risk_tier: e.vesselRiskTier,
        encounter_partner_mmsi: e.encounterPartnerMmsi,
        encounter_partner_name: e.encounterPartnerName,
        encounter_partner_flag: e.encounterPartnerFlag,
        port_name: e.portName,
      },
    }));
  return { type: 'FeatureCollection' as const, features };
}

/**
 * Renders GFW event markers on a MapLibre map with color-coded circles by event type.
 * Must be rendered as a child of a react-map-gl <Map>.
 */
export function GfwEventLayer({ visible }: GfwEventLayerProps) {
  const { current: map } = useMap();
  const showGfwEventTypes = useVesselStore((s) => s.filters.showGfwEventTypes);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const [popup, setPopup] = useState<{
    lon: number;
    lat: number;
    properties: GfwEventFeatureProperties;
  } | null>(null);

  const { data: events = [] } = useQuery({
    queryKey: ['gfw-events'],
    queryFn: async () => {
      const res = await fetch('/api/gfw/events');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: visible,
    refetchInterval: 300_000,
  });

  const geojson = useMemo(
    () => buildGfwEventsGeoJson(events, showGfwEventTypes),
    [events, showGfwEventTypes],
  );

  // Click handler for markers
  useEffect(() => {
    if (!map || !visible) return;
    const onClick = (e: maplibregl.MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (feature && feature.geometry.type === 'Point') {
        const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates;
        setPopup({ lon, lat, properties: feature.properties as unknown as GfwEventFeatureProperties });
      }
    };
    const onMouseEnter = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const onMouseLeave = () => {
      map.getCanvas().style.cursor = '';
    };
    map.on('click', 'gfw-event-markers', onClick);
    map.on('mouseenter', 'gfw-event-markers', onMouseEnter);
    map.on('mouseleave', 'gfw-event-markers', onMouseLeave);
    return () => {
      map.off('click', 'gfw-event-markers', onClick);
      map.off('mouseenter', 'gfw-event-markers', onMouseEnter);
      map.off('mouseleave', 'gfw-event-markers', onMouseLeave);
    };
  }, [map, visible]);

  const handleClosePopup = useCallback(() => {
    setPopup(null);
  }, []);

  const handleGoToVessel = useCallback((mmsi: number) => {
    selectVessel(mmsi);
    setPopup(null);
  }, [selectVessel]);

  if (!visible) return null;

  const p = popup?.properties;

  return (
    <>
      {geojson && (
        <Source id="gfw-events" type="geojson" data={geojson}>
          <Layer
            id="gfw-event-markers"
            type="circle"
            paint={{
              'circle-color': [
                'match',
                ['get', 'type'],
                'ENCOUNTER', '#F97316',
                'LOITERING', '#EAB308',
                'AIS_DISABLING', '#EF4444',
                'PORT_VISIT', '#3B82F6',
                '#6B7280',
              ],
              'circle-radius': 5,
              'circle-stroke-width': 1,
              'circle-stroke-color': '#0F172A',
            }}
          />
        </Source>
      )}

      {popup && p && (
        <Popup
          longitude={popup.lon}
          latitude={popup.lat}
          onClose={handleClosePopup}
          closeButton={false}
          closeOnClick={false}
          className="sar-popup"
          anchor="bottom"
          offset={12}
        >
          <div className="bg-[#0B1120] border border-slate-700 text-white p-3 rounded-lg text-xs min-w-[220px] shadow-xl shadow-black/50">
            {/* Header */}
            <div className="flex items-start justify-between mb-2">
              <div className={`font-bold text-sm ${EVENT_TYPE_COLORS[p.type] ?? 'text-gray-300'}`}>
                {EVENT_TYPE_LABELS[p.type as GfwEventType] ?? p.type}
              </div>
              <button
                onClick={handleClosePopup}
                className="ml-3 -mt-0.5 -mr-1 w-6 h-6 flex items-center justify-center rounded hover:bg-slate-700 text-gray-400 hover:text-white transition-colors cursor-pointer"
                aria-label="Close"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
              </button>
            </div>

            {/* Vessel info */}
            {p.mmsi != null && (
              <div className="mb-2">
                <div className="text-gray-300 font-medium">
                  {p.vessel_name || `MMSI ${p.mmsi}`}
                  {p.vessel_flag && <span className="text-gray-500 ml-1">{p.vessel_flag}</span>}
                </div>
                {p.vessel_type && (
                  <div className="text-gray-500">{p.vessel_type}</div>
                )}
                {p.vessel_risk_tier && p.vessel_risk_tier !== 'green' && (
                  <div className={RISK_TIER_COLORS[p.vessel_risk_tier] ?? 'text-gray-400'}>
                    Risk: {p.vessel_risk_tier}
                  </div>
                )}
              </div>
            )}

            {/* Event details */}
            <div className="space-y-0.5 text-gray-400">
              {p.start && (
                <div>Start: <span className="text-gray-300">{formatTime(p.start)}</span></div>
              )}
              {p.end && (
                <div>End: <span className="text-gray-300">{formatTime(p.end)}</span></div>
              )}
              {p.duration_hours != null && (
                <div>Duration: <span className="text-gray-300">{formatDuration(Number(p.duration_hours))}</span></div>
              )}
              {p.type === 'PORT_VISIT' && p.port_name && (
                <div>Port: <span className="text-gray-300">{p.port_name}</span></div>
              )}
            </div>

            {/* Encounter partner */}
            {p.type === 'ENCOUNTER' && p.encounter_partner_mmsi != null && (
              <div className="mt-2 pt-2 border-t border-slate-700">
                <div className="text-gray-500 text-[0.6rem] uppercase tracking-wider mb-1">Encounter partner</div>
                <div className="text-gray-300 font-medium">
                  {p.encounter_partner_name || `MMSI ${p.encounter_partner_mmsi}`}
                  {p.encounter_partner_flag && <span className="text-gray-500 ml-1">{p.encounter_partner_flag}</span>}
                </div>
                <button
                  onClick={() => handleGoToVessel(Number(p.encounter_partner_mmsi))}
                  className="mt-1 w-full text-center px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded text-gray-300 hover:text-white transition-colors cursor-pointer"
                >
                  Open partner vessel
                </button>
              </div>
            )}

            {/* Open vessel button */}
            {p.mmsi != null && (
              <button
                onClick={() => handleGoToVessel(Number(p.mmsi))}
                className="mt-2 w-full text-center px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded text-gray-300 hover:text-white transition-colors cursor-pointer"
              >
                Open vessel
              </button>
            )}
          </div>
        </Popup>
      )}
    </>
  );
}
