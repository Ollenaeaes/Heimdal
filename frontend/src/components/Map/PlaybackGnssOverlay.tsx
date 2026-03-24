import { useEffect, useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import type { FillLayerSpecification, LineLayerSpecification } from 'maplibre-gl';
import { useLookbackStore } from '../../hooks/useLookbackStore';

/** Color palette matching GnssHeatmap */
const ZONE_COLORS = {
  spoofing: { fill: 'rgba(239,68,68,0.25)', stroke: 'rgba(239,68,68,0.7)' },
  interference_area: { fill: 'rgba(6,182,212,0.20)', stroke: 'rgba(6,182,212,0.6)' },
  jamming: { fill: 'rgba(168,85,247,0.22)', stroke: 'rgba(168,85,247,0.65)' },
};

/**
 * Filter zone features that overlap the current playback time window.
 * A zone is visible if its [detected_at, expires_at] overlaps [windowStart, windowEnd].
 */
export function filterZonesByTime(
  features: GeoJSON.Feature[],
  currentTime: Date,
  windowSize: '6h' | '12h' | '24h' | '3d' | '7d',
): GeoJSON.Feature[] {
  const windowHours: Record<string, number> = { '6h': 6, '12h': 12, '24h': 24, '3d': 72, '7d': 168 };
  const halfMs = ((windowHours[windowSize] ?? 24) / 2) * 3_600_000;
  const windowStart = currentTime.getTime() - halfMs;
  const windowEnd = currentTime.getTime() + halfMs;

  return features.filter((feature) => {
    const detectedAt = feature.properties?.detected_at;
    const expiresAt = feature.properties?.expires_at;
    if (!detectedAt || !expiresAt) return false;
    const dMs = new Date(detectedAt).getTime();
    const eMs = new Date(expiresAt).getTime();
    return dMs <= windowEnd && eMs >= windowStart;
  });
}

/**
 * Calculate opacity factor for a zone based on time distance from current playhead.
 * Zones closer to the current time are more opaque.
 */
export function calculateOpacityFactor(
  detectedAt: string,
  currentTime: Date,
  windowSize: '6h' | '12h' | '24h' | '3d' | '7d',
): number {
  const windowHours: Record<string, number> = { '6h': 6, '12h': 12, '24h': 24, '3d': 72, '7d': 168 };
  const windowMs = (windowHours[windowSize] ?? 24) * 3_600_000;
  const distMs = Math.abs(new Date(detectedAt).getTime() - currentTime.getTime());
  const ratio = Math.min(distMs / windowMs, 1);
  return Math.max(0.05, 1 - ratio * ratio);
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
 * PlaybackGnssOverlay renders GNSS zone polygons during lookback playback.
 */
export function PlaybackGnssOverlay() {
  const showGnssOverlay = useLookbackStore((s) => s.showGnssOverlay);
  const gnssOverlayWindow = useLookbackStore((s) => s.gnssOverlayWindow);
  const gnssZonesCache = useLookbackStore((s) => s.gnssZonesCache);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const dateRange = useLookbackStore((s) => s.dateRange);
  const setGnssZonesCache = useLookbackStore((s) => s.setGnssZonesCache);

  // Pre-fetch all GNSS zones for the playback date range
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
          // Filter out features with null geometry
          data.features = data.features.filter((f) => f.geometry != null);
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

  // Filter zones by current playhead time
  const data = useMemo(() => {
    if (!gnssZonesCache) return null;
    // Map gnssOverlayWindow to zone-compatible window
    const windowMap: Record<string, '6h' | '12h' | '24h' | '3d' | '7d'> = {
      '1h': '6h', '3h': '6h', '6h': '6h', '12h': '12h', '24h': '24h', '3d': '3d', '7d': '7d',
    };
    const mappedWindow = windowMap[gnssOverlayWindow] ?? '24h';
    const filtered = filterZonesByTime(gnssZonesCache.features, currentTime, mappedWindow);
    return { type: 'FeatureCollection' as const, features: filtered };
  }, [gnssZonesCache, currentTime, gnssOverlayWindow]);

  const fillPaint: FillLayerSpecification['paint'] = {
    'fill-color': [
      'match', ['get', 'event_type'],
      'spoofing', ZONE_COLORS.spoofing.fill,
      'interference_area', ZONE_COLORS.interference_area.fill,
      'jamming', ZONE_COLORS.jamming.fill,
      'rgba(239,68,68,0.2)',
    ],
    'fill-opacity': 0.8,
  };

  const linePaint: LineLayerSpecification['paint'] = {
    'line-color': [
      'match', ['get', 'event_type'],
      'spoofing', ZONE_COLORS.spoofing.stroke,
      'interference_area', ZONE_COLORS.interference_area.stroke,
      'jamming', ZONE_COLORS.jamming.stroke,
      'rgba(239,68,68,0.6)',
    ],
    'line-width': 1.5,
    'line-opacity': 0.9,
  };

  if (!showGnssOverlay || !data) return null;

  return (
    <Source id="playback-gnss-zones" type="geojson" data={data}>
      <Layer
        id="playback-gnss-zone-fill"
        type="fill"
        paint={fillPaint}
      />
      <Layer
        id="playback-gnss-zone-outline"
        type="line"
        paint={linePaint}
      />
    </Source>
  );
}
