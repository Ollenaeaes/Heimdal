import type { Viewer } from 'cesium';

export const INITIAL_LON = 15;
export const INITIAL_LAT = 68;
export const INITIAL_ALT = 5_000_000;

/** Module-level viewer reference so other hooks can access the Cesium viewer */
let _globalViewer: Viewer | null = null;

export function getCesiumViewer(): Viewer | null {
  return _globalViewer;
}

export function setCesiumViewer(viewer: Viewer | null): void {
  _globalViewer = viewer;
}
