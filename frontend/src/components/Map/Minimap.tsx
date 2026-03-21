import { Map as MapGL, Source, Layer } from 'react-map-gl/maplibre';
import { useCallback, useEffect, useState, useMemo } from 'react';
import { useVesselStore } from '../../hooks/useVesselStore';
import { getMapInstance } from './mapInstance';
import type { StyleSpecification } from 'maplibre-gl';
import type { Feature, FeatureCollection, Polygon, Point } from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css';

const WIDTH = 200;
const HEIGHT = 150;

export function createMinimapStyle(): StyleSpecification {
  const key = import.meta.env.VITE_MAPTILER_KEY || '';
  return {
    version: 8,
    sources: {
      openmaptiles: {
        type: 'vector',
        url: `https://api.maptiler.com/tiles/v3/tiles.json?key=${key}`,
      },
    },
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': '#0A1628' },
      },
      {
        id: 'land',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'landcover',
        paint: { 'fill-color': '#1A2332' },
      },
      {
        id: 'water',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'water',
        paint: { 'fill-color': '#0A1628' },
      },
    ],
  };
}

export default function Minimap() {
  const [viewportRect, setViewportRect] = useState<Feature<Polygon> | null>(null);
  const vessels = useVesselStore((s) => s.vessels);

  const minimapStyle = useMemo(() => createMinimapStyle(), []);

  // Listen to main map moveend to update viewport rectangle
  useEffect(() => {
    const mainMap = getMapInstance();
    if (!mainMap) return;

    const updateRect = () => {
      const bounds = mainMap.getBounds();
      const sw = bounds.getSouthWest();
      const ne = bounds.getNorthEast();
      // Only show if viewport is smaller than the world
      if (ne.lng - sw.lng > 350) {
        setViewportRect(null);
        return;
      }
      setViewportRect({
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [sw.lng, sw.lat],
            [ne.lng, sw.lat],
            [ne.lng, ne.lat],
            [sw.lng, ne.lat],
            [sw.lng, sw.lat],
          ]],
        },
        properties: {},
      });
    };

    mainMap.on('moveend', updateRect);
    updateRect();
    return () => { mainMap.off('moveend', updateRect); };
  }, []);

  // Build vessel dots GeoJSON — filter out green vessels
  const vesselDots = useMemo<FeatureCollection<Point>>(() => {
    const features: Feature<Point>[] = [];
    for (const v of vessels.values()) {
      if (v.riskTier === 'green') continue;
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [v.lon, v.lat] },
        properties: { riskTier: v.riskTier },
      });
    }
    return { type: 'FeatureCollection', features };
  }, [vessels]);

  // Click on minimap to navigate the main map
  const handleClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const mainMap = getMapInstance();
    if (!mainMap) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // Convert pixel to lon/lat (equirectangular approximation)
    const lon = (x / WIDTH) * 360 - 180;
    const lat = 90 - (y / HEIGHT) * 180;
    mainMap.flyTo({ center: [lon, lat], zoom: 5, duration: 1500 });
  }, []);

  return (
    <div
      className="absolute bottom-10 left-3 z-30 rounded border border-[#1F2937] overflow-hidden shadow-lg cursor-crosshair"
      style={{ width: WIDTH, height: HEIGHT }}
      onClick={handleClick}
    >
      <MapGL
        style={{ width: WIDTH, height: HEIGHT }}
        mapStyle={minimapStyle}
        interactive={false}
        attributionControl={false}
        initialViewState={{ longitude: 0, latitude: 30, zoom: 0 }}
      >
        {/* Viewport rectangle */}
        {viewportRect && (
          <Source id="viewport-rect" type="geojson" data={viewportRect}>
            <Layer
              id="viewport-rect-line"
              type="line"
              paint={{ 'line-color': 'rgba(255,255,255,0.7)', 'line-width': 1 }}
            />
          </Source>
        )}
        {/* Vessel dots */}
        {vesselDots.features.length > 0 && (
          <Source id="minimap-vessels" type="geojson" data={vesselDots}>
            <Layer
              id="minimap-vessel-dots"
              type="circle"
              paint={{
                'circle-radius': 1.5,
                'circle-color': [
                  'match', ['get', 'riskTier'],
                  'red', '#EF4444',
                  'yellow', '#EAB308',
                  'blacklisted', '#9333EA',
                  '#6B7280',
                ],
              }}
            />
          </Source>
        )}
      </MapGL>
    </div>
  );
}
