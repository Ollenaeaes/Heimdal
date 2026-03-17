import { useEffect } from 'react';
import { useQueries } from '@tanstack/react-query';
import { useLookbackStore } from './useLookbackStore';
import type { TrackPoint } from '../types/api';

interface NetworkResponse {
  mmsi: number;
  edges: Array<{
    vessel_a_mmsi: number;
    vessel_b_mmsi: number;
  }>;
  vessels: Record<string, unknown>;
}

async function fetchTrack(
  mmsi: number,
  start: Date,
  end: Date,
): Promise<TrackPoint[]> {
  const params = new URLSearchParams({
    start: start.toISOString(),
    end: end.toISOString(),
  });
  // Simplify if large time range (>3 days)
  const rangeDays = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);
  if (rangeDays > 3) {
    params.set('simplify', '0.001');
  }
  const res = await fetch(`/api/vessels/${mmsi}/track?${params}`);
  if (!res.ok) throw new Error(`Track fetch failed for ${mmsi}: ${res.status}`);
  return res.json();
}

async function fetchNetworkMmsis(mmsi: number): Promise<number[]> {
  const res = await fetch(`/api/vessels/${mmsi}/network?depth=1`);
  if (!res.ok) return [];
  const data: NetworkResponse = await res.json();
  const mmsis = new Set<number>();
  for (const edge of data.edges) {
    mmsis.add(edge.vessel_a_mmsi);
    mmsis.add(edge.vessel_b_mmsi);
  }
  mmsis.delete(mmsi);
  return [...mmsis];
}

/**
 * Fetches tracks for all lookback vessels (selected + optional network).
 * Writes results directly into the lookback store.
 */
export function useLookbackTracks() {
  const isActive = useLookbackStore((s) => s.isActive);
  const selectedVessels = useLookbackStore((s) => s.selectedVessels);
  const showNetwork = useLookbackStore((s) => s.showNetwork);
  const dateRange = useLookbackStore((s) => s.dateRange);
  const setTracks = useLookbackStore((s) => s.setTracks);
  const setTrackError = useLookbackStore((s) => s.setTrackError);

  // Step 1: Fetch network MMSIs if showNetwork is enabled
  const networkQueries = useQueries({
    queries: isActive && showNetwork
      ? selectedVessels.map((mmsi) => ({
          queryKey: ['lookback-network', mmsi],
          queryFn: () => fetchNetworkMmsis(mmsi),
          staleTime: Infinity,
        }))
      : [],
  });

  // Collect unique network MMSIs
  const networkMmsis = new Set<number>();
  if (showNetwork) {
    for (const q of networkQueries) {
      if (q.data) {
        for (const m of q.data) {
          if (!selectedVessels.includes(m)) {
            networkMmsis.add(m);
          }
        }
      }
    }
  }

  // Update network vessels in store
  useEffect(() => {
    if (isActive && showNetwork) {
      const store = useLookbackStore.getState();
      const current = new Set(store.networkVessels);
      const desired = networkMmsis;
      if (
        current.size !== desired.size ||
        [...desired].some((m) => !current.has(m))
      ) {
        useLookbackStore.setState({ networkVessels: [...desired] });
      }
    }
  }, [isActive, showNetwork, networkMmsis.size]);

  // Step 2: Fetch tracks for all vessels (selected + network)
  const allMmsis = isActive
    ? [...selectedVessels, ...networkMmsis]
    : [];

  const trackQueries = useQueries({
    queries: allMmsis.map((mmsi) => ({
      queryKey: ['lookback-track', mmsi, dateRange.start.toISOString(), dateRange.end.toISOString()],
      queryFn: () => fetchTrack(mmsi, dateRange.start, dateRange.end),
      staleTime: Infinity,
      enabled: isActive,
    })),
  });

  // Sync track results into the lookback store
  useEffect(() => {
    if (!isActive) return;

    for (let i = 0; i < allMmsis.length; i++) {
      const mmsi = allMmsis[i];
      const query = trackQueries[i];
      if (!query) continue;

      if (query.data) {
        setTracks(mmsi, query.data);
      } else if (query.error) {
        setTrackError(
          mmsi,
          query.error instanceof Error ? query.error.message : 'Failed to load track',
        );
      }
    }
  }, [isActive, trackQueries.map((q) => q.dataUpdatedAt).join(',')]);

  const isLoading = trackQueries.some((q) => q.isLoading);
  const allLoaded = trackQueries.every((q) => q.isSuccess || q.isError);

  return { isLoading, allLoaded };
}
