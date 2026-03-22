import { Source, Layer } from 'react-map-gl/maplibre';
import { useQuery } from '@tanstack/react-query';
import stsZonesData from '../../data/stsZones.json';
import terminalsData from '../../data/terminals.json';

export interface StaticOverlaysProps {
  showStsZones: boolean;
  showTerminals: boolean;
  showSeaBorders: boolean;
  showSeaBordersEez: boolean;
  showSeaBorders12nm: boolean;
}

export function StaticOverlays({
  showStsZones,
  showTerminals,
  showSeaBorders,
  showSeaBordersEez,
  showSeaBorders12nm,
}: StaticOverlaysProps) {
  // Fetch EEZ boundary lines
  const { data: eezData } = useQuery({
    queryKey: ['maritime-boundaries', 'eez'],
    queryFn: async () => {
      const res = await fetch('/api/maritime-zones/boundaries?zone_type=eez&simplify=0.03');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: showSeaBorders && showSeaBordersEez,
    staleTime: Infinity,
  });

  // Fetch 12nm boundaries
  const { data: nm12Data } = useQuery({
    queryKey: ['maritime-boundaries', '12nm'],
    queryFn: async () => {
      const res = await fetch('/api/maritime-zones/boundaries?zone_type=12nm&simplify=0.3');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: showSeaBorders && showSeaBorders12nm,
    staleTime: Infinity,
  });

  return (
    <>
      {/* STS Zone Polygons */}
      {showStsZones && (
        <Source id="sts-zones" type="geojson" data={stsZonesData as GeoJSON.FeatureCollection}>
          <Layer
            id="sts-zones-fill"
            type="fill"
            paint={{
              'fill-color': 'rgba(255, 170, 30, 0.18)',
            }}
          />
          <Layer
            id="sts-zones-outline"
            type="line"
            paint={{
              'line-color': '#FFB020',
              'line-width': 2,
            }}
          />
          <Layer
            id="sts-zones-labels"
            type="symbol"
            layout={{
              'text-field': ['get', 'name'],
              'text-size': 11,
              'text-font': ['Open Sans Regular'],
            }}
            paint={{
              'text-color': '#FFB020',
              'text-halo-color': '#000000',
              'text-halo-width': 1,
            }}
          />
        </Source>
      )}

      {/* Russian Terminal Point Markers */}
      {showTerminals && (
        <Source id="terminals" type="geojson" data={terminalsData as GeoJSON.FeatureCollection}>
          <Layer
            id="terminals-circles"
            type="circle"
            paint={{
              'circle-color': '#06B6D4',
              'circle-radius': 6,
              'circle-stroke-width': 1,
              'circle-stroke-color': 'rgba(6, 182, 212, 0.4)',
            }}
          />
          <Layer
            id="terminals-labels"
            type="symbol"
            layout={{
              'text-field': ['get', 'name'],
              'text-size': 11,
              'text-offset': [0, -1.5],
              'text-font': ['Open Sans Regular'],
            }}
            paint={{
              'text-color': '#FFFFFF',
              'text-halo-color': '#000000',
              'text-halo-width': 1,
            }}
          />
        </Source>
      )}

      {/* EEZ Boundaries */}
      {showSeaBorders && showSeaBordersEez && eezData && (
        <Source id="eez-boundaries" type="geojson" data={eezData}>
          <Layer
            id="eez-lines"
            type="line"
            paint={{
              'line-color': '#60A5FA',
              'line-width': 1,
              'line-opacity': 0.5,
              'line-dasharray': [6, 3],
            }}
          />
        </Source>
      )}

      {/* 12nm Territorial Sea Boundaries */}
      {showSeaBorders && showSeaBorders12nm && nm12Data && (
        <Source id="12nm-boundaries" type="geojson" data={nm12Data}>
          <Layer
            id="12nm-lines"
            type="line"
            paint={{
              'line-color': '#93C5FD',
              'line-width': 0.7,
              'line-opacity': 0.35,
              'line-dasharray': [3, 3],
            }}
          />
        </Source>
      )}
    </>
  );
}
