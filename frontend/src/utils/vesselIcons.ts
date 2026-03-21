import { RISK_COLORS, type RiskTier } from './riskColors';

/**
 * Vessel icon generation for MapLibre.
 *
 * Three icon types:
 * 1. Arrow — small directional chevron for moving vessels at medium zoom
 * 2. Hull — ship-shaped polygon for port-level zoom, proportioned by AIS dimensions
 * 3. Dot — simple circle for stationary vessels (handled by circle layer, no icon needed)
 *
 * All icons point north (0°). MapLibre rotates them via icon-rotate using HEADING.
 */

const ARROW_SIZE = 24;
const HULL_SIZE = 64; // larger canvas for detailed hull

/** MapLibre-compatible image data format. */
interface MapImage {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

/** Generate a small directional arrow/chevron icon. Points north. */
function drawArrowIcon(color: string): MapImage {
  const size = ARROW_SIZE;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;

  const cx = size / 2;

  // Arrow chevron — narrow, directional, points up (north)
  ctx.beginPath();
  ctx.moveTo(cx, 2);                    // tip (bow)
  ctx.lineTo(size - 4, size * 0.75);    // right wing
  ctx.lineTo(cx, size * 0.55);          // notch
  ctx.lineTo(4, size * 0.75);           // left wing
  ctx.closePath();

  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 0.8;
  ctx.stroke();

  const imageData = ctx.getImageData(0, 0, size, size);
  return { width: size, height: size, data: imageData.data };
}

/**
 * Draw a ship hull icon. Points north (bow at top).
 * The hull is drawn with a realistic ship shape:
 * - Pointed bow
 * - Parallel sides
 * - Squared stern
 * - Bridge dot near stern
 */
function drawHullIcon(color: string): MapImage {
  const size = HULL_SIZE;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;

  const cx = size / 2;
  const bowY = 2;
  const sternY = size - 3;
  const hullLen = sternY - bowY;
  // Realistic L:B ratio ~5.5:1 — beam is narrow relative to length
  const beamHalf = hullLen / 11; // full beam = hullLen/5.5
  const shoulderY = bowY + hullLen * 0.15; // bow taper region
  const sternNotchY = sternY - hullLen * 0.03; // slight stern taper

  // Hull shape — elongated with proper ship proportions
  ctx.beginPath();
  ctx.moveTo(cx, bowY);                              // bow tip
  // Bow curves — smooth taper using quadratic curves
  ctx.quadraticCurveTo(cx + beamHalf * 0.4, bowY + (shoulderY - bowY) * 0.3,
                       cx + beamHalf, shoulderY);     // right bow curve
  ctx.lineTo(cx + beamHalf, sternNotchY);             // right side
  ctx.lineTo(cx + beamHalf * 0.85, sternY);           // right stern taper
  ctx.lineTo(cx - beamHalf * 0.85, sternY);           // stern
  ctx.lineTo(cx - beamHalf, sternNotchY);             // left stern taper
  ctx.lineTo(cx - beamHalf, shoulderY);               // left side
  ctx.quadraticCurveTo(cx - beamHalf * 0.4, bowY + (shoulderY - bowY) * 0.3,
                       cx, bowY);                     // left bow curve
  ctx.closePath();

  ctx.fillStyle = color;
  ctx.globalAlpha = 0.85;
  ctx.fill();
  ctx.globalAlpha = 1.0;
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 0.8;
  ctx.stroke();

  // Bridge/superstructure block (near stern, ~70% down the hull)
  const bridgeY = bowY + hullLen * 0.68;
  const bridgeH = hullLen * 0.08;
  const bridgeW = beamHalf * 1.2;
  ctx.fillStyle = 'rgba(255,255,255,0.25)';
  ctx.fillRect(cx - bridgeW / 2, bridgeY, bridgeW, bridgeH);

  // Bridge dot
  ctx.beginPath();
  ctx.arc(cx, bridgeY + bridgeH / 2, 1.5, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.fill();

  const imageData = ctx.getImageData(0, 0, size, size);
  return { width: size, height: size, data: imageData.data };
}

export type IconKey = `arrow-${RiskTier}` | `hull-${RiskTier}`;

const tiers: RiskTier[] = ['green', 'yellow', 'red', 'blacklisted'];

/**
 * Register all vessel icons into a MapLibre map instance.
 * Call this once after the map loads.
 */
export function registerVesselIcons(map: maplibregl.Map): void {
  for (const tier of tiers) {
    const color = RISK_COLORS[tier];

    const arrowKey: IconKey = `arrow-${tier}`;
    if (!map.hasImage(arrowKey)) {
      const arrowData = drawArrowIcon(color);
      map.addImage(arrowKey, arrowData);
    }

    const hullKey: IconKey = `hull-${tier}`;
    if (!map.hasImage(hullKey)) {
      const hullData = drawHullIcon(color);
      map.addImage(hullKey, hullData);
    }
  }
}

export { ARROW_SIZE, HULL_SIZE };
