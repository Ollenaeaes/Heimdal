import { useMemo } from 'react';
import { Entity, PolylineGraphics } from 'resium';
import { Cartesian3, Color } from 'cesium';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { TrackPoint } from '../../types/api';

async function fetchTrack(mmsi: number): Promise<TrackPoint[]> {
  const res = await fetch(`/api/vessels/${mmsi}/track?hours=24`);
  if (!res.ok) return [];
  return res.json() as Promise<TrackPoint[]>;
}

/**
 * Renders a track trail polyline for the currently selected vessel.
 * Must be a child of a Resium <Viewer>.
 */
export function TrackTrail() {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);

  const { data: track } = useQuery<TrackPoint[]>({
    queryKey: ['vessel-track', selectedMmsi],
    queryFn: () => fetchTrack(selectedMmsi!),
    enabled: selectedMmsi !== null,
    refetchInterval: 30_000,
  });

  const positions = useMemo(() => {
    if (!track || track.length < 2) return null;
    return Cartesian3.fromDegreesArray(
      track.flatMap((p) => [p.lon, p.lat]),
    );
  }, [track]);

  if (!positions || selectedMmsi === null) return null;

  return (
    <Entity>
      <PolylineGraphics
        positions={positions}
        width={3}
        material={Color.fromCssColorString('#38bdf8').withAlpha(0.8)}
      />
    </Entity>
  );
}
