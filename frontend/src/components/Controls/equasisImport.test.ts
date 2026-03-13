import { describe, it, expect, beforeEach } from 'vitest';
import { useVesselStore } from '../../hooks/useVesselStore';
import {
  buildUploadFormData,
  formatSuccessMessage,
  ACCEPTED_FILE_TYPE,
} from './EquasisImport';
import type { EquasisUploadResponse } from './EquasisImport';

function resetStore() {
  useVesselStore.setState({
    vessels: new Map(),
    positionHistory: new Map(),
    selectedMmsi: null,
    filters: {
      riskTiers: new Set(),
      shipTypes: [],
      bbox: null,
      activeSince: null,
      darkShipsOnly: false,
      showGfwEventTypes: [],
    },
  });
}

// ─── Story 5: EquasisImport — pure function tests ──────────────────

describe('EquasisImport — ACCEPTED_FILE_TYPE', () => {
  it('only accepts PDF files', () => {
    expect(ACCEPTED_FILE_TYPE).toBe('.pdf');
  });
});

describe('EquasisImport — buildUploadFormData', () => {
  it('creates FormData with "file" field and no mmsi param', () => {
    const file = new File(['pdf-content'], 'equasis-report.pdf', {
      type: 'application/pdf',
    });
    const fd = buildUploadFormData(file);
    expect(fd.get('file')).toBe(file);
    expect(fd.get('mmsi')).toBeNull();
  });

  it('does not include extra fields', () => {
    const file = new File(['data'], 'report.pdf', { type: 'application/pdf' });
    const fd = buildUploadFormData(file);
    const keys: string[] = [];
    fd.forEach((_v, k) => keys.push(k));
    expect(keys).toEqual(['file']);
  });
});

describe('EquasisImport — formatSuccessMessage', () => {
  it('returns "New vessel added" message when created is true', () => {
    const res: EquasisUploadResponse = {
      mmsi: 613414602,
      imo: 9236353,
      ship_name: 'BLUE',
      created: true,
      equasis_data_id: 1,
      summary: {},
    };
    expect(formatSuccessMessage(res)).toBe(
      'New vessel added: BLUE (IMO 9236353)',
    );
  });

  it('returns standard import message when created is false', () => {
    const res: EquasisUploadResponse = {
      mmsi: 613414602,
      imo: 9236353,
      ship_name: 'BLUE',
      created: false,
      equasis_data_id: 1,
      summary: {},
    };
    expect(formatSuccessMessage(res)).toBe('Equasis data imported for BLUE');
  });
});

describe('EquasisImport — selectVessel integration', () => {
  beforeEach(resetStore);

  it('selectVessel updates selectedMmsi (simulating success auto-select)', () => {
    const { selectVessel } = useVesselStore.getState();
    selectVessel(613414602);
    expect(useVesselStore.getState().selectedMmsi).toBe(613414602);
  });

  it('selectVessel works for new vessel mmsi not yet in vessel map', () => {
    const { selectVessel } = useVesselStore.getState();
    expect(useVesselStore.getState().vessels.has(999999999)).toBe(false);
    selectVessel(999999999);
    expect(useVesselStore.getState().selectedMmsi).toBe(999999999);
  });
});
