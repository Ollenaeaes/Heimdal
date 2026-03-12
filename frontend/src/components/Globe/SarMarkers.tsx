import { useMemo, useRef, useState, useCallback } from 'react';
import { CustomDataSource, Entity, BillboardGraphics } from 'resium';
import { useCesium } from 'resium';
import {
  Cartesian3,
  CallbackProperty,
  NearFarScalar,
  type Viewer as CesiumViewer,
} from 'cesium';
import { useQuery } from '@tanstack/react-query';
import type { SarDetection } from '../../types/api';
import { getSarIcon } from '../../utils/eventIcons';
import { useVesselStore } from '../../hooks/useVesselStore';

export interface SarMarkersProps {
  visible: boolean;
}

/**
 * Format a detection timestamp for display.
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
 * Renders SAR detection markers on the globe.
 * Dark ships pulse and have a red border; matched detections are smaller and gray.
 */
export function SarMarkers({ visible }: SarMarkersProps) {
  const { viewer } = useCesium();
  const darkShipsOnly = useVesselStore((s) => s.filters.darkShipsOnly);
  const [selectedDetection, setSelectedDetection] = useState<SarDetection | null>(null);

  const { data: detections = [] } = useQuery<SarDetection[]>({
    queryKey: ['sarDetections'],
    queryFn: () => fetch('/api/sar/detections').then((r) => r.json()),
    refetchInterval: 300_000,
    enabled: visible,
  });

  const filteredDetections = useMemo(() => {
    if (darkShipsOnly) {
      return detections.filter((d) => d.isDark);
    }
    return detections;
  }, [detections, darkShipsOnly]);

  // Pulsing scale for dark ship markers
  const pulseRef = useRef(0);
  const darkPulseScale = useMemo(
    () =>
      new CallbackProperty(() => {
        pulseRef.current = (pulseRef.current + 0.03) % (2 * Math.PI);
        return 1.0 + 0.25 * Math.sin(pulseRef.current);
      }, false),
    [],
  );

  const handleClick = useCallback(
    (detection: SarDetection) => {
      setSelectedDetection(detection);
      if (viewer) {
        (viewer as CesiumViewer).camera.flyTo({
          destination: Cartesian3.fromDegrees(detection.lon, detection.lat, 50_000),
          duration: 1.5,
        });
      }
    },
    [viewer],
  );

  const handleClosePopup = useCallback(() => {
    setSelectedDetection(null);
  }, []);

  if (!visible) return null;

  return (
    <>
      <CustomDataSource name="sar-detections">
        {filteredDetections.map((d) => {
          const position = Cartesian3.fromDegrees(d.lon, d.lat);
          return (
            <Entity
              key={d.id}
              id={`sar-${d.id}`}
              position={position}
              onClick={() => handleClick(d)}
            >
              <BillboardGraphics
                image={getSarIcon(d.isDark)}
                scale={d.isDark ? (darkPulseScale as unknown as number) : 0.8}
                translucencyByDistance={
                  new NearFarScalar(1.0e3, 1.0, 1.5e7, 0.6)
                }
              />
            </Entity>
          );
        })}
      </CustomDataSource>

      {/* SAR Detection Popup */}
      {selectedDetection && (
        <div
          className="absolute top-4 right-4 z-20 bg-gray-900/95 text-gray-200 rounded-lg shadow-lg p-4 min-w-[280px] max-w-[360px] border border-gray-700"
          data-testid="sar-popup"
        >
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white">
              {selectedDetection.isDark ? 'Dark Ship Detection' : 'SAR Detection'}
            </h3>
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
              <span className="text-gray-400">Detected</span>
              <span>{formatTime(selectedDetection.detectedAt)}</span>
            </div>
            {selectedDetection.estimatedLength != null && (
              <div className="flex justify-between">
                <span className="text-gray-400">Est. Length</span>
                <span>{selectedDetection.estimatedLength} m</span>
              </div>
            )}
            {selectedDetection.matchingScore != null && (
              <div className="flex justify-between">
                <span className="text-gray-400">Matching Score</span>
                <span>{(selectedDetection.matchingScore * 100).toFixed(0)}%</span>
              </div>
            )}
            {selectedDetection.fishingScore != null && (
              <div className="flex justify-between">
                <span className="text-gray-400">Fishing Score</span>
                <span>{(selectedDetection.fishingScore * 100).toFixed(0)}%</span>
              </div>
            )}
            {selectedDetection.matchedMmsi != null && (
              <div className="flex justify-between">
                <span className="text-gray-400">Matched MMSI</span>
                <span>{selectedDetection.matchedMmsi}</span>
              </div>
            )}
            {selectedDetection.matchedVesselName && (
              <div className="flex justify-between">
                <span className="text-gray-400">Matched Vessel</span>
                <span>{selectedDetection.matchedVesselName}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-gray-400">Position</span>
              <span>{selectedDetection.lat.toFixed(4)}, {selectedDetection.lon.toFixed(4)}</span>
            </div>
            {selectedDetection.isDark && (
              <div className="mt-2 px-2 py-1 bg-red-900/40 border border-red-700/50 rounded text-red-300 text-xs">
                No AIS transmission detected
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
