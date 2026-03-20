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

/**
 * Format a timestamp for display.
 */
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

/**
 * Format duration in hours to a human-readable string.
 */
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
  encounter_partner_mmsi: number | null;
  encounter_partner_name: string | null;
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
        encounter_partner_mmsi: e.encounterPartnerMmsi,
        encounter_partner_name: e.encounterPartnerName,
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

  if (!visible) return null;

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

      {popup && (
        <Popup
          longitude={popup.lon}
          latitude={popup.lat}
          onClose={handleClosePopup}
          closeButton={true}
          closeOnClick={false}
          className="text-xs"
        >
          <div className="bg-slate-800 text-white p-2 rounded text-xs">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-bold">
                {EVENT_TYPE_LABELS[popup.properties.type as GfwEventType] ?? popup.properties.type}
              </span>
            </div>
            <div className="space-y-0.5">
              <div>
                Vessel: {popup.properties.vessel_name || popup.properties.mmsi || 'Unknown'}
              </div>
              <div>Start: {formatTime(popup.properties.start)}</div>
              {popup.properties.end && (
                <div>End: {formatTime(popup.properties.end)}</div>
              )}
              {popup.properties.duration_hours != null && (
                <div>Duration: {formatDuration(popup.properties.duration_hours)}</div>
              )}
              {popup.properties.type === 'ENCOUNTER' && popup.properties.encounter_partner_mmsi != null && (
                <div>
                  Partner: {popup.properties.encounter_partner_name || popup.properties.encounter_partner_mmsi}
                </div>
              )}
              {popup.properties.type === 'PORT_VISIT' && popup.properties.port_name && (
                <div>Port: {popup.properties.port_name}</div>
              )}
            </div>
          </div>
        </Popup>
      )}
    </>
  );
}
