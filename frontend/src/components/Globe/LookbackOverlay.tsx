import { useMemo } from 'react';
import { Entity, BillboardGraphics, PolylineGraphics } from 'resium';
import { Cartesian3, Color } from 'cesium';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { useVesselStore } from '../../hooks/useVesselStore';
import { getVesselIcon, cogToRotation } from '../../utils/vesselIcons';
import { RISK_COLORS } from '../../utils/riskColors';
import type { TrackPoint } from '../../types/api';

/** Interpolate position at a given time between two track points. */
function interpolatePosition(
  before: TrackPoint,
  after: TrackPoint,
  time: Date,
): { lat: number; lon: number; cog: number | null; sog: number | null } {
  const t1 = new Date(before.timestamp).getTime();
  const t2 = new Date(after.timestamp).getTime();
  const t = time.getTime();

  if (t2 === t1) return { lat: before.lat, lon: before.lon, cog: before.cog, sog: before.sog };

  const ratio = (t - t1) / (t2 - t1);
  return {
    lat: before.lat + (after.lat - before.lat) * ratio,
    lon: before.lon + (after.lon - before.lon) * ratio,
    cog: after.cog,
    sog: before.sog !== null && after.sog !== null
      ? before.sog + (after.sog - before.sog) * ratio
      : after.sog,
  };
}

/** Find the interpolated position for a vessel at the given time. */
function getPositionAtTime(
  track: TrackPoint[],
  time: Date,
): { lat: number; lon: number; cog: number | null; sog: number | null } | null {
  if (track.length === 0) return null;

  const timeMs = time.getTime();
  const firstMs = new Date(track[0].timestamp).getTime();
  const lastMs = new Date(track[track.length - 1].timestamp).getTime();

  if (timeMs <= firstMs) {
    return { lat: track[0].lat, lon: track[0].lon, cog: track[0].cog, sog: track[0].sog };
  }
  if (timeMs >= lastMs) {
    const last = track[track.length - 1];
    return { lat: last.lat, lon: last.lon, cog: last.cog, sog: last.sog };
  }

  // Binary search for surrounding points
  let lo = 0;
  let hi = track.length - 1;
  while (lo < hi - 1) {
    const mid = Math.floor((lo + hi) / 2);
    const midMs = new Date(track[mid].timestamp).getTime();
    if (midMs <= timeMs) {
      lo = mid;
    } else {
      hi = mid;
    }
  }

  return interpolatePosition(track[lo], track[hi], time);
}

/** Get track trail positions up to the current time. */
function getTrailPositions(track: TrackPoint[], currentTime: Date): Cartesian3[] {
  const currentMs = currentTime.getTime();
  const positions: Cartesian3[] = [];

  for (const pt of track) {
    const ptMs = new Date(pt.timestamp).getTime();
    if (ptMs > currentMs) break;
    positions.push(Cartesian3.fromDegrees(pt.lon, pt.lat));
  }

  // Add interpolated current position
  const pos = getPositionAtTime(track, currentTime);
  if (pos && positions.length > 0) {
    positions.push(Cartesian3.fromDegrees(pos.lon, pos.lat));
  }

  return positions;
}

export function LookbackOverlay() {
  const isActive = useLookbackStore((s) => s.isActive);
  const selectedVessels = useLookbackStore((s) => s.selectedVessels);
  const networkVessels = useLookbackStore((s) => s.networkVessels);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const tracks = useLookbackStore((s) => s.tracks);
  const isAreaMode = useLookbackStore((s) => s.isAreaMode);
  const areaPolygon = useLookbackStore((s) => s.areaPolygon);
  const vessels = useVesselStore((s) => s.vessels);

  // Compute current positions for all vessels
  const vesselPositions = useMemo(() => {
    if (!isActive) return [];

    const allMmsis = [...selectedVessels, ...networkVessels];
    const result: Array<{
      mmsi: number;
      lat: number;
      lon: number;
      cog: number | null;
      sog: number | null;
      isNetwork: boolean;
      riskTier: string;
    }> = [];

    for (const mmsi of allMmsis) {
      const track = tracks.get(mmsi);
      if (!track || track.length === 0) continue;

      const pos = getPositionAtTime(track, currentTime);
      if (!pos) continue;

      const vesselData = vessels.get(mmsi);
      result.push({
        mmsi,
        ...pos,
        isNetwork: networkVessels.includes(mmsi),
        riskTier: vesselData?.riskTier ?? 'green',
      });
    }

    return result;
  }, [isActive, selectedVessels, networkVessels, currentTime, tracks, vessels]);

  // Compute trail positions for each vessel
  const trailData = useMemo(() => {
    if (!isActive) return [];

    const allMmsis = [...selectedVessels, ...networkVessels];
    const result: Array<{
      mmsi: number;
      positions: Cartesian3[];
      isNetwork: boolean;
      riskTier: string;
    }> = [];

    for (const mmsi of allMmsis) {
      const track = tracks.get(mmsi);
      if (!track || track.length < 2) continue;

      const vesselData = vessels.get(mmsi);
      result.push({
        mmsi,
        positions: getTrailPositions(track, currentTime),
        isNetwork: networkVessels.includes(mmsi),
        riskTier: vesselData?.riskTier ?? 'green',
      });
    }

    return result;
  }, [isActive, selectedVessels, networkVessels, currentTime, tracks, vessels]);

  if (!isActive) return null;

  return (
    <>
      {/* Track trails */}
      {trailData.map((trail) => {
        if (trail.positions.length < 2) return null;
        const color = RISK_COLORS[trail.riskTier as keyof typeof RISK_COLORS] ?? '#22C55E';
        const alpha = trail.isNetwork ? 0.25 : 0.6;
        const width = trail.isNetwork ? 1 : 2;

        return (
          <Entity key={`lookback-trail-${trail.mmsi}`}>
            <PolylineGraphics
              positions={trail.positions}
              width={width}
              material={Color.fromCssColorString(color).withAlpha(alpha)}
            />
          </Entity>
        );
      })}

      {/* Vessel markers */}
      {vesselPositions.map((v) => {
        const position = Cartesian3.fromDegrees(v.lon, v.lat);
        const scale = v.isNetwork ? 0.35 : 0.6;
        const alpha = v.isNetwork ? 0.4 : 1.0;
        const tier = v.riskTier as keyof typeof RISK_COLORS;

        return (
          <Entity
            key={`lookback-marker-${v.mmsi}`}
            position={position}
            name={`Lookback: ${v.mmsi}`}
            description={`MMSI: ${v.mmsi} | SOG: ${v.sog?.toFixed(1) ?? 'N/A'} kn | ${v.isNetwork ? 'Network' : 'Selected'}`}
          >
            <BillboardGraphics
              image={getVesselIcon(tier)}
              scale={scale}
              rotation={cogToRotation(v.cog)}
              color={Color.WHITE.withAlpha(alpha)}
            />
          </Entity>
        );
      })}

      {/* Area polygon overlay (if in area mode) */}
      {isAreaMode && areaPolygon && areaPolygon.length >= 3 && (
        <Entity key="lookback-area-polygon">
          <PolylineGraphics
            positions={[
              ...areaPolygon.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat)),
              Cartesian3.fromDegrees(areaPolygon[0][0], areaPolygon[0][1]),
            ]}
            width={2}
            material={Color.fromCssColorString('#3B82F6').withAlpha(0.6)}
          />
        </Entity>
      )}
    </>
  );
}
