import { useCallback, useMemo } from 'react';
import { Entity, BillboardGraphics } from 'resium';
import {
  Cartesian3,
  NearFarScalar,
  type Viewer as CesiumViewer,
} from 'cesium';
import { useCesium } from 'resium';
import { useVesselStore } from '../../hooks/useVesselStore';
import { useWatchlistStore } from '../../hooks/useWatchlist';
import type { VesselState } from '../../types/vessel';
import { getVesselIcon, MARKER_STYLE, cogToRotation } from '../../utils/vesselIcons';

/** Thin white selection ring for the currently selected vessel. */
const SELECTION_RING_IMAGE = (() => {
  if (typeof document === 'undefined') return '';
  const size = 32;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  return canvas.toDataURL();
})();

/** Spoof indicator — dashed circle with contrasting white dashes. */
export const SPOOF_INDICATOR_IMAGE = (() => {
  if (typeof document === 'undefined') return '';
  const size = 36;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.stroke();
  }
  return canvas.toDataURL();
})();

/** Subtle watchlist indicator — thin dashed circle. */
const HALO_IMAGE = (() => {
  if (typeof document === 'undefined') return '';
  const size = 36;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.stroke();
  }
  return canvas.toDataURL();
})();

/**
 * Filter vessels according to the active FilterState.
 */
export function filterVessels(
  vessels: Map<number, VesselState>,
  filters: { riskTiers: Set<string>; shipTypes: number[]; activeSince: string | null },
): VesselState[] {
  const result: VesselState[] = [];

  for (const vessel of vessels.values()) {
    if (filters.riskTiers.size > 0 && !filters.riskTiers.has(vessel.riskTier)) {
      continue;
    }
    if (
      filters.shipTypes.length > 0 &&
      vessel.shipType != null &&
      !filters.shipTypes.includes(vessel.shipType)
    ) {
      continue;
    }
    if (filters.activeSince && vessel.timestamp < filters.activeSince) {
      continue;
    }
    result.push(vessel);
  }

  // Sort: green drawn first (behind), red on top
  const tierOrder: Record<string, number> = { green: 0, yellow: 1, red: 2, blacklisted: 3 };
  result.sort((a, b) => (tierOrder[a.riskTier] ?? 0) - (tierOrder[b.riskTier] ?? 0));

  return result;
}

/**
 * Determine if an anomaly rule_id represents a spoofing anomaly.
 * Spoofing anomalies have rule_id starting with 'spoof_'.
 */
export function isSpoofAnomaly(ruleId: string): boolean {
  return ruleId.startsWith('spoof_');
}

/** Camera altitude when flying to a vessel (meters). */
const FLY_TO_ALT = 50_000;

/**
 * Inner component that has access to the Cesium viewer context.
 * No animations — the visual theme spec explicitly prohibits pulsing.
 */
function VesselMarkersInner() {
  const { viewer } = useCesium();
  const vessels = useVesselStore((s) => s.vessels);
  const filters = useVesselStore((s) => s.filters);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const watchedMmsis = useWatchlistStore((s) => s.watchedMmsis);
  const spoofedMmsis = useVesselStore((s) => s.spoofedMmsis);

  const handleClick = useCallback(
    (mmsi: number, lat: number, lon: number) => {
      selectVessel(mmsi);
      if (viewer) {
        (viewer as CesiumViewer).camera.flyTo({
          destination: Cartesian3.fromDegrees(lon, lat, FLY_TO_ALT),
          duration: 1.5,
        });
      }
    },
    [selectVessel, viewer],
  );

  const visibleVessels = useMemo(() => filterVessels(vessels, filters), [vessels, filters]);

  return (
    <>
      {visibleVessels.map((v) => {
        const style = MARKER_STYLE[v.riskTier];
        const position = Cartesian3.fromDegrees(v.lon, v.lat);
        return (
          <Entity
            key={v.mmsi}
            id={`vessel-${v.mmsi}`}
            position={position}
            onClick={() => handleClick(v.mmsi, v.lat, v.lon)}
          >
            <BillboardGraphics
              image={getVesselIcon(v.riskTier)}
              scale={style.scale}
              color={undefined}
              rotation={cogToRotation(v.cog)}
              translucencyByDistance={
                new NearFarScalar(1.0e3, style.opacity, 1.5e7, style.opacityFar)
              }
            />
          </Entity>
        );
      })}
      {/* Selection ring for the currently selected vessel */}
      {SELECTION_RING_IMAGE && selectedMmsi != null && visibleVessels
        .filter((v) => v.mmsi === selectedMmsi)
        .map((v) => (
          <Entity
            key={`sel-${v.mmsi}`}
            position={Cartesian3.fromDegrees(v.lon, v.lat)}
          >
            <BillboardGraphics
              image={SELECTION_RING_IMAGE}
              scale={1.2}
              translucencyByDistance={new NearFarScalar(1.0e3, 0.9, 1.5e7, 0.4)}
            />
          </Entity>
        ))}
      {/* Watchlist halo indicators */}
      {HALO_IMAGE && visibleVessels
        .filter((v) => watchedMmsis.has(v.mmsi))
        .map((v) => (
          <Entity
            key={`halo-${v.mmsi}`}
            position={Cartesian3.fromDegrees(v.lon, v.lat)}
          >
            <BillboardGraphics
              image={HALO_IMAGE}
              scale={0.9}
              translucencyByDistance={new NearFarScalar(1.0e3, 0.6, 1.5e7, 0.2)}
            />
          </Entity>
        ))}
      {/* Spoof indicator — dashed circle for vessels with active spoof anomalies */}
      {SPOOF_INDICATOR_IMAGE && visibleVessels
        .filter((v) => spoofedMmsis.has(v.mmsi))
        .map((v) => (
          <Entity
            key={`spoof-${v.mmsi}`}
            position={Cartesian3.fromDegrees(v.lon, v.lat)}
          >
            <BillboardGraphics
              image={SPOOF_INDICATOR_IMAGE}
              scale={1.1}
              translucencyByDistance={new NearFarScalar(1.0e3, 0.9, 1.5e7, 0.4)}
            />
          </Entity>
        ))}
    </>
  );
}

/**
 * Renders vessel markers on the Cesium globe.
 * Must be rendered as a child of a Resium <Viewer>.
 */
export function VesselMarkers() {
  return <VesselMarkersInner />;
}
