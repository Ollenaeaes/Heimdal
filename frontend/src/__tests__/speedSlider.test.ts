import { describe, it, expect } from 'vitest';
import { speedToSlider, sliderToSpeed, formatSpeedLabel } from '../components/Map/SpeedSlider';

describe('speedToSlider / sliderToSpeed inverse', () => {
  it('boundary: 60 (1 min/sec) → slider 0', () => {
    expect(speedToSlider(60)).toBeCloseTo(0, 5);
    expect(sliderToSpeed(0)).toBeCloseTo(60, 1);
  });

  it('boundary: 18000 (5 hr/sec) → slider 100', () => {
    expect(speedToSlider(18000)).toBeCloseTo(100, 5);
    expect(sliderToSpeed(100)).toBeCloseTo(18000, 0);
  });

  it('midpoint: 1800 (30 min/sec) round-trips', () => {
    const slider = speedToSlider(1800);
    const speed = sliderToSpeed(slider);
    expect(speed).toBeCloseTo(1800, 0);
  });

  it('round-trips at various values', () => {
    for (const speed of [60, 120, 600, 1800, 3600, 10800, 18000]) {
      const slider = speedToSlider(speed);
      const recovered = sliderToSpeed(slider);
      expect(recovered).toBeCloseTo(speed, 0);
    }
  });
});

describe('formatSpeedLabel', () => {
  it('60 → "1 min/sec"', () => {
    expect(formatSpeedLabel(60)).toBe('1 min/sec');
  });

  it('600 → "10 min/sec"', () => {
    expect(formatSpeedLabel(600)).toBe('10 min/sec');
  });

  it('1800 → "30 min/sec"', () => {
    expect(formatSpeedLabel(1800)).toBe('30 min/sec');
  });

  it('3600 → "1 hr/sec"', () => {
    expect(formatSpeedLabel(3600)).toBe('1 hr/sec');
  });

  it('10800 → "3 hr/sec"', () => {
    expect(formatSpeedLabel(10800)).toBe('3 hr/sec');
  });

  it('18000 → "5 hr/sec"', () => {
    expect(formatSpeedLabel(18000)).toBe('5 hr/sec');
  });
});

describe('slider range', () => {
  it('sliderToSpeed at 0 gives minimum speed (60)', () => {
    expect(sliderToSpeed(0)).toBeCloseTo(60, 1);
  });

  it('sliderToSpeed at 100 gives maximum speed (18000)', () => {
    expect(sliderToSpeed(100)).toBeCloseTo(18000, 0);
  });

  it('speedToSlider maps full range to 0–100', () => {
    expect(speedToSlider(60)).toBeCloseTo(0, 5);
    expect(speedToSlider(18000)).toBeCloseTo(100, 5);
  });
});

describe('edge cases: clamping', () => {
  it('value below 60 clamps to 60 in speedToSlider', () => {
    expect(speedToSlider(10)).toBeCloseTo(0, 5);
    expect(speedToSlider(0)).toBeCloseTo(0, 5);
    expect(speedToSlider(-100)).toBeCloseTo(0, 5);
  });

  it('value above 18000 clamps to 18000 in speedToSlider', () => {
    expect(speedToSlider(20000)).toBeCloseTo(100, 5);
    expect(speedToSlider(100000)).toBeCloseTo(100, 5);
  });

  it('slider below 0 clamps in sliderToSpeed', () => {
    expect(sliderToSpeed(-10)).toBeCloseTo(60, 1);
  });

  it('slider above 100 clamps in sliderToSpeed', () => {
    expect(sliderToSpeed(150)).toBeCloseTo(18000, 0);
  });

  it('formatSpeedLabel clamps below 60', () => {
    expect(formatSpeedLabel(10)).toBe('1 min/sec');
  });

  it('formatSpeedLabel clamps above 18000', () => {
    expect(formatSpeedLabel(50000)).toBe('5 hr/sec');
  });
});
