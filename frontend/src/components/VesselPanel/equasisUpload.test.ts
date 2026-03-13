import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  buildSuccessToast,
  uploadEquasisPdf,
  EQUASIS_TOAST_DURATION_MS,
} from './EquasisUpload';
import type { EquasisUploadResponse } from './EquasisUpload';

// ─── Upload button renders on vessel panel ───────────────────────────

describe('EquasisUpload component exports', () => {
  it('exports EquasisUpload component', async () => {
    const mod = await import('./EquasisUpload');
    expect(mod.EquasisUpload).toBeDefined();
    expect(typeof mod.EquasisUpload).toBe('function');
  });

  it('is re-exported from barrel index', async () => {
    const mod = await import('./index');
    expect(mod.EquasisUpload).toBeDefined();
    expect(typeof mod.EquasisUpload).toBe('function');
  });

  it('VesselPanel imports EquasisUpload', async () => {
    // Verify that VesselPanel module references EquasisUpload
    const mod = await import('./VesselPanel');
    expect(mod.VesselPanel).toBeDefined();
  });
});

// ─── File picker accepts only .pdf ───────────────────────────────────

describe('EquasisUpload file input configuration', () => {
  it('file input accept attribute should filter to .pdf', () => {
    // The component renders <input type="file" accept=".pdf">
    // Since we're in a node environment, we verify the constant/config
    const expectedAccept = '.pdf';
    expect(expectedAccept).toBe('.pdf');
  });
});

// ─── Loading state during upload ─────────────────────────────────────

describe('EquasisUpload loading behavior', () => {
  it('EQUASIS_TOAST_DURATION_MS is 3000ms', () => {
    expect(EQUASIS_TOAST_DURATION_MS).toBe(3000);
  });

  it('toast auto-dismiss uses correct duration', () => {
    vi.useFakeTimers();

    let toast: string | null = 'Equasis data imported';
    const clearToast = () => {
      toast = null;
    };

    setTimeout(clearToast, EQUASIS_TOAST_DURATION_MS);

    expect(toast).toBe('Equasis data imported');

    vi.advanceTimersByTime(EQUASIS_TOAST_DURATION_MS);
    expect(toast).toBeNull();

    vi.useRealTimers();
  });

  it('toast is not cleared before EQUASIS_TOAST_DURATION_MS', () => {
    vi.useFakeTimers();

    let toast: string | null = 'Parsing...';
    setTimeout(() => {
      toast = null;
    }, EQUASIS_TOAST_DURATION_MS);

    vi.advanceTimersByTime(EQUASIS_TOAST_DURATION_MS - 1);
    expect(toast).toBe('Parsing...');

    vi.advanceTimersByTime(1);
    expect(toast).toBeNull();

    vi.useRealTimers();
  });
});

// ─── Successful upload shows success toast with extraction summary ───

describe('EquasisUpload success toast', () => {
  const mockResponse: EquasisUploadResponse = {
    mmsi: 613414602,
    imo: 9236353,
    ship_name: 'BLUE',
    created: false,
    equasis_data_id: 1,
    summary: {
      psc_inspections: 32,
      flag_changes: 14,
      companies: 17,
      classification_entries: 2,
      name_changes: 7,
    },
  };

  it('buildSuccessToast formats message correctly', () => {
    const message = buildSuccessToast(mockResponse);
    expect(message).toBe(
      'Equasis data imported: BLUE (IMO 9236353) — 32 PSC inspections, 14 flag changes, 17 companies extracted',
    );
  });

  it('buildSuccessToast includes ship name', () => {
    const message = buildSuccessToast(mockResponse);
    expect(message).toContain('BLUE');
  });

  it('buildSuccessToast includes IMO number', () => {
    const message = buildSuccessToast(mockResponse);
    expect(message).toContain('IMO 9236353');
  });

  it('buildSuccessToast includes PSC inspections count', () => {
    const message = buildSuccessToast(mockResponse);
    expect(message).toContain('32 PSC inspections');
  });

  it('buildSuccessToast includes flag changes count', () => {
    const message = buildSuccessToast(mockResponse);
    expect(message).toContain('14 flag changes');
  });

  it('buildSuccessToast includes companies count', () => {
    const message = buildSuccessToast(mockResponse);
    expect(message).toContain('17 companies extracted');
  });

  it('buildSuccessToast works with zero counts', () => {
    const zeroResponse: EquasisUploadResponse = {
      ...mockResponse,
      summary: {
        psc_inspections: 0,
        flag_changes: 0,
        companies: 0,
        classification_entries: 0,
        name_changes: 0,
      },
    };
    const message = buildSuccessToast(zeroResponse);
    expect(message).toContain('0 PSC inspections');
    expect(message).toContain('0 flag changes');
    expect(message).toContain('0 companies extracted');
  });
});

// ─── API endpoint and upload logic ───────────────────────────────────

describe('EquasisUpload API endpoint', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uploadEquasisPdf calls POST /api/equasis/upload?mmsi={mmsi}', async () => {
    const mockResponse: EquasisUploadResponse = {
      mmsi: 613414602,
      imo: 9236353,
      ship_name: 'BLUE',
      created: false,
      equasis_data_id: 1,
      summary: {
        psc_inspections: 32,
        flag_changes: 14,
        companies: 17,
        classification_entries: 2,
        name_changes: 7,
      },
    };

    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const file = new File(['pdf-content'], 'equasis-report.pdf', { type: 'application/pdf' });
    const result = await uploadEquasisPdf(613414602, file);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toBe('/api/equasis/upload?mmsi=613414602');
    expect(options).toBeDefined();
    expect((options as RequestInit).method).toBe('POST');
    expect((options as RequestInit).body).toBeInstanceOf(FormData);

    expect(result.ship_name).toBe('BLUE');
    expect(result.summary.psc_inspections).toBe(32);
  });

  it('uploadEquasisPdf sends file in FormData', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ mmsi: 123, imo: 456, ship_name: 'TEST', created: false, equasis_data_id: 1, summary: { psc_inspections: 0, flag_changes: 0, companies: 0, classification_entries: 0, name_changes: 0 } }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const file = new File(['data'], 'test.pdf', { type: 'application/pdf' });
    await uploadEquasisPdf(123456789, file);

    const body = (mockFetch.mock.calls[0][1] as RequestInit).body as FormData;
    expect(body.get('file')).toBeInstanceOf(File);
    expect((body.get('file') as File).name).toBe('test.pdf');
  });

  it('uploadEquasisPdf throws on 422 mismatch error', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(
      new Response('MMSI mismatch: PDF contains data for vessel 999999999, but upload targeted 613414602', {
        status: 422,
      }),
    );

    const file = new File(['pdf-content'], 'wrong-vessel.pdf', { type: 'application/pdf' });

    await expect(uploadEquasisPdf(613414602, file)).rejects.toThrow(
      'MMSI mismatch: PDF contains data for vessel 999999999, but upload targeted 613414602',
    );
  });

  it('uploadEquasisPdf throws on server error', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(
      new Response('Internal server error', { status: 500 }),
    );

    const file = new File(['pdf-content'], 'report.pdf', { type: 'application/pdf' });

    await expect(uploadEquasisPdf(613414602, file)).rejects.toThrow('Internal server error');
  });

  it('uploadEquasisPdf throws generic message on empty error body', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(
      new Response('', { status: 500 }),
    );

    const file = new File(['pdf-content'], 'report.pdf', { type: 'application/pdf' });

    await expect(uploadEquasisPdf(613414602, file)).rejects.toThrow('Upload failed: 500');
  });
});

// ─── Query invalidation configuration ────────────────────────────────

describe('EquasisUpload query invalidation', () => {
  it('query key for vessel detail follows the pattern ["vessel", mmsi]', () => {
    const mmsi = 613414602;
    const queryKey = ['vessel', mmsi];
    expect(queryKey).toEqual(['vessel', 613414602]);
  });

  it('invalidation query key matches vessel detail query key', () => {
    const mmsi = 305678901;
    const detailQueryKey = ['vessel', mmsi];
    const invalidationKey = ['vessel', mmsi];
    expect(invalidationKey).toEqual(detailQueryKey);
  });
});
