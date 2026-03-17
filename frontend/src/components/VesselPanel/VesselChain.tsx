import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { NetworkApiResponse } from './NetworkGraph';
import { CollapsibleSection } from './CollapsibleSection';

export interface ChainNode {
  mmsi?: number;
  label: string;
  flag?: string;
  date?: string;
  type: 'port' | 'vessel';
}

/**
 * Build a linear chain from network edges.
 * Heuristic: find a path starting from a port_visit edge, flowing through
 * encounter/proximity edges. Returns empty array if chain can't be built.
 */
export function buildChain(data: NetworkApiResponse): ChainNode[] {
  if (!data.edges || data.edges.length === 0) return [];

  const portEdges = data.edges.filter((e) => e.edge_type === 'port_visit');
  const otherEdges = data.edges.filter((e) => e.edge_type !== 'port_visit');

  if (portEdges.length === 0 && otherEdges.length === 0) return [];

  const chain: ChainNode[] = [];
  const visited = new Set<number>();

  // Start with first port_visit if available
  if (portEdges.length > 0) {
    const first = portEdges[0];
    const portName =
      (first.details?.port_name as string) ?? 'Terminal';
    chain.push({
      label: portName,
      date: first.last_observed ?? undefined,
      type: 'port',
    });
    chain.push({
      mmsi: first.vessel_a_mmsi,
      label:
        data.vessels[String(first.vessel_a_mmsi)]?.ship_name ??
        String(first.vessel_a_mmsi),
      flag: data.vessels[String(first.vessel_a_mmsi)]?.flag_country ?? undefined,
      date: first.last_observed ?? undefined,
      type: 'vessel',
    });
    visited.add(first.vessel_a_mmsi);
  }

  // Walk through encounter/proximity edges
  for (const edge of otherEdges) {
    const aVessel = data.vessels[String(edge.vessel_a_mmsi)];
    const bVessel = data.vessels[String(edge.vessel_b_mmsi)];

    if (!visited.has(edge.vessel_a_mmsi)) {
      chain.push({
        mmsi: edge.vessel_a_mmsi,
        label: aVessel?.ship_name ?? String(edge.vessel_a_mmsi),
        flag: aVessel?.flag_country ?? undefined,
        date: edge.last_observed ?? undefined,
        type: 'vessel',
      });
      visited.add(edge.vessel_a_mmsi);
    }
    if (!visited.has(edge.vessel_b_mmsi)) {
      chain.push({
        mmsi: edge.vessel_b_mmsi,
        label: bVessel?.ship_name ?? String(edge.vessel_b_mmsi),
        flag: bVessel?.flag_country ?? undefined,
        date: edge.last_observed ?? undefined,
        type: 'vessel',
      });
      visited.add(edge.vessel_b_mmsi);
    }
  }

  return chain.length >= 2 ? chain : [];
}

export function VesselChain({ mmsi }: { mmsi: number }) {
  const selectVessel = useVesselStore((s) => s.selectVessel);

  const { data, isLoading } = useQuery<NetworkApiResponse>({
    queryKey: ['vesselNetwork', mmsi, 2],
    queryFn: () =>
      fetch(`/api/vessels/${mmsi}/network?depth=2`).then((r) => r.json()),
  });

  const chain = useMemo(() => (data ? buildChain(data) : []), [data]);

  const isEmpty = !isLoading && chain.length === 0;

  return (
    <CollapsibleSection title="Vessel Chain" testId="vessel-chain">
      {isLoading && (
        <div className="text-xs text-gray-500 py-4 text-center">
          Loading chain...
        </div>
      )}

      {isEmpty && (
        <div
          className="text-xs text-gray-500 py-4 text-center"
          data-testid="chain-insufficient"
        >
          Insufficient data for chain analysis
        </div>
      )}

      {chain.length > 0 && (
        <div
          className="flex items-center gap-1 overflow-x-auto mt-2 pb-2"
          data-testid="chain-container"
        >
          {chain.map((node, i) => (
            <div key={`chain-${i}`} className="flex items-center shrink-0">
              {/* Node */}
              <button
                className={`flex flex-col items-center px-2 py-1.5 rounded border text-xs ${
                  node.type === 'port'
                    ? 'bg-[#1E293B] border-cyan-800 text-cyan-300'
                    : 'bg-[#1F2937] border-[#374151] text-gray-200 hover:border-purple-500'
                }`}
                onClick={() => {
                  if (node.mmsi) selectVessel(node.mmsi);
                }}
                disabled={!node.mmsi}
                data-testid="chain-node"
                data-mmsi={node.mmsi ?? ''}
              >
                <span className="font-medium truncate max-w-[80px]">
                  {node.label}
                </span>
                {node.flag && (
                  <span className="text-[10px] text-gray-500">
                    {node.flag}
                  </span>
                )}
                {node.date && (
                  <span className="text-[10px] text-gray-600">
                    {new Date(node.date).toLocaleDateString()}
                  </span>
                )}
              </button>

              {/* Arrow between nodes */}
              {i < chain.length - 1 && (
                <span className="text-gray-600 mx-1 text-xs">&rarr;</span>
              )}
            </div>
          ))}
        </div>
      )}
    </CollapsibleSection>
  );
}
