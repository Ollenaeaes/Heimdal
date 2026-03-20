/**
 * No-op stub — the Cesium imperative overlay system has been replaced by
 * MapLibre declarative layers. This export remains so that App.tsx compiles
 * without changes to the overlay toggle wiring. Will be removed in Story 11.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useOverlays(_overlays: any) {
  /* will be removed in Story 11 */
}
