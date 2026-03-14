import { useMemo } from 'react';
import { Entity, PolylineGraphics, PointGraphics, CustomDataSource } from 'resium';
import { Cartesian3, Color, PolylineDashMaterialProperty } from 'cesium';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { NetworkApiResponse } from '../VesselPanel/NetworkGraph';

export interface NetworkOverlayProps {
  visible: boolean;
}

/** Edge type to line color mapping */
const EDGE_TYPE_COLORS: Record<string, string> = {
  encounter: '#FFFFFF',
  proximity: '#94A3B8',
  port_visit: '#06B6D4',
  ownership: '#A78BFA',
};

/**
 * Globe overlay that highlights network connections for the selected vessel.
 * When active, draws lines between connected vessels at encounter locations
 * and highlights connected vessel positions.
 */
export function NetworkOverlay({ visible }: NetworkOverlayProps) {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const vessels = useVesselStore((s) => s.vessels);

  const enabled = visible && selectedMmsi !== null;

  const { data } = useQuery<NetworkApiResponse>({
    queryKey: ['vesselNetwork', selectedMmsi, 1],
    queryFn: () =>
      fetch(`/api/vessels/${selectedMmsi}/network?depth=1`).then((r) =>
        r.json(),
      ),
    enabled,
  });

  const { lines, highlights } = useMemo(() => {
    if (!data || !data.edges) {
      return { lines: [] as Array<{ id: string; positions: Cartesian3[]; color: Color; dashed: boolean }>, highlights: [] as Array<{ mmsi: number; position: Cartesian3 }> };
    }

    const lineArr = data.edges
      .filter((e) => e.lat != null && e.lon != null)
      .map((edge, i) => {
        // Draw line from selected vessel to encounter location
        const selectedVessel = vessels.get(selectedMmsi!);
        if (!selectedVessel) return null;

        const positions = [
          Cartesian3.fromDegrees(selectedVessel.lon, selectedVessel.lat),
          Cartesian3.fromDegrees(edge.lon!, edge.lat!),
        ];

        const colorHex = EDGE_TYPE_COLORS[edge.edge_type] ?? '#FFFFFF';
        const color = Color.fromCssColorString(colorHex);
        const dashed = edge.edge_type === 'proximity';

        return {
          id: `net-line-${i}`,
          positions,
          color,
          dashed,
        };
      })
      .filter(Boolean) as Array<{ id: string; positions: Cartesian3[]; color: Color; dashed: boolean }>;

    // Highlight connected vessels on globe
    const highlightArr: Array<{ mmsi: number; position: Cartesian3 }> = [];
    if (data.vessels) {
      for (const [key] of Object.entries(data.vessels)) {
        const vMmsi = Number(key);
        if (vMmsi === selectedMmsi) continue;
        const vesselPos = vessels.get(vMmsi);
        if (vesselPos) {
          highlightArr.push({
            mmsi: vMmsi,
            position: Cartesian3.fromDegrees(vesselPos.lon, vesselPos.lat),
          });
        }
      }
    }

    return { lines: lineArr, highlights: highlightArr };
  }, [data, vessels, selectedMmsi]);

  if (!visible || !selectedMmsi) return null;

  return (
    <CustomDataSource name="network-overlay" data-testid="network-overlay">
      {/* Connection lines */}
      {lines.map((line) => (
        <Entity key={line.id} id={line.id}>
          <PolylineGraphics
            positions={line.positions}
            width={2}
            material={
              line.dashed
                ? new PolylineDashMaterialProperty({
                    color: line.color,
                    dashLength: 12,
                  })
                : line.color
            }
          />
        </Entity>
      ))}

      {/* Connected vessel highlights */}
      {highlights.map((h) => (
        <Entity
          key={`net-hl-${h.mmsi}`}
          id={`network-highlight-${h.mmsi}`}
          position={h.position}
        >
          <PointGraphics
            pixelSize={14}
            color={Color.fromCssColorString('rgba(168, 85, 247, 0.6)')}
            outlineColor={Color.fromCssColorString('#A855F7')}
            outlineWidth={2}
          />
        </Entity>
      ))}
    </CustomDataSource>
  );
}
