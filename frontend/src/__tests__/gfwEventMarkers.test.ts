import { describe, it, expect, vi } from 'vitest';

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(() => ({ data: [], isLoading: false })),
}));

import type { GfwEvent, GfwEventType } from '../types/api';
import { GFW_EVENT_COLORS } from '../utils/eventIcons';

// Realistic GFW event test data
const makeGfwEvent = (overrides: Partial<GfwEvent> = {}): GfwEvent => ({
  id: 'gfw-evt-3f9a',
  type: 'ENCOUNTER',
  startTime: '2025-11-14T22:15:00Z',
  endTime: '2025-11-15T03:42:00Z',
  lat: 68.3142,
  lon: 32.8765,
  vesselMmsi: 273456780,
  vesselName: 'Primorsky Prospect',
  encounterPartnerMmsi: 636092587,
  encounterPartnerName: 'Liberian Carrier',
  portName: null,
  durationHours: 5.45,
  ...overrides,
});

describe('GFW Event color constants', () => {
  it('defines correct colors for all event types', () => {
    expect(GFW_EVENT_COLORS.ENCOUNTER).toBe('#E67E22');
    expect(GFW_EVENT_COLORS.LOITERING).toBe('#F1C40F');
    expect(GFW_EVENT_COLORS.AIS_DISABLING).toBe('#C0392B');
    expect(GFW_EVENT_COLORS.PORT_VISIT).toBe('#3498DB');
  });

  it('has entries for all four event types', () => {
    const types: GfwEventType[] = ['ENCOUNTER', 'LOITERING', 'AIS_DISABLING', 'PORT_VISIT'];
    for (const t of types) {
      expect(GFW_EVENT_COLORS[t]).toBeDefined();
      expect(GFW_EVENT_COLORS[t]).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });
});

describe('GFW Event data shape', () => {
  it('creates a valid encounter event', () => {
    const evt = makeGfwEvent();
    expect(evt.type).toBe('ENCOUNTER');
    expect(evt.encounterPartnerMmsi).toBe(636092587);
    expect(evt.encounterPartnerName).toBe('Liberian Carrier');
    expect(evt.durationHours).toBe(5.45);
    expect(evt.vesselMmsi).toBe(273456780);
  });

  it('creates a valid loitering event', () => {
    const evt = makeGfwEvent({
      id: 'gfw-evt-8b2c',
      type: 'LOITERING',
      lat: 36.9215,
      lon: 22.4830,
      vesselMmsi: 538006789,
      vesselName: 'Marshall Islands Tanker',
      encounterPartnerMmsi: null,
      encounterPartnerName: null,
      durationHours: 72.3,
    });
    expect(evt.type).toBe('LOITERING');
    expect(evt.encounterPartnerMmsi).toBeNull();
    expect(evt.durationHours).toBe(72.3);
  });

  it('creates a valid AIS disabling event', () => {
    const evt = makeGfwEvent({
      id: 'gfw-evt-c5d1',
      type: 'AIS_DISABLING',
      lat: 65.7832,
      lon: 12.3456,
      vesselMmsi: 273001234,
      vesselName: 'NS Champion',
      encounterPartnerMmsi: null,
      encounterPartnerName: null,
      portName: null,
      durationHours: 18.0,
    });
    expect(evt.type).toBe('AIS_DISABLING');
    expect(evt.vesselName).toBe('NS Champion');
  });

  it('creates a valid port visit event', () => {
    const evt = makeGfwEvent({
      id: 'gfw-evt-a7e2',
      type: 'PORT_VISIT',
      lat: 60.3500,
      lon: 28.6700,
      vesselMmsi: 273456780,
      vesselName: 'Primorsky Prospect',
      encounterPartnerMmsi: null,
      encounterPartnerName: null,
      portName: 'Primorsk',
      durationHours: 48.5,
    });
    expect(evt.type).toBe('PORT_VISIT');
    expect(evt.portName).toBe('Primorsk');
  });

  it('GFW event has all required fields', () => {
    const evt = makeGfwEvent();
    expect(evt).toHaveProperty('id');
    expect(evt).toHaveProperty('type');
    expect(evt).toHaveProperty('startTime');
    expect(evt).toHaveProperty('lat');
    expect(evt).toHaveProperty('lon');
    expect(typeof evt.id).toBe('string');
    expect(typeof evt.type).toBe('string');
    expect(typeof evt.lat).toBe('number');
    expect(typeof evt.lon).toBe('number');
  });
});

describe('GFW Event type filtering', () => {
  it('filters events by selected event types', () => {
    const events: GfwEvent[] = [
      makeGfwEvent({ id: 'gfw-1', type: 'ENCOUNTER' }),
      makeGfwEvent({ id: 'gfw-2', type: 'LOITERING' }),
      makeGfwEvent({ id: 'gfw-3', type: 'AIS_DISABLING' }),
      makeGfwEvent({ id: 'gfw-4', type: 'PORT_VISIT' }),
      makeGfwEvent({ id: 'gfw-5', type: 'ENCOUNTER' }),
    ];

    const showTypes: GfwEventType[] = ['ENCOUNTER', 'AIS_DISABLING'];
    const filtered = events.filter((e) => showTypes.includes(e.type));
    expect(filtered).toHaveLength(3);
    expect(filtered.every((e) => e.type === 'ENCOUNTER' || e.type === 'AIS_DISABLING')).toBe(true);
  });

  it('returns all events when all types selected', () => {
    const events: GfwEvent[] = [
      makeGfwEvent({ id: 'gfw-1', type: 'ENCOUNTER' }),
      makeGfwEvent({ id: 'gfw-2', type: 'LOITERING' }),
    ];

    const showTypes: GfwEventType[] = ['ENCOUNTER', 'LOITERING', 'AIS_DISABLING', 'PORT_VISIT'];
    const filtered = events.filter((e) => showTypes.includes(e.type));
    expect(filtered).toHaveLength(2);
  });

  it('returns no events when no types selected', () => {
    const events: GfwEvent[] = [
      makeGfwEvent({ id: 'gfw-1', type: 'ENCOUNTER' }),
    ];

    const showTypes: GfwEventType[] = [];
    const filtered = events.filter((e) => showTypes.includes(e.type));
    expect(filtered).toHaveLength(0);
  });

  it('filters a single event type correctly', () => {
    const events: GfwEvent[] = [
      makeGfwEvent({ id: 'gfw-1', type: 'ENCOUNTER' }),
      makeGfwEvent({ id: 'gfw-2', type: 'LOITERING' }),
      makeGfwEvent({ id: 'gfw-3', type: 'PORT_VISIT' }),
    ];

    const showTypes: GfwEventType[] = ['LOITERING'];
    const filtered = events.filter((e) => showTypes.includes(e.type));
    expect(filtered).toHaveLength(1);
    expect(filtered[0].type).toBe('LOITERING');
  });
});

// GfwEventMarkers Cesium component removed in Story 11 (MapLibre migration)

describe('GFW store integration', () => {
  it('showGfwEventTypes filter exists in store with all types enabled by default', async () => {
    const { useVesselStore } = await import('../hooks/useVesselStore');
    const state = useVesselStore.getState();
    expect(state.filters).toHaveProperty('showGfwEventTypes');
    expect(state.filters.showGfwEventTypes).toContain('ENCOUNTER');
    expect(state.filters.showGfwEventTypes).toContain('LOITERING');
    expect(state.filters.showGfwEventTypes).toContain('AIS_DISABLING');
    expect(state.filters.showGfwEventTypes).toContain('PORT_VISIT');
  });

  it('showGfwEventTypes can be updated via setFilter', async () => {
    const { useVesselStore } = await import('../hooks/useVesselStore');
    useVesselStore.getState().setFilter({ showGfwEventTypes: ['ENCOUNTER'] });
    expect(useVesselStore.getState().filters.showGfwEventTypes).toEqual(['ENCOUNTER']);

    // Reset
    useVesselStore.getState().setFilter({ showGfwEventTypes: ['ENCOUNTER', 'LOITERING', 'AIS_DISABLING', 'PORT_VISIT'] });
  });
});
