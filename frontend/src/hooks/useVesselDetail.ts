import { useQuery } from '@tanstack/react-query';
import type { VesselDetail } from '../types/api';

async function fetchVesselDetail(mmsi: number): Promise<VesselDetail> {
  const res = await fetch(`/api/vessels/${mmsi}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch vessel ${mmsi}: ${res.status}`);
  }
  return res.json() as Promise<VesselDetail>;
}

export function useVesselDetail(mmsi: number | null) {
  return useQuery<VesselDetail>({
    queryKey: ['vessel', mmsi],
    queryFn: () => fetchVesselDetail(mmsi!),
    enabled: mmsi !== null,
  });
}
