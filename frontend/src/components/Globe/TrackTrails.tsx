import { useMemo } from 'react';
import { Entity, PolylineGraphics } from 'resium';
import { Cartesian3, Color } from 'cesium';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { PositionHistoryEntry } from '../../hooks/useVesselStore';
import { RISK_COLORS, type RiskTier } from '../../utils/riskColors';

export interface TrackTrailsProps {
  /** Whether track trails are rendered (default: true) */
  enabled?: boolean;
  /** Maximum trail age in hours (default: 1) */
  maxAgeHours?: number;
}

/**
 * Build a color array for a Cesium polyline where each segment fades
 * from transparent (oldest) to full opacity (newest / vessel position).
 */
export function buildTrailColors(riskTier: RiskTier, pointCount: number): Color[] {
  const base = Color.fromCssColorString(RISK_COLORS[riskTier]);
  const colors: Color[] = [];
  for (let i = 0; i < pointCount; i++) {
    // alpha goes from 0 (oldest, i=0) to 1 (newest, i=pointCount-1)
    const alpha = pointCount > 1 ? i / (pointCount - 1) : 1;
    colors.push(base.withAlpha(alpha));
  }
  return colors;
}

/**
 * Filter history entries to only include those within maxAgeHours of the newest entry.
 */
export function filterHistoryByAge(
  history: PositionHistoryEntry[],
  maxAgeHours: number,
): PositionHistoryEntry[] {
  if (history.length === 0) return [];
  const newestTime = new Date(history[history.length - 1].timestamp).getTime();
  const maxAgeMs = maxAgeHours * 60 * 60 * 1000;
  return history.filter(
    (e) => newestTime - new Date(e.timestamp).getTime() <= maxAgeMs,
  );
}

/**
 * Renders a fading polyline trail behind each vessel, colored by risk tier.
 * Must be rendered as a child of a Resium <Viewer>.
 */
export function TrackTrails({ enabled = true, maxAgeHours = 1 }: TrackTrailsProps) {
  const positionHistory = useVesselStore((s) => s.positionHistory);
  const vessels = useVesselStore((s) => s.vessels);

  const trails = useMemo(() => {
    if (!enabled) return [];

    const result: Array<{
      mmsi: number;
      positions: Cartesian3[];
      colors: Color[];
    }> = [];

    for (const [mmsi, history] of positionHistory) {
      const vessel = vessels.get(mmsi);
      if (!vessel) continue;

      const filtered = filterHistoryByAge(history, maxAgeHours);
      // Need at least 2 points to draw a line
      if (filtered.length < 2) continue;

      const positions = filtered.map((e) =>
        Cartesian3.fromDegrees(e.lon, e.lat),
      );
      const colors = buildTrailColors(vessel.riskTier, filtered.length);

      result.push({ mmsi, positions, colors });
    }

    return result;
  }, [enabled, positionHistory, vessels, maxAgeHours]);

  if (!enabled) return null;

  return (
    <>
      {trails.map(({ mmsi, positions, colors }) => (
        <Entity key={`trail-${mmsi}`}>
          <PolylineGraphics
            positions={positions}
            width={3}
            material={colors[colors.length - 1]}
            clampToGround={false}
          />
        </Entity>
      ))}
    </>
  );
}
