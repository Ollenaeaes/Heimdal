import { Source, Layer, useMap } from 'react-map-gl/maplibre';
import { useEffect, useState, useMemo, useCallback } from 'react';
import { useLookbackStore } from '../../hooks/useLookbackStore';

/**
 * AreaDrawingTool lets users draw a polygon on the MapLibre map
 * for area-based lookback queries.
 *
 * - Click to place vertices
 * - Double-click to close the polygon (requires >= 3 vertices)
 * - Escape to cancel drawing
 */
export function AreaDrawingTool() {
  const { current: mapRef } = useMap();
  const isDrawing = useLookbackStore((s) => s.isDrawing);
  const finishDrawing = useLookbackStore((s) => s.finishDrawing);
  const cancelDrawing = useLookbackStore((s) => s.cancelDrawing);
  const [vertices, setVertices] = useState<[number, number][]>([]);

  const handleClick = useCallback(
    (e: maplibregl.MapMouseEvent) => {
      const newVertex: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      setVertices((prev) => [...prev, newVertex]);
    },
    [],
  );

  const handleDblClick = useCallback(
    (e: maplibregl.MapMouseEvent) => {
      e.preventDefault();
      setVertices((prev) => {
        if (prev.length >= 3) {
          finishDrawing(prev);
          return [];
        }
        return prev;
      });
    },
    [finishDrawing],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        cancelDrawing();
        setVertices([]);
      }
    },
    [cancelDrawing],
  );

  useEffect(() => {
    if (!mapRef || !isDrawing) return;

    const map = mapRef.getMap();
    map.getCanvas().style.cursor = 'crosshair';

    // Disable double-click zoom while drawing
    map.doubleClickZoom.disable();

    map.on('click', handleClick);
    map.on('dblclick', handleDblClick);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      map.off('click', handleClick);
      map.off('dblclick', handleDblClick);
      document.removeEventListener('keydown', handleKeyDown);
      map.getCanvas().style.cursor = '';
      map.doubleClickZoom.enable();
    };
  }, [mapRef, isDrawing, handleClick, handleDblClick, handleKeyDown]);

  // Reset vertices when drawing mode is turned off
  useEffect(() => {
    if (!isDrawing) {
      setVertices([]);
    }
  }, [isDrawing]);

  const previewGeoJson = useMemo(() => {
    if (vertices.length === 0) return null;

    const features: GeoJSON.Feature[] = [];

    // Vertex points
    for (const v of vertices) {
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: v },
        properties: {},
      });
    }

    // Line connecting vertices
    if (vertices.length >= 2) {
      features.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: vertices },
        properties: {},
      });
    }

    // Polygon fill preview when 3+ vertices
    if (vertices.length >= 3) {
      features.push({
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[...vertices, vertices[0]]],
        },
        properties: {},
      });
    }

    return { type: 'FeatureCollection' as const, features };
  }, [vertices]);

  if (!isDrawing || !previewGeoJson) return null;

  return (
    <Source id="area-drawing" type="geojson" data={previewGeoJson}>
      <Layer
        id="area-drawing-fill"
        type="fill"
        filter={['==', ['geometry-type'], 'Polygon']}
        paint={{ 'fill-color': 'rgba(96, 165, 250, 0.2)' }}
      />
      <Layer
        id="area-drawing-line"
        type="line"
        filter={['==', ['geometry-type'], 'LineString']}
        paint={{ 'line-color': '#60A5FA', 'line-width': 2 }}
      />
      <Layer
        id="area-drawing-vertices"
        type="circle"
        filter={['==', ['geometry-type'], 'Point']}
        paint={{
          'circle-radius': 4,
          'circle-color': '#60A5FA',
          'circle-stroke-width': 1,
          'circle-stroke-color': '#FFFFFF',
        }}
      />
    </Source>
  );
}
