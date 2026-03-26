import { useEffect, useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import type { CircleLayerSpecification } from 'maplibre-gl';
import { useLookbackStore } from '../../hooks/useLookbackStore';

/** Color palette for interference severity */
const SEVERITY_COLORS = {
  severe: { fill: 'rgba(239,68,68,0.30)', stroke: 'rgba(239,68,68,0.8)' },
  moderate: { fill: 'rgba(251,191,36,0.25)', stroke: 'rgba(251,191,36,0.7)' },
};

/**
 * Filter interference zone features that overlap the current playback time window.
 */
function filterZonesByTime(
  features: GeoJSON.Feature[],
  currentTime: Date,
  windowSize: '1h' | '3h' | '6h',
): GeoJSON.Feature[] {
  const windowHours: Record<string, number> = { '1h': 1, '3h': 3, '6h': 6 };
  const halfMs = ((windowHours[windowSize] ?? 3) / 2) * 3_600_000;
  const windowStart = currentTime.getTime() - halfMs;
  const windowEnd = currentTime.getTime() + halfMs;

  return features.filter((feature) => {
    const timeStart = feature.properties?.time_start;
    const timeEnd = feature.properties?.time_end;
    if (!timeStart || !timeEnd) return false;
    const sMs = new Date(timeStart).getTime();
    const eMs = new Date(timeEnd).getTime();
    return sMs <= windowEnd && eMs >= windowStart;
  });
}

/**
 * Determine the API window parameter that covers the full playback date range.
 */
function computeFetchWindow(dateRange: { start: Date; end: Date }): string {
  const totalHours = (dateRange.end.getTime() - dateRange.start.getTime()) / 3_600_000;
  if (totalHours <= 6) return '6h';
  if (totalHours <= 12) return '12h';
  if (totalHours <= 24) return '24h';
  if (totalHours <= 72) return '3d';
  return '7d';
}

/**
 * PlaybackGnssOverlay renders ADS-B interference zones during lookback playback.
 */
export function PlaybackGnssOverlay() {
  const showGnssOverlay = useLookbackStore((s) => s.showGnssOverlay);
  const gnssOverlayWindow = useLookbackStore((s) => s.gnssOverlayWindow);
  const gnssZonesCache = useLookbackStore((s) => s.gnssZonesCache);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const dateRange = useLookbackStore((s) => s.dateRange);
  const setGnssZonesCache = useLookbackStore((s) => s.setGnssZonesCache);

  // Pre-fetch all interference zones for the playback date range
  useEffect(() => {
    if (!showGnssOverlay) {
      setGnssZonesCache(null);
      return;
    }

    const midpoint = new Date((dateRange.start.getTime() + dateRange.end.getTime()) / 2);
    const windowParam = computeFetchWindow(dateRange);

    const params = new URLSearchParams({
      center: midpoint.toISOString(),
      window: windowParam,
    });

    let cancelled = false;

    fetch(`/api/adsb/interference-zones?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Interference zones fetch failed: ${res.status}`);
        return res.json();
      })
      .then((data: GeoJSON.FeatureCollection) => {
        if (!cancelled) {
          data.features = data.features.filter((f) => f.geometry != null);
          setGnssZonesCache(data);
        }
      })
      .catch((err) => {
        console.error('Failed to fetch interference zones for playback:', err);
      });

    return () => {
      cancelled = true;
    };
  }, [showGnssOverlay, dateRange, setGnssZonesCache]);

  // Filter zones by current playhead time
  const data = useMemo(() => {
    if (!gnssZonesCache) return null;
    const filtered = filterZonesByTime(gnssZonesCache.features, currentTime, gnssOverlayWindow);
    return { type: 'FeatureCollection' as const, features: filtered };
  }, [gnssZonesCache, currentTime, gnssOverlayWindow]);

  const circlePaint: CircleLayerSpecification['paint'] = {
    'circle-radius': [
      'interpolate', ['exponential', 2], ['zoom'],
      3, ['*', ['get', 'radius_km'], 0.3],
      6, ['*', ['get', 'radius_km'], 1.5],
      10, ['*', ['get', 'radius_km'], 8],
    ],
    'circle-color': [
      'match', ['get', 'severity'],
      'severe', SEVERITY_COLORS.severe.fill,
      'moderate', SEVERITY_COLORS.moderate.fill,
      'rgba(251,191,36,0.2)',
    ],
    'circle-opacity': 0.7,
    'circle-stroke-width': 1.5,
    'circle-stroke-color': [
      'match', ['get', 'severity'],
      'severe', SEVERITY_COLORS.severe.stroke,
      'moderate', SEVERITY_COLORS.moderate.stroke,
      'rgba(251,191,36,0.6)',
    ],
    'circle-blur': 0.3,
  };

  if (!showGnssOverlay || !data) return null;

  return (
    <Source id="playback-interference-zones" type="geojson" data={data}>
      <Layer
        id="playback-interference-circles"
        type="circle"
        paint={circlePaint}
      />
    </Source>
  );
}
