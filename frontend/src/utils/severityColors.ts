export const SEVERITY_COLORS = {
  critical: '#991B1B',
  high: '#DC2626',
  moderate: '#F59E0B',
  low: '#6B7280',
} as const;

export type Severity = keyof typeof SEVERITY_COLORS;

export function getSeverityColor(severity: Severity): string {
  return SEVERITY_COLORS[severity];
}
