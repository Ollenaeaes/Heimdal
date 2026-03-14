import { RISK_COLORS, type RiskTier } from './riskColors';

/** Size of the generated vessel icon canvas (px). */
const ICON_SIZE = 24;

/**
 * Marker visual properties per risk tier.
 * Per visual theme spec: progressive disclosure with zoom-dependent opacity.
 *
 * Green: subdued at all zoom levels (0.2 overview → 0.7 port zoom)
 * Yellow: visible at all zoom levels (0.8)
 * Red: always full opacity, 1.5x scale
 */
export const MARKER_STYLE: Record<
  RiskTier,
  { opacity: number; opacityFar: number; scale: number }
> = {
  green: { opacity: 0.7, opacityFar: 0.2, scale: 0.5 },
  yellow: { opacity: 0.8, opacityFar: 0.8, scale: 0.7 },
  red: { opacity: 1.0, opacityFar: 1.0, scale: 0.85 },
};

/**
 * Convert COG (degrees, clockwise from north) to Cesium billboard rotation
 * (radians, counter-clockwise).
 */
export function cogToRotation(cogDeg: number | null): number {
  if (cogDeg == null) return 0;
  return -cogDeg * (Math.PI / 180);
}

/**
 * Draw a clean, minimal vessel chevron on a canvas and return the data URL.
 * No glow, no pulsing — just the shape with a thin outline.
 * Points upward (north) so billboard rotation aligns with COG.
 */
function drawVesselIcon(color: string): string {
  const size = ICON_SIZE;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;

  const cx = size / 2;

  // Clean chevron — narrow, directional
  ctx.beginPath();
  ctx.moveTo(cx, 1);                    // bow tip
  ctx.lineTo(size - 3, size * 0.7);     // right wing
  ctx.lineTo(cx, size * 0.5);           // stern notch
  ctx.lineTo(3, size * 0.7);            // left wing
  ctx.closePath();

  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.6)';
  ctx.lineWidth = 0.8;
  ctx.stroke();

  return canvas.toDataURL('image/png');
}

/** Cache generated icon data URLs per risk tier. */
const iconCache = new Map<RiskTier, string>();

/**
 * Get (or generate) a vessel icon data URL for the given risk tier.
 */
export function getVesselIcon(tier: RiskTier): string {
  let url = iconCache.get(tier);
  if (!url) {
    url = drawVesselIcon(RISK_COLORS[tier]);
    iconCache.set(tier, url);
  }
  return url;
}
