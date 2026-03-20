import { Source, Layer } from 'react-map-gl/maplibre';
import { useMemo } from 'react';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { TrackPoint } from '../../types/api';

/**
 * Interpolate a vessel position along a track at a given time using binary search.
 * Returns the lat/lon (and optionally cog/sog) at targetMs, or null if track is empty.
 */
export function interpolatePosition(
  track: TrackPoint[],
  targetMs: number,
): { lat: number; lon: number; cog: number | null; sog: number | null } | null {
  if (!track || track.length === 0) return null;

  const firstMs = new Date(track[0].timestamp).getTime();
  const lastMs = new Date(track[track.length - 1].timestamp).getTime();

  if (targetMs <= firstMs) {
    return { lat: track[0].lat, lon: track[0].lon, cog: track[0].cog, sog: track[0].sog };
  }
  if (targetMs >= lastMs) {
    const last = track[track.length - 1];
    return { lat: last.lat, lon: last.lon, cog: last.cog, sog: last.sog };
  }

  // Binary search for the bracketing pair
  let lo = 0;
  let hi = track.length - 1;
  while (lo < hi - 1) {
    const mid = Math.floor((lo + hi) / 2);
    const midMs = new Date(track[mid].timestamp).getTime();
    if (midMs <= targetMs) lo = mid;
    else hi = mid;
  }

  const tLo = new Date(track[lo].timestamp).getTime();
  const tHi = new Date(track[hi].timestamp).getTime();

  if (tHi === tLo) {
    return { lat: track[lo].lat, lon: track[lo].lon, cog: track[lo].cog, sog: track[lo].sog };
  }

  const frac = (targetMs - tLo) / (tHi - tLo);
  return {
    lat: track[lo].lat + (track[hi].lat - track[lo].lat) * frac,
    lon: track[lo].lon + (track[hi].lon - track[lo].lon) * frac,
    cog: track[hi].cog,
    sog:
      track[lo].sog !== null && track[hi].sog !== null
        ? track[lo].sog + (track[hi].sog - track[lo].sog) * frac
        : track[hi].sog,
  };
}

/**
 * LookbackLayer renders interpolated vessel positions and progressive trails
 * during lookback playback on a MapLibre map.
 */
export function LookbackLayer() {
  const isActive = useLookbackStore((s) => s.isActive);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const tracks = useLookbackStore((s) => s.tracks);
  const selectedVessels = useLookbackStore((s) => s.selectedVessels);
  const networkVessels = useLookbackStore((s) => s.networkVessels);
  const isAreaMode = useLookbackStore((s) => s.isAreaMode);
  const areaPolygon = useLookbackStore((s) => s.areaPolygon);
  const vessels = useVesselStore((s) => s.vessels);

  const lookbackData = useMemo(() => {
    if (!isActive || !currentTime) return null;

    const targetMs = currentTime.getTime();
    const markers: GeoJSON.Feature[] = [];
    const trails: GeoJSON.Feature[] = [];

    const allMmsis = [...selectedVessels, ...networkVessels];

    for (const mmsi of allMmsis) {
      const track = tracks.get(mmsi);
      if (!track || track.length === 0) continue;

      const isNetwork =
        networkVessels.includes(mmsi) && !selectedVessels.includes(mmsi);
      const vesselData = vessels.get(mmsi);
      const name = vesselData?.name || `MMSI ${mmsi}`;

      const pos = interpolatePosition(track, targetMs);
      if (!pos) continue;

      // Marker at interpolated position
      markers.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [pos.lon, pos.lat] },
        properties: {
          mmsi,
          name,
          isNetwork,
        },
      });

      // Trail up to current time (plus interpolated position at end)
      const trailCoords: [number, number][] = [];
      for (const p of track) {
        if (new Date(p.timestamp).getTime() > targetMs) break;
        trailCoords.push([p.lon, p.lat]);
      }
      // Append the interpolated position for a smooth trail end
      trailCoords.push([pos.lon, pos.lat]);

      if (trailCoords.length >= 2) {
        trails.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: trailCoords },
          properties: { mmsi, isNetwork },
        });
      }
    }

    return {
      markers: { type: 'FeatureCollection' as const, features: markers },
      trails: { type: 'FeatureCollection' as const, features: trails },
    };
  }, [isActive, currentTime, tracks, selectedVessels, networkVessels, vessels]);

  // Area polygon GeoJSON for rendering the search area boundary
  const areaGeoJson = useMemo(() => {
    if (!isAreaMode || !areaPolygon || areaPolygon.length < 3) return null;
    const closed = [...areaPolygon, areaPolygon[0]];
    return {
      type: 'FeatureCollection' as const,
      features: [
        {
          type: 'Feature' as const,
          geometry: { type: 'Polygon' as const, coordinates: [closed] },
          properties: {},
        },
      ],
    };
  }, [isAreaMode, areaPolygon]);

  if (!isActive || !lookbackData) return null;

  return (
    <>
      {/* Trail lines */}
      <Source id="lookback-trails" type="geojson" data={lookbackData.trails}>
        <Layer
          id="lookback-trail-lines"
          type="line"
          paint={{
            'line-color': [
              'case',
              ['get', 'isNetwork'],
              'rgba(147, 51, 234, 0.25)',
              '#60A5FA',
            ],
            'line-width': ['case', ['get', 'isNetwork'], 1, 2],
            'line-opacity': 0.6,
          }}
        />
      </Source>

      {/* Vessel marker circles */}
      <Source id="lookback-markers" type="geojson" data={lookbackData.markers}>
        <Layer
          id="lookback-marker-circles"
          type="circle"
          paint={{
            'circle-radius': 5,
            'circle-color': ['case', ['get', 'isNetwork'], '#9333EA', '#60A5FA'],
            'circle-opacity': ['case', ['get', 'isNetwork'], 0.25, 1],
            'circle-stroke-width': 1,
            'circle-stroke-color': '#FFFFFF',
          }}
        />
        <Layer
          id="lookback-marker-labels"
          type="symbol"
          layout={{
            'text-field': ['get', 'name'],
            'text-size': 10,
            'text-offset': [0, 1.5],
            'text-font': ['Open Sans Regular'],
          }}
          paint={{
            'text-color': '#FFFFFF',
            'text-halo-color': '#000000',
            'text-halo-width': 1,
          }}
        />
      </Source>

      {/* Area polygon overlay (if in area mode) */}
      {areaGeoJson && (
        <Source id="lookback-area-polygon" type="geojson" data={areaGeoJson}>
          <Layer
            id="lookback-area-polygon-fill"
            type="fill"
            paint={{
              'fill-color': 'rgba(59, 130, 246, 0.1)',
            }}
          />
          <Layer
            id="lookback-area-polygon-line"
            type="line"
            paint={{
              'line-color': '#3B82F6',
              'line-width': 2,
              'line-opacity': 0.6,
            }}
          />
        </Source>
      )}
    </>
  );
}
