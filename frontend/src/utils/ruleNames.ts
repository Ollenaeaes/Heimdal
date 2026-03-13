export const RULE_NAMES: Record<string, string> = {
  ais_gap: 'AIS Transmission Gap',
  sts_proximity: 'STS Zone Loitering',
  destination_spoof: 'Destination Spoofing',
  draft_change: 'Suspicious Draft Change',
  flag_hopping: 'Flag Hopping',
  sanctions_match: 'Sanctions Match',
  vessel_age: 'Vessel Age Risk',
  speed_anomaly: 'Speed Anomaly',
  identity_mismatch: 'Identity Mismatch',
  gfw_ais_disabling: 'AIS Disabling (GFW)',
  gfw_encounter: 'Vessel Encounter (GFW)',
  gfw_loitering: 'Loitering (GFW)',
  gfw_port_visit: 'Port Visit (GFW)',
  flag_of_convenience: 'Flag of Convenience',
  gfw_dark_sar: 'Dark Vessel SAR (GFW)',
} as const;

export function getRuleName(ruleId: string): string {
  return RULE_NAMES[ruleId] ?? ruleId;
}
