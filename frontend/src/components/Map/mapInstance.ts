import type { Map } from 'maplibre-gl';

let mapInstance: Map | null = null;

export function getMapInstance(): Map | null {
  return mapInstance;
}

export function setMapInstance(map: Map | null) {
  mapInstance = map;
}

export const INITIAL_CENTER: [number, number] = [15, 68]; // lon, lat
export const INITIAL_ZOOM = 4;
