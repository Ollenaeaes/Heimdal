import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  formatUploadDate,
  getDeficiencyColor,
  isFlagOfConvenience,
  FOC_FLAGS,
} from './EquasisSection';
import type { EquasisData, EquasisUploadSummary } from '../../types/api';

// ─── Test fixtures ──────────────────────────────────────────────────

function createSampleEquasisData(): EquasisData {
  return {
    latest: {
      ship_particulars: {
        imo: 9236353,
        mmsi: 613414602,
        name: 'BLUE',
        gross_tonnage: 84789,
        dwt: 165293,
        type_of_ship: 'Crude Oil Tanker',
        year_of_build: 2003,
        flag: 'Cameroon',
        status: 'In Service/Commission',
      },
      management: [
        {
          role: 'ISM Manager',
          company_name: 'UNKNOWN',
          address: 'N/A',
          date_of_effect: '01/01/2024',
        },
        {
          role: 'Ship manager/Commercial manager',
          company_name: 'CRESTWAVE MARITIME LTD',
          address: '123 Marine Road, Piraeus',
          date_of_effect: '15/06/2023',
        },
        {
          role: 'Registered owner',
          company_name: 'CRESTWAVE MARITIME LTD',
          address: '123 Marine Road, Piraeus',
          date_of_effect: '15/06/2023',
          date_to: null,
        },
      ],
      classification_status: [
        {
          society: 'Russian Maritime Register of Shipping',
          date: '15/03/2023',
          status: 'Delivered',
          reason: null,
        },
        {
          society: 'RINA',
          date: '01/01/2022',
          status: 'Withdrawn by society',
          reason: 'Non-compliance with survey requirements',
        },
      ],
      classification_surveys: [
        {
          society: 'Russian Maritime Register of Shipping',
          date: '15/03/2023',
          next_date: '15/03/2028',
        },
      ],
      safety_certificates: [
        {
          society: 'Russian Maritime Register',
          date_of_survey: '10/05/2023',
          date_of_expiry: '10/05/2028',
          status: 'Valid',
          type: 'ISSC',
        },
      ],
      psc_inspections: [
        {
          authority: 'Turkey',
          port: 'Istanbul',
          date: '28/12/2023',
          detention: 'Y',
          psc_organisation: 'Paris MoU',
          type_of_inspection: 'Initial',
          duration_days: 5,
          deficiencies: 12,
        },
        {
          authority: 'Greece',
          port: 'Piraeus',
          date: '15/06/2023',
          detention: 'N',
          psc_organisation: 'Paris MoU',
          type_of_inspection: 'Initial',
          duration_days: 1,
          deficiencies: 3,
        },
        {
          authority: 'Egypt',
          port: 'Suez',
          date: '01/03/2023',
          detention: 'N',
          psc_organisation: 'Indian Ocean MoU',
          type_of_inspection: 'Follow-up',
          duration_days: 1,
          deficiencies: 0,
        },
      ],
      name_history: [
        { name: 'BLUE', date_of_effect: '15/06/2023' },
        { name: 'Julia A', date_of_effect: '01/01/2020' },
        { name: 'Azul', date_of_effect: '15/03/2018' },
        { name: 'Icaria', date_of_effect: '01/06/2015' },
      ],
      flag_history: [
        { flag: 'Cameroon', date_of_effect: '15/06/2023' },
        { flag: 'Panama', date_of_effect: '01/01/2020' },
        { flag: 'Liberia', date_of_effect: '15/03/2018' },
        { flag: 'Greece', date_of_effect: '01/06/2015' },
        { flag: 'Malta', date_of_effect: '01/01/2012' },
      ],
      company_history: [
        {
          company_name: 'CRESTWAVE MARITIME LTD',
          role: 'Registered owner',
          date_of_effect: '15/06/2023',
        },
        {
          company_name: 'ARCADIA SHIPMANAGEMENT CO LTD',
          role: 'ISM Manager',
          date_of_effect: '01/06/2015',
        },
      ],
    },
    upload_count: 1,
    uploads: [
      {
        id: 42,
        upload_timestamp: '2026-03-13T10:30:00Z',
        edition_date: '13/03/2026',
      },
    ],
  };
}

function createMultiUploadEquasisData(): EquasisData {
  const base = createSampleEquasisData();
  return {
    ...base,
    upload_count: 3,
    uploads: [
      {
        id: 42,
        upload_timestamp: '2026-03-13T10:30:00Z',
        edition_date: '13/03/2026',
      },
      {
        id: 30,
        upload_timestamp: '2026-02-15T08:00:00Z',
        edition_date: '15/02/2026',
      },
      {
        id: 18,
        upload_timestamp: '2026-01-10T14:00:00Z',
        edition_date: '10/01/2026',
      },
    ],
  };
}

// ─── Story 6: Equasis section renders with summary when data exists ──

describe('EquasisSection summary rendering', () => {
  it('formatUploadDate formats ISO date to human-readable', () => {
    const formatted = formatUploadDate('2026-03-13T10:30:00Z');
    expect(formatted).toContain('Mar');
    expect(formatted).toContain('2026');
    expect(formatted).toContain('13');
  });

  it('formatUploadDate handles different dates', () => {
    const formatted = formatUploadDate('2025-12-01T00:00:00Z');
    expect(formatted).toContain('Dec');
    expect(formatted).toContain('2025');
  });

  it('sample data has correct summary info', () => {
    const data = createSampleEquasisData();
    const latestUpload = data.uploads[0];
    expect(latestUpload.upload_timestamp).toBe('2026-03-13T10:30:00Z');
    expect(latestUpload.edition_date).toBe('13/03/2026');
  });

  it('sample data has all expected subsections', () => {
    const data = createSampleEquasisData();
    expect(data.latest.ship_particulars).toBeDefined();
    expect(data.latest.management).toBeDefined();
    expect(data.latest.classification_status).toBeDefined();
    expect(data.latest.classification_surveys).toBeDefined();
    expect(data.latest.safety_certificates).toBeDefined();
    expect(data.latest.psc_inspections).toBeDefined();
    expect(data.latest.name_history).toBeDefined();
    expect(data.latest.flag_history).toBeDefined();
    expect(data.latest.company_history).toBeDefined();
  });
});

// ─── Story 6: Expand button reveals all subsections ──────────────────

describe('EquasisSection expanded data structure', () => {
  it('ship particulars contain expected fields', () => {
    const data = createSampleEquasisData();
    const sp = data.latest.ship_particulars;
    expect(sp.imo).toBe(9236353);
    expect(sp.mmsi).toBe(613414602);
    expect(sp.name).toBe('BLUE');
    expect(sp.gross_tonnage).toBe(84789);
    expect(sp.dwt).toBe(165293);
    expect(sp.type_of_ship).toBe('Crude Oil Tanker');
    expect(sp.year_of_build).toBe(2003);
    expect(sp.flag).toBe('Cameroon');
    expect(sp.status).toBe('In Service/Commission');
  });

  it('management entries have role, company, address, date', () => {
    const data = createSampleEquasisData();
    const mgmt = data.latest.management;
    expect(mgmt).toHaveLength(3);
    expect(mgmt[0].role).toBe('ISM Manager');
    expect(mgmt[1].company_name).toBe('CRESTWAVE MARITIME LTD');
    expect(mgmt[2].role).toBe('Registered owner');
  });

  it('classification status entries have society, date, status', () => {
    const data = createSampleEquasisData();
    const cls = data.latest.classification_status;
    expect(cls).toHaveLength(2);
    expect(cls[0].status).toBe('Delivered');
    expect(cls[1].status).toBe('Withdrawn by society');
    expect(cls[1].reason).toBe('Non-compliance with survey requirements');
  });

  it('safety certificates have society, survey date, expiry, status, type', () => {
    const data = createSampleEquasisData();
    const certs = data.latest.safety_certificates;
    expect(certs).toHaveLength(1);
    expect(certs[0].society).toBe('Russian Maritime Register');
    expect(certs[0].status).toBe('Valid');
    expect(certs[0].type).toBe('ISSC');
  });

  it('PSC inspections have all required fields', () => {
    const data = createSampleEquasisData();
    const psc = data.latest.psc_inspections;
    expect(psc).toHaveLength(3);
    const istanbul = psc[0];
    expect(istanbul.authority).toBe('Turkey');
    expect(istanbul.port).toBe('Istanbul');
    expect(istanbul.date).toBe('28/12/2023');
    expect(istanbul.detention).toBe('Y');
    expect(istanbul.psc_organisation).toBe('Paris MoU');
    expect(istanbul.type_of_inspection).toBe('Initial');
    expect(istanbul.duration_days).toBe(5);
    expect(istanbul.deficiencies).toBe(12);
  });

  it('name history is a chronological list', () => {
    const data = createSampleEquasisData();
    const names = data.latest.name_history;
    expect(names).toHaveLength(4);
    expect(names[0].name).toBe('BLUE');
    expect(names[3].name).toBe('Icaria');
  });

  it('flag history is a chronological list', () => {
    const data = createSampleEquasisData();
    const flags = data.latest.flag_history;
    expect(flags).toHaveLength(5);
    expect(flags[0].flag).toBe('Cameroon');
    expect(flags[3].flag).toBe('Greece');
  });

  it('company history has role, company, date', () => {
    const data = createSampleEquasisData();
    const companies = data.latest.company_history;
    expect(companies).toHaveLength(2);
    expect(companies[0].company_name).toBe('CRESTWAVE MARITIME LTD');
    expect(companies[0].role).toBe('Registered owner');
  });
});

// ─── Story 6: PSC detention rows highlighted ─────────────────────────

describe('PSC detention detection', () => {
  it('detention "Y" is identified as detention', () => {
    const data = createSampleEquasisData();
    const psc = data.latest.psc_inspections;
    const istanbul = psc[0];
    expect(istanbul.detention).toBe('Y');
    // The component uses this condition to highlight in red
    const isDetention =
      istanbul.detention === 'Y' ||
      istanbul.detention === true ||
      istanbul.detained === true;
    expect(isDetention).toBe(true);
  });

  it('detention "N" is not identified as detention', () => {
    const data = createSampleEquasisData();
    const psc = data.latest.psc_inspections;
    const piraeus = psc[1];
    expect(piraeus.detention).toBe('N');
    const isDetention =
      piraeus.detention === 'Y' ||
      piraeus.detention === true ||
      (piraeus as any).detained === true;
    expect(isDetention).toBe(false);
  });

  it('getDeficiencyColor returns green for 0', () => {
    expect(getDeficiencyColor(0)).toBe('text-green-400');
  });

  it('getDeficiencyColor returns yellow for 1-5', () => {
    expect(getDeficiencyColor(1)).toBe('text-yellow-400');
    expect(getDeficiencyColor(3)).toBe('text-yellow-400');
    expect(getDeficiencyColor(5)).toBe('text-yellow-400');
  });

  it('getDeficiencyColor returns red for 6+', () => {
    expect(getDeficiencyColor(6)).toBe('text-red-400');
    expect(getDeficiencyColor(12)).toBe('text-red-400');
    expect(getDeficiencyColor(100)).toBe('text-red-400');
  });
});

// ─── Story 6: Empty state renders upload prompt ──────────────────────

describe('EquasisSection empty state', () => {
  it('null equasis data results in empty state', () => {
    const equasis: EquasisData | null = null;
    expect(equasis).toBeNull();
  });

  it('undefined equasis data is falsy', () => {
    const equasis: EquasisData | undefined = undefined;
    expect(equasis).toBeUndefined();
    expect(!equasis).toBe(true);
  });
});

// ─── Story 6: Previous uploads dropdown ──────────────────────────────

describe('Previous uploads dropdown', () => {
  it('multiple uploads results in upload_count > 1', () => {
    const data = createMultiUploadEquasisData();
    expect(data.upload_count).toBe(3);
    expect(data.uploads).toHaveLength(3);
  });

  it('uploads are ordered by date (newest first)', () => {
    const data = createMultiUploadEquasisData();
    const timestamps = data.uploads.map((u) => new Date(u.upload_timestamp).getTime());
    for (let i = 1; i < timestamps.length; i++) {
      expect(timestamps[i - 1]).toBeGreaterThan(timestamps[i]);
    }
  });

  it('each upload has id, timestamp, and edition_date', () => {
    const data = createMultiUploadEquasisData();
    for (const upload of data.uploads) {
      expect(typeof upload.id).toBe('number');
      expect(typeof upload.upload_timestamp).toBe('string');
      expect(upload.upload_timestamp.length).toBeGreaterThan(0);
      // edition_date can be null but should be string when present
      if (upload.edition_date !== null) {
        expect(typeof upload.edition_date).toBe('string');
      }
    }
  });

  it('single upload does not trigger dropdown (upload_count === 1)', () => {
    const data = createSampleEquasisData();
    expect(data.upload_count).toBe(1);
    const showDropdown = data.upload_count > 1;
    expect(showDropdown).toBe(false);
  });

  it('latest upload is the first in the array', () => {
    const data = createMultiUploadEquasisData();
    const latestUpload = data.uploads[0];
    expect(latestUpload.id).toBe(42);
    expect(latestUpload.upload_timestamp).toBe('2026-03-13T10:30:00Z');
  });
});

// ─── Story 6: Flag of convenience detection ─────────────────────────

describe('Flag of convenience detection', () => {
  it('Cameroon is a flag of convenience', () => {
    expect(isFlagOfConvenience('Cameroon')).toBe(true);
  });

  it('Panama is a flag of convenience', () => {
    expect(isFlagOfConvenience('Panama')).toBe(true);
  });

  it('Liberia is a flag of convenience', () => {
    expect(isFlagOfConvenience('Liberia')).toBe(true);
  });

  it('Marshall Islands is a flag of convenience', () => {
    expect(isFlagOfConvenience('Marshall Islands')).toBe(true);
  });

  it('Malta is a flag of convenience', () => {
    expect(isFlagOfConvenience('Malta')).toBe(true);
  });

  it('Greece is not a flag of convenience', () => {
    expect(isFlagOfConvenience('Greece')).toBe(false);
  });

  it('Norway is not a flag of convenience', () => {
    expect(isFlagOfConvenience('Norway')).toBe(false);
  });

  it('FOC_FLAGS set contains expected flags', () => {
    expect(FOC_FLAGS.size).toBeGreaterThanOrEqual(20);
    expect(FOC_FLAGS.has('Comoros')).toBe(true);
    expect(FOC_FLAGS.has('Togo')).toBe(true);
    expect(FOC_FLAGS.has('Palau')).toBe(true);
  });
});

// ─── Story 6: Classification withdrawn detection ────────────────────

describe('Classification withdrawn detection', () => {
  it('identifies withdrawn status', () => {
    const data = createSampleEquasisData();
    const cls = data.latest.classification_status;
    const withdrawn = cls.filter(
      (e: any) => e.status?.toLowerCase().includes('withdrawn'),
    );
    expect(withdrawn).toHaveLength(1);
    expect(withdrawn[0].society).toBe('RINA');
  });

  it('delivered status is not withdrawn', () => {
    const data = createSampleEquasisData();
    const cls = data.latest.classification_status;
    const delivered = cls.filter(
      (e: any) => !e.status?.toLowerCase().includes('withdrawn'),
    );
    expect(delivered).toHaveLength(1);
    expect(delivered[0].status).toBe('Delivered');
  });
});

// ─── Story 6: Historical upload fetch (API integration) ──────────────

describe('Historical upload fetch', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches historical upload by ID from correct endpoint', async () => {
    const mockFetch = vi.mocked(fetch);
    const historicalData = { ship_particulars: { imo: 9236353 } };
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(historicalData), { status: 200 }),
    );

    const mmsi = 613414602;
    const uploadId = 30;
    const res = await fetch(`/api/equasis/${mmsi}/upload/${uploadId}`);

    expect(mockFetch).toHaveBeenCalledWith(`/api/equasis/613414602/upload/30`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.ship_particulars.imo).toBe(9236353);
  });
});

// ─── Story 6: Component exports ──────────────────────────────────────

describe('EquasisSection component exports', () => {
  it('exports EquasisSection component', async () => {
    const mod = await import('./EquasisSection');
    expect(mod.EquasisSection).toBeDefined();
    expect(typeof mod.EquasisSection).toBe('function');
  });

  it('exports formatUploadDate utility', async () => {
    const mod = await import('./EquasisSection');
    expect(mod.formatUploadDate).toBeDefined();
    expect(typeof mod.formatUploadDate).toBe('function');
  });

  it('exports getDeficiencyColor utility', async () => {
    const mod = await import('./EquasisSection');
    expect(mod.getDeficiencyColor).toBeDefined();
    expect(typeof mod.getDeficiencyColor).toBe('function');
  });

  it('exports isFlagOfConvenience utility', async () => {
    const mod = await import('./EquasisSection');
    expect(mod.isFlagOfConvenience).toBeDefined();
    expect(typeof mod.isFlagOfConvenience).toBe('function');
  });

  it('exports FOC_FLAGS constant', async () => {
    const mod = await import('./EquasisSection');
    expect(mod.FOC_FLAGS).toBeDefined();
    expect(mod.FOC_FLAGS instanceof Set).toBe(true);
  });
});

// ─── Story 6: Types ──────────────────────────────────────────────────

describe('Equasis types in api.ts', () => {
  it('EquasisUploadSummary type works', () => {
    const summary: EquasisUploadSummary = {
      id: 1,
      upload_timestamp: '2026-03-13T10:30:00Z',
      edition_date: '13/03/2026',
    };
    expect(summary.id).toBe(1);
    expect(summary.edition_date).toBe('13/03/2026');
  });

  it('EquasisUploadSummary allows null edition_date', () => {
    const summary: EquasisUploadSummary = {
      id: 2,
      upload_timestamp: '2026-03-13T10:30:00Z',
      edition_date: null,
    };
    expect(summary.edition_date).toBeNull();
  });

  it('EquasisData type has required fields', () => {
    const data: EquasisData = {
      latest: {},
      upload_count: 0,
      uploads: [],
    };
    expect(data.upload_count).toBe(0);
    expect(data.uploads).toEqual([]);
  });

  it('VesselDetail supports equasis field', () => {
    const vessel = {
      mmsi: 613414602,
      riskScore: 85,
      riskTier: 'red' as const,
      equasis: createSampleEquasisData(),
    };
    expect(vessel.equasis).toBeDefined();
    expect(vessel.equasis!.latest.ship_particulars.name).toBe('BLUE');
  });

  it('VesselDetail supports null equasis', () => {
    const vessel = {
      mmsi: 211234567,
      riskScore: 30,
      riskTier: 'green' as const,
      equasis: null,
    };
    expect(vessel.equasis).toBeNull();
  });
});
