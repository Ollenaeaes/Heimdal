export interface AnomalyEvent {
  id: number;
  mmsi: number;
  timestamp: string;
  ruleId: string;
  severity: 'critical' | 'high' | 'moderate' | 'low';
  points: number;
  details: Record<string, unknown>;
  resolved: boolean;
}
