export const SEVERITY_COLORS = {
  critical: '#7F1D1D',
  high: '#DC2626',
  moderate: '#D4820C',
  low: '#6B7280',
} as const;

export type Severity = keyof typeof SEVERITY_COLORS;

export function getSeverityColor(severity: Severity): string {
  return SEVERITY_COLORS[severity];
}
