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

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
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
  matched_vessel_flag: string | null;
  matched_vessel_type: string | null;
  matched_vessel_risk_tier: string | null;
  matched_vessel_last_lat: number | null;
  matched_vessel_last_lon: number | null;
  matched_vessel_last_seen: string | null;
  matched_category: string | null;
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
        matched_vessel_flag: d.matchedVesselFlag,
        matched_vessel_type: d.matchedVesselType,
        matched_vessel_risk_tier: d.matchedVesselRiskTier,
        matched_vessel_last_lat: d.matchedVesselLastLat,
        matched_vessel_last_lon: d.matchedVesselLastLon,
        matched_vessel_last_seen: d.matchedVesselLastSeen,
        matched_category: d.matchedCategory,
      },
    }));
  return { type: 'FeatureCollection' as const, features };
}

const RISK_TIER_COLORS: Record<string, string> = {
  green: 'text-green-400',
  yellow: 'text-yellow-400',
  red: 'text-red-400',
  blacklisted: 'text-red-300',
};

/**
 * Renders SAR detection markers on a MapLibre map.
 * Dark ships are white with a red stroke; matched detections are smaller and gray.
 * Must be rendered as a child of a react-map-gl <Map>.
 */
export function SarDetectionLayer({ visible }: SarDetectionLayerProps) {
  const { current: map } = useMap();
  const darkShipsOnly = useVesselStore((s) => s.filters.darkShipsOnly);
  const selectVessel = useVesselStore((s) => s.selectVessel);
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

  const handleGoToVessel = useCallback(() => {
    if (!popup?.properties.matched_mmsi) return;
    const mmsi = Number(popup.properties.matched_mmsi);
    selectVessel(mmsi);
    setPopup(null);

    // Fly to vessel's last known position if available, otherwise stay at SAR location
    if (map && popup.properties.matched_vessel_last_lat && popup.properties.matched_vessel_last_lon) {
      map.flyTo({
        center: [popup.properties.matched_vessel_last_lon, popup.properties.matched_vessel_last_lat],
        zoom: Math.max(map.getZoom(), 10),
        duration: 1500,
      });
    }
  }, [popup, map, selectVessel]);

  if (!visible) return null;

  const p = popup?.properties;

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

      {popup && p && (
        <Popup
          longitude={popup.lon}
          latitude={popup.lat}
          onClose={handleClosePopup}
          closeButton={true}
          closeOnClick={false}
          className="text-xs"
        >
          <div className="bg-slate-800 text-white p-2 rounded text-xs min-w-[200px]">
            <div className="font-bold mb-1.5">
              {p.is_dark ? 'Dark Ship Detection' : 'SAR Detection'}
            </div>

            <div className="space-y-0.5 text-gray-400">
              {p.detected_at && (
                <div>Detected: <span className="text-gray-300">{formatTime(p.detected_at)}</span></div>
              )}
              {p.length_m != null && (
                <div>Est. length: <span className="text-gray-300">{p.length_m} m</span></div>
              )}
              {p.matched_category && p.matched_category !== 'unmatched' && (
                <div>Category: <span className="text-gray-300">{p.matched_category}</span></div>
              )}
              {p.matching_score != null && (
                <div>Match confidence: <span className="text-gray-300">{(p.matching_score * 100).toFixed(0)}%</span></div>
              )}
              {p.fishing_score != null && (
                <div>Fishing score: <span className="text-gray-300">{(p.fishing_score * 100).toFixed(0)}%</span></div>
              )}
            </div>

            {/* Matched vessel info */}
            {p.matched_mmsi != null && (
              <div className="mt-2 pt-2 border-t border-slate-700">
                <div className="text-gray-500 text-[0.6rem] uppercase tracking-wider mb-1">Matched vessel</div>
                <div className="space-y-0.5">
                  <div className="text-gray-300 font-medium">
                    {p.matched_vessel_name || `MMSI ${p.matched_mmsi}`}
                    {p.matched_vessel_flag && (
                      <span className="text-gray-500 ml-1">{p.matched_vessel_flag}</span>
                    )}
                  </div>
                  {p.matched_vessel_type && (
                    <div className="text-gray-500">{p.matched_vessel_type}</div>
                  )}
                  {p.matched_vessel_risk_tier && p.matched_vessel_risk_tier !== 'green' && (
                    <div className={RISK_TIER_COLORS[p.matched_vessel_risk_tier] ?? 'text-gray-400'}>
                      Risk: {p.matched_vessel_risk_tier}
                    </div>
                  )}
                  {p.matched_vessel_last_seen && (
                    <div className="text-gray-500">
                      Last AIS: {timeAgo(p.matched_vessel_last_seen)}
                    </div>
                  )}
                  <button
                    onClick={handleGoToVessel}
                    className="mt-1.5 w-full text-center px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded text-gray-300 hover:text-white transition-colors cursor-pointer"
                  >
                    Open vessel →
                  </button>
                </div>
              </div>
            )}

            {p.is_dark && (
              <div className="mt-2 px-1.5 py-0.5 bg-red-900/40 border border-red-700/50 rounded text-red-300 text-center">
                No AIS transmission detected
              </div>
            )}
          </div>
        </Popup>
      )}
    </>
  );
}
