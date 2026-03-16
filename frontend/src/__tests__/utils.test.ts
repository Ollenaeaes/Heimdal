import { describe, it, expect } from 'vitest';
import { getRiskColor, RISK_COLORS } from '../utils/riskColors';
import {
  formatCoordinate,
  formatSpeed,
  formatCourse,
  formatTimestampAbsolute,
} from '../utils/formatters';
import stsZones from '../data/stsZones.json';
import terminals from '../data/terminals.json';

describe('riskColors', () => {
  it('returns correct hex for green', () => {
    expect(getRiskColor('green')).toBe('#22C55E');
  });

  it('returns correct hex for yellow', () => {
    expect(getRiskColor('yellow')).toBe('#F59E0B');
  });

  it('returns correct hex for red', () => {
    expect(getRiskColor('red')).toBe('#EF4444');
  });

  it('RISK_COLORS has exactly 4 tiers', () => {
    expect(Object.keys(RISK_COLORS)).toEqual(['green', 'yellow', 'red', 'blacklisted']);
  });
});

describe('formatCoordinate', () => {
  it('formats latitude in DMS (positive = N)', () => {
    // 68.1230 -> 68 deg 07'22.8"N
    const result = formatCoordinate(68.123, 'lat');
    expect(result).toContain('68');
    expect(result).toContain('N');
    expect(result).toContain("07'");
  });

  it('formats negative latitude as S', () => {
    const result = formatCoordinate(-33.85, 'lat');
    expect(result).toContain('S');
    expect(result).toContain('33');
  });

  it('formats longitude in DMS (positive = E)', () => {
    const result = formatCoordinate(28.67, 'lon');
    expect(result).toContain('E');
    expect(result).toContain('28');
  });

  it('formats negative longitude as W', () => {
    const result = formatCoordinate(-5.31, 'lon');
    expect(result).toContain('W');
    expect(result).toContain('5');
  });
});

describe('formatSpeed', () => {
  it('formats valid knots', () => {
    expect(formatSpeed(12.3)).toBe('12.3 kn');
  });

  it('returns N/A for null', () => {
    expect(formatSpeed(null)).toBe('N/A');
  });

  it('formats zero speed', () => {
    expect(formatSpeed(0)).toBe('0.0 kn');
  });
});

describe('formatCourse', () => {
  it('formats valid course', () => {
    expect(formatCourse(180.5)).toBe('180.5\u00B0');
  });

  it('returns N/A for null', () => {
    expect(formatCourse(null)).toBe('N/A');
  });
});

describe('formatTimestampAbsolute', () => {
  it('formats ISO timestamp to UTC string', () => {
    const result = formatTimestampAbsolute('2024-03-15T14:30:00Z');
    expect(result).toBe('2024-03-15 14:30:00 UTC');
  });
});

describe('stsZones.json', () => {
  it('has 6 STS zones', () => {
    expect(stsZones.features).toHaveLength(6);
  });

  it('each zone has a name and polygon geometry', () => {
    for (const feature of stsZones.features) {
      expect(feature.properties.name).toBeTruthy();
      expect(feature.geometry.type).toBe('Polygon');
    }
  });

  it('contains Kalamata zone', () => {
    const kalamata = stsZones.features.find((f) =>
      f.properties.name.includes('Kalamata')
    );
    expect(kalamata).toBeDefined();
  });
});

describe('terminals.json', () => {
  it('has 7 Russian terminals', () => {
    expect(terminals.features).toHaveLength(7);
  });

  it('each terminal has a name and point geometry', () => {
    for (const feature of terminals.features) {
      expect(feature.properties.name).toBeTruthy();
      expect(feature.geometry.type).toBe('Point');
    }
  });

  it('contains Primorsk terminal', () => {
    const primorsk = terminals.features.find((f) =>
      f.properties.name.includes('Primorsk')
    );
    expect(primorsk).toBeDefined();
  });
});
