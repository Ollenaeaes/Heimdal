import { useMemo, useState, useCallback } from 'react';
import { CustomDataSource, Entity, BillboardGraphics } from 'resium';
import { useCesium } from 'resium';
import {
  Cartesian3,
  NearFarScalar,
  type Viewer as CesiumViewer,
} from 'cesium';
import { useQuery } from '@tanstack/react-query';
import type { GfwEvent, GfwEventType } from '../../types/api';
import { getGfwEventIcon, GFW_EVENT_COLORS } from '../../utils/eventIcons';
import { useVesselStore } from '../../hooks/useVesselStore';

export interface GfwEventMarkersProps {
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

/**
 * Renders GFW event markers on the globe with color-coded shapes by event type.
 */
export function GfwEventMarkers({ visible }: GfwEventMarkersProps) {
  const { viewer } = useCesium();
  const showGfwEventTypes = useVesselStore((s) => s.filters.showGfwEventTypes);
  const [selectedEvent, setSelectedEvent] = useState<GfwEvent | null>(null);

  const { data: events = [] } = useQuery<GfwEvent[]>({
    queryKey: ['gfwEvents'],
    queryFn: () => fetch('/api/gfw/events').then((r) => r.json()),
    refetchInterval: 300_000,
    enabled: visible,
  });

  const filteredEvents = useMemo(() => {
    return events.filter((e) => showGfwEventTypes.includes(e.type));
  }, [events, showGfwEventTypes]);

  const handleClick = useCallback(
    (event: GfwEvent) => {
      setSelectedEvent(event);
      if (viewer) {
        (viewer as CesiumViewer).camera.flyTo({
          destination: Cartesian3.fromDegrees(event.lon, event.lat, 50_000),
          duration: 1.5,
        });
      }
    },
    [viewer],
  );

  const handleClosePopup = useCallback(() => {
    setSelectedEvent(null);
  }, []);

  if (!visible) return null;

  return (
    <>
      <CustomDataSource name="gfw-events">
        {filteredEvents.map((e) => {
          const position = Cartesian3.fromDegrees(e.lon, e.lat);
          return (
            <Entity
              key={e.id}
              id={`gfw-${e.id}`}
              position={position}
              onClick={() => handleClick(e)}
            >
              <BillboardGraphics
                image={getGfwEventIcon(e.type)}
                scale={1.0}
                translucencyByDistance={
                  new NearFarScalar(1.0e3, 1.0, 1.5e7, 0.6)
                }
              />
            </Entity>
          );
        })}
      </CustomDataSource>

      {/* GFW Event Popup */}
      {selectedEvent && (
        <div
          className="absolute top-4 right-4 z-20 bg-gray-900/95 text-gray-200 rounded-lg shadow-lg p-4 min-w-[280px] max-w-[360px] border border-gray-700"
          data-testid="gfw-popup"
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span
                className="inline-block w-3 h-3 rounded-sm"
                style={{ backgroundColor: GFW_EVENT_COLORS[selectedEvent.type] }}
              />
              <h3 className="text-sm font-semibold text-white">
                {EVENT_TYPE_LABELS[selectedEvent.type]}
              </h3>
            </div>
            <button
              onClick={handleClosePopup}
              className="text-gray-400 hover:text-white text-lg leading-none"
              aria-label="Close"
            >
              &times;
            </button>
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-400">Start</span>
              <span>{formatTime(selectedEvent.startTime)}</span>
            </div>
            {selectedEvent.endTime && (
              <div className="flex justify-between">
                <span className="text-gray-400">End</span>
                <span>{formatTime(selectedEvent.endTime)}</span>
              </div>
            )}
            {selectedEvent.durationHours != null && (
              <div className="flex justify-between">
                <span className="text-gray-400">Duration</span>
                <span>{formatDuration(selectedEvent.durationHours)}</span>
              </div>
            )}
            {selectedEvent.vesselMmsi != null && (
              <div className="flex justify-between">
                <span className="text-gray-400">Vessel MMSI</span>
                <span>{selectedEvent.vesselMmsi}</span>
              </div>
            )}
            {selectedEvent.vesselName && (
              <div className="flex justify-between">
                <span className="text-gray-400">Vessel</span>
                <span>{selectedEvent.vesselName}</span>
              </div>
            )}
            {selectedEvent.type === 'ENCOUNTER' && selectedEvent.encounterPartnerMmsi != null && (
              <>
                <div className="flex justify-between">
                  <span className="text-gray-400">Partner MMSI</span>
                  <span>{selectedEvent.encounterPartnerMmsi}</span>
                </div>
                {selectedEvent.encounterPartnerName && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Partner Vessel</span>
                    <span>{selectedEvent.encounterPartnerName}</span>
                  </div>
                )}
              </>
            )}
            {selectedEvent.type === 'PORT_VISIT' && selectedEvent.portName && (
              <div className="flex justify-between">
                <span className="text-gray-400">Port</span>
                <span>{selectedEvent.portName}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-gray-400">Position</span>
              <span>{selectedEvent.lat.toFixed(4)}, {selectedEvent.lon.toFixed(4)}</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
