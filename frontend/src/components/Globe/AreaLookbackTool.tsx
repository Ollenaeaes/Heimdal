import { useEffect, useRef, useCallback, useState } from 'react';
import {
  Cartographic,
  Math as CesiumMath,
  ScreenSpaceEventType,
  ScreenSpaceEventHandler,
  Cartesian3,
  Color,
} from 'cesium';
import { Entity, PolylineGraphics, PolygonGraphics } from 'resium';
import { useCesium } from 'resium';
import { useLookbackStore } from '../../hooks/useLookbackStore';

/** Distance in pixels to consider "close to first vertex" for closing the polygon. */
const CLOSE_THRESHOLD_PX = 15;

function AreaDrawingInner() {
  const { viewer } = useCesium();
  const isDrawing = useLookbackStore((s) => s.isDrawing);
  const finishDrawing = useLookbackStore((s) => s.finishDrawing);
  const cancelDrawing = useLookbackStore((s) => s.cancelDrawing);

  const [vertices, setVertices] = useState<[number, number][]>([]);
  const [cursorPos, setCursorPos] = useState<[number, number] | null>(null);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);

  useEffect(() => {
    if (!isDrawing || !viewer) return;

    // Set crosshair cursor
    const container = viewer.canvas.parentElement;
    if (container) container.style.cursor = 'crosshair';

    const handler = new ScreenSpaceEventHandler(viewer.canvas);
    handlerRef.current = handler;

    // LEFT_CLICK — place vertex or close polygon
    handler.setInputAction((event: { position: { x: number; y: number } }) => {
      const cartesian = viewer.camera.pickEllipsoid(
        event.position,
        viewer.scene.globe.ellipsoid,
      );
      if (!cartesian) return;

      const carto = Cartographic.fromCartesian(cartesian);
      const lon = CesiumMath.toDegrees(carto.longitude);
      const lat = CesiumMath.toDegrees(carto.latitude);

      setVertices((prev) => {
        // Check if close to first vertex (close the polygon)
        if (prev.length >= 3) {
          const firstCart = Cartesian3.fromDegrees(prev[0][0], prev[0][1]);
          const firstScreen = viewer.scene.cartesianToCanvasCoordinates(firstCart);
          if (firstScreen) {
            const dx = event.position.x - firstScreen.x;
            const dy = event.position.y - firstScreen.y;
            if (Math.sqrt(dx * dx + dy * dy) < CLOSE_THRESHOLD_PX) {
              finishDrawing(prev);
              return [];
            }
          }
        }
        return [...prev, [lon, lat]];
      });
    }, ScreenSpaceEventType.LEFT_CLICK);

    // DOUBLE_CLICK — close polygon
    handler.setInputAction(() => {
      setVertices((prev) => {
        if (prev.length >= 3) {
          finishDrawing(prev);
          return [];
        }
        return prev;
      });
    }, ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

    // MOUSE_MOVE — update cursor position for preview line
    handler.setInputAction((event: { endPosition: { x: number; y: number } }) => {
      const cartesian = viewer.camera.pickEllipsoid(
        event.endPosition,
        viewer.scene.globe.ellipsoid,
      );
      if (!cartesian) return;
      const carto = Cartographic.fromCartesian(cartesian);
      setCursorPos([
        CesiumMath.toDegrees(carto.longitude),
        CesiumMath.toDegrees(carto.latitude),
      ]);
    }, ScreenSpaceEventType.MOUSE_MOVE);

    // ESC to cancel
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        cancelDrawing();
        setVertices([]);
      }
    };
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      handler.destroy();
      handlerRef.current = null;
      if (container) container.style.cursor = '';
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isDrawing, viewer, finishDrawing, cancelDrawing]);

  // Reset vertices when drawing stops
  useEffect(() => {
    if (!isDrawing) {
      setVertices([]);
      setCursorPos(null);
    }
  }, [isDrawing]);

  if (!isDrawing || vertices.length === 0) return null;

  // Build preview polyline: vertices + cursor position
  const previewPositions = [
    ...vertices.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat)),
    ...(cursorPos ? [Cartesian3.fromDegrees(cursorPos[0], cursorPos[1])] : []),
  ];

  return (
    <>
      {/* Preview polyline */}
      {previewPositions.length >= 2 && (
        <Entity key="area-draw-preview">
          <PolylineGraphics
            positions={previewPositions}
            width={2}
            material={Color.fromCssColorString('#3B82F6').withAlpha(0.7)}
          />
        </Entity>
      )}

      {/* Semi-transparent fill when 3+ vertices */}
      {vertices.length >= 3 && (
        <Entity key="area-draw-fill">
          <PolygonGraphics
            hierarchy={vertices.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat))}
            material={Color.fromCssColorString('#3B82F6').withAlpha(0.15)}
          />
        </Entity>
      )}
    </>
  );
}

/** Button to activate area lookback drawing mode. */
export function AreaLookbackButton() {
  const isDrawing = useLookbackStore((s) => s.isDrawing);
  const isActive = useLookbackStore((s) => s.isActive);
  const startDrawing = useLookbackStore((s) => s.startDrawing);
  const cancelDrawing = useLookbackStore((s) => s.cancelDrawing);

  if (isActive) return null; // Don't show button during active lookback

  return (
    <button
      onClick={() => (isDrawing ? cancelDrawing() : startDrawing())}
      className={`px-3 py-1.5 text-xs rounded transition-colors ${
        isDrawing
          ? 'bg-red-600 hover:bg-red-700 text-white'
          : 'bg-[#1F2937] hover:bg-[#374151] text-gray-300 hover:text-white border border-[#374151]'
      }`}
      data-testid="area-lookback-button"
      aria-label={isDrawing ? 'Cancel drawing' : 'Area Lookback'}
    >
      {isDrawing ? 'Cancel Drawing' : 'Area Lookback'}
    </button>
  );
}

/** Renders the polygon drawing tool on the Cesium globe. Must be a child of <Viewer>. */
export function AreaLookbackDrawing() {
  return <AreaDrawingInner />;
}
