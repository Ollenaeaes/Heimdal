export const RISK_COLORS = {
  green: '#22C55E',
  yellow: '#F59E0B',
  red: '#EF4444',
} as const;

export type RiskTier = keyof typeof RISK_COLORS;

export function getRiskColor(tier: RiskTier): string {
  return RISK_COLORS[tier];
}
