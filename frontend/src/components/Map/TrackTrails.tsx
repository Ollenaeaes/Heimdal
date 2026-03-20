import { useMemo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import { useVesselStore } from '../../hooks/useVesselStore';

/**
 * Renders 1-hour fading trails for all non-green vessels as GeoJSON LineStrings.
 * Each trail is colored by the vessel's risk tier.
 */
export function TrackTrails() {
  const positionHistory = useVesselStore((s) => s.positionHistory);
  const vessels = useVesselStore((s) => s.vessels);

  const trailData = useMemo(() => {
    const features: GeoJSON.Feature[] = [];

    for (const [mmsi, positions] of positionHistory) {
      if (positions.length < 2) continue;
      const vessel = vessels.get(mmsi);
      if (!vessel || vessel.riskTier === 'green') continue;

      features.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: positions.map((p) => [p.lon, p.lat]),
        },
        properties: {
          mmsi,
          riskTier: vessel.riskTier,
        },
      });
    }

    return {
      type: 'FeatureCollection' as const,
      features,
    };
  }, [vessels, positionHistory]);

  return (
    <Source id="track-trails" type="geojson" data={trailData}>
      <Layer
        id="track-trails-line"
        type="line"
        paint={{
          'line-color': [
            'match',
            ['get', 'riskTier'],
            'yellow',
            '#F59E0B',
            'red',
            '#EF4444',
            'blacklisted',
            '#9333EA',
            '#6B7280',
          ],
          'line-width': 2,
          'line-opacity': 0.6,
        }}
      />
    </Source>
  );
}
