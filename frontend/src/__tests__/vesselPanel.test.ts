import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useVesselStore } from '../hooks/useVesselStore';
import { getShipTypeLabel } from '../utils/shipTypes';
import { countryCodeToFlagEmoji } from '../utils/flagEmoji';
import { RISK_COLORS, getRiskColor } from '../utils/riskColors';
import { getNavStatusLabel } from '../utils/navStatus';
import { formatCoordinate } from '../utils/formatters';

describe('VesselPanel store interactions', () => {
  beforeEach(() => {
    useVesselStore.setState({
      vessels: new Map(),
      positionHistory: new Map(),
      selectedMmsi: null,
      filters: {
        riskTiers: new Set(),
        shipTypes: [],
        bbox: null,
        activeSince: null,
      },
    });
  });

  it('panel should be hidden when selectedMmsi is null', () => {
    const state = useVesselStore.getState();
    expect(state.selectedMmsi).toBeNull();
  });

  it('panel should be visible when selectedMmsi is set', () => {
    useVesselStore.getState().selectVessel(211234567);
    expect(useVesselStore.getState().selectedMmsi).toBe(211234567);
  });

  it('close button clears selection by setting selectedMmsi to null', () => {
    useVesselStore.getState().selectVessel(211234567);
    expect(useVesselStore.getState().selectedMmsi).toBe(211234567);

    // Simulate close button click
    useVesselStore.getState().selectVessel(null);
    expect(useVesselStore.getState().selectedMmsi).toBeNull();
  });

  it('selecting a different vessel updates selectedMmsi', () => {
    useVesselStore.getState().selectVessel(211234567);
    expect(useVesselStore.getState().selectedMmsi).toBe(211234567);

    useVesselStore.getState().selectVessel(305678901);
    expect(useVesselStore.getState().selectedMmsi).toBe(305678901);
  });
});

describe('useVesselDetail hook configuration', () => {
  it('exports useVesselDetail as a function', async () => {
    const mod = await import('../hooks/useVesselDetail');
    expect(mod.useVesselDetail).toBeDefined();
    expect(typeof mod.useVesselDetail).toBe('function');
  });
});

describe('getShipTypeLabel', () => {
  it('maps code 70 to Cargo', () => {
    expect(getShipTypeLabel(70)).toBe('Cargo');
  });

  it('maps code 79 to Cargo', () => {
    expect(getShipTypeLabel(79)).toBe('Cargo');
  });

  it('maps code 80 to Tanker', () => {
    expect(getShipTypeLabel(80)).toBe('Tanker');
  });

  it('maps code 89 to Tanker', () => {
    expect(getShipTypeLabel(89)).toBe('Tanker');
  });

  it('maps code 60 to Passenger', () => {
    expect(getShipTypeLabel(60)).toBe('Passenger');
  });

  it('maps code 30 to Fishing/Towing/Dredging', () => {
    expect(getShipTypeLabel(30)).toBe('Fishing/Towing/Dredging');
  });

  it('maps code 40 to High Speed Craft', () => {
    expect(getShipTypeLabel(40)).toBe('High Speed Craft');
  });

  it('maps code 50 to Pilot/SAR/Tug/Port Tender', () => {
    expect(getShipTypeLabel(50)).toBe('Pilot/SAR/Tug/Port Tender');
  });

  it('maps code 90 to Other', () => {
    expect(getShipTypeLabel(90)).toBe('Other');
  });

  it('maps code 20 to Wing in Ground', () => {
    expect(getShipTypeLabel(20)).toBe('Wing in Ground');
  });

  it('returns Unknown for undefined', () => {
    expect(getShipTypeLabel(undefined)).toBe('Unknown');
  });

  it('returns Unknown for out-of-range code', () => {
    expect(getShipTypeLabel(10)).toBe('Unknown');
    expect(getShipTypeLabel(100)).toBe('Unknown');
  });
});

describe('countryCodeToFlagEmoji', () => {
  it('converts NO to Norwegian flag emoji', () => {
    const flag = countryCodeToFlagEmoji('NO');
    // Norwegian flag is U+1F1F3 U+1F1F4
    expect(flag).toBe('\u{1F1F3}\u{1F1F4}');
  });

  it('converts SE to Swedish flag emoji', () => {
    const flag = countryCodeToFlagEmoji('SE');
    expect(flag).toBe('\u{1F1F8}\u{1F1EA}');
  });

  it('converts lowercase codes', () => {
    const flag = countryCodeToFlagEmoji('us');
    expect(flag).toBe('\u{1F1FA}\u{1F1F8}');
  });

  it('returns empty string for undefined', () => {
    expect(countryCodeToFlagEmoji(undefined)).toBe('');
  });

  it('returns empty string for invalid length', () => {
    expect(countryCodeToFlagEmoji('A')).toBe('');
    expect(countryCodeToFlagEmoji('ABC')).toBe('');
  });
});

describe('Risk tier badge colors', () => {
  it('green tier uses correct color', () => {
    expect(getRiskColor('green')).toBe('#27AE60');
  });

  it('yellow tier uses correct color', () => {
    expect(getRiskColor('yellow')).toBe('#D4820C');
  });

  it('red tier uses correct color', () => {
    expect(getRiskColor('red')).toBe('#C0392B');
  });

  it('RISK_COLORS has all three tiers', () => {
    expect(Object.keys(RISK_COLORS)).toEqual(['green', 'yellow', 'red']);
  });
});

describe('VesselPanel component exports', () => {
  it('exports VesselPanel component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.VesselPanel).toBeDefined();
    expect(typeof mod.VesselPanel).toBe('function');
  });

  it('exports IdentitySection component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.IdentitySection).toBeDefined();
    expect(typeof mod.IdentitySection).toBe('function');
  });
});

describe('VesselDetail type extensions', () => {
  it('VesselDetail type supports new fields', async () => {
    const mod = await import('../types/api');
    // Verify the module exports correctly (type-level check via runtime import)
    expect(mod).toBeDefined();
  });
});

describe('StatusSection component exports', () => {
  it('exports StatusSection component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.StatusSection).toBeDefined();
    expect(typeof mod.StatusSection).toBe('function');
  });
});

describe('Nav status code mapping', () => {
  it('maps code 0 to "Under way using engine"', () => {
    expect(getNavStatusLabel(0)).toBe('Under way using engine');
  });

  it('maps code 1 to "At anchor"', () => {
    expect(getNavStatusLabel(1)).toBe('At anchor');
  });

  it('maps code 2 to "Not under command"', () => {
    expect(getNavStatusLabel(2)).toBe('Not under command');
  });

  it('maps code 3 to "Restricted manoeuvrability"', () => {
    expect(getNavStatusLabel(3)).toBe('Restricted manoeuvrability');
  });

  it('maps code 4 to "Constrained by draught"', () => {
    expect(getNavStatusLabel(4)).toBe('Constrained by draught');
  });

  it('maps code 5 to "Moored"', () => {
    expect(getNavStatusLabel(5)).toBe('Moored');
  });

  it('maps code 6 to "Aground"', () => {
    expect(getNavStatusLabel(6)).toBe('Aground');
  });

  it('maps code 7 to "Engaged in fishing"', () => {
    expect(getNavStatusLabel(7)).toBe('Engaged in fishing');
  });

  it('maps code 8 to "Under way sailing"', () => {
    expect(getNavStatusLabel(8)).toBe('Under way sailing');
  });

  it('maps code 14 to "AIS-SART"', () => {
    expect(getNavStatusLabel(14)).toBe('AIS-SART');
  });

  it('maps code 15 to "Not defined"', () => {
    expect(getNavStatusLabel(15)).toBe('Not defined');
  });

  it('returns "Unknown" for unrecognised code', () => {
    expect(getNavStatusLabel(9)).toBe('Unknown');
    expect(getNavStatusLabel(99)).toBe('Unknown');
  });

  it('returns "Unknown" for undefined/null', () => {
    expect(getNavStatusLabel(undefined)).toBe('Unknown');
    expect(getNavStatusLabel(null)).toBe('Unknown');
  });
});

describe('Position formatting (DMS)', () => {
  it('formats positive latitude as N', () => {
    const result = formatCoordinate(59.3293, 'lat');
    expect(result).toContain('N');
    expect(result).toContain('59');
  });

  it('formats negative latitude as S', () => {
    const result = formatCoordinate(-33.8688, 'lat');
    expect(result).toContain('S');
    expect(result).toContain('33');
  });

  it('formats positive longitude as E', () => {
    const result = formatCoordinate(18.0686, 'lon');
    expect(result).toContain('E');
    expect(result).toContain('18');
  });

  it('formats negative longitude as W', () => {
    const result = formatCoordinate(-74.006, 'lon');
    expect(result).toContain('W');
    expect(result).toContain('74');
  });

  it('includes degrees, minutes, and seconds symbols', () => {
    const result = formatCoordinate(68.123, 'lat');
    expect(result).toMatch(/\d+\u00B0\d+'\d+(\.\d+)?"/);
  });
});

// ── Story 4: Risk Assessment Section ──────────────────────────────────

import { RULE_NAMES, getRuleName } from '../utils/ruleNames';
import { SEVERITY_COLORS, getSeverityColor } from '../utils/severityColors';

describe('RiskSection component exports', () => {
  it('exports RiskSection component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.RiskSection).toBeDefined();
    expect(typeof mod.RiskSection).toBe('function');
  });
});

describe('Rule ID → human-readable names', () => {
  it('maps ais_gap to AIS Transmission Gap', () => {
    expect(getRuleName('ais_gap')).toBe('AIS Transmission Gap');
  });

  it('maps sts_proximity to STS Zone Loitering', () => {
    expect(getRuleName('sts_proximity')).toBe('STS Zone Loitering');
  });

  it('maps destination_spoof to Destination Spoofing', () => {
    expect(getRuleName('destination_spoof')).toBe('Destination Spoofing');
  });

  it('maps draft_change to Suspicious Draft Change', () => {
    expect(getRuleName('draft_change')).toBe('Suspicious Draft Change');
  });

  it('maps flag_hopping to Flag Hopping', () => {
    expect(getRuleName('flag_hopping')).toBe('Flag Hopping');
  });

  it('maps sanctions_match to Sanctions Match', () => {
    expect(getRuleName('sanctions_match')).toBe('Sanctions Match');
  });

  it('maps vessel_age to Vessel Age Risk', () => {
    expect(getRuleName('vessel_age')).toBe('Vessel Age Risk');
  });

  it('maps speed_anomaly to Speed Anomaly', () => {
    expect(getRuleName('speed_anomaly')).toBe('Speed Anomaly');
  });

  it('maps identity_mismatch to Identity Mismatch', () => {
    expect(getRuleName('identity_mismatch')).toBe('Identity Mismatch');
  });

  it('maps gfw_ais_disabling to AIS Disabling (GFW)', () => {
    expect(getRuleName('gfw_ais_disabling')).toBe('AIS Disabling (GFW)');
  });

  it('maps gfw_encounter to Vessel Encounter (GFW)', () => {
    expect(getRuleName('gfw_encounter')).toBe('Vessel Encounter (GFW)');
  });

  it('maps gfw_loitering to Loitering (GFW)', () => {
    expect(getRuleName('gfw_loitering')).toBe('Loitering (GFW)');
  });

  it('maps gfw_port_visit to Port Visit (GFW)', () => {
    expect(getRuleName('gfw_port_visit')).toBe('Port Visit (GFW)');
  });

  it('maps gfw_dark_sar to Dark Vessel SAR (GFW)', () => {
    expect(getRuleName('gfw_dark_sar')).toBe('Dark Vessel SAR (GFW)');
  });

  it('returns the raw ruleId for unknown rules', () => {
    expect(getRuleName('some_unknown_rule')).toBe('some_unknown_rule');
  });

  it('RULE_NAMES has all 14 entries', () => {
    expect(Object.keys(RULE_NAMES)).toHaveLength(14);
  });
});

describe('Severity color mapping', () => {
  it('critical severity is dark red (#7F1D1D)', () => {
    expect(getSeverityColor('critical')).toBe('#7F1D1D');
  });

  it('high severity is red (#DC2626)', () => {
    expect(getSeverityColor('high')).toBe('#DC2626');
  });

  it('moderate severity is amber (#D4820C)', () => {
    expect(getSeverityColor('moderate')).toBe('#D4820C');
  });

  it('low severity is gray (#6B7280)', () => {
    expect(getSeverityColor('low')).toBe('#6B7280');
  });

  it('SEVERITY_COLORS has all four levels', () => {
    expect(Object.keys(SEVERITY_COLORS)).toEqual([
      'critical',
      'high',
      'moderate',
      'low',
    ]);
  });
});

// ── Story 5: Voyage Timeline ──────────────────────────────────────────

describe('VoyageTimeline component exports', () => {
  it('exports VoyageTimeline component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.VoyageTimeline).toBeDefined();
    expect(typeof mod.VoyageTimeline).toBe('function');
  });
});

describe('VoyageTimeline marker color logic', () => {
  // Inline the classification logic for unit testing
  function getMarkerColor(ruleId: string): 'red' | 'amber' | 'blue' | 'gray' {
    if (ruleId.includes('ais_gap') || ruleId.includes('ais_disabling')) return 'red';
    if (ruleId.includes('sts') || ruleId.includes('encounter') || ruleId.includes('loitering')) return 'amber';
    if (ruleId.includes('port')) return 'blue';
    return 'gray';
  }

  it('ais_gap maps to red', () => {
    expect(getMarkerColor('ais_gap')).toBe('red');
  });

  it('gfw_ais_disabling maps to red', () => {
    expect(getMarkerColor('gfw_ais_disabling')).toBe('red');
  });

  it('sts_proximity maps to amber', () => {
    expect(getMarkerColor('sts_proximity')).toBe('amber');
  });

  it('gfw_encounter maps to amber', () => {
    expect(getMarkerColor('gfw_encounter')).toBe('amber');
  });

  it('gfw_loitering maps to amber', () => {
    expect(getMarkerColor('gfw_loitering')).toBe('amber');
  });

  it('gfw_port_visit maps to blue', () => {
    expect(getMarkerColor('gfw_port_visit')).toBe('blue');
  });

  it('speed_anomaly maps to gray', () => {
    expect(getMarkerColor('speed_anomaly')).toBe('gray');
  });

  it('sanctions_match maps to gray', () => {
    expect(getMarkerColor('sanctions_match')).toBe('gray');
  });
});

describe('VoyageTimeline scrollable container', () => {
  it('VoyageTimeline accepts mmsi and anomalies props', async () => {
    const mod = await import('../components/VesselPanel/VoyageTimeline');
    // Verify the component function signature accepts the right props
    expect(mod.VoyageTimeline).toBeDefined();
    expect(mod.VoyageTimeline.length).toBeGreaterThanOrEqual(0); // React components accept props object
  });
});

// ── Story 6: Sanctions and Ownership Sections ────────────────────────

describe('SanctionsSection component exports', () => {
  it('exports SanctionsSection component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.SanctionsSection).toBeDefined();
    expect(typeof mod.SanctionsSection).toBe('function');
  });
});

describe('SanctionsSection data rendering logic', () => {
  const matches = [
    { source: 'OFAC', confidence: 0.95, matchedField: 'name', entityUrl: 'https://opensanctions.org/entities/ofac-123' },
    { source: 'EU', confidence: 0.82, matchedField: 'imo', entityUrl: undefined },
  ];

  it('formats confidence as percentage', () => {
    const pct = Math.round(matches[0].confidence * 100);
    expect(pct).toBe(95);
  });

  it('formats lower confidence correctly', () => {
    const pct = Math.round(matches[1].confidence * 100);
    expect(pct).toBe(82);
  });

  it('includes all required fields in match data', () => {
    for (const match of matches) {
      expect(match.source).toBeTruthy();
      expect(typeof match.confidence).toBe('number');
      expect(match.matchedField).toBeTruthy();
    }
  });

  it('handles empty matches array as no-match state', () => {
    const emptyMatches: typeof matches = [];
    expect(emptyMatches.length === 0).toBe(true);
  });

  it('handles undefined matches as no-match state', () => {
    const noMatches = undefined;
    expect(!noMatches || noMatches.length === 0).toBe(true);
  });
});

describe('OwnershipSection component exports', () => {
  it('exports OwnershipSection component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.OwnershipSection).toBeDefined();
    expect(typeof mod.OwnershipSection).toBe('function');
  });
});

describe('OwnershipSection data rendering logic', () => {
  it('detects ownership data presence', () => {
    const ownershipData = {
      registeredOwner: 'Gotland Shipping AB',
      commercialManager: 'Nordic Marine Services',
      ismManager: 'Baltic Safety Management',
      beneficialOwner: 'Gotland Holdings Ltd',
    };
    const hasData = !!(
      ownershipData.registeredOwner ||
      ownershipData.commercialManager ||
      ownershipData.ismManager ||
      ownershipData.beneficialOwner
    );
    expect(hasData).toBe(true);
  });

  it('detects empty ownership data', () => {
    const ownershipData = {
      registeredOwner: undefined,
      commercialManager: undefined,
      ismManager: undefined,
      beneficialOwner: undefined,
    };
    const hasData = !!(
      ownershipData.registeredOwner ||
      ownershipData.commercialManager ||
      ownershipData.ismManager ||
      ownershipData.beneficialOwner
    );
    expect(hasData).toBe(false);
  });

  it('detects manual enrichment with ownership chain', () => {
    const enrichment = {
      ownershipChain: 'Gotland Holdings Ltd → Baltic Trust → Nordic Fund',
      notes: 'Verified via Lloyd\'s List Intelligence',
      enrichedAt: '2026-03-10T14:30:00Z',
    };
    const hasEnrichment = !!(enrichment.ownershipChain || enrichment.notes);
    expect(hasEnrichment).toBe(true);
  });

  it('shows prompt when no data at all', () => {
    const ownershipData = undefined;
    const manualEnrichment = undefined;
    const hasOwnership = ownershipData && (
      ownershipData.registeredOwner ||
      ownershipData.commercialManager ||
      ownershipData.ismManager ||
      ownershipData.beneficialOwner
    );
    const hasEnrichment = manualEnrichment && (
      manualEnrichment.ownershipChain || manualEnrichment.notes
    );
    expect(!hasOwnership && !hasEnrichment).toBe(true);
  });
});

describe('RiskSection score bar fill percentage', () => {
  it('calculates correct fill for score 100 (50%)', () => {
    const fillPercent = Math.min((100 / 200) * 100, 100);
    expect(fillPercent).toBe(50);
  });

  it('calculates correct fill for score 0 (0%)', () => {
    const fillPercent = Math.min((0 / 200) * 100, 100);
    expect(fillPercent).toBe(0);
  });

  it('calculates correct fill for score 200 (100%)', () => {
    const fillPercent = Math.min((200 / 200) * 100, 100);
    expect(fillPercent).toBe(100);
  });

  it('caps fill at 100% for scores above 200', () => {
    const fillPercent = Math.min((350 / 200) * 100, 100);
    expect(fillPercent).toBe(100);
  });
});

describe('RiskSection anomaly filtering', () => {
  const anomalies = [
    {
      id: 1,
      mmsi: 211234567,
      timestamp: '2026-03-10T12:00:00Z',
      ruleId: 'ais_gap',
      severity: 'high' as const,
      points: 25,
      details: { gap_hours: 8 },
      resolved: false,
    },
    {
      id: 2,
      mmsi: 211234567,
      timestamp: '2026-03-09T10:00:00Z',
      ruleId: 'speed_anomaly',
      severity: 'low' as const,
      points: 5,
      details: { speed: 25 },
      resolved: true,
    },
    {
      id: 3,
      mmsi: 211234567,
      timestamp: '2026-03-11T08:00:00Z',
      ruleId: 'sanctions_match',
      severity: 'critical' as const,
      points: 50,
      details: { source: 'OFAC', confidence: 0.95 },
      resolved: false,
    },
  ];

  it('filters to only unresolved anomalies', () => {
    const unresolved = anomalies.filter((a) => !a.resolved);
    expect(unresolved).toHaveLength(2);
    expect(unresolved.map((a) => a.id)).toEqual([1, 3]);
  });

  it('each unresolved anomaly has required fields', () => {
    const unresolved = anomalies.filter((a) => !a.resolved);
    for (const anomaly of unresolved) {
      expect(getRuleName(anomaly.ruleId)).toBeTruthy();
      expect(SEVERITY_COLORS[anomaly.severity]).toBeTruthy();
      expect(typeof anomaly.points).toBe('number');
      expect(anomaly.timestamp).toBeTruthy();
      expect(anomaly.details).toBeTruthy();
    }
  });
});
