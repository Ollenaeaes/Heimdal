const NAV_STATUS_LABELS: Record<number, string> = {
  0: 'Under way using engine',
  1: 'At anchor',
  2: 'Not under command',
  3: 'Restricted manoeuvrability',
  4: 'Constrained by draught',
  5: 'Moored',
  6: 'Aground',
  7: 'Engaged in fishing',
  8: 'Under way sailing',
  14: 'AIS-SART',
  15: 'Not defined',
};

/**
 * Map AIS navigational status code to a human-readable label.
 * Returns "Unknown" for unrecognised codes.
 */
export function getNavStatusLabel(code: number | undefined | null): string {
  if (code === undefined || code === null) return 'Unknown';
  return NAV_STATUS_LABELS[code] ?? 'Unknown';
}
