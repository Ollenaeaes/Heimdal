import { RISK_COLORS, type RiskTier } from './riskColors';

/** Size of the generated vessel icon canvas (px). */
const ICON_SIZE = 32;

/**
 * Marker visual properties per risk tier.
 * Used by VesselMarkers for billboard rendering.
 */
export const MARKER_STYLE: Record<
  RiskTier,
  { opacity: number; scale: number }
> = {
  green: { opacity: 0.4, scale: 0.6 },
  yellow: { opacity: 0.9, scale: 0.8 },
  red: { opacity: 1.0, scale: 1.0 },
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
 * Draw a triangular vessel shape on a canvas and return the data URL.
 * The triangle points upward (north) so that billboard rotation aligns
 * naturally with COG.
 */
function drawVesselIcon(color: string): string {
  const canvas = document.createElement('canvas');
  canvas.width = ICON_SIZE;
  canvas.height = ICON_SIZE;
  const ctx = canvas.getContext('2d')!;

  const cx = ICON_SIZE / 2;

  // Arrow / triangular ship shape pointing up
  ctx.beginPath();
  ctx.moveTo(cx, 2); // top (bow)
  ctx.lineTo(ICON_SIZE - 4, ICON_SIZE - 4); // bottom-right
  ctx.lineTo(cx, ICON_SIZE - 8); // notch
  ctx.lineTo(4, ICON_SIZE - 4); // bottom-left
  ctx.closePath();

  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.6)';
  ctx.lineWidth = 1;
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
