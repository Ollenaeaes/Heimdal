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
import type { VesselState } from '../../types/vessel';
import { getVesselIcon, MARKER_STYLE, cogToRotation } from '../../utils/vesselIcons';

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

  // Pulsing scale for red vessels — oscillates between 0.8 and 1.2
  const pulseRef = useRef(0);
  const redPulseScale = useMemo(
    () =>
      new CallbackProperty(() => {
        pulseRef.current = (pulseRef.current + 0.02) % (2 * Math.PI);
        const pulse = 1.0 + 0.2 * Math.sin(pulseRef.current);
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
