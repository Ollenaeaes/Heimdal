import { useEffect, useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import type { CircleLayerSpecification } from 'maplibre-gl';
import { useLookbackStore } from '../../hooks/useLookbackStore';

/**
 * Window size string to milliseconds.
 */
function windowToMs(w: '1h' | '3h' | '6h'): number {
  switch (w) {
    case '1h': return 3_600_000;
    case '3h': return 3 * 3_600_000;
    case '6h': return 6 * 3_600_000;
  }
}

/**
 * Filter positions from the cache that fall within the current playback time window.
 * Exported for testing.
 */
export function filterPositionsByTime(
  features: GeoJSON.Feature[],
  currentTime: Date,
  windowSize: '1h' | '3h' | '6h',
): GeoJSON.Feature[] {
  const currentMs = currentTime.getTime();
  const halfMs = windowToMs(windowSize) / 2;
  const windowStart = currentMs - halfMs;
  const windowEnd = currentMs + halfMs;

  return features.filter((feature) => {
    const detectedAt = feature.properties?.detected_at;
    if (!detectedAt) return false;
    const ms = new Date(detectedAt).getTime();
    return ms >= windowStart && ms <= windowEnd;
  });
}

/**
 * Determine the API window parameter that covers the full playback date range.
 */
function computeFetchWindow(dateRange: { start: Date; end: Date }): string {
  const totalHours = (dateRange.end.getTime() - dateRange.start.getTime()) / 3_600_000;
  if (totalHours <= 1) return '1h';
  if (totalHours <= 3) return '3h';
  if (totalHours <= 6) return '6h';
  // For longer ranges, we need to fetch all positions in the range directly
  return `${Math.ceil(totalHours)}h`;
}

/**
 * PlaybackGnssOverlay renders GNSS spoofed position dots during lookback playback.
 */
export function PlaybackGnssOverlay() {
  const showGnssOverlay = useLookbackStore((s) => s.showGnssOverlay);
  const gnssOverlayWindow = useLookbackStore((s) => s.gnssOverlayWindow);
  const gnssZonesCache = useLookbackStore((s) => s.gnssZonesCache);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const dateRange = useLookbackStore((s) => s.dateRange);
  const setGnssZonesCache = useLookbackStore((s) => s.setGnssZonesCache);

  // Pre-fetch all GNSS positions for the playback date range
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

    fetch(`/api/gnss-positions?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error(`GNSS positions fetch failed: ${res.status}`);
        return res.json();
      })
      .then((data: GeoJSON.FeatureCollection) => {
        if (!cancelled) {
          setGnssZonesCache(data);
        }
      })
      .catch((err) => {
        console.error('Failed to fetch GNSS positions for playback:', err);
      });

    return () => {
      cancelled = true;
    };
  }, [showGnssOverlay, dateRange, setGnssZonesCache]);

  // Filter positions by current playhead time
  const data = useMemo(() => {
    if (!gnssZonesCache) return null;
    const filtered = filterPositionsByTime(gnssZonesCache.features, currentTime, gnssOverlayWindow);
    return { type: 'FeatureCollection' as const, features: filtered };
  }, [gnssZonesCache, currentTime, gnssOverlayWindow]);

  const spoofedPaint: CircleLayerSpecification['paint'] = {
    'circle-color': 'rgba(239,68,68,0.7)',
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2, 6, 4, 10, 6],
    'circle-stroke-width': 0.5,
    'circle-stroke-color': 'rgba(239,68,68,0.5)',
  };

  const realPaint: CircleLayerSpecification['paint'] = {
    'circle-color': 'rgba(6,182,212,0.6)',
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2, 6, 3, 10, 5],
    'circle-stroke-width': 0.5,
    'circle-stroke-color': 'rgba(6,182,212,0.4)',
  };

  if (!showGnssOverlay || !data) return null;

  return (
    <Source id="playback-gnss-positions" type="geojson" data={data}>
      <Layer
        id="playback-gnss-spoofed-dots"
        type="circle"
        filter={['==', ['get', 'point_type'], 'spoofed']}
        paint={spoofedPaint}
      />
      <Layer
        id="playback-gnss-real-dots"
        type="circle"
        filter={['==', ['get', 'point_type'], 'real']}
        paint={realPaint}
      />
    </Source>
  );
}
