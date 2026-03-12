import type { GfwEventType } from '../types/api';

/** Size of the generated event icon canvas (px). */
const ICON_SIZE = 24;

/** Colors for GFW event types */
export const GFW_EVENT_COLORS: Record<GfwEventType, string> = {
  ENCOUNTER: '#E67E22',    // orange
  LOITERING: '#F1C40F',    // yellow
  AIS_DISABLING: '#C0392B', // red
  PORT_VISIT: '#3498DB',   // blue
};

/** SAR marker colors */
export const SAR_DARK_COLOR = '#FFFFFF';
export const SAR_DARK_BORDER = '#C0392B';
export const SAR_MATCHED_COLOR = '#888888';

/**
 * Draw a diamond shape on canvas. Used for ENCOUNTER events.
 */
function drawDiamond(ctx: CanvasRenderingContext2D, size: number, color: string): void {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy - r);        // top
  ctx.lineTo(cx + r, cy);        // right
  ctx.lineTo(cx, cy + r);        // bottom
  ctx.lineTo(cx - r, cy);        // left
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

/**
 * Draw a circle shape on canvas. Used for LOITERING events.
 */
function drawCircle(ctx: CanvasRenderingContext2D, size: number, color: string): void {
  const cx = size / 2;
  const cy = size / 2;
  ctx.beginPath();
  ctx.arc(cx, cy, size / 2 - 2, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

/**
 * Draw a triangle shape on canvas. Used for AIS_DISABLING events.
 */
function drawTriangle(ctx: CanvasRenderingContext2D, size: number, color: string): void {
  const cx = size / 2;
  ctx.beginPath();
  ctx.moveTo(cx, 2);                      // top
  ctx.lineTo(size - 2, size - 2);         // bottom-right
  ctx.lineTo(2, size - 2);                // bottom-left
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

/**
 * Draw a square shape on canvas. Used for PORT_VISIT events.
 */
function drawSquare(ctx: CanvasRenderingContext2D, size: number, color: string): void {
  const margin = 2;
  ctx.fillStyle = color;
  ctx.fillRect(margin, margin, size - margin * 2, size - margin * 2);
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 1.5;
  ctx.strokeRect(margin, margin, size - margin * 2, size - margin * 2);
}

const GFW_DRAW_FNS: Record<GfwEventType, (ctx: CanvasRenderingContext2D, size: number, color: string) => void> = {
  ENCOUNTER: drawDiamond,
  LOITERING: drawCircle,
  AIS_DISABLING: drawTriangle,
  PORT_VISIT: drawSquare,
};

/** Cache for generated GFW event icons */
const gfwIconCache = new Map<GfwEventType, string>();

/**
 * Get (or generate) a GFW event icon data URL for the given event type.
 */
export function getGfwEventIcon(eventType: GfwEventType): string {
  let url = gfwIconCache.get(eventType);
  if (!url) {
    const canvas = document.createElement('canvas');
    canvas.width = ICON_SIZE;
    canvas.height = ICON_SIZE;
    const ctx = canvas.getContext('2d')!;
    GFW_DRAW_FNS[eventType](ctx, ICON_SIZE, GFW_EVENT_COLORS[eventType]);
    url = canvas.toDataURL('image/png');
    gfwIconCache.set(eventType, url);
  }
  return url;
}

/** Cache for SAR detection icons */
const sarIconCache = new Map<string, string>();

/**
 * Draw a SAR detection marker. Dark ships get a white circle with red border;
 * matched detections get a smaller gray circle.
 */
export function getSarIcon(isDark: boolean): string {
  const key = isDark ? 'dark' : 'matched';
  let url = sarIconCache.get(key);
  if (!url) {
    const size = isDark ? ICON_SIZE : 16;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d')!;
    const cx = size / 2;

    ctx.beginPath();
    ctx.arc(cx, cx, size / 2 - 2, 0, 2 * Math.PI);
    ctx.fillStyle = isDark ? SAR_DARK_COLOR : SAR_MATCHED_COLOR;
    ctx.fill();
    ctx.strokeStyle = isDark ? SAR_DARK_BORDER : 'rgba(255,255,255,0.5)';
    ctx.lineWidth = isDark ? 2.5 : 1;
    ctx.stroke();

    url = canvas.toDataURL('image/png');
    sarIconCache.set(key, url);
  }
  return url;
}
