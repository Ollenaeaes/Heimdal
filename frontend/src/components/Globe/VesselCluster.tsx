import { useEffect, useMemo, useRef, useCallback } from 'react';
import { CustomDataSource, Entity, BillboardGraphics } from 'resium';
import { useCesium } from 'resium';
import {
  Cartesian3,
  ConstantProperty,
  CallbackProperty,
  NearFarScalar,
  type Viewer as CesiumViewer,
  type CustomDataSource as CesiumCustomDataSource,
  type Entity as CesiumEntity,
} from 'cesium';
import { useVesselStore } from '../../hooks/useVesselStore';
import { filterVessels } from './VesselMarkers';
import { RISK_COLORS, type RiskTier } from '../../utils/riskColors';
import { getVesselIcon, MARKER_STYLE, cogToRotation } from '../../utils/vesselIcons';

/** Cluster pixel range — distance in pixels below which entities cluster. */
export const CLUSTER_PIXEL_RANGE = 50;

/** Minimum cluster size before clustering activates. */
const CLUSTER_MIN_SIZE = 2;

/** Risk tier priority for determining cluster color (higher = more severe). */
const RISK_TIER_PRIORITY: Record<RiskTier, number> = {
  green: 0,
  yellow: 1,
  red: 2,
  blacklisted: 3,
};

const RISK_TIERS_BY_PRIORITY: RiskTier[] = ['green', 'yellow', 'red', 'blacklisted'];

/**
 * Given an array of risk tiers, return the highest-severity tier.
 * Exported for testing.
 */
export function getHighestRiskTier(tiers: RiskTier[]): RiskTier {
  if (tiers.length === 0) return 'green';
  let maxPriority = 0;
  for (const tier of tiers) {
    const p = RISK_TIER_PRIORITY[tier];
    if (p > maxPriority) maxPriority = p;
  }
  return RISK_TIERS_BY_PRIORITY[maxPriority];
}

/**
 * Create a cluster label canvas showing the count, colored by risk tier.
 */
function createClusterCanvas(count: number, riskTier: RiskTier): HTMLCanvasElement {
  const size = 48;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;

  // Circle background
  const color = RISK_COLORS[riskTier];
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 2, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 2;
  ctx.stroke();

  // Count text
  ctx.fillStyle = '#FFFFFF';
  ctx.font = 'bold 16px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const text = count > 999 ? `${Math.floor(count / 1000)}k` : String(count);
  ctx.fillText(text, size / 2, size / 2);

  return canvas;
}

/**
 * Renders vessel markers with Cesium's built-in EntityCluster for
 * automatic clustering at low zoom levels.
 *
 * Must be rendered as a child of a Resium <Viewer>.
 */
export function VesselCluster() {
  const { viewer } = useCesium();
  const vessels = useVesselStore((s) => s.vessels);
  const filters = useVesselStore((s) => s.filters);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const dataSourceRef = useRef<CesiumCustomDataSource | null>(null);

  const visibleVessels = useMemo(() => filterVessels(vessels, filters), [vessels, filters]);

  // Build a map of mmsi -> riskTier for cluster coloring
  const vesselRiskMap = useMemo(() => {
    const map = new Map<string, RiskTier>();
    for (const v of visibleVessels) {
      map.set(String(v.mmsi), v.riskTier);
    }
    return map;
  }, [visibleVessels]);

  const handleClick = useCallback(
    (mmsi: number, lat: number, lon: number) => {
      selectVessel(mmsi);
      if (viewer) {
        (viewer as CesiumViewer).camera.flyTo({
          destination: Cartesian3.fromDegrees(lon, lat, 50_000),
          duration: 1.5,
        });
      }
    },
    [selectVessel, viewer],
  );

  // Set up clustering on the data source
  useEffect(() => {
    const ds = dataSourceRef.current;
    if (!ds) return;

    const cluster = ds.clustering;
    cluster.enabled = true;
    cluster.pixelRange = CLUSTER_PIXEL_RANGE;
    cluster.minimumClusterSize = CLUSTER_MIN_SIZE;

    const removeListener = cluster.clusterEvent.addEventListener(
      (clusteredEntities: CesiumEntity[], cluster: { billboard: { show: boolean; image: string }; label: { show: boolean }; point: { show: boolean } }) => {
        // Determine highest risk tier in cluster
        const tiers: RiskTier[] = [];
        for (const entity of clusteredEntities) {
          const tier = vesselRiskMap.get(entity.id);
          if (tier) tiers.push(tier);
        }
        const highestTier = getHighestRiskTier(tiers);

        cluster.label.show = false;
        cluster.point.show = false;
        cluster.billboard.show = true;
        (cluster.billboard as unknown as { image: HTMLCanvasElement }).image = createClusterCanvas(clusteredEntities.length, highestTier);
      },
    );

    return () => {
      removeListener();
    };
  }, [vesselRiskMap]);

  // Pulsing scale for red vessels
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

  return (
    <CustomDataSource
      name="vessels"
      ref={(ref: unknown) => {
        // Resium passes the CesiumCustomDataSource instance
        if (ref && typeof ref === 'object' && 'cesiumElement' in ref) {
          dataSourceRef.current = (ref as { cesiumElement: CesiumCustomDataSource }).cesiumElement;
        }
      }}
    >
      {visibleVessels.map((v) => {
        const style = MARKER_STYLE[v.riskTier];
        const isRed = v.riskTier === 'red' || v.riskTier === 'blacklisted';
        const position = Cartesian3.fromDegrees(v.lon, v.lat);

        return (
          <Entity
            key={v.mmsi}
            id={String(v.mmsi)}
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
    </CustomDataSource>
  );
}
