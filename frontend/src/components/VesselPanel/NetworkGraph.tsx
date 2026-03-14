import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../../hooks/useVesselStore';
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from 'd3-force';

export interface NetworkNode extends SimulationNodeDatum {
  mmsi: number;
  name?: string;
  riskTier: string;
  riskScore?: number;
}

export interface NetworkLink extends SimulationLinkDatum<NetworkNode> {
  type: string;
  date?: string;
  location?: string;
}

export interface NetworkApiResponse {
  mmsi: number;
  depth: number;
  edges: Array<{
    vessel_a_mmsi: number;
    vessel_b_mmsi: number;
    edge_type: string;
    confidence: number;
    lat: number | null;
    lon: number | null;
    last_observed: string | null;
    details: Record<string, unknown>;
  }>;
  vessels: Record<
    string,
    {
      mmsi: number;
      ship_name: string | null;
      flag_country: string | null;
      risk_tier: string;
      ship_type: number | null;
      network_score: number;
    }
  >;
}

const RISK_TIER_COLORS: Record<string, string> = {
  green: '#22C55E',
  yellow: '#EAB308',
  red: '#EF4444',
};

const NODE_BASE_RADIUS = 8;
const SVG_SIZE = 380;
const CENTER = SVG_SIZE / 2;

export function NetworkGraph({ mmsi }: { mmsi: number }) {
  const [depth, setDepth] = useState(1);
  const [collapsed, setCollapsed] = useState(false);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const svgRef = useRef<SVGSVGElement>(null);

  const { data, isLoading } = useQuery<NetworkApiResponse>({
    queryKey: ['vesselNetwork', mmsi, depth],
    queryFn: () =>
      fetch(`/api/vessels/${mmsi}/network?depth=${depth}`).then((r) =>
        r.json(),
      ),
  });

  const { nodes, links } = useMemo(() => {
    if (!data || !data.vessels || Object.keys(data.vessels).length === 0) {
      return { nodes: [] as NetworkNode[], links: [] as NetworkLink[] };
    }

    const nodeMap = new Map<number, NetworkNode>();
    for (const [key, v] of Object.entries(data.vessels)) {
      const vMmsi = Number(key);
      nodeMap.set(vMmsi, {
        mmsi: vMmsi,
        name: v.ship_name ?? undefined,
        riskTier: v.risk_tier ?? 'green',
        riskScore: v.network_score ?? 0,
      });
    }

    const linkArr: NetworkLink[] = (data.edges ?? []).map((e) => ({
      source: e.vessel_a_mmsi,
      target: e.vessel_b_mmsi,
      type: e.edge_type,
      date: e.last_observed ?? undefined,
    }));

    return { nodes: Array.from(nodeMap.values()), links: linkArr };
  }, [data]);

  // Run force simulation
  const [simNodes, setSimNodes] = useState<NetworkNode[]>([]);
  const [simLinks, setSimLinks] = useState<NetworkLink[]>([]);

  useEffect(() => {
    if (nodes.length === 0) {
      setSimNodes([]);
      setSimLinks([]);
      return;
    }

    // Deep clone to avoid mutating original data
    const clonedNodes = nodes.map((n) => ({ ...n, x: CENTER, y: CENTER }));
    const clonedLinks = links.map((l) => ({ ...l }));

    const simulation = forceSimulation<NetworkNode>(clonedNodes)
      .force(
        'link',
        forceLink<NetworkNode, NetworkLink>(clonedLinks)
          .id((d) => d.mmsi)
          .distance(60),
      )
      .force('charge', forceManyBody().strength(-120))
      .force('center', forceCenter(CENTER, CENTER))
      .force('collide', forceCollide(15))
      .stop();

    // Run 120 ticks synchronously
    for (let i = 0; i < 120; i++) {
      simulation.tick();
    }

    setSimNodes([...clonedNodes]);
    setSimLinks([...clonedLinks]);

    return () => {
      simulation.stop();
    };
  }, [nodes, links]);

  const handleNodeClick = useCallback(
    (nodeMmsi: number) => {
      selectVessel(nodeMmsi);
    },
    [selectVessel],
  );

  const getNodeRadius = (node: NetworkNode) => {
    const score = node.riskScore ?? 0;
    return NODE_BASE_RADIUS + Math.min(score / 20, 6);
  };

  const isEmpty =
    !isLoading && (!data || Object.keys(data.vessels ?? {}).length === 0);

  return (
    <div
      className="px-3 py-2 border-b border-[#1F2937]"
      data-testid="network-graph"
    >
      {/* Header */}
      <button
        className="flex items-center justify-between w-full text-left"
        onClick={() => setCollapsed(!collapsed)}
        data-testid="network-graph-toggle"
      >
        <span className="text-xs text-gray-400 uppercase tracking-wide">
          Network Graph
        </span>
        <span className="text-gray-500 text-[0.65rem]">
          {collapsed ? '\u25B6' : '\u25BC'}
        </span>
      </button>

      {!collapsed && (
        <>
          {/* Depth selector */}
          <div
            className="flex items-center gap-2 mt-2 mb-2"
            data-testid="depth-selector"
          >
            <span className="text-xs text-gray-500">Depth:</span>
            {[1, 2, 3].map((d) => (
              <button
                key={d}
                onClick={() => setDepth(d)}
                className={`px-2 py-0.5 rounded text-xs ${
                  depth === d
                    ? 'bg-purple-600 text-white'
                    : 'bg-[#1F2937] text-gray-400 hover:bg-[#374151]'
                }`}
                data-testid={`depth-btn-${d}`}
              >
                {d}
              </button>
            ))}
          </div>

          {isLoading && (
            <div className="text-xs text-gray-500 py-4 text-center">
              Loading network...
            </div>
          )}

          {isEmpty && (
            <div
              className="text-xs text-gray-500 py-4 text-center"
              data-testid="network-empty"
            >
              No network connections found
            </div>
          )}

          {simNodes.length > 0 && (
            <svg
              ref={svgRef}
              width={SVG_SIZE}
              height={SVG_SIZE}
              className="mx-auto"
              data-testid="network-svg"
            >
              {/* Links */}
              {simLinks.map((link, i) => {
                const source = link.source as NetworkNode;
                const target = link.target as NetworkNode;
                return (
                  <g key={`link-${i}`}>
                    <line
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      stroke="#4B5563"
                      strokeWidth={1.5}
                      data-testid="network-link"
                    />
                    <text
                      x={((source.x ?? 0) + (target.x ?? 0)) / 2}
                      y={((source.y ?? 0) + (target.y ?? 0)) / 2 - 4}
                      fill="#6B7280"
                      fontSize="9"
                      textAnchor="middle"
                    >
                      {link.type}
                    </text>
                  </g>
                );
              })}

              {/* Nodes */}
              {simNodes.map((node) => {
                const r = getNodeRadius(node);
                const fill = RISK_TIER_COLORS[node.riskTier] ?? '#6B7280';
                const isCurrent = node.mmsi === mmsi;
                return (
                  <g
                    key={node.mmsi}
                    onClick={() => handleNodeClick(node.mmsi)}
                    style={{ cursor: 'pointer' }}
                    data-testid="network-node"
                    data-mmsi={node.mmsi}
                    data-risk-tier={node.riskTier}
                  >
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={r}
                      fill={fill}
                      stroke={isCurrent ? '#FFFFFF' : '#1F2937'}
                      strokeWidth={isCurrent ? 2 : 1}
                    />
                    <text
                      x={node.x}
                      y={(node.y ?? 0) + r + 12}
                      fill="#9CA3AF"
                      fontSize="9"
                      textAnchor="middle"
                    >
                      {node.name ?? String(node.mmsi)}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
        </>
      )}
    </div>
  );
}
