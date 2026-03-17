import { useEffect, useRef, useCallback } from 'react';
import { Math as CesiumMath } from 'cesium';
import { getCesiumViewer } from '../components/Globe/cesiumViewer';
import { useVesselStore } from './useVesselStore';
import type { VesselState } from '../types/vessel';

/** Debounce delay after camera stops moving (ms). */
const DEBOUNCE_MS = 500;

/** Re-fetch green vessels within viewport periodically (ms). */
const REFETCH_MS = 60_000;

/**
 * Compute a deterministic sample rate based on viewport span (degrees).
 * Wider view = fewer green vessels shown. Returns 1 (all) to 10 (every 10th).
 */
function sampleRateFromSpan(lonSpan: number): number {
  if (lonSpan > 120) return 10;  // global view — every 10th
  if (lonSpan > 60) return 5;    // continental — every 5th
  if (lonSpan > 30) return 3;    // multi-country — every 3rd
  if (lonSpan > 15) return 2;    // regional — every 2nd
  return 1;                       // close zoom — show all
}

/**
 * Loads green-tier vessels only within the current camera viewport.
 * Listens to camera moveEnd events and fetches green vessels in the
 * visible bounding box. This avoids loading thousands of green vessels
 * on the other side of the globe. At wider zoom levels, thins results
 * using deterministic sampling (every Nth vessel by MMSI).
 */
export function useViewportGreenVessels() {
  const replaceGreenVessels = useVesselStore((s) => s.replaceGreenVessels);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastBboxRef = useRef<string>('');
  const removeListenerRef = useRef<(() => void) | null>(null);

  const fetchGreenInBbox = useCallback(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    try {
      const rect = viewer.camera.computeViewRectangle();
      if (!rect) return;

      // Add 10% buffer around the viewport
      const dLon = (rect.east - rect.west) * 0.1;
      const dLat = (rect.north - rect.south) * 0.1;

      const sw_lat = CesiumMath.toDegrees(rect.south - dLat);
      const sw_lon = CesiumMath.toDegrees(rect.west - dLon);
      const ne_lat = CesiumMath.toDegrees(rect.north + dLat);
      const ne_lon = CesiumMath.toDegrees(rect.east + dLon);

      const lonSpan = CesiumMath.toDegrees(rect.east - rect.west);
      const sample = sampleRateFromSpan(lonSpan);

      const bboxStr = `${sw_lat.toFixed(2)},${sw_lon.toFixed(2)},${ne_lat.toFixed(2)},${ne_lon.toFixed(2)},s${sample}`;

      // Skip if bbox and sample haven't changed meaningfully
      if (bboxStr === lastBboxRef.current) return;
      lastBboxRef.current = bboxStr;

      const sampleParam = sample > 1 ? `&sample=${sample}` : '';
      fetch(`/api/vessels/snapshot?risk_tiers=green&bbox=${sw_lat.toFixed(2)},${sw_lon.toFixed(2)},${ne_lat.toFixed(2)},${ne_lon.toFixed(2)}${sampleParam}`)
        .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
        .then((data: Array<Record<string, unknown>>) => {
          const vessels: VesselState[] = data.map((d) => ({
            mmsi: d.mmsi as number,
            lat: d.lat as number,
            lon: d.lon as number,
            sog: (d.sog as number) ?? null,
            cog: (d.cog as number) ?? null,
            heading: null,
            riskTier: (d.risk_tier as VesselState['riskTier']) ?? 'green',
            riskScore: (d.risk_score as number) ?? 0,
            name: d.name as string | undefined,
            shipType: d.ship_type as number | undefined,
            timestamp: new Date().toISOString(),
          }));
          replaceGreenVessels(vessels);
        })
        .catch(() => {});
    } catch {
      /* viewer destroyed */
    }
  }, [replaceGreenVessels]);

  useEffect(() => {
    let mounted = true;

    // Wait for Cesium viewer to initialize
    const pollForViewer = setInterval(() => {
      const viewer = getCesiumViewer();
      if (!viewer || viewer.isDestroyed()) return;
      clearInterval(pollForViewer);
      if (!mounted) return;

      // Subscribe to camera movement
      removeListenerRef.current = viewer.camera.moveEnd.addEventListener(() => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(fetchGreenInBbox, DEBOUNCE_MS);
      });

      // Initial fetch after viewer settles
      debounceRef.current = setTimeout(fetchGreenInBbox, 1000);
    }, 200);

    // Periodic refresh of green vessels in viewport
    const refreshInterval = setInterval(() => {
      lastBboxRef.current = ''; // Force refetch
      fetchGreenInBbox();
    }, REFETCH_MS);

    return () => {
      mounted = false;
      clearInterval(pollForViewer);
      clearInterval(refreshInterval);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (removeListenerRef.current) removeListenerRef.current();
    };
  }, [fetchGreenInBbox]);
}
