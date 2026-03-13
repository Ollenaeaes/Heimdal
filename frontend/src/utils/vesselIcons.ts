import { RISK_COLORS, type RiskTier } from './riskColors';

/** Size of the generated vessel icon canvas (px). */
const ICON_SIZE = 32;
/** Larger canvas for high-risk icons with glow. */
const ICON_SIZE_GLOW = 48;

/**
 * Marker visual properties per risk tier.
 * Used by VesselMarkers for billboard rendering.
 */
export const MARKER_STYLE: Record<
  RiskTier,
  { opacity: number; scale: number }
> = {
  green: { opacity: 0.35, scale: 0.5 },
  yellow: { opacity: 1.0, scale: 1.0 },
  red: { opacity: 1.0, scale: 1.2 },
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
 * naturally with COG. High-risk vessels get a glow ring for visibility.
 */
function drawVesselIcon(color: string, glow: boolean): string {
  const size = glow ? ICON_SIZE_GLOW : ICON_SIZE;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;

  const cx = size / 2;
  // Offset so the triangle is centered in the larger glow canvas
  const pad = glow ? (ICON_SIZE_GLOW - ICON_SIZE) / 2 : 0;

  if (glow) {
    // Draw glow ring behind the icon
    ctx.beginPath();
    ctx.arc(cx, cx, size / 2 - 2, 0, Math.PI * 2);
    ctx.fillStyle = color + '30'; // ~19% opacity fill
    ctx.fill();
    ctx.strokeStyle = color + '80'; // ~50% opacity ring
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // Arrow / triangular ship shape pointing up
  ctx.beginPath();
  ctx.moveTo(cx, pad + 2); // top (bow)
  ctx.lineTo(pad + ICON_SIZE - 4, pad + ICON_SIZE - 4); // bottom-right
  ctx.lineTo(cx, pad + ICON_SIZE - 8); // notch
  ctx.lineTo(pad + 4, pad + ICON_SIZE - 4); // bottom-left
  ctx.closePath();

  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = glow ? 1.5 : 1;
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
    const glow = tier === 'red' || tier === 'yellow';
    url = drawVesselIcon(RISK_COLORS[tier], glow);
    iconCache.set(tier, url);
  }
  return url;
}
