import { useEffect, useRef, useState, useCallback } from 'react';
import {
  SingleTileImageryProvider,
  ImageryLayer,
  Rectangle,
  Color,
  Cartesian3,
} from 'cesium';
import { useQuery } from '@tanstack/react-query';
import { getCesiumViewer } from './cesiumViewer';
import { SpoofingTimeControls } from './SpoofingTimeControls';

export interface GnssZoneOverlayProps {
  visible: boolean;
}

/** Exported for tests. */
export function computeGnssOpacity(affectedCount: number): number {
  if (affectedCount <= 3) return 0.15;
  if (affectedCount >= 10) return 0.5;
  return 0.15 + ((affectedCount - 3) / (10 - 3)) * (0.5 - 0.15);
}

interface SpoofingPoint {
  lat: number;
  lon: number;
  mmsi: number;
  rule: string;
  severity: string;
  ship_name: string | null;
  time: string | null;
}

/** Heatmap canvas resolution. */
const CANVAS_W = 1800;
const CANVAS_H = 900;

/** Gaussian kernel radius in pixels (each pixel ≈ 0.2 degrees). */
const RADIUS = 15;

/**
 * Renders GNSS spoofing events as a smooth heatmap overlay on the globe.
 * Includes time preset buttons and a timeline scrubber.
 */
export function GnssZoneOverlay({ visible }: GnssZoneOverlayProps) {
  const layerRef = useRef<ImageryLayer | null>(null);
  const [timeRange, setTimeRange] = useState<{ start: Date; end: Date }>(() => {
    const now = new Date();
    return { start: new Date(now.getTime() - 24 * 3600_000), end: now };
  });

  const queryParams = visible
    ? `?start=${timeRange.start.toISOString()}&end=${timeRange.end.toISOString()}`
    : '';

  const { data } = useQuery<{ points: SpoofingPoint[]; count: number }>({
    queryKey: ['gnssSpoofingEvents', timeRange.start.toISOString(), timeRange.end.toISOString()],
    queryFn: () => fetch(`/api/gnss-spoofing-events${queryParams}`).then((r) => r.json()),
    refetchInterval: 60_000,
    enabled: visible,
  });

  const handleTimeRangeChange = useCallback((start: Date, end: Date) => {
    setTimeRange({ start, end });
  }, []);

  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    // Remove previous heatmap layer
    if (layerRef.current) {
      viewer.imageryLayers.remove(layerRef.current, false);
      layerRef.current = null;
    }

    if (!visible || !data?.points?.length) return;

    // Build heatmap canvas
    const canvas = buildHeatmapCanvas(data.points);

    const provider = new SingleTileImageryProvider({
      url: canvas.toDataURL(),
      rectangle: Rectangle.fromDegrees(-180, -90, 180, 90),
    });

    const layer = viewer.imageryLayers.addImageryProvider(provider);
    layer.alpha = 0.75;
    layerRef.current = layer;

    return () => {
      if (viewer && !viewer.isDestroyed() && layerRef.current) {
        viewer.imageryLayers.remove(layerRef.current, false);
        layerRef.current = null;
      }
    };
  }, [visible, data]);

  return <SpoofingTimeControls visible={visible} onTimeRangeChange={handleTimeRangeChange} />;
}

/**
 * Renders spoofing points onto a canvas as a smooth gaussian heatmap.
 * Returns a canvas element that can be used as an imagery tile.
 */
function buildHeatmapCanvas(points: SpoofingPoint[]): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = CANVAS_W;
  canvas.height = CANVAS_H;
  const ctx = canvas.getContext('2d')!;

  // Build intensity grid
  const grid = new Float32Array(CANVAS_W * CANVAS_H);

  // Severity weights
  const sevWeight: Record<string, number> = {
    critical: 3,
    high: 2,
    moderate: 1,
    low: 0.5,
  };

  for (const pt of points) {
    // Map lat/lon to pixel coordinates
    const px = ((pt.lon + 180) / 360) * CANVAS_W;
    const py = ((90 - pt.lat) / 180) * CANVAS_H;
    const weight = sevWeight[pt.severity] ?? 1;

    // Apply gaussian splat
    const r = RADIUS;
    const x0 = Math.max(0, Math.floor(px - r));
    const x1 = Math.min(CANVAS_W - 1, Math.ceil(px + r));
    const y0 = Math.max(0, Math.floor(py - r));
    const y1 = Math.min(CANVAS_H - 1, Math.ceil(py + r));

    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const dx = x - px;
        const dy = y - py;
        const dist2 = dx * dx + dy * dy;
        if (dist2 > r * r) continue;
        const falloff = Math.exp(-dist2 / (2 * (r / 2.5) ** 2));
        grid[y * CANVAS_W + x] += weight * falloff;
      }
    }
  }

  // Find max intensity for normalization
  let maxVal = 0;
  for (let i = 0; i < grid.length; i++) {
    if (grid[i] > maxVal) maxVal = grid[i];
  }
  if (maxVal === 0) return canvas;

  // Render to canvas with color gradient
  const imgData = ctx.createImageData(CANVAS_W, CANVAS_H);

  for (let i = 0; i < grid.length; i++) {
    const t = Math.min(grid[i] / maxVal, 1);
    if (t < 0.01) continue; // Skip empty pixels (transparent)

    const idx = i * 4;

    // Color ramp: transparent → yellow → orange → red
    let r: number, g: number, b: number, a: number;
    if (t < 0.33) {
      // Yellow: low intensity
      const s = t / 0.33;
      r = 234; g = 179; b = 8; // #EAB308
      a = s * 120;
    } else if (t < 0.66) {
      // Orange: medium intensity
      const s = (t - 0.33) / 0.33;
      r = Math.round(234 + (249 - 234) * s);
      g = Math.round(179 + (115 - 179) * s);
      b = Math.round(8 + (22 - 8) * s);
      a = 120 + s * 60;
    } else {
      // Red: high intensity
      const s = (t - 0.66) / 0.34;
      r = Math.round(249 + (239 - 249) * s);
      g = Math.round(115 + (68 - 115) * s);
      b = Math.round(22 + (68 - 22) * s);
      a = 180 + s * 75;
    }

    imgData.data[idx] = r;
    imgData.data[idx + 1] = g;
    imgData.data[idx + 2] = b;
    imgData.data[idx + 3] = Math.round(a);
  }

  ctx.putImageData(imgData, 0, 0);
  return canvas;
}
