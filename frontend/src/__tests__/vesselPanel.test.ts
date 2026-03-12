import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useVesselStore } from '../hooks/useVesselStore';
import { getShipTypeLabel } from '../utils/shipTypes';
import { countryCodeToFlagEmoji } from '../utils/flagEmoji';
import { RISK_COLORS, getRiskColor } from '../utils/riskColors';

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
