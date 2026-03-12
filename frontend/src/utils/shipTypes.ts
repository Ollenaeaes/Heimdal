/** Maps AIS ship type codes to human-readable labels. */
const SHIP_TYPE_RANGES: [number, number, string][] = [
  [20, 29, 'Wing in Ground'],
  [30, 35, 'Fishing/Towing/Dredging'],
  [36, 39, 'Sailing/Pleasure'],
  [40, 49, 'High Speed Craft'],
  [50, 59, 'Pilot/SAR/Tug/Port Tender'],
  [60, 69, 'Passenger'],
  [70, 79, 'Cargo'],
  [80, 89, 'Tanker'],
  [90, 99, 'Other'],
];

export function getShipTypeLabel(code: number | undefined): string {
  if (code === undefined || code === null) return 'Unknown';
  for (const [min, max, label] of SHIP_TYPE_RANGES) {
    if (code >= min && code <= max) return label;
  }
  return 'Unknown';
}
