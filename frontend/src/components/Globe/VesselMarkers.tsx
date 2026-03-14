import { useRef, useCallback, useMemo } from 'react';
import { Entity, BillboardGraphics } from 'resium';
import {
  Cartesian3,
  ConstantProperty,
  CallbackProperty,
  NearFarScalar,
  type Viewer as CesiumViewer,
} from 'cesium';
import { useCesium } from 'resium';
import { useVesselStore } from '../../hooks/useVesselStore';
import { useWatchlistStore } from '../../hooks/useWatchlist';
import type { VesselState } from '../../types/vessel';
import { getVesselIcon, MARKER_STYLE, cogToRotation } from '../../utils/vesselIcons';

/** Create a simple white circle data URI for the watchlist halo. */
const HALO_IMAGE = (() => {
  if (typeof document === 'undefined') return '';
  const size = 48;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  return canvas.toDataURL();
})();

/** Bright white selection ring for the currently selected vessel. */
const SELECTION_RING_IMAGE = (() => {
  if (typeof document === 'undefined') return '';
  const size = 48;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
    ctx.lineWidth = 3;
    ctx.stroke();
  }
  return canvas.toDataURL();
})();

/** Semi-transparent amber glow billboard for yellow-tier vessels. */
const AMBER_GLOW_IMAGE = (() => {
  if (typeof document === 'undefined') return '';
  const size = 56;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    const cx = size / 2;
    const gradient = ctx.createRadialGradient(cx, cx, 4, cx, cx, cx - 2);
    gradient.addColorStop(0, 'rgba(245, 158, 11, 0.35)');
    gradient.addColorStop(1, 'rgba(245, 158, 11, 0)');
    ctx.beginPath();
    ctx.arc(cx, cx, cx - 2, 0, Math.PI * 2);
    ctx.fillStyle = gradient;
    ctx.fill();
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
    // Risk tier filter — empty set means "show all"
    if (filters.riskTiers.size > 0 && !filters.riskTiers.has(vessel.riskTier)) {
      continue;
    }
    // Ship type filter — empty array means "show all"
    if (
      filters.shipTypes.length > 0 &&
      vessel.shipType != null &&
      !filters.shipTypes.includes(vessel.shipType)
    ) {
      continue;
    }
    // Active-since filter
    if (filters.activeSince && vessel.timestamp < filters.activeSince) {
      continue;
    }
    result.push(vessel);
  }

  // Sort so high-risk vessels render last (on top of green ones)
  const tierOrder: Record<string, number> = { green: 0, yellow: 1, red: 2 };
  result.sort((a, b) => (tierOrder[a.riskTier] ?? 0) - (tierOrder[b.riskTier] ?? 0));

  return result;
}

/** Camera altitude when flying to a vessel (meters). */
const FLY_TO_ALT = 50_000;

/**
 * Inner component that has access to the Cesium viewer context.
 */
function VesselMarkersInner() {
  const { viewer } = useCesium();
  const vessels = useVesselStore((s) => s.vessels);
  const filters = useVesselStore((s) => s.filters);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const watchedMmsis = useWatchlistStore((s) => s.watchedMmsis);

  // Pulsing scale for red vessels — oscillates between 1.0x and 1.15x at ~1Hz
  const pulseRef = useRef(0);
  const redPulseScale = useMemo(
    () =>
      new CallbackProperty(() => {
        pulseRef.current = (pulseRef.current + 0.06) % (2 * Math.PI);
        const pulse = 1.0 + 0.15 * Math.sin(pulseRef.current);
        return MARKER_STYLE.red.scale * pulse;
      }, false),
    [],
  );

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
        const isRed = v.riskTier === 'red';
        const position = Cartesian3.fromDegrees(v.lon, v.lat);
        return (
          <Entity
            key={v.mmsi}
            position={position}
            onClick={() => handleClick(v.mmsi, v.lat, v.lon)}
          >
            <BillboardGraphics
              image={getVesselIcon(v.riskTier)}
              scale={isRed ? (redPulseScale as unknown as number) : style.scale}
              color={undefined}
              rotation={new ConstantProperty(cogToRotation(v.cog))}
              alignedAxis={Cartesian3.UNIT_Z}
              translucencyByDistance={
                new NearFarScalar(1.0e3, style.opacity, 1.5e7, style.opacity * 0.6)
              }
            />
          </Entity>
        );
      })}
      {/* Amber glow behind yellow-tier vessels */}
      {AMBER_GLOW_IMAGE && visibleVessels
        .filter((v) => v.riskTier === 'yellow')
        .map((v) => (
          <Entity
            key={`glow-${v.mmsi}`}
            position={Cartesian3.fromDegrees(v.lon, v.lat)}
          >
            <BillboardGraphics
              image={AMBER_GLOW_IMAGE}
              scale={1.2}
              translucencyByDistance={new NearFarScalar(1.0e3, 0.6, 1.5e7, 0.2)}
            />
          </Entity>
        ))}
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
              scale={1.0}
              translucencyByDistance={new NearFarScalar(1.0e3, 1.0, 1.5e7, 0.6)}
            />
          </Entity>
        ))}
      {/* Watchlist halo indicators — rendered behind vessel markers */}
      {HALO_IMAGE && visibleVessels
        .filter((v) => watchedMmsis.has(v.mmsi))
        .map((v) => (
          <Entity
            key={`halo-${v.mmsi}`}
            position={Cartesian3.fromDegrees(v.lon, v.lat)}
          >
            <BillboardGraphics
              image={HALO_IMAGE}
              scale={0.8}
              translucencyByDistance={new NearFarScalar(1.0e3, 0.8, 1.5e7, 0.3)}
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
