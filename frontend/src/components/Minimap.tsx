import { useRef, useEffect, useCallback } from 'react';
import { getCesiumViewer } from './Globe/cesiumViewer';
import { useVesselStore } from '../hooks/useVesselStore';
import { Cartesian3, Math as CesiumMath } from 'cesium';

const WIDTH = 200;
const HEIGHT = 150;

const BG_COLOR = '#0F172A';
const LAND_COLOR = '#1E293B';
const RED_DOT = '#EF4444';
const YELLOW_DOT = '#EAB308';
const VIEW_RECT_COLOR = 'rgba(255, 255, 255, 0.7)';

/**
 * Simplified continent outlines as arrays of [lon, lat] polygons.
 * These are rough shapes for a tiny 200x150 minimap — not cartographic precision.
 */
const CONTINENTS: [number, number][][] = [
  // North America
  [[-130,55],[-120,60],[-100,65],[-80,70],[-60,65],[-55,50],[-65,45],[-80,30],[-100,20],[-105,25],[-120,35],[-130,50],[-130,55]],
  // South America
  [[-80,10],[-60,10],[-35,-5],[-35,-20],[-50,-30],[-55,-35],[-70,-55],[-75,-45],[-70,-20],[-80,0],[-80,10]],
  // Europe
  [[-10,36],[0,40],[5,44],[0,48],[-5,48],[0,52],[5,55],[10,55],[15,55],[20,55],[25,55],[30,60],[30,70],[25,70],[15,68],[10,63],[5,58],[0,52],[-5,50],[-10,44],[-10,36]],
  // Africa
  [[-15,10],[-15,15],[-5,35],[10,37],[15,32],[30,32],[35,30],[40,12],[50,12],[42,0],[40,-5],[35,-15],[30,-25],[30,-35],[20,-35],[15,-28],[12,-18],[5,-5],[8,5],[0,5],[-5,5],[-15,10]],
  // Asia
  [[30,35],[35,35],[40,40],[50,40],[55,45],[60,40],[65,40],[70,35],[75,30],[80,28],[85,28],[90,22],[95,20],[100,22],[105,22],[110,20],[115,25],[120,30],[125,35],[130,40],[135,35],[140,40],[145,45],[140,50],[135,55],[130,55],[120,55],[110,50],[100,50],[90,50],[80,50],[70,55],[60,55],[55,55],[50,50],[40,45],[35,42],[30,35]],
  // Australia
  [[115,-15],[130,-12],[140,-12],[150,-15],[153,-25],[148,-35],[140,-38],[132,-35],[125,-30],[115,-22],[115,-15]],
  // Greenland
  [[-55,60],[-45,60],[-20,70],[-20,80],[-40,83],[-55,80],[-55,70],[-55,60]],
];

/** Convert longitude/latitude to canvas pixel coordinates (equirectangular). */
function lonLatToCanvas(lon: number, lat: number): [number, number] {
  const x = ((lon + 180) / 360) * WIDTH;
  const y = ((90 - lat) / 180) * HEIGHT;
  return [x, y];
}

/** Convert canvas pixel coordinates back to longitude/latitude. */
function canvasToLonLat(px: number, py: number): [number, number] {
  const lon = (px / WIDTH) * 360 - 180;
  const lat = 90 - (py / HEIGHT) * 180;
  return [lon, lat];
}

export default function Minimap() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // --- Background ---
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    // --- Land masses ---
    ctx.fillStyle = LAND_COLOR;
    for (const continent of CONTINENTS) {
      ctx.beginPath();
      const [sx, sy] = lonLatToCanvas(continent[0][0], continent[0][1]);
      ctx.moveTo(sx, sy);
      for (let i = 1; i < continent.length; i++) {
        const [cx, cy] = lonLatToCanvas(continent[i][0], continent[i][1]);
        ctx.lineTo(cx, cy);
      }
      ctx.closePath();
      ctx.fill();
    }

    // --- Vessel dots ---
    const vessels = useVesselStore.getState().vessels;
    for (const v of vessels.values()) {
      if (v.riskTier === 'green') continue;
      const [vx, vy] = lonLatToCanvas(v.lon, v.lat);
      ctx.fillStyle = v.riskTier === 'red' ? RED_DOT : YELLOW_DOT;
      ctx.fillRect(vx - 1, vy - 1, 2, 2);
    }

    // --- View extent rectangle ---
    const viewer = getCesiumViewer();
    if (viewer) {
      try {
        const rect = viewer.camera.computeViewRectangle();
        if (rect) {
          const west = CesiumMath.toDegrees(rect.west);
          const south = CesiumMath.toDegrees(rect.south);
          const east = CesiumMath.toDegrees(rect.east);
          const north = CesiumMath.toDegrees(rect.north);

          const [x1, y1] = lonLatToCanvas(west, north);
          const [x2, y2] = lonLatToCanvas(east, south);

          let rw = x2 - x1;
          let rh = y2 - y1;

          // Handle wrapping (west > east means crossing antimeridian)
          if (rw < 0) rw += WIDTH;

          // Only draw if the view is smaller than the whole world
          if (rw < WIDTH - 4 && rh < HEIGHT - 4) {
            ctx.strokeStyle = VIEW_RECT_COLOR;
            ctx.lineWidth = 1;
            ctx.strokeRect(x1, y1, rw, rh);
          }
        }
      } catch {
        // computeViewRectangle can throw in some camera states
      }
    }

    animFrameRef.current = requestAnimationFrame(draw);
  }, []);

  useEffect(() => {
    // Start after a short delay so the viewer is initialised
    const timeout = setTimeout(() => {
      animFrameRef.current = requestAnimationFrame(draw);
    }, 1000);
    return () => {
      clearTimeout(timeout);
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [draw]);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const [lon, lat] = canvasToLonLat(px, py);

    const viewer = getCesiumViewer();
    if (!viewer) return;

    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(lon, lat, 5_000_000),
      duration: 1.5,
    });
  }, []);

  return (
    <div
      className="absolute bottom-10 left-3 z-30 rounded border border-slate-700/50 overflow-hidden shadow-lg"
      style={{ width: WIDTH, height: HEIGHT }}
    >
      <canvas
        ref={canvasRef}
        width={WIDTH}
        height={HEIGHT}
        onClick={handleClick}
        className="cursor-crosshair"
      />
    </div>
  );
}
