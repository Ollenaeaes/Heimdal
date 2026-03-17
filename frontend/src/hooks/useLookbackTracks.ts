import { useEffect, useRef } from 'react';
import { useLookbackStore } from './useLookbackStore';
import type { TrackPoint } from '../types/api';

async function fetchTrack(
  mmsi: number,
  start: Date,
  end: Date,
): Promise<TrackPoint[]> {
  const params = new URLSearchParams({
    start: start.toISOString(),
    end: end.toISOString(),
  });
  const rangeDays = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);
  if (rangeDays > 3) {
    params.set('simplify', '0.001');
  }
  const res = await fetch(`/api/vessels/${mmsi}/track?${params}`);
  if (!res.ok) throw new Error(`Track fetch failed for ${mmsi}: ${res.status}`);
  return res.json();
}

async function fetchNetworkMmsis(mmsi: number): Promise<number[]> {
  try {
    const res = await fetch(`/api/vessels/${mmsi}/network?depth=1`);
    if (!res.ok) return [];
    const data = await res.json();
    const mmsis = new Set<number>();
    for (const edge of data.edges ?? []) {
      mmsis.add(edge.vessel_a_mmsi);
      mmsis.add(edge.vessel_b_mmsi);
    }
    mmsis.delete(mmsi);
    return [...mmsis];
  } catch {
    return [];
  }
}

/**
 * Fetches tracks for all lookback vessels when lookback activates.
 * Uses plain fetch + useEffect instead of useQueries to avoid sync issues.
 */
export function useLookbackTracks() {
  const isActive = useLookbackStore((s) => s.isActive);
  const selectedVessels = useLookbackStore((s) => s.selectedVessels);
  const showNetwork = useLookbackStore((s) => s.showNetwork);
  const dateRange = useLookbackStore((s) => s.dateRange);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!isActive || selectedVessels.length === 0) return;

    // Cancel any previous fetch cycle
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const { setTracks, setTrackError } = useLookbackStore.getState();

    async function loadAll() {
      const allMmsis = [...selectedVessels];

      // Resolve network vessels if enabled
      if (showNetwork) {
        const networkResults = await Promise.all(
          selectedVessels.map((mmsi) => fetchNetworkMmsis(mmsi)),
        );
        const networkSet = new Set<number>();
        for (const list of networkResults) {
          for (const m of list) {
            if (!selectedVessels.includes(m)) networkSet.add(m);
          }
        }
        const networkArr = [...networkSet];
        useLookbackStore.setState({ networkVessels: networkArr });
        allMmsis.push(...networkArr);
      }

      if (controller.signal.aborted) return;

      // Fetch all tracks in parallel
      const results = await Promise.allSettled(
        allMmsis.map((mmsi) => fetchTrack(mmsi, dateRange.start, dateRange.end)),
      );

      if (controller.signal.aborted) return;

      for (let i = 0; i < allMmsis.length; i++) {
        const mmsi = allMmsis[i];
        const result = results[i];
        if (result.status === 'fulfilled') {
          setTracks(mmsi, result.value);
        } else {
          setTrackError(mmsi, result.reason?.message ?? 'Failed to load track');
        }
      }
    }

    loadAll();

    return () => {
      controller.abort();
    };
  }, [isActive, selectedVessels.join(','), showNetwork, dateRange.start.getTime(), dateRange.end.getTime()]);
}
