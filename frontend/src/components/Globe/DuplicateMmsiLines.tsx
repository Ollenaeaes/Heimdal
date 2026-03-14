import { Entity, PolylineGraphics, LabelGraphics } from 'resium';
import {
  Cartesian3,
  Color,
  PolylineDashMaterialProperty,
  LabelStyle,
  VerticalOrigin,
  Cartesian2,
} from 'cesium';
import { useQuery } from '@tanstack/react-query';

export interface DuplicateMmsiLinesProps {
  visible: boolean;
}

interface DuplicateAnomalyItem {
  id: number;
  mmsi: number;
  rule_id: string;
  details: {
    reported_lat?: number;
    reported_lon?: number;
    other_lat?: number;
    other_lon?: number;
    position_a?: { lat: number; lon: number };
    position_b?: { lat: number; lon: number };
    [key: string]: unknown;
  };
}

interface AnomalyResponse {
  items: DuplicateAnomalyItem[];
  total: number;
}

/** Line color: bright red-orange for duplicate MMSI connectors. */
const DUPLICATE_LINE_COLOR = Color.fromCssColorString('#FF6B6B');

/**
 * Extract the two positions from a duplicate MMSI anomaly's details.
 * Returns null if positions cannot be determined.
 */
export function extractDuplicatePositions(
  details: DuplicateAnomalyItem['details'],
): { posA: { lat: number; lon: number }; posB: { lat: number; lon: number } } | null {
  // Try position_a/position_b first
  if (details.position_a && details.position_b) {
    return { posA: details.position_a, posB: details.position_b };
  }
  // Fall back to reported/other
  if (
    details.reported_lat != null &&
    details.reported_lon != null &&
    details.other_lat != null &&
    details.other_lon != null
  ) {
    return {
      posA: { lat: details.reported_lat, lon: details.reported_lon },
      posB: { lat: details.other_lat, lon: details.other_lon },
    };
  }
  return null;
}

/**
 * Renders dashed lines between duplicate MMSI position pairs.
 * Each line connects two reported positions for the same MMSI.
 */
export function DuplicateMmsiLines({ visible }: DuplicateMmsiLinesProps) {
  const { data } = useQuery<AnomalyResponse>({
    queryKey: ['duplicateMmsi'],
    queryFn: () =>
      fetch('/api/anomalies?rule_id=spoof_duplicate_mmsi&resolved=false&per_page=1000').then(
        (r) => r.json(),
      ),
    refetchInterval: 60_000,
    enabled: visible,
  });

  if (!visible || !data?.items) return null;

  return (
    <>
      {data.items.map((anomaly) => {
        const positions = extractDuplicatePositions(anomaly.details);
        if (!positions) return null;

        const { posA, posB } = positions;
        const startPos = Cartesian3.fromDegrees(posA.lon, posA.lat);
        const endPos = Cartesian3.fromDegrees(posB.lon, posB.lat);
        const midpoint = Cartesian3.fromDegrees(
          (posA.lon + posB.lon) / 2,
          (posA.lat + posB.lat) / 2,
        );

        return (
          <Entity key={`dup-mmsi-${anomaly.id}`}>
            <PolylineGraphics
              positions={[startPos, endPos]}
              width={2}
              material={
                new PolylineDashMaterialProperty({
                  color: DUPLICATE_LINE_COLOR,
                  dashLength: 12,
                })
              }
            />
            <LabelGraphics
              text="Duplicate MMSI"
              font="11px sans-serif"
              fillColor={Color.WHITE}
              style={LabelStyle.FILL_AND_OUTLINE}
              outlineColor={Color.BLACK}
              outlineWidth={2}
              verticalOrigin={VerticalOrigin.CENTER}
              pixelOffset={new Cartesian2(0, -12)}
              position={midpoint}
            />
          </Entity>
        );
      })}
    </>
  );
}
