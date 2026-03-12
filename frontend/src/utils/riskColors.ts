export const RISK_COLORS = {
  green: '#27AE60', // subdued green
  yellow: '#D4820C', // amber/orange
  red: '#C0392B', // danger red
} as const;

export type RiskTier = keyof typeof RISK_COLORS;

export function getRiskColor(tier: RiskTier): string {
  return RISK_COLORS[tier];
}
