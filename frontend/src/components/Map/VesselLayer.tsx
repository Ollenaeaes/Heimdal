import { useCallback, useEffect, useMemo } from 'react';
import { Source, Layer, useMap } from 'react-map-gl/maplibre';
import type { MapLayerMouseEvent } from 'react-map-gl/maplibre';
import type { FeatureCollection, Point, LineString, Feature } from 'geojson';
import { useVesselStore } from '../../hooks/useVesselStore';
import { useWatchlistStore } from '../../hooks/useWatchlist';
import type { VesselState } from '../../types/vessel';
import { registerVesselIcons } from '../../utils/vesselIcons';

/** Speed threshold (knots) below which a vessel is considered stationary. */
const STATIONARY_SPEED = 0.5;

/** Zoom level at which we switch from arrows to hull shapes. */
const HULL_ZOOM = 13;

/** Speed vector: 10 minutes of travel at current SOG, drawn as a line from vessel position. */
const VECTOR_MINUTES = 10;

/**
 * Filter vessels according to the active FilterState.
 */
export function filterVessels(
  vessels: Map<number, VesselState>,
  filters: { riskTiers: Set<string>; shipTypes: number[]; activeSince: string | null },
): VesselState[] {
  const result: VesselState[] = [];
  for (const vessel of vessels.values()) {
    if (filters.riskTiers.size > 0 && !filters.riskTiers.has(vessel.riskTier)) continue;
    if (
      filters.shipTypes.length > 0 &&
      vessel.shipType != null &&
      !filters.shipTypes.includes(vessel.shipType)
    ) continue;
    if (filters.activeSince && vessel.timestamp < filters.activeSince) continue;
    result.push(vessel);
  }
  const tierOrder: Record<string, number> = { green: 0, yellow: 1, red: 2, blacklisted: 3 };
  result.sort((a, b) => (tierOrder[a.riskTier] ?? 0) - (tierOrder[b.riskTier] ?? 0));
  return result;
}

/** Map riskTier to a numeric score for data-driven styling. */
const RISK_SCORE_MAP: Record<string, number> = {
  green: 0,
  yellow: 50,
  red: 100,
  blacklisted: 150,
};

export interface VesselFeatureProperties {
  mmsi: number;
  riskTier: string;
  riskScore: number;
  cog: number | null;
  heading: number | null;
  sog: number | null;
  shipName: string;
  isWatchlisted: boolean;
  isSpoofed: boolean;
  isMoving: boolean;
  vesselLength: number;
  vesselWidth: number;
  rotation: number;
}

/**
 * Convert a vessel list into a GeoJSON FeatureCollection.
 * Exported for testing.
 */
export function buildVesselGeoJson(
  vessels: VesselState[],
  watchedMmsis: Set<number>,
  spoofedMmsis: Set<number>,
): FeatureCollection<Point, VesselFeatureProperties> {
  const features = vessels.map((v) => ({
    type: 'Feature' as const,
    geometry: {
      type: 'Point' as const,
      coordinates: [v.lon, v.lat],
    },
    properties: {
      mmsi: v.mmsi,
      riskTier: v.riskTier,
      riskScore: RISK_SCORE_MAP[v.riskTier] ?? 0,
      cog: v.cog ?? null,
      heading: v.heading ?? null,
      sog: v.sog ?? null,
      // Pre-computed rotation: heading preferred, COG fallback
      rotation: v.heading ?? v.cog ?? 0,
      shipName: v.name ?? `MMSI ${v.mmsi}`,
      isWatchlisted: watchedMmsis.has(v.mmsi),
      isSpoofed: spoofedMmsis.has(v.mmsi),
      isMoving: (v.sog ?? 0) >= STATIONARY_SPEED,
      vesselLength: v.length ?? 0,
      vesselWidth: v.width ?? 0,
    },
  }));

  return {
    type: 'FeatureCollection',
    features,
  };
}

/**
 * Build speed vector lines for moving vessels (10-minute projected path from COG + SOG).
 * Only generated for vessels with sog >= STATIONARY_SPEED and a valid COG.
 */
export function buildSpeedVectors(
  vessels: VesselState[],
): FeatureCollection<LineString> {
  const features: Feature<LineString>[] = [];

  for (const v of vessels) {
    const sog = v.sog ?? 0;
    const cog = v.cog;
    if (sog < STATIONARY_SPEED || cog == null) continue;

    // Distance in nautical miles for VECTOR_MINUTES at current SOG
    const distNm = sog * (VECTOR_MINUTES / 60);
    // Convert to approximate degrees (1° lat ≈ 60nm)
    const distDeg = distNm / 60;
    const cogRad = (cog * Math.PI) / 180;

    const endLon = v.lon + distDeg * Math.sin(cogRad) / Math.cos((v.lat * Math.PI) / 180);
    const endLat = v.lat + distDeg * Math.cos(cogRad);

    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [v.lon, v.lat],
          [endLon, endLat],
        ],
      },
      properties: {
        riskTier: v.riskTier,
      },
    });
  }

  return { type: 'FeatureCollection', features };
}

/**
 * Renders vessel markers on a MapLibre map with zoom-dependent symbology:
 * - Zoomed out: dots (stationary) + directional arrows (moving)
 * - Port-level zoom (>=13): hull shapes rotated by heading, sized by AIS dimensions
 * - Speed vectors (10 min COG projection) shown at port-level zoom
 *
 * No clustering. All vessels above green are always visible.
 */
export function VesselLayer() {
  const { current: map } = useMap();
  const vessels = useVesselStore((s) => s.vessels);
  const filters = useVesselStore((s) => s.filters);
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const watchedMmsis = useWatchlistStore((s) => s.watchedMmsis);
  const spoofedMmsis = useVesselStore((s) => s.spoofedMmsis);

  // Register vessel icons when map is available
  useEffect(() => {
    if (!map) return;
    const mapInstance = map.getMap();
    const register = () => registerVesselIcons(mapInstance);

    // Try immediately if style already loaded
    if (mapInstance.isStyleLoaded()) {
      register();
    }
    // Also register on load/style.load to handle race conditions
    mapInstance.on('load', register);
    mapInstance.on('style.load', register);
    // Handle missing images as fallback
    mapInstance.on('styleimagemissing', (e: { id: string }) => {
      if (e.id.startsWith('arrow-') || e.id.startsWith('hull-')) {
        register();
      }
    });

    return () => {
      mapInstance.off('load', register);
      mapInstance.off('style.load', register);
    };
  }, [map]);

  const visibleVessels = useMemo(() => filterVessels(vessels, filters), [vessels, filters]);

  const geojson = useMemo(
    () => buildVesselGeoJson(visibleVessels, watchedMmsis, spoofedMmsis),
    [visibleVessels, watchedMmsis, spoofedMmsis],
  );

  const speedVectors = useMemo(
    () => buildSpeedVectors(visibleVessels),
    [visibleVessels],
  );

  /** Click handler for vessel markers (any layer). */
  const onVesselClick = useCallback(
    (e: MapLayerMouseEvent) => {
      if (!map || !e.features?.[0]) return;
      const feature = e.features[0];
      const mmsi = feature.properties?.mmsi;
      if (mmsi == null) return;

      selectVessel(Number(mmsi));

      if (feature.geometry?.type === 'Point') {
        map.flyTo({
          center: feature.geometry.coordinates as [number, number],
          zoom: Math.max(map.getZoom(), 10),
          duration: 1500,
        });
      }
    },
    [map, selectVessel],
  );

  const onMouseEnter = useCallback(() => {
    if (map) map.getCanvas().style.cursor = 'pointer';
  }, [map]);

  const onMouseLeave = useCallback(() => {
    if (map) map.getCanvas().style.cursor = '';
  }, [map]);

  // Hull icon sizes — small at zoom 13, grow as you zoom in
  const hullIconSize: maplibregl.ExpressionSpecification = [
    'interpolate', ['linear'], ['zoom'],
    HULL_ZOOM, [
      'step', ['get', 'vesselLength'],
      0.15,   // < 50m
      50, 0.2,
      150, 0.28,
      300, 0.35,
    ],
    16, [
      'step', ['get', 'vesselLength'],
      0.35,
      50, 0.5,
      150, 0.7,
      300, 0.9,
    ],
    18, [
      'step', ['get', 'vesselLength'],
      0.6,
      50, 0.85,
      150, 1.2,
      300, 1.5,
    ],
  ];

  return (
    <>
      {/* ── Speed vectors (COG projected 10 min) ── */}
      <Source id="vessel-vectors" type="geojson" data={speedVectors}>
        <Layer
          id="vessel-speed-vector"
          type="line"
          minzoom={HULL_ZOOM}
          paint={{
            'line-color': [
              'match',
              ['get', 'riskTier'],
              'green', '#22C55E',
              'yellow', '#F59E0B',
              'red', '#EF4444',
              'blacklisted', '#9333EA',
              '#6B7280',
            ],
            'line-width': 1.5,
            'line-opacity': 0.6,
            'line-dasharray': [2, 3],
          }}
        />
      </Source>

      {/* ── Vessel points source (no clustering) ── */}
      <Source id="vessels" type="geojson" data={geojson}>

        {/* ── Stationary dots (all zoom levels) ── */}
        <Layer
          id="vessel-dots-stationary"
          type="circle"
          filter={['==', ['get', 'isMoving'], false]}
          paint={{
            'circle-color': [
              'match',
              ['get', 'riskTier'],
              'green', '#22C55E',
              'yellow', '#F59E0B',
              'red', '#EF4444',
              'blacklisted', '#9333EA',
              '#6B7280',
            ],
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              3, ['match', ['get', 'riskTier'],
                'green', 1.5,
                'yellow', 2.5,
                'red', 3,
                'blacklisted', 3.5,
                2],
              8, ['match', ['get', 'riskTier'],
                'green', 2,
                'yellow', 3.5,
                'red', 4.5,
                'blacklisted', 5,
                3],
              HULL_ZOOM, ['match', ['get', 'riskTier'],
                'green', 3,
                'yellow', 5,
                'red', 6,
                'blacklisted', 7,
                4],
            ],
            'circle-opacity': [
              'match',
              ['get', 'riskTier'],
              'green', 0.35,
              'yellow', 0.9,
              1,
            ],
            'circle-stroke-width': [
              'match', ['get', 'riskTier'],
              'green', 0,
              0.5,
            ],
            'circle-stroke-color': '#0A1628',
          }}
          maxzoom={HULL_ZOOM + 1}
          onClick={onVesselClick}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
        />

        {/* ── Moving vessel arrows (zoomed out, below hull zoom) ── */}
        <Layer
          id="vessel-arrows"
          type="symbol"
          filter={['==', ['get', 'isMoving'], true]}
          maxzoom={HULL_ZOOM + 1}
          layout={{
            'icon-image': [
              'match',
              ['get', 'riskTier'],
              'green', 'arrow-green',
              'yellow', 'arrow-yellow',
              'red', 'arrow-red',
              'blacklisted', 'arrow-blacklisted',
              'arrow-green',
            ],
            'icon-size': [
              'interpolate', ['linear'], ['zoom'],
              3, ['match', ['get', 'riskTier'],
                'green', 0.3,
                'yellow', 0.45,
                'red', 0.55,
                'blacklisted', 0.6,
                0.4],
              8, ['match', ['get', 'riskTier'],
                'green', 0.45,
                'yellow', 0.65,
                'red', 0.8,
                'blacklisted', 0.85,
                0.6],
              HULL_ZOOM, ['match', ['get', 'riskTier'],
                'green', 0.6,
                'yellow', 0.8,
                'red', 1.0,
                'blacklisted', 1.05,
                0.8],
            ],
            'icon-rotate': ['get', 'rotation'],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          }}
          paint={{
            'icon-opacity': [
              'match',
              ['get', 'riskTier'],
              'green', 0.4,
              1,
            ],
          }}
          onClick={onVesselClick}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
        />

        {/* ── Hull shapes (port-level zoom, all vessels) ── */}
        <Layer
          id="vessel-hulls"
          type="symbol"
          minzoom={HULL_ZOOM}
          layout={{
            'icon-image': [
              'match',
              ['get', 'riskTier'],
              'green', 'hull-green',
              'yellow', 'hull-yellow',
              'red', 'hull-red',
              'blacklisted', 'hull-blacklisted',
              'hull-green',
            ],
            'icon-size': hullIconSize as unknown as number,
            'icon-rotate': ['get', 'rotation'],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          }}
          paint={{
            'icon-opacity': [
              'match',
              ['get', 'riskTier'],
              'green', 0.6,
              1,
            ],
          }}
          onClick={onVesselClick}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
        />

        {/* ── Watchlist halo ── */}
        <Layer
          id="vessel-watchlist-halo"
          type="circle"
          filter={['==', ['get', 'isWatchlisted'], true]}
          paint={{
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              3, 6,
              8, 8,
              HULL_ZOOM, 14,
              18, 22,
            ],
            'circle-color': 'transparent',
            'circle-stroke-width': 2,
            'circle-stroke-color': 'rgba(255, 255, 255, 0.4)',
          }}
        />

        {/* ── Selection ring ── */}
        <Layer
          id="vessel-selection"
          type="circle"
          filter={['==', ['get', 'mmsi'], selectedMmsi ?? '']}
          paint={{
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              3, 8,
              8, 10,
              HULL_ZOOM, 16,
              18, 24,
            ],
            'circle-color': 'transparent',
            'circle-stroke-width': 2,
            'circle-stroke-color': '#FFFFFF',
          }}
        />
      </Source>
    </>
  );
}
