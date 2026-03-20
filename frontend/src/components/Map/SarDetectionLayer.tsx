import { useEffect, useMemo, useState, useCallback } from 'react';
import { Source, Layer, Popup, useMap } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';

export interface SarDetectionLayerProps {
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

interface SarFeatureProperties {
  id: string;
  is_dark: boolean;
  length_m: number | null;
  fishing_score: number | null;
  matching_score: number | null;
  detected_at: string;
  matched_mmsi: number | null;
  matched_vessel_name: string | null;
}

/**
 * Build a GeoJSON FeatureCollection from SAR detections, optionally filtering to dark ships only.
 * Exported for testing.
 */
export function buildSarGeoJson(detections: any[], darkOnly: boolean) {
  const features = (detections || [])
    .filter((d: any) => !darkOnly || d.isDark)
    .map((d: any) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [d.lon, d.lat] },
      properties: {
        id: d.id,
        is_dark: d.isDark,
        length_m: d.estimatedLength,
        fishing_score: d.fishingScore,
        matching_score: d.matchingScore,
        detected_at: d.detectedAt,
        matched_mmsi: d.matchedMmsi,
        matched_vessel_name: d.matchedVesselName,
      },
    }));
  return { type: 'FeatureCollection' as const, features };
}

/**
 * Renders SAR detection markers on a MapLibre map.
 * Dark ships are white with a red stroke; matched detections are smaller and gray.
 * Must be rendered as a child of a react-map-gl <Map>.
 */
export function SarDetectionLayer({ visible }: SarDetectionLayerProps) {
  const { current: map } = useMap();
  const darkShipsOnly = useVesselStore((s) => s.filters.darkShipsOnly);
  const [popup, setPopup] = useState<{
    lon: number;
    lat: number;
    properties: SarFeatureProperties;
  } | null>(null);

  const { data: detections = [] } = useQuery({
    queryKey: ['sar-detections'],
    queryFn: async () => {
      const res = await fetch('/api/sar/detections');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: visible,
    refetchInterval: 300_000,
  });

  const geojson = useMemo(
    () => buildSarGeoJson(detections, darkShipsOnly),
    [detections, darkShipsOnly],
  );

  // Click handler for markers
  useEffect(() => {
    if (!map || !visible) return;
    const onClick = (e: maplibregl.MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (feature && feature.geometry.type === 'Point') {
        const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates;
        setPopup({ lon, lat, properties: feature.properties as unknown as SarFeatureProperties });
      }
    };
    const onMouseEnter = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const onMouseLeave = () => {
      map.getCanvas().style.cursor = '';
    };
    // Register on both layers
    map.on('click', 'sar-dark', onClick);
    map.on('click', 'sar-matched', onClick);
    map.on('mouseenter', 'sar-dark', onMouseEnter);
    map.on('mouseenter', 'sar-matched', onMouseEnter);
    map.on('mouseleave', 'sar-dark', onMouseLeave);
    map.on('mouseleave', 'sar-matched', onMouseLeave);
    return () => {
      map.off('click', 'sar-dark', onClick);
      map.off('click', 'sar-matched', onClick);
      map.off('mouseenter', 'sar-dark', onMouseEnter);
      map.off('mouseenter', 'sar-matched', onMouseEnter);
      map.off('mouseleave', 'sar-dark', onMouseLeave);
      map.off('mouseleave', 'sar-matched', onMouseLeave);
    };
  }, [map, visible]);

  const handleClosePopup = useCallback(() => {
    setPopup(null);
  }, []);

  if (!visible) return null;

  return (
    <>
      {geojson && (
        <Source id="sar-detections" type="geojson" data={geojson}>
          {/* Dark ships -- larger, white with red stroke */}
          <Layer
            id="sar-dark"
            type="circle"
            filter={['==', ['get', 'is_dark'], true]}
            paint={{
              'circle-color': '#FFFFFF',
              'circle-radius': 5,
              'circle-stroke-width': 2,
              'circle-stroke-color': '#EF4444',
            }}
          />
          {/* Matched detections -- smaller, gray */}
          <Layer
            id="sar-matched"
            type="circle"
            filter={['!=', ['get', 'is_dark'], true]}
            paint={{
              'circle-color': '#6B7280',
              'circle-radius': 3,
              'circle-stroke-width': 1,
              'circle-stroke-color': '#374151',
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
            <div className="font-bold mb-1">
              {popup.properties.is_dark ? 'Dark Ship Detection' : 'SAR Detection'}
            </div>
            <div className="space-y-0.5">
              {popup.properties.detected_at && (
                <div>Detected: {formatTime(popup.properties.detected_at)}</div>
              )}
              {popup.properties.length_m != null && (
                <div>Est. Length: {popup.properties.length_m} m</div>
              )}
              {popup.properties.matching_score != null && (
                <div>Matching: {(popup.properties.matching_score * 100).toFixed(0)}%</div>
              )}
              {popup.properties.fishing_score != null && (
                <div>Fishing: {(popup.properties.fishing_score * 100).toFixed(0)}%</div>
              )}
              {popup.properties.matched_mmsi != null && (
                <div>
                  Matched: {popup.properties.matched_vessel_name || popup.properties.matched_mmsi}
                </div>
              )}
              {popup.properties.is_dark && (
                <div className="mt-1 px-1.5 py-0.5 bg-red-900/40 border border-red-700/50 rounded text-red-300">
                  No AIS transmission detected
                </div>
              )}
            </div>
          </div>
        </Popup>
      )}
    </>
  );
}
