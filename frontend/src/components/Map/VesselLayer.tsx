import { useCallback, useMemo } from 'react';
import { Source, Layer, useMap } from 'react-map-gl/maplibre';
import type { MapLayerMouseEvent, GeoJSONSource } from 'react-map-gl/maplibre';
import type { FeatureCollection, Point } from 'geojson';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { FilterState } from '../../hooks/useVesselStore';
import { useWatchlistStore } from '../../hooks/useWatchlist';
import type { VesselState } from '../../types/vessel';

/**
 * Filter vessels according to the active FilterState.
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

/** Map riskTier to a numeric score for cluster aggregation. */
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
  shipName: string;
  isWatchlisted: boolean;
  isSpoofed: boolean;
}

/**
 * Convert a vessel Map into a GeoJSON FeatureCollection.
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
      cog: v.cog,
      shipName: v.name ?? `MMSI ${v.mmsi}`,
      isWatchlisted: watchedMmsis.has(v.mmsi),
      isSpoofed: spoofedMmsis.has(v.mmsi),
    },
  }));

  return {
    type: 'FeatureCollection',
    features,
  };
}

/**
 * Renders vessel markers with clustering on a MapLibre map.
 * Must be rendered as a child of a react-map-gl <Map>.
 */
export function VesselLayer() {
  const { current: map } = useMap();
  const vessels = useVesselStore((s) => s.vessels);
  const filters = useVesselStore((s) => s.filters);
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const watchedMmsis = useWatchlistStore((s) => s.watchedMmsis);
  const spoofedMmsis = useVesselStore((s) => s.spoofedMmsis);

  const visibleVessels = useMemo(() => filterVessels(vessels, filters), [vessels, filters]);

  const geojson = useMemo(
    () => buildVesselGeoJson(visibleVessels, watchedMmsis, spoofedMmsis),
    [visibleVessels, watchedMmsis, spoofedMmsis],
  );

  /** Click handler for cluster circles — zoom to expand. */
  const onClusterClick = useCallback(
    (e: MapLayerMouseEvent) => {
      if (!map || !e.features?.[0]) return;
      const feature = e.features[0];
      const clusterId = feature.properties?.cluster_id;
      if (clusterId == null) return;

      const source = map.getSource('vessels') as GeoJSONSource | undefined;
      if (!source) return;

      (source as unknown as { getClusterExpansionZoom: (id: number, cb: (err: Error | null, zoom: number) => void) => void })
        .getClusterExpansionZoom(clusterId, (err: Error | null, zoom: number) => {
          if (err || !feature.geometry || feature.geometry.type !== 'Point') return;
          map.flyTo({
            center: feature.geometry.coordinates as [number, number],
            zoom,
            duration: 500,
          });
        });
    },
    [map],
  );

  /** Click handler for individual vessel markers. */
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
          zoom: 10,
          duration: 1500,
        });
      }
    },
    [map, selectVessel],
  );

  /** Change cursor to pointer on hover over interactive layers. */
  const onMouseEnter = useCallback(() => {
    if (map) map.getCanvas().style.cursor = 'pointer';
  }, [map]);

  const onMouseLeave = useCallback(() => {
    if (map) map.getCanvas().style.cursor = '';
  }, [map]);

  return (
    <Source
      id="vessels"
      type="geojson"
      data={geojson}
      cluster={true}
      clusterRadius={50}
      clusterMaxZoom={14}
      clusterProperties={{
        maxRiskScore: ['max', ['get', 'riskScore']],
      }}
    >
      {/* Cluster circles — color by highest risk in cluster */}
      <Layer
        id="vessel-clusters"
        type="circle"
        filter={['has', 'point_count']}
        paint={{
          'circle-color': [
            'step',
            ['get', 'maxRiskScore'],
            '#22C55E', // green (0-29)
            30,
            '#F59E0B', // yellow (30-99)
            100,
            '#EF4444', // red (100+)
          ],
          'circle-radius': ['step', ['get', 'point_count'], 20, 10, 25, 50, 30],
          'circle-stroke-width': 2,
          'circle-stroke-color': '#1F2937',
        }}
        onClick={onClusterClick}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      />

      {/* Cluster count labels */}
      <Layer
        id="vessel-cluster-count"
        type="symbol"
        filter={['has', 'point_count']}
        layout={{
          'text-field': '{point_count_abbreviated}',
          'text-size': 12,
          'text-font': ['Open Sans Bold'],
        }}
        paint={{
          'text-color': '#FFFFFF',
        }}
      />

      {/* Watchlist halo — rendered behind vessel markers */}
      {/* Individual vessel markers (unclustered) */}
      <Layer
        id="vessel-markers"
        type="circle"
        filter={['!', ['has', 'point_count']]}
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
            'match',
            ['get', 'riskTier'],
            'green', 3,
            4,
          ],
          'circle-opacity': [
            'match',
            ['get', 'riskTier'],
            'green', 0.3,
            1,
          ],
          'circle-stroke-width': 1,
          'circle-stroke-color': '#0F172A',
        }}
        onClick={onVesselClick}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      />

      {/* Watchlist halo — rendered after markers, visually behind via larger radius */}
      <Layer
        id="vessel-watchlist-halo"
        type="circle"
        filter={[
          'all',
          ['!', ['has', 'point_count']],
          ['==', ['get', 'isWatchlisted'], true],
        ]}
        paint={{
          'circle-radius': 8,
          'circle-color': 'transparent',
          'circle-stroke-width': 2,
          'circle-stroke-color': 'rgba(255, 255, 255, 0.4)',
        }}
      />

      {/* Selection ring for currently selected vessel */}
      <Layer
        id="vessel-selection"
        type="circle"
        filter={['==', ['get', 'mmsi'], selectedMmsi ?? '']}
        paint={{
          'circle-radius': 10,
          'circle-color': 'transparent',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#FFFFFF',
        }}
      />
    </Source>
  );
}
