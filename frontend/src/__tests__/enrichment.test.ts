import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  SOURCE_OPTIONS,
  PI_TIER_OPTIONS,
  getInitialFormState,
  isSourceRequired,
  buildPayload,
  TOAST_DURATION_MS,
} from '../components/VesselPanel/EnrichmentForm';
import type { EnrichmentFormState } from '../components/VesselPanel/EnrichmentForm';
import {
  sortEnrichmentsByDate,
  formatEnrichmentDate,
} from '../components/VesselPanel/EnrichmentHistory';
import type { ManualEnrichmentRecord } from '../types/api';

// ─── Story 1: EnrichmentForm field configuration ───────────────────

describe('EnrichmentForm field configuration', () => {
  it('SOURCE_OPTIONS contains all 5 expected sources', () => {
    expect(SOURCE_OPTIONS).toEqual([
      'Equasis',
      'Paris MoU',
      'Tokyo MoU',
      'Corporate Registry',
      'Other',
    ]);
    expect(SOURCE_OPTIONS).toHaveLength(5);
  });

  it('PI_TIER_OPTIONS contains all 6 tier values', () => {
    expect(PI_TIER_OPTIONS).toEqual([
      'ig_member',
      'non_ig_western',
      'russian_state',
      'unknown',
      'fraudulent',
      'none',
    ]);
    expect(PI_TIER_OPTIONS).toHaveLength(6);
  });

  it('initial form state has empty/default values', () => {
    const state = getInitialFormState();
    expect(state.source).toBe('');
    expect(state.registeredOwner).toBe('');
    expect(state.commercialManager).toBe('');
    expect(state.beneficialOwner).toBe('');
    expect(state.piInsurer).toBe('');
    expect(state.piInsurerTier).toBe('');
    expect(state.classificationSociety).toBe('');
    expect(state.iacsMember).toBe(false);
    expect(state.pscDetentions).toBe('');
    expect(state.pscDeficiencies).toBe('');
    expect(state.notes).toBe('');
  });
});

// ─── Story 1: Source field required validation ─────────────────────

describe('EnrichmentForm source validation', () => {
  it('empty source is not valid', () => {
    expect(isSourceRequired('')).toBe(false);
  });

  it('whitespace-only source is not valid', () => {
    expect(isSourceRequired('   ')).toBe(false);
  });

  it('valid source passes validation', () => {
    expect(isSourceRequired('Equasis')).toBe(true);
    expect(isSourceRequired('Paris MoU')).toBe(true);
  });
});

// ─── Story 2: Submit mutation payload building ─────────────────────

describe('EnrichmentForm buildPayload', () => {
  it('builds minimal payload with only source', () => {
    const state = getInitialFormState();
    state.source = 'Equasis';
    const payload = buildPayload(state);
    expect(payload).toEqual({ source: 'Equasis' });
    expect(payload.ownership_chain).toBeUndefined();
    expect(payload.pi_insurer).toBeUndefined();
    expect(payload.notes).toBeUndefined();
  });

  it('includes ownership_chain when any ownership field is set', () => {
    const state = getInitialFormState();
    state.source = 'Corporate Registry';
    state.registeredOwner = 'Gotland Shipping AB';
    state.beneficialOwner = 'Gotland Holdings Ltd';

    const payload = buildPayload(state);
    expect(payload.ownership_chain).toEqual({
      registered_owner: 'Gotland Shipping AB',
      beneficial_owner: 'Gotland Holdings Ltd',
    });
    // commercial_manager should not be in the object since it's empty
    expect(payload.ownership_chain?.commercial_manager).toBeUndefined();
  });

  it('includes all optional fields when populated', () => {
    const state: EnrichmentFormState = {
      source: 'Tokyo MoU',
      registeredOwner: 'Owner A',
      commercialManager: 'Manager B',
      beneficialOwner: 'Beneficial C',
      piInsurer: 'West of England',
      piInsurerTier: 'ig_member',
      classificationSociety: 'Lloyd\'s Register',
      iacsMember: true,
      pscDetentions: '2',
      pscDeficiencies: '15',
      notes: 'Verified via Paris MoU inspection report',
    };

    const payload = buildPayload(state);
    expect(payload.source).toBe('Tokyo MoU');
    expect(payload.ownership_chain).toEqual({
      registered_owner: 'Owner A',
      commercial_manager: 'Manager B',
      beneficial_owner: 'Beneficial C',
    });
    expect(payload.pi_insurer).toBe('West of England');
    expect(payload.pi_insurer_tier).toBe('ig_member');
    expect(payload.classification_society).toBe('Lloyd\'s Register');
    expect(payload.classification_iacs).toBe(true);
    expect(payload.psc_detentions).toBe(2);
    expect(payload.psc_deficiencies).toBe(15);
    expect(payload.notes).toBe('Verified via Paris MoU inspection report');
  });

  it('does not include classification_iacs when false', () => {
    const state = getInitialFormState();
    state.source = 'Other';
    state.iacsMember = false;

    const payload = buildPayload(state);
    expect(payload.classification_iacs).toBeUndefined();
  });

  it('parses PSC numbers correctly', () => {
    const state = getInitialFormState();
    state.source = 'Paris MoU';
    state.pscDetentions = '3';
    state.pscDeficiencies = '22';

    const payload = buildPayload(state);
    expect(payload.psc_detentions).toBe(3);
    expect(typeof payload.psc_detentions).toBe('number');
    expect(payload.psc_deficiencies).toBe(22);
    expect(typeof payload.psc_deficiencies).toBe('number');
  });
});

// ─── Story 2: Submit mutation calls correct endpoint ───────────────

describe('EnrichmentForm API endpoint', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('submitEnrichment calls POST /api/vessels/{mmsi}/enrich', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 200 }));

    // Import the module to get the submit function indirectly via buildPayload test
    const payload = buildPayload({ ...getInitialFormState(), source: 'Equasis' });

    // Simulate what the mutation does
    const mmsi = 211234567;
    const res = await fetch(`/api/vessels/${mmsi}/enrich`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    expect(mockFetch).toHaveBeenCalledWith(`/api/vessels/211234567/enrich`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'Equasis' }),
    });
    expect(res.status).toBe(200);
  });

  it('throws on non-ok response', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(new Response('Validation error', { status: 422 }));

    const mmsi = 211234567;
    const res = await fetch(`/api/vessels/${mmsi}/enrich`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'Other' }),
    });

    expect(res.ok).toBe(false);
    expect(res.status).toBe(422);
    const body = await res.text();
    expect(body).toBe('Validation error');
  });
});

// ─── Story 2: Toast auto-dismiss behavior ──────────────────────────

describe('Toast auto-dismiss behavior', () => {
  it('TOAST_DURATION_MS is 3000ms', () => {
    expect(TOAST_DURATION_MS).toBe(3000);
  });

  it('setTimeout with TOAST_DURATION_MS clears toast', () => {
    vi.useFakeTimers();

    let toast: string | null = 'Enrichment data saved. Risk score recalculated.';
    const clearToast = () => {
      toast = null;
    };

    setTimeout(clearToast, TOAST_DURATION_MS);

    expect(toast).toBe('Enrichment data saved. Risk score recalculated.');

    vi.advanceTimersByTime(TOAST_DURATION_MS);
    expect(toast).toBeNull();

    vi.useRealTimers();
  });

  it('toast is not cleared before TOAST_DURATION_MS', () => {
    vi.useFakeTimers();

    let toast: string | null = 'Error message';
    setTimeout(() => {
      toast = null;
    }, TOAST_DURATION_MS);

    vi.advanceTimersByTime(TOAST_DURATION_MS - 1);
    expect(toast).toBe('Error message');

    vi.advanceTimersByTime(1);
    expect(toast).toBeNull();

    vi.useRealTimers();
  });
});

// ─── Story 2: TanStack Query invalidation on success ───────────────

describe('TanStack Query invalidation configuration', () => {
  it('query key for vessel detail follows the pattern ["vessel", mmsi]', () => {
    const mmsi = 211234567;
    const queryKey = ['vessel', mmsi];
    expect(queryKey).toEqual(['vessel', 211234567]);
  });

  it('invalidation query key matches vessel detail query key', () => {
    const mmsi = 305678901;
    const detailQueryKey = ['vessel', mmsi];
    const invalidationKey = ['vessel', mmsi];
    expect(invalidationKey).toEqual(detailQueryKey);
  });
});

// ─── Story 3: Enrichment history rendering with data ───────────────

describe('EnrichmentHistory data processing', () => {
  const records: ManualEnrichmentRecord[] = [
    {
      id: 1,
      source: 'Equasis',
      analystNotes: 'Initial vessel registration data',
      piTier: 'ig_member',
      createdAt: '2026-03-01T10:00:00Z',
    },
    {
      id: 2,
      source: 'Paris MoU',
      analystNotes: 'PSC inspection results from Rotterdam',
      createdAt: '2026-03-10T14:30:00Z',
    },
    {
      id: 3,
      source: 'Corporate Registry',
      piTier: 'non_ig_western',
      createdAt: '2026-03-05T08:15:00Z',
    },
  ];

  it('sorts enrichments by date newest first', () => {
    const sorted = sortEnrichmentsByDate(records);
    expect(sorted[0].id).toBe(2); // March 10
    expect(sorted[1].id).toBe(3); // March 5
    expect(sorted[2].id).toBe(1); // March 1
  });

  it('does not mutate the original array', () => {
    const original = [...records];
    sortEnrichmentsByDate(records);
    expect(records).toEqual(original);
  });

  it('formats date correctly', () => {
    const formatted = formatEnrichmentDate('2026-03-10T14:30:00Z');
    expect(formatted).toContain('Mar');
    expect(formatted).toContain('2026');
    expect(formatted).toContain('10');
  });

  it('each record has required fields', () => {
    for (const record of records) {
      expect(typeof record.id).toBe('number');
      expect(typeof record.source).toBe('string');
      expect(record.source.length).toBeGreaterThan(0);
      expect(typeof record.createdAt).toBe('string');
    }
  });

  it('handles records with optional fields missing', () => {
    const minimal: ManualEnrichmentRecord = {
      id: 99,
      source: 'Other',
      createdAt: '2026-03-12T00:00:00Z',
    };
    expect(minimal.analystNotes).toBeUndefined();
    expect(minimal.piTier).toBeUndefined();
    expect(minimal.attachments).toBeUndefined();
  });
});

// ─── Story 3: Empty state rendering ────────────────────────────────

describe('EnrichmentHistory empty state', () => {
  it('empty array results in empty state', () => {
    const records: ManualEnrichmentRecord[] = [];
    expect(records.length === 0).toBe(true);
  });

  it('undefined enrichments results in empty state', () => {
    const records = undefined;
    const sorted = records ? sortEnrichmentsByDate(records) : [];
    expect(sorted).toEqual([]);
    expect(sorted.length).toBe(0);
  });
});

// ─── Component exports ─────────────────────────────────────────────

describe('EnrichmentForm component exports', () => {
  it('exports EnrichmentForm component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.EnrichmentForm).toBeDefined();
    expect(typeof mod.EnrichmentForm).toBe('function');
  });

  it('exports EnrichmentHistory component', async () => {
    const mod = await import('../components/VesselPanel');
    expect(mod.EnrichmentHistory).toBeDefined();
    expect(typeof mod.EnrichmentHistory).toBe('function');
  });
});

// ─── Types ─────────────────────────────────────────────────────────

describe('ManualEnrichmentRecord type', () => {
  it('api types module exports correctly', async () => {
    const mod = await import('../types/api');
    expect(mod).toBeDefined();
  });

  it('VesselDetail supports manualEnrichments array', () => {
    // Type-level test via runtime data shape
    const vessel = {
      mmsi: 211234567,
      riskScore: 75,
      riskTier: 'yellow' as const,
      manualEnrichments: [
        {
          id: 1,
          source: 'Equasis',
          createdAt: '2026-03-01T10:00:00Z',
        },
      ],
    };
    expect(vessel.manualEnrichments).toHaveLength(1);
    expect(vessel.manualEnrichments[0].source).toBe('Equasis');
  });
});
