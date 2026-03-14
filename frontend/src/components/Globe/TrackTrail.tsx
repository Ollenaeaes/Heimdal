import { useMemo } from 'react';
import { Entity, PolylineGraphics } from 'resium';
import { Cartesian3, Color, PolylineDashMaterialProperty } from 'cesium';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';
import { RISK_COLORS } from '../../utils/riskColors';
import type { RiskTier } from '../../utils/riskColors';
import type { TrackPoint } from '../../types/api';

async function fetchTrack(mmsi: number): Promise<TrackPoint[]> {
  const res = await fetch(`/api/vessels/${mmsi}/track?hours=24`);
  if (!res.ok) return [];
  return res.json() as Promise<TrackPoint[]>;
}

/** AIS gap threshold in milliseconds (10 minutes) */
const GAP_THRESHOLD_MS = 10 * 60 * 1000;

/** Width tiers from oldest to newest */
const WIDTH_TIERS = [0.5, 1, 1.5, 2] as const;

interface TrackSegment {
  positions: Cartesian3[];
  isGap: boolean;
  /** Index of the width tier (0 = oldest, 3 = newest) */
  widthTierIndex: number;
}

/**
 * Splits track points into segments based on AIS gaps and assigns width tiers
 * based on recency.
 */
function buildSegments(track: TrackPoint[]): TrackSegment[] {
  if (track.length < 2) return [];

  const totalPoints = track.length;
  const tierSize = Math.max(1, Math.ceil(totalPoints / WIDTH_TIERS.length));

  const segments: TrackSegment[] = [];
  let currentPositions: Cartesian3[] = [
    Cartesian3.fromDegrees(track[0].lon, track[0].lat),
  ];
  let currentIsGap = false;
  // Track points are ordered oldest-first; index 0 = oldest
  let currentWidthTier = 0;

  for (let i = 1; i < totalPoints; i++) {
    const prev = track[i - 1];
    const curr = track[i];
    const prevTime = new Date(prev.timestamp).getTime();
    const currTime = new Date(curr.timestamp).getTime();
    const gap = Math.abs(currTime - prevTime);
    const isGap = gap > GAP_THRESHOLD_MS;
    const widthTier = Math.min(
      Math.floor(i / tierSize),
      WIDTH_TIERS.length - 1,
    );

    // Start a new segment when gap type changes or width tier changes
    if (isGap !== currentIsGap || widthTier !== currentWidthTier) {
      // Finish current segment — it needs at least 2 points
      if (currentPositions.length >= 2) {
        segments.push({
          positions: currentPositions,
          isGap: currentIsGap,
          widthTierIndex: currentWidthTier,
        });
      }
      // New segment starts with the previous point (for continuity)
      currentPositions = [
        Cartesian3.fromDegrees(prev.lon, prev.lat),
      ];
      currentIsGap = isGap;
      currentWidthTier = widthTier;
    }

    currentPositions.push(Cartesian3.fromDegrees(curr.lon, curr.lat));
  }

  // Push the final segment
  if (currentPositions.length >= 2) {
    segments.push({
      positions: currentPositions,
      isGap: currentIsGap,
      widthTierIndex: currentWidthTier,
    });
  }

  return segments;
}

/**
 * Renders a track trail polyline for the currently selected vessel.
 * - Color matches the vessel's risk tier at reduced opacity
 * - Width tapers from 2px (newest) to 0.5px (oldest) in 4 discrete tiers
 * - AIS gaps (>10 min) render as dashed segments; continuous positions as solid
 *
 * Must be a child of a Resium <Viewer>.
 */
export function TrackTrail() {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const vessel = useVesselStore((s) =>
    s.selectedMmsi !== null ? s.vessels.get(s.selectedMmsi) : undefined,
  );

  const { data: track } = useQuery<TrackPoint[]>({
    queryKey: ['vessel-track', selectedMmsi],
    queryFn: () => fetchTrack(selectedMmsi!),
    enabled: selectedMmsi !== null,
    refetchInterval: 30_000,
  });

  const riskTier: RiskTier = vessel?.riskTier ?? 'green';
  const baseColor = Color.fromCssColorString(RISK_COLORS[riskTier]);
  const trailColor = baseColor.withAlpha(0.6);

  const segments = useMemo(() => {
    if (!track || track.length < 2) return [];
    return buildSegments(track);
  }, [track]);

  if (segments.length === 0 || selectedMmsi === null) return null;

  return (
    <>
      {segments.map((seg, idx) => {
        const width = WIDTH_TIERS[seg.widthTierIndex];
        const material = seg.isGap
          ? new PolylineDashMaterialProperty({
              color: trailColor,
              dashLength: 12,
            })
          : trailColor;

        return (
          <Entity key={`track-seg-${idx}`}>
            <PolylineGraphics
              positions={seg.positions}
              width={width}
              material={material}
            />
          </Entity>
        );
      })}
    </>
  );
}
