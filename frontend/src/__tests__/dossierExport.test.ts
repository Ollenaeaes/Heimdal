import { describe, it, expect, vi, beforeEach } from 'vitest';
import { buildDossier, buildFilename } from '../components/VesselPanel/DossierExport';
import type { VesselDetail, TrackPoint, GfwEvent } from '../types/api';

// ─── Story 3: Vessel Dossier Export ────────────────────────────────

const mockVessel: VesselDetail = {
  mmsi: 259000340,
  imo: 9876543,
  name: 'NORDIC EXPLORER',
  shipType: 80,
  shipTypeText: 'Tanker',
  flagCountry: 'NO',
  callSign: 'LHSV',
  length: 228,
  width: 36,
  draught: 12.5,
  destination: 'ROTTERDAM',
  riskScore: 145,
  riskTier: 'red',
  owner: 'Nordic Tankers AS',
  operator: 'Scandinavian Shipping Management',
  yearBuilt: 2008,
  anomalies: [
    {
      id: 101,
      mmsi: 259000340,
      timestamp: '2026-03-10T14:30:00Z',
      ruleId: 'ais_gap',
      severity: 'high',
      points: 25,
      details: { gap_hours: 8.5, lat: 69.2, lon: 14.8 },
      resolved: false,
    },
    {
      id: 102,
      mmsi: 259000340,
      timestamp: '2026-03-09T08:15:00Z',
      ruleId: 'sts_proximity',
      severity: 'moderate',
      points: 15,
      details: { zone_name: 'Murmansk STS', distance_nm: 2.3 },
      resolved: false,
    },
  ],
  sanctionsMatches: [
    { source: 'OFAC', confidence: 0.92, matchedField: 'imo', entityUrl: 'https://opensanctions.org/entities/ofac-456' },
  ],
  ownershipData: {
    registeredOwner: 'Nordic Tankers AS',
    commercialManager: 'Scandinavian Shipping Management',
    ismManager: 'Nordic Safety Services',
    beneficialOwner: 'Nordic Maritime Holdings Ltd',
  },
  manualEnrichment: {
    ownershipChain: 'Nordic Maritime Holdings Ltd -> Baltic Trust -> Gotland Fund',
    notes: 'Verified via Lloyd\'s List Intelligence database',
    enrichedAt: '2026-03-08T10:00:00Z',
  },
  manualEnrichments: [
    {
      id: 1,
      source: 'Lloyd\'s List Intelligence',
      analystNotes: 'Ownership chain confirmed through corporate registry filings',
      piTier: 'ig_member',
      createdAt: '2026-03-08T10:00:00Z',
    },
  ],
};

const mockTrack: TrackPoint[] = [
  { timestamp: '2026-03-10T00:00:00Z', lat: 68.0, lon: 15.0, sog: 12.3, cog: 180.5, heading: 179 },
  { timestamp: '2026-03-10T01:00:00Z', lat: 68.05, lon: 15.05, sog: 11.8, cog: 182.0, heading: 181 },
  { timestamp: '2026-03-10T02:00:00Z', lat: 68.1, lon: 15.1, sog: 12.0, cog: 179.5, heading: 180 },
];

const mockGfwEvents: GfwEvent[] = [
  {
    id: 'gfw-001',
    type: 'ENCOUNTER',
    startTime: '2026-03-09T15:00:00Z',
    endTime: '2026-03-09T17:30:00Z',
    lat: 69.1,
    lon: 14.5,
    vesselMmsi: 259000340,
    vesselName: 'NORDIC EXPLORER',
    encounterPartnerMmsi: 273456789,
    encounterPartnerName: 'VOLGA TANKER',
    portName: null,
    durationHours: 2.5,
  },
  {
    id: 'gfw-002',
    type: 'LOITERING',
    startTime: '2026-03-08T10:00:00Z',
    endTime: '2026-03-08T18:00:00Z',
    lat: 69.3,
    lon: 33.1,
    vesselMmsi: 259000340,
    vesselName: 'NORDIC EXPLORER',
    encounterPartnerMmsi: null,
    encounterPartnerName: null,
    portName: null,
    durationHours: 8.0,
  },
];

describe('buildDossier', () => {
  it('builds complete dossier with all sections', () => {
    const dossier = buildDossier(mockVessel, mockTrack, mockGfwEvents);

    expect(dossier.exportedAt).toBeTruthy();
    expect(dossier.vessel.mmsi).toBe(259000340);
    expect(dossier.vessel.name).toBe('NORDIC EXPLORER');
    expect(dossier.vessel.flagCountry).toBe('NO');
    expect(dossier.vessel.shipType).toBe(80);
  });

  it('includes risk assessment with anomalies', () => {
    const dossier = buildDossier(mockVessel, mockTrack, mockGfwEvents);

    expect(dossier.riskAssessment.riskScore).toBe(145);
    expect(dossier.riskAssessment.riskTier).toBe('red');
    expect(dossier.riskAssessment.anomalies).toHaveLength(2);
  });

  it('includes sanctions matches', () => {
    const dossier = buildDossier(mockVessel, mockTrack, mockGfwEvents);

    expect(dossier.sanctions).toHaveLength(1);
    expect(dossier.sanctions![0].source).toBe('OFAC');
    expect(dossier.sanctions![0].confidence).toBe(0.92);
  });

  it('includes ownership data', () => {
    const dossier = buildDossier(mockVessel, mockTrack, mockGfwEvents);

    expect(dossier.ownership).toBeDefined();
    expect(dossier.ownership!.registeredOwner).toBe('Nordic Tankers AS');
    expect(dossier.ownership!.beneficialOwner).toBe('Nordic Maritime Holdings Ltd');
  });

  it('includes enrichment data', () => {
    const dossier = buildDossier(mockVessel, mockTrack, mockGfwEvents);

    expect(dossier.enrichment.manual).toBeDefined();
    expect(dossier.enrichment.manual!.ownershipChain).toContain('Nordic Maritime Holdings');
    expect(dossier.enrichment.history).toHaveLength(1);
  });

  it('includes GFW events', () => {
    const dossier = buildDossier(mockVessel, mockTrack, mockGfwEvents);

    expect(dossier.gfwEvents).toHaveLength(2);
    expect(dossier.gfwEvents[0].type).toBe('ENCOUNTER');
    expect(dossier.gfwEvents[1].type).toBe('LOITERING');
  });

  it('includes recent track', () => {
    const dossier = buildDossier(mockVessel, mockTrack, mockGfwEvents);

    expect(dossier.recentTrack).toHaveLength(3);
    expect(dossier.recentTrack[0].lat).toBe(68.0);
  });

  it('produces valid JSON string', () => {
    const dossier = buildDossier(mockVessel, mockTrack, mockGfwEvents);
    const json = JSON.stringify(dossier, null, 2);
    const parsed = JSON.parse(json);

    expect(parsed.vessel.mmsi).toBe(259000340);
    expect(parsed.riskAssessment.riskScore).toBe(145);
    expect(parsed.gfwEvents).toHaveLength(2);
  });
});

describe('buildDossier with empty/missing data', () => {
  const minimalVessel: VesselDetail = {
    mmsi: 211234567,
    riskScore: 0,
    riskTier: 'green',
  };

  it('handles vessel with no optional fields', () => {
    const dossier = buildDossier(minimalVessel, [], []);

    expect(dossier.vessel.mmsi).toBe(211234567);
    expect(dossier.vessel.name).toBeUndefined();
    expect(dossier.vessel.imo).toBeUndefined();
    expect(dossier.riskAssessment.anomalies).toEqual([]);
    expect(dossier.sanctions).toEqual([]);
    expect(dossier.ownership).toEqual({});
    expect(dossier.gfwEvents).toEqual([]);
    expect(dossier.recentTrack).toEqual([]);
  });

  it('enrichment section handles missing data gracefully', () => {
    const dossier = buildDossier(minimalVessel, [], []);

    expect(dossier.enrichment.manual).toBeUndefined();
    expect(dossier.enrichment.history).toEqual([]);
  });
});

describe('buildFilename', () => {
  it('generates correct filename format', () => {
    const filename = buildFilename(259000340);
    expect(filename).toMatch(/^heimdal-dossier-259000340-\d{4}-\d{2}-\d{2}\.json$/);
  });

  it('includes mmsi in filename', () => {
    const filename = buildFilename(211234567);
    expect(filename).toContain('211234567');
  });

  it('includes current date in filename', () => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    const filename = buildFilename(259000340);
    expect(filename).toContain(`${y}-${m}-${d}`);
  });

  it('has .json extension', () => {
    const filename = buildFilename(259000340);
    expect(filename.endsWith('.json')).toBe(true);
  });
});

describe('DossierExport component exports', () => {
  it('exports DossierExport component', async () => {
    const mod = await import('../components/VesselPanel/DossierExport');
    expect(mod.DossierExport).toBeDefined();
    expect(typeof mod.DossierExport).toBe('function');
  });

  it('exports buildDossier function', async () => {
    const mod = await import('../components/VesselPanel/DossierExport');
    expect(mod.buildDossier).toBeDefined();
    expect(typeof mod.buildDossier).toBe('function');
  });

  it('exports buildFilename function', async () => {
    const mod = await import('../components/VesselPanel/DossierExport');
    expect(mod.buildFilename).toBeDefined();
    expect(typeof mod.buildFilename).toBe('function');
  });
});
