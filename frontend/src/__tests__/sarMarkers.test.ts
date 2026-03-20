import { describe, it, expect, vi } from 'vitest';

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(() => ({ data: [], isLoading: false })),
}));

import type { SarDetection } from '../types/api';
import { SAR_DARK_COLOR, SAR_DARK_BORDER, SAR_MATCHED_COLOR } from '../utils/eventIcons';

// Realistic SAR detection test data
const makeSarDetection = (overrides: Partial<SarDetection> = {}): SarDetection => ({
  id: 'sar-det-7a3f',
  detectedAt: '2025-11-15T08:22:00Z',
  lat: 69.4521,
  lon: 33.1208,
  estimatedLength: 274,
  isDark: true,
  matchingScore: 0.87,
  fishingScore: 0.12,
  matchedMmsi: 273456780,
  matchedVesselName: 'Primorsky Prospect',
  satellite: 'Sentinel-1A',
  imageUrl: null,
  ...overrides,
});

describe('SAR Detection color constants', () => {
  it('defines correct SAR color constants', () => {
    expect(SAR_DARK_COLOR).toBe('#FFFFFF');
    expect(SAR_DARK_BORDER).toBe('#C0392B');
    expect(SAR_MATCHED_COLOR).toBe('#888888');
  });
});

describe('SAR Detection data shape', () => {
  it('creates a valid dark ship detection', () => {
    const det = makeSarDetection();
    expect(det.isDark).toBe(true);
    expect(det.matchedMmsi).toBe(273456780);
    expect(det.estimatedLength).toBe(274);
    expect(det.matchingScore).toBe(0.87);
    expect(det.lat).toBeCloseTo(69.4521, 4);
    expect(det.lon).toBeCloseTo(33.1208, 4);
  });

  it('creates a valid matched (non-dark) detection', () => {
    const det = makeSarDetection({
      id: 'sar-det-b2c1',
      isDark: false,
      matchedMmsi: 311045920,
      matchedVesselName: 'Bahamian Star',
      matchingScore: 0.95,
      estimatedLength: 183,
      lat: 67.8914,
      lon: 14.5623,
    });
    expect(det.isDark).toBe(false);
    expect(det.matchedVesselName).toBe('Bahamian Star');
  });

  it('handles detections with null optional fields', () => {
    const det = makeSarDetection({
      estimatedLength: null,
      matchingScore: null,
      fishingScore: null,
      matchedMmsi: null,
      matchedVesselName: null,
      satellite: null,
    });
    expect(det.estimatedLength).toBeNull();
    expect(det.matchedMmsi).toBeNull();
    expect(det.fishingScore).toBeNull();
  });

  it('SAR detection has all required fields', () => {
    const det = makeSarDetection();
    expect(det).toHaveProperty('id');
    expect(det).toHaveProperty('detectedAt');
    expect(det).toHaveProperty('lat');
    expect(det).toHaveProperty('lon');
    expect(det).toHaveProperty('isDark');
    expect(typeof det.id).toBe('string');
    expect(typeof det.lat).toBe('number');
    expect(typeof det.lon).toBe('number');
    expect(typeof det.isDark).toBe('boolean');
  });
});

describe('SAR dark ship filtering', () => {
  it('filters to only dark detections', () => {
    const detections: SarDetection[] = [
      makeSarDetection({ id: 'sar-1', isDark: true }),
      makeSarDetection({ id: 'sar-2', isDark: false }),
      makeSarDetection({ id: 'sar-3', isDark: true }),
      makeSarDetection({ id: 'sar-4', isDark: false }),
    ];

    const darkOnly = detections.filter((d) => d.isDark);
    expect(darkOnly).toHaveLength(2);
    expect(darkOnly.every((d) => d.isDark)).toBe(true);
  });

  it('returns all detections when filter is off', () => {
    const detections: SarDetection[] = [
      makeSarDetection({ id: 'sar-1', isDark: true }),
      makeSarDetection({ id: 'sar-2', isDark: false }),
    ];

    const darkShipsOnly = false;
    const filtered = darkShipsOnly ? detections.filter((d) => d.isDark) : detections;
    expect(filtered).toHaveLength(2);
  });

  it('handles empty detection list gracefully', () => {
    const detections: SarDetection[] = [];
    const darkOnly = detections.filter((d) => d.isDark);
    expect(darkOnly).toHaveLength(0);
  });

  it('handles all-dark detection list', () => {
    const detections: SarDetection[] = [
      makeSarDetection({ id: 'sar-1', isDark: true }),
      makeSarDetection({ id: 'sar-2', isDark: true }),
    ];
    const darkOnly = detections.filter((d) => d.isDark);
    expect(darkOnly).toHaveLength(2);
  });
});

// SarMarkers Cesium component removed in Story 11 (MapLibre migration)

describe('SAR store integration', () => {
  it('darkShipsOnly filter exists in store', async () => {
    const { useVesselStore } = await import('../hooks/useVesselStore');
    const state = useVesselStore.getState();
    expect(state.filters).toHaveProperty('darkShipsOnly');
    expect(typeof state.filters.darkShipsOnly).toBe('boolean');
    expect(state.filters.darkShipsOnly).toBe(false);
  });

  it('darkShipsOnly can be toggled via setFilter', async () => {
    const { useVesselStore } = await import('../hooks/useVesselStore');
    useVesselStore.getState().setFilter({ darkShipsOnly: true });
    expect(useVesselStore.getState().filters.darkShipsOnly).toBe(true);

    useVesselStore.getState().setFilter({ darkShipsOnly: false });
    expect(useVesselStore.getState().filters.darkShipsOnly).toBe(false);
  });
});
