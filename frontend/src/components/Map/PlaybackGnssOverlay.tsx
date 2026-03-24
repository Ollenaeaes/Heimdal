import { useEffect, useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import type { FillLayerSpecification, LineLayerSpecification } from 'maplibre-gl';
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
 * Filter zones from the cache that overlap with the current playback time window.
 * A zone is visible if: detected_at <= currentTime + windowHalf AND expires_at >= currentTime - windowHalf.
 *
 * Exported for testing.
 */
export function filterZonesByTime(
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
    const expiresAt = feature.properties?.expires_at;
    if (!detectedAt || !expiresAt) return false;

    const detectedMs = new Date(detectedAt).getTime();
    const expiresMs = new Date(expiresAt).getTime();

    return detectedMs <= windowEnd && expiresMs >= windowStart;
  });
}

/**
 * Calculate opacity_factor for a zone relative to the playback currentTime.
 * Zones detected closer to currentTime are more opaque.
 * Ranges from 1.0 (detected at currentTime) to 0.2 (at edge of window).
 *
 * Exported for testing.
 */
export function calculateOpacityFactor(
  detectedAt: string,
  currentTime: Date,
  windowSize: '1h' | '3h' | '6h',
): number {
  const currentMs = currentTime.getTime();
  const detectedMs = new Date(detectedAt).getTime();
  const windowMs = windowToMs(windowSize);
  const ageMs = Math.abs(currentMs - detectedMs);
  const ratio = Math.min(1, ageMs / windowMs);
  // Quadratic falloff — zones fade quickly then linger faintly
  return Math.max(0.05, 1 - ratio * ratio);
}

/**
 * Add opacity_factor to each filtered feature based on temporal proximity to playhead.
 */
function addTemporalFade(
  features: GeoJSON.Feature[],
  currentTime: Date,
  windowSize: '1h' | '3h' | '6h',
): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: features.map((feature) => {
      const detectedAt = feature.properties?.detected_at;
      const opacityFactor = detectedAt
        ? calculateOpacityFactor(detectedAt, currentTime, windowSize)
        : 1;

      return {
        ...feature,
        properties: { ...feature.properties, opacity_factor: opacityFactor },
      };
    }),
  };
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
  if (totalHours <= 168) return '7d';
  return '30d';
}

/**
 * PlaybackGnssOverlay renders GNSS interference zones during lookback playback.
 *
 * It reads the pre-fetched gnssZonesCache, filters zones by the current playhead
 * time and overlay window, applies temporal fade, and renders polygons using the
 * same paint styles as GnssHeatmap.
 */
export function PlaybackGnssOverlay() {
  const showGnssOverlay = useLookbackStore((s) => s.showGnssOverlay);
  const gnssOverlayWindow = useLookbackStore((s) => s.gnssOverlayWindow);
  const gnssZonesCache = useLookbackStore((s) => s.gnssZonesCache);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const dateRange = useLookbackStore((s) => s.dateRange);
  const setGnssZonesCache = useLookbackStore((s) => s.setGnssZonesCache);

  // Pre-fetch GNSS zones when overlay is toggled on
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

    fetch(`/api/gnss-zones?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error(`GNSS zones fetch failed: ${res.status}`);
        return res.json();
      })
      .then((data: GeoJSON.FeatureCollection) => {
        if (!cancelled) {
          setGnssZonesCache(data);
        }
      })
      .catch((err) => {
        console.error('Failed to fetch GNSS zones for playback:', err);
      });

    return () => {
      cancelled = true;
    };
  }, [showGnssOverlay, dateRange, setGnssZonesCache]);

  // Filter and fade zones based on current playhead time
  const data = useMemo(() => {
    if (!gnssZonesCache) return null;
    const filtered = filterZonesByTime(gnssZonesCache.features, currentTime, gnssOverlayWindow);
    return addTemporalFade(filtered, currentTime, gnssOverlayWindow);
  }, [gnssZonesCache, currentTime, gnssOverlayWindow]);

  // Paint styles matching GnssHeatmap
  const fillPaint: FillLayerSpecification['paint'] = {
    'fill-color': [
      'case',
      ['==', ['get', 'event_type'], 'jamming'],
      [
        'interpolate', ['linear'], ['get', 'affected_count'],
        1, 'rgba(147,51,234,0.3)',
        15, 'rgba(99,102,241,0.8)',
      ],
      [
        'interpolate', ['linear'], ['get', 'affected_count'],
        1, 'rgba(249,115,22,0.3)',
        15, 'rgba(239,68,68,0.8)',
      ],
    ],
    'fill-opacity': ['get', 'opacity_factor'],
  };

  const linePaint: LineLayerSpecification['paint'] = {
    'line-color': [
      'case',
      ['==', ['get', 'event_type'], 'jamming'],
      'rgba(99,102,241,0.9)',
      'rgba(239,68,68,0.9)',
    ],
    'line-width': 1,
  };

  if (!showGnssOverlay || !data) return null;

  return (
    <Source id="playback-gnss-zones" type="geojson" data={data}>
      <Layer
        id="playback-gnss-zones-fill"
        type="fill"
        paint={fillPaint}
      />
      <Layer
        id="playback-gnss-zones-outline"
        type="line"
        paint={linePaint}
      />
    </Source>
  );
}
