import { describe, it, expect } from 'vitest';
import { HoverTooltip, getShipTypeLabel } from '../components/Map/HoverTooltip';
import type { TooltipData } from '../components/Map/HoverTooltip';

describe('HoverTooltip', () => {
  it('exports HoverTooltip component', () => {
    expect(HoverTooltip).toBeDefined();
    expect(typeof HoverTooltip).toBe('function');
  });

  it('exports TooltipData type (compile-time check)', () => {
    // Type-level check — if this compiles, the type is exported correctly
    const vesselTooltip: TooltipData = {
      type: 'vessel',
      x: 100,
      y: 200,
      mmsi: 123456789,
    };
    const infraTooltip: TooltipData = {
      type: 'infrastructure',
      x: 100,
      y: 200,
      name: 'Test Cable',
      routeType: 'telecom_cable',
    };
    expect(vesselTooltip.type).toBe('vessel');
    expect(infraTooltip.type).toBe('infrastructure');
  });
});

describe('getShipTypeLabel', () => {
  it('returns "Vessel" for null/undefined', () => {
    expect(getShipTypeLabel(null)).toBe('Vessel');
    expect(getShipTypeLabel(undefined)).toBe('Vessel');
  });

  it('returns correct labels for known ship type ranges', () => {
    expect(getShipTypeLabel(70)).toBe('Cargo');
    expect(getShipTypeLabel(79)).toBe('Cargo');
    expect(getShipTypeLabel(80)).toBe('Tanker');
    expect(getShipTypeLabel(89)).toBe('Tanker');
    expect(getShipTypeLabel(60)).toBe('Passenger');
    expect(getShipTypeLabel(69)).toBe('Passenger');
    expect(getShipTypeLabel(30)).toBe('Fishing');
    expect(getShipTypeLabel(39)).toBe('Fishing');
    expect(getShipTypeLabel(40)).toBe('HSC');
    expect(getShipTypeLabel(49)).toBe('HSC');
    expect(getShipTypeLabel(50)).toBe('Special Craft');
    expect(getShipTypeLabel(59)).toBe('Special Craft');
  });

  it('returns "Vessel" for unknown ship types', () => {
    expect(getShipTypeLabel(0)).toBe('Vessel');
    expect(getShipTypeLabel(99)).toBe('Vessel');
    expect(getShipTypeLabel(20)).toBe('Vessel');
  });
});
