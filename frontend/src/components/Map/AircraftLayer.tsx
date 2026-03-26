import { useEffect, useMemo } from 'react';
import { Source, Layer, useMap } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import type { SymbolLayerSpecification } from 'maplibre-gl';
import { registerAircraftIcons, buildIconImageExpression, getIconCategory } from '../../utils/aircraftIcons';
import { useLookbackStore } from '../../hooks/useLookbackStore';

interface AircraftTrackPoint {
  time: string;
  lat: number;
  lon: number;
  alt_baro: number | null;
  ground_speed: number | null;
  track: number | null;
}

interface AircraftTrackData {
  icao_hex: string;
  callsign: string | null;
  registration: string | null;
  type_code: string | null;
  description: string | null;
  category: string | null;
  country: string | null;
  points: AircraftTrackPoint[];
}

/**
 * Interpolate aircraft position at a given time.
 */
function interpolateAircraftPosition(
  points: AircraftTrackPoint[],
  targetMs: number,
): { lat: number; lon: number; track: number | null } | null {
  if (!points || points.length === 0) return null;

  const firstMs = new Date(points[0].time).getTime();
  const lastMs = new Date(points[points.length - 1].time).getTime();

  if (targetMs <= firstMs) return { lat: points[0].lat, lon: points[0].lon, track: points[0].track };
  if (targetMs >= lastMs) {
    const last = points[points.length - 1];
    return { lat: last.lat, lon: last.lon, track: last.track };
  }

  let lo = 0;
  let hi = points.length - 1;
  while (lo < hi - 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (new Date(points[mid].time).getTime() <= targetMs) lo = mid;
    else hi = mid;
  }

  const tLo = new Date(points[lo].time).getTime();
  const tHi = new Date(points[hi].time).getTime();
  if (tHi === tLo) return { lat: points[lo].lat, lon: points[lo].lon, track: points[lo].track };

  const frac = (targetMs - tLo) / (tHi - tLo);
  return {
    lat: points[lo].lat + (points[hi].lat - points[lo].lat) * frac,
    lon: points[lo].lon + (points[hi].lon - points[lo].lon) * frac,
    track: points[hi].track,
  };
}

/**
 * Aircraft of interest layer — always visible.
 *
 * Live mode: latest positions from /api/adsb/aircraft.
 * Playback mode: full tracks with progressive trails + interpolated markers.
 */
export function AircraftLayer() {
  const { current: map } = useMap();
  const lookbackActive = useLookbackStore((s) => s.isActive);
  const showAircraftOverlay = useLookbackStore((s) => s.showAircraftOverlay);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const dateRange = useLookbackStore((s) => s.dateRange);

  // Register icons
  useEffect(() => {
    if (!map) return;
    const mapInstance = map.getMap();
    const register = () => registerAircraftIcons(mapInstance);
    if (mapInstance.isStyleLoaded()) register();
    mapInstance.on('load', register);
    mapInstance.on('style.load', register);
    mapInstance.on('styleimagemissing', (e: { id: string }) => {
      if (e.id.startsWith('ac-')) register();
    });
    return () => {
      mapInstance.off('load', register);
      mapInstance.off('style.load', register);
    };
  }, [map]);

  // --- Live mode: fetch latest positions ---
  const { data: liveData } = useQuery<GeoJSON.FeatureCollection>({
    queryKey: ['adsbAircraft', 'live'],
    queryFn: async () => {
      const res = await fetch('/api/adsb/aircraft?window=1h');
      if (!res.ok) throw new Error(`ADS-B aircraft fetch failed: ${res.status}`);
      return res.json();
    },
    enabled: !lookbackActive,
    refetchInterval: 15_000,
  });

  // --- Playback mode: fetch all tracks for date range ---
  const { data: trackData } = useQuery<{ aircraft: Record<string, AircraftTrackData>; count: number }>({
    queryKey: ['adsbTracks', dateRange.start.toISOString(), dateRange.end.toISOString()],
    queryFn: async () => {
      const params = new URLSearchParams({
        start: dateRange.start.toISOString(),
        end: dateRange.end.toISOString(),
      });
      const res = await fetch(`/api/adsb/aircraft/tracks?${params}`);
      if (!res.ok) throw new Error(`ADS-B tracks fetch failed: ${res.status}`);
      return res.json();
    },
    enabled: lookbackActive && showAircraftOverlay,
  });

  // --- Live mode GeoJSON ---
  const liveGeoJson = useMemo(() => {
    if (lookbackActive || !liveData) return null;
    const features = liveData.features
      .filter((f) => f.geometry != null)
      .map((f) => ({
        ...f,
        properties: {
          ...f.properties,
          icon_type: getIconCategory(f.properties?.type_code),
        },
      }));
    return { type: 'FeatureCollection' as const, features };
  }, [lookbackActive, liveData]);

  // --- Playback mode: markers + trails ---
  const playbackData = useMemo(() => {
    if (!lookbackActive || !showAircraftOverlay || !trackData?.aircraft) return null;

    const targetMs = currentTime.getTime();
    const markers: GeoJSON.Feature[] = [];
    const trails: GeoJSON.Feature[] = [];

    for (const ac of Object.values(trackData.aircraft)) {
      if (ac.points.length === 0) continue;

      // Only show aircraft that have data near current time
      const firstMs = new Date(ac.points[0].time).getTime();
      const lastMs = new Date(ac.points[ac.points.length - 1].time).getTime();
      if (targetMs < firstMs - 60000 || targetMs > lastMs + 60000) continue;

      const pos = interpolateAircraftPosition(ac.points, targetMs);
      if (!pos) continue;

      // Marker
      markers.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [pos.lon, pos.lat] },
        properties: {
          icao_hex: ac.icao_hex,
          callsign: ac.callsign,
          registration: ac.registration,
          type_code: ac.type_code,
          description: ac.description,
          category: ac.category,
          country: ac.country,
          track: pos.track,
          icon_type: getIconCategory(ac.type_code),
        },
      });

      // Trail up to current time
      const trailCoords: [number, number][] = [];
      for (const p of ac.points) {
        if (new Date(p.time).getTime() > targetMs) break;
        trailCoords.push([p.lon, p.lat]);
      }
      trailCoords.push([pos.lon, pos.lat]);

      if (trailCoords.length >= 2) {
        trails.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: trailCoords },
          properties: { icao_hex: ac.icao_hex, category: ac.category },
        });
      }
    }

    return {
      markers: { type: 'FeatureCollection' as const, features: markers },
      trails: { type: 'FeatureCollection' as const, features: trails },
    };
  }, [lookbackActive, showAircraftOverlay, trackData, currentTime]);

  // Determine which data to show
  const markerData = lookbackActive ? playbackData?.markers : liveGeoJson;
  const iconExpression = buildIconImageExpression();

  const symbolLayout: SymbolLayerSpecification['layout'] = {
    'icon-image': iconExpression,
    'icon-size': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 6, 0.8, 10, 1.1],
    'icon-rotate': ['coalesce', ['get', 'track'], 0],
    'icon-rotation-alignment': 'map',
    'icon-allow-overlap': true,
    'icon-ignore-placement': true,
    'text-field': ['step', ['zoom'], '', 8, ['coalesce', ['get', 'callsign'], ['get', 'registration'], '']],
    'text-size': 10,
    'text-offset': [0, 1.5],
    'text-anchor': 'top',
    'text-optional': true,
  };

  const symbolPaint: SymbolLayerSpecification['paint'] = {
    'text-color': '#e2e8f0',
    'text-halo-color': 'rgba(0,0,0,0.8)',
    'text-halo-width': 1,
  };

  if (lookbackActive && !showAircraftOverlay) return null;
  if (!markerData || markerData.features.length === 0) {
    // Still render trails if we have them
    if (!playbackData?.trails || playbackData.trails.features.length === 0) return null;
  }

  return (
    <>
      {/* Aircraft trails (playback only) */}
      {playbackData?.trails && playbackData.trails.features.length > 0 && (
        <Source id="adsb-aircraft-trails" type="geojson" data={playbackData.trails}>
          <Layer
            id="adsb-aircraft-trail-lines"
            type="line"
            paint={{
              'line-color': [
                'match', ['get', 'category'],
                'military', '#f59e0b',
                'coast_guard', '#06b6d4',
                'police', '#3b82f6',
                'government', '#8b5cf6',
                '#9ca3af',
              ],
              'line-width': 1.5,
              'line-opacity': 0.5,
              'line-dasharray': [2, 2],
            }}
          />
        </Source>
      )}

      {/* Aircraft markers */}
      {markerData && markerData.features.length > 0 && (
        <Source id="adsb-aircraft" type="geojson" data={markerData}>
          <Layer
            id="adsb-aircraft-icons"
            type="symbol"
            layout={symbolLayout}
            paint={symbolPaint}
          />
        </Source>
      )}
    </>
  );
}
