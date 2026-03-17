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
import { CollapsibleSection } from './CollapsibleSection';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface NetworkNode extends SimulationNodeDatum {
  mmsi: number;
  name?: string;
  riskTier: string;
  riskScore?: number;
  flagCountry?: string;
  shipType?: number;
}

export interface NetworkLink extends SimulationLinkDatum<NetworkNode> {
  type: string;
  date?: string;
  location?: string;
  confidence?: number;
  details?: Record<string, unknown>;
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

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const RISK_TIER_COLORS: Record<string, string> = {
  green: '#22C55E',
  yellow: '#EAB308',
  red: '#EF4444',
  blacklisted: '#991B1B',
};

const EDGE_TYPE_LABELS: Record<string, string> = {
  shared_owner: 'Shared Owner',
  ownership: 'Shared Owner',
  encounter: 'Encounter',
  sts_proximity: 'STS Proximity',
  proximity: 'Proximity',
  port_visit: 'Port Visit',
};

/** Returns SVG stroke-dasharray for each edge type */
const EDGE_DASH: Record<string, string | undefined> = {
  shared_owner: undefined,       // solid
  ownership: undefined,          // solid
  encounter: '6 3',              // dashed
  sts_proximity: '2 3',          // dotted
  proximity: '2 3',              // dotted
  port_visit: '8 4 2 4',         // dash-dot
};

const EDGE_COLORS: Record<string, string> = {
  shared_owner: '#A78BFA',
  ownership: '#A78BFA',
  encounter: '#FFFFFF',
  sts_proximity: '#F59E0B',
  proximity: '#94A3B8',
  port_visit: '#06B6D4',
};

const NODE_BASE_RADIUS = 8;
const SVG_SIZE = 380;
const CENTER = SVG_SIZE / 2;

/* ------------------------------------------------------------------ */
/*  Tooltip types                                                      */
/* ------------------------------------------------------------------ */

interface TooltipInfo {
  x: number;
  y: number;
  kind: 'node' | 'edge';
  node?: NetworkNode;
  edge?: NetworkLink;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatDate(iso: string | undefined | null): string {
  if (!iso) return 'Unknown';
  try {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return String(iso);
  }
}

function formatRiskTier(tier: string): string {
  return tier.charAt(0).toUpperCase() + tier.slice(1);
}

function edgeLabel(type: string): string {
  return EDGE_TYPE_LABELS[type] ?? type.replace(/_/g, ' ');
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function NetworkGraph({ mmsi }: { mmsi: number }) {
  const [depth, setDepth] = useState(1);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data, isLoading } = useQuery<NetworkApiResponse>({
    queryKey: ['vesselNetwork', mmsi, depth],
    queryFn: () =>
      fetch(`/api/vessels/${mmsi}/network?depth=${depth}`).then((r) =>
        r.json(),
      ),
  });

  /* ---------- Build nodes & links from API response ---------- */

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
        flagCountry: v.flag_country ?? undefined,
        shipType: v.ship_type ?? undefined,
      });
    }

    const linkArr: NetworkLink[] = (data.edges ?? []).map((e) => ({
      source: e.vessel_a_mmsi,
      target: e.vessel_b_mmsi,
      type: e.edge_type,
      date: e.last_observed ?? undefined,
      confidence: e.confidence,
      details: e.details,
      location:
        e.lat != null && e.lon != null
          ? `${e.lat.toFixed(2)}, ${e.lon.toFixed(2)}`
          : undefined,
    }));

    return { nodes: Array.from(nodeMap.values()), links: linkArr };
  }, [data]);

  /* ---------- Force simulation ---------- */

  const [simNodes, setSimNodes] = useState<NetworkNode[]>([]);
  const [simLinks, setSimLinks] = useState<NetworkLink[]>([]);

  useEffect(() => {
    if (nodes.length === 0) {
      setSimNodes([]);
      setSimLinks([]);
      return;
    }

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

    for (let i = 0; i < 120; i++) {
      simulation.tick();
    }

    setSimNodes([...clonedNodes]);
    setSimLinks([...clonedLinks]);

    return () => {
      simulation.stop();
    };
  }, [nodes, links]);

  /* ---------- Interaction handlers ---------- */

  const handleNodeClick = useCallback(
    (nodeMmsi: number) => {
      selectVessel(nodeMmsi);
    },
    [selectVessel],
  );

  const showNodeTooltip = useCallback(
    (e: React.MouseEvent, node: NetworkNode) => {
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      setTooltip({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        kind: 'node',
        node,
      });
    },
    [],
  );

  const showEdgeTooltip = useCallback(
    (e: React.MouseEvent, edge: NetworkLink) => {
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      setTooltip({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        kind: 'edge',
        edge,
      });
    },
    [],
  );

  const hideTooltip = useCallback(() => setTooltip(null), []);

  const getNodeRadius = (node: NetworkNode) => {
    const score = node.riskScore ?? 0;
    return NODE_BASE_RADIUS + Math.min(score / 20, 6);
  };

  const isEmpty =
    !isLoading && (!data || Object.keys(data.vessels ?? {}).length === 0);

  /* ---------- Render ---------- */

  return (
    <CollapsibleSection title="Network Graph" testId="network-graph">
      <div ref={containerRef}>
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
          <div className="relative" onMouseLeave={hideTooltip}>
            <svg
              ref={svgRef}
              width={SVG_SIZE}
              height={SVG_SIZE}
              className="mx-auto"
              data-testid="network-svg"
            >
              {/* SVG defs for edge dash patterns */}
              <defs>
                <filter id="node-glow" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Links */}
              {simLinks.map((link, i) => {
                const source = link.source as NetworkNode;
                const target = link.target as NetworkNode;
                const edgeColor = EDGE_COLORS[link.type] ?? '#4B5563';
                const dashArray = EDGE_DASH[link.type];
                return (
                  <g key={`link-${i}`}>
                    {/* Invisible wider hit area for hover */}
                    <line
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      stroke="transparent"
                      strokeWidth={12}
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={(e) => showEdgeTooltip(e, link)}
                      onMouseMove={(e) => showEdgeTooltip(e, link)}
                      onMouseLeave={hideTooltip}
                    />
                    {/* Visible line */}
                    <line
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      stroke={edgeColor}
                      strokeWidth={1.5}
                      strokeDasharray={dashArray}
                      strokeOpacity={0.7}
                      pointerEvents="none"
                      data-testid="network-link"
                    />
                    {/* Edge label */}
                    <text
                      x={((source.x ?? 0) + (target.x ?? 0)) / 2}
                      y={((source.y ?? 0) + (target.y ?? 0)) / 2 - 4}
                      fill="#6B7280"
                      fontSize="8"
                      textAnchor="middle"
                      pointerEvents="none"
                    >
                      {edgeLabel(link.type)}
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
                    onMouseEnter={(e) => showNodeTooltip(e, node)}
                    onMouseMove={(e) => showNodeTooltip(e, node)}
                    onMouseLeave={hideTooltip}
                    style={{ cursor: 'pointer' }}
                    data-testid="network-node"
                    data-mmsi={node.mmsi}
                    data-risk-tier={node.riskTier}
                  >
                    {/* Glow ring for selected vessel */}
                    {isCurrent && (
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={r + 4}
                        fill="none"
                        stroke="#FFFFFF"
                        strokeWidth={1.5}
                        strokeOpacity={0.4}
                        filter="url(#node-glow)"
                      />
                    )}
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
                      pointerEvents="none"
                    >
                      {node.name ?? String(node.mmsi)}
                    </text>
                  </g>
                );
              })}
            </svg>

            {/* Tooltip overlay */}
            {tooltip && (
              <NetworkTooltip tooltip={tooltip} currentMmsi={mmsi} />
            )}

            {/* Legend */}
            <NetworkLegend />
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}

/* ------------------------------------------------------------------ */
/*  Tooltip sub-component                                              */
/* ------------------------------------------------------------------ */

function NetworkTooltip({
  tooltip,
  currentMmsi,
}: {
  tooltip: TooltipInfo;
  currentMmsi: number;
}) {
  // Position tooltip so it doesn't overflow the SVG
  const left = Math.min(tooltip.x + 12, SVG_SIZE - 180);
  const top = Math.max(tooltip.y - 10, 0);

  if (tooltip.kind === 'node' && tooltip.node) {
    const n = tooltip.node;
    const isCurrent = n.mmsi === currentMmsi;
    return (
      <div
        className="absolute pointer-events-none z-50"
        style={{ left, top }}
        data-testid="network-tooltip"
      >
        <div className="bg-[#111827] border border-[#374151] rounded-lg px-3 py-2 shadow-xl text-xs min-w-[160px]">
          <div className="font-semibold text-white mb-1 flex items-center gap-1.5">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: RISK_TIER_COLORS[n.riskTier] ?? '#6B7280' }}
            />
            {n.name ?? 'Unknown Vessel'}
            {isCurrent && (
              <span className="text-[0.6rem] text-purple-400 ml-1">(selected)</span>
            )}
          </div>
          <div className="space-y-0.5 text-gray-400">
            <div>MMSI: <span className="text-gray-300">{n.mmsi}</span></div>
            {n.flagCountry && (
              <div>Flag: <span className="text-gray-300">{n.flagCountry}</span></div>
            )}
            {n.shipType != null && (
              <div>Ship Type: <span className="text-gray-300">{n.shipType}</span></div>
            )}
            <div>
              Risk:{' '}
              <span
                className="font-medium"
                style={{ color: RISK_TIER_COLORS[n.riskTier] ?? '#6B7280' }}
              >
                {formatRiskTier(n.riskTier)}
              </span>
            </div>
            {n.riskScore != null && (
              <div>Network Score: <span className="text-gray-300">{n.riskScore}</span></div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (tooltip.kind === 'edge' && tooltip.edge) {
    const e = tooltip.edge;
    const sourceName =
      (e.source as NetworkNode).name ?? String((e.source as NetworkNode).mmsi);
    const targetName =
      (e.target as NetworkNode).name ?? String((e.target as NetworkNode).mmsi);

    // Extract useful detail fields
    const detailEntries = e.details
      ? Object.entries(e.details).filter(
          ([, v]) => v != null && v !== '' && typeof v !== 'object',
        )
      : [];

    return (
      <div
        className="absolute pointer-events-none z-50"
        style={{ left, top }}
        data-testid="network-tooltip"
      >
        <div className="bg-[#111827] border border-[#374151] rounded-lg px-3 py-2 shadow-xl text-xs min-w-[160px]">
          <div className="font-semibold text-white mb-1">
            {edgeLabel(e.type)}
          </div>
          <div className="space-y-0.5 text-gray-400">
            <div>
              {sourceName}{' '}
              <span className="text-gray-600">&#8596;</span>{' '}
              {targetName}
            </div>
            {e.date && (
              <div>Last Seen: <span className="text-gray-300">{formatDate(e.date)}</span></div>
            )}
            {e.confidence != null && (
              <div>Confidence: <span className="text-gray-300">{(e.confidence * 100).toFixed(0)}%</span></div>
            )}
            {e.location && (
              <div>Location: <span className="text-gray-300">{e.location}</span></div>
            )}
            {detailEntries.map(([key, val]) => (
              <div key={key}>
                {key.replace(/_/g, ' ')}:{' '}
                <span className="text-gray-300">{String(val)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return null;
}

/* ------------------------------------------------------------------ */
/*  Legend sub-component                                                */
/* ------------------------------------------------------------------ */

function NetworkLegend() {
  return (
    <div
      className="flex flex-wrap gap-x-3 gap-y-1 mt-1 px-1 text-[0.6rem] text-gray-500"
      data-testid="network-legend"
    >
      {/* Risk tier colors */}
      {Object.entries(RISK_TIER_COLORS).map(([tier, color]) => (
        <span key={tier} className="flex items-center gap-1">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: color }}
          />
          {formatRiskTier(tier)}
        </span>
      ))}

      {/* Edge type styles */}
      <span className="flex items-center gap-1">
        <svg width="16" height="6" className="inline-block">
          <line x1="0" y1="3" x2="16" y2="3" stroke="#A78BFA" strokeWidth="1.5" />
        </svg>
        Owner
      </span>
      <span className="flex items-center gap-1">
        <svg width="16" height="6" className="inline-block">
          <line x1="0" y1="3" x2="16" y2="3" stroke="#FFFFFF" strokeWidth="1.5" strokeDasharray="6 3" />
        </svg>
        Encounter
      </span>
      <span className="flex items-center gap-1">
        <svg width="16" height="6" className="inline-block">
          <line x1="0" y1="3" x2="16" y2="3" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="2 3" />
        </svg>
        STS
      </span>
    </div>
  );
}
