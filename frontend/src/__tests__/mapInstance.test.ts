import { describe, it, expect, beforeEach } from 'vitest';
import {
  getMapInstance,
  setMapInstance,
  INITIAL_CENTER,
  INITIAL_ZOOM,
} from '../components/Map/mapInstance';

describe('mapInstance', () => {
  beforeEach(() => {
    setMapInstance(null);
  });

  it('starts with null instance', () => {
    expect(getMapInstance()).toBeNull();
  });

  it('get/set round-trips a value', () => {
    const fakeMap = { id: 'test' } as unknown as import('maplibre-gl').Map;
    setMapInstance(fakeMap);
    expect(getMapInstance()).toBe(fakeMap);
  });

  it('can be reset to null', () => {
    const fakeMap = { id: 'test' } as unknown as import('maplibre-gl').Map;
    setMapInstance(fakeMap);
    setMapInstance(null);
    expect(getMapInstance()).toBeNull();
  });

  it('exports correct initial center', () => {
    expect(INITIAL_CENTER).toEqual([15, 68]);
  });

  it('exports correct initial zoom', () => {
    expect(INITIAL_ZOOM).toBe(4);
  });
});
