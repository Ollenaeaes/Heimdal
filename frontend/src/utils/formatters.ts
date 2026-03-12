import { formatDistanceToNow, parseISO } from 'date-fns';

/**
 * Convert decimal degrees to DMS format.
 * e.g., 68.1230 lat -> 68 07'22.8"N
 */
export function formatCoordinate(
  value: number,
  type: 'lat' | 'lon'
): string {
  const absolute = Math.abs(value);
  const degrees = Math.floor(absolute);
  const minutesDecimal = (absolute - degrees) * 60;
  const minutes = Math.floor(minutesDecimal);
  const seconds = (minutesDecimal - minutes) * 60;

  let direction: string;
  if (type === 'lat') {
    direction = value >= 0 ? 'N' : 'S';
  } else {
    direction = value >= 0 ? 'E' : 'W';
  }

  return `${degrees}\u00B0${minutes.toString().padStart(2, '0')}'${seconds.toFixed(1).padStart(4, '0')}"${direction}`;
}

/**
 * Format speed in knots, e.g., "12.3 kn" or "N/A"
 */
export function formatSpeed(knots: number | null): string {
  if (knots === null || knots === undefined) return 'N/A';
  return `${knots.toFixed(1)} kn`;
}

/**
 * Format course in degrees, e.g., "180.5 " or "N/A"
 */
export function formatCourse(degrees: number | null): string {
  if (degrees === null || degrees === undefined) return 'N/A';
  return `${degrees.toFixed(1)}\u00B0`;
}

/**
 * Format timestamp as relative, e.g., "3 min ago"
 */
export function formatTimestamp(iso: string): string {
  return formatDistanceToNow(parseISO(iso), { addSuffix: true });
}

/**
 * Format timestamp as absolute UTC, e.g., "2024-03-15 14:30:00 UTC"
 */
export function formatTimestampAbsolute(iso: string): string {
  const date = parseISO(iso);
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, '0');
  const d = String(date.getUTCDate()).padStart(2, '0');
  const hh = String(date.getUTCHours()).padStart(2, '0');
  const mm = String(date.getUTCMinutes()).padStart(2, '0');
  const ss = String(date.getUTCSeconds()).padStart(2, '0');
  return `${y}-${m}-${d} ${hh}:${mm}:${ss} UTC`;
}
