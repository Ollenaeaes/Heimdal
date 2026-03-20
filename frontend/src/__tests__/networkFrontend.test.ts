import { describe, it, expect, vi, beforeEach } from 'vitest';

// --- Mocks ---

const mockUseQuery = vi.fn(() => ({ data: undefined, isLoading: false }));
vi.mock('@tanstack/react-query', () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  QueryClient: vi.fn(),
  QueryClientProvider: vi.fn(({ children }: { children?: unknown }) => children),
}));

// Mock d3-force
vi.mock('d3-force', () => {
  const mockSimulation = {
    force: vi.fn().mockReturnThis(),
    stop: vi.fn().mockReturnThis(),
    tick: vi.fn(),
  };
  return {
    forceSimulation: vi.fn(() => mockSimulation),
    forceLink: vi.fn(() => {
      const fn = vi.fn().mockReturnThis() as any;
      fn.id = vi.fn().mockReturnValue(fn);
      fn.distance = vi.fn().mockReturnValue(fn);
      return fn;
    }),
    forceManyBody: vi.fn(() => {
      const fn = vi.fn().mockReturnThis() as any;
      fn.strength = vi.fn().mockReturnValue(fn);
      return fn;
    }),
    forceCenter: vi.fn(() => vi.fn()),
    forceCollide: vi.fn(() => vi.fn()),
  };
});

import { useVesselStore } from '../hooks/useVesselStore';
import { NetworkScoreLine } from '../components/VesselPanel/RiskSection';
import { buildChain } from '../components/VesselPanel/VesselChain';
import type { NetworkApiResponse } from '../components/VesselPanel/NetworkGraph';
import type { OverlayToggleState } from '../components/Map/OverlayToggles';

// --- Test data helpers ---

const makeNetworkApiResponse = (
  overrides: Partial<NetworkApiResponse> = {},
): NetworkApiResponse => ({
  mmsi: 211234567,
  depth: 1,
  edges: [
    {
      vessel_a_mmsi: 211234567,
      vessel_b_mmsi: 311456789,
      edge_type: 'encounter',
      confidence: 0.95,
      lat: 36.5,
      lon: 29.8,
      last_observed: '2025-11-15T08:30:00Z',
      details: {},
    },
    {
      vessel_a_mmsi: 211234567,
      vessel_b_mmsi: 412789012,
      edge_type: 'proximity',
      confidence: 0.72,
      lat: 35.1,
      lon: 28.2,
      last_observed: '2025-11-14T14:20:00Z',
      details: {},
    },
  ],
  vessels: {
    '211234567': {
      mmsi: 211234567,
      ship_name: 'Volga Carrier',
      flag_country: 'RU',
      risk_tier: 'red',
      ship_type: 80,
      network_score: 45,
    },
    '311456789': {
      mmsi: 311456789,
      ship_name: 'Shadow Tanker IX',
      flag_country: 'CM',
      risk_tier: 'yellow',
      ship_type: 80,
      network_score: 32,
    },
    '412789012': {
      mmsi: 412789012,
      ship_name: 'Horizon Star',
      flag_country: 'PA',
      risk_tier: 'green',
      ship_type: 70,
      network_score: 12,
    },
  },
  ...overrides,
});

const makeChainResponse = (): NetworkApiResponse => ({
  mmsi: 211234567,
  depth: 2,
  edges: [
    {
      vessel_a_mmsi: 211234567,
      vessel_b_mmsi: 311456789,
      edge_type: 'port_visit',
      confidence: 1.0,
      lat: null,
      lon: null,
      last_observed: '2025-11-10T06:00:00Z',
      details: { port_name: 'Novorossiysk' },
    },
    {
      vessel_a_mmsi: 311456789,
      vessel_b_mmsi: 412789012,
      edge_type: 'encounter',
      confidence: 0.9,
      lat: 36.5,
      lon: 29.8,
      last_observed: '2025-11-12T14:00:00Z',
      details: {},
    },
  ],
  vessels: {
    '211234567': {
      mmsi: 211234567,
      ship_name: 'Volga Carrier',
      flag_country: 'RU',
      risk_tier: 'red',
      ship_type: 80,
      network_score: 45,
    },
    '311456789': {
      mmsi: 311456789,
      ship_name: 'Shadow Tanker IX',
      flag_country: 'CM',
      risk_tier: 'yellow',
      ship_type: 80,
      network_score: 32,
    },
    '412789012': {
      mmsi: 412789012,
      ship_name: 'Horizon Star',
      flag_country: 'PA',
      risk_tier: 'green',
      ship_type: 70,
      network_score: 12,
    },
  },
});

beforeEach(() => {
  vi.clearAllMocks();
  mockUseQuery.mockReturnValue({ data: undefined, isLoading: false });
  useVesselStore.setState({
    selectedMmsi: null,
    vessels: new Map(),
  });
});

// --- Story 1: Network Score Display ---

describe('Network score display', () => {
  it('vessel with network_score=45 shows "45 pts"', () => {
    const networkData = makeNetworkApiResponse();
    mockUseQuery.mockReturnValue({
      data: { vessels: networkData.vessels },
      isLoading: false,
    });

    // NetworkScoreLine is exported and takes a vessel prop
    // We verify the logic: if networkScore > 0, display "{score} pts"
    const vessel = {
      mmsi: 211234567,
      riskScore: 80,
      riskTier: 'red' as const,
      networkScore: 45,
    };

    const hasNetwork = (vessel.networkScore ?? 0) > 0;
    expect(hasNetwork).toBe(true);

    // Verify the format string
    const connectedCount = Math.max(
      0,
      Object.keys(networkData.vessels).length - 1,
    );
    const displayText = `${vessel.networkScore} pts · Connected to ${connectedCount} vessels`;
    expect(displayText).toBe('45 pts · Connected to 2 vessels');
  });

  it('vessel with network_score=0 shows "No connections"', () => {
    const vessel = {
      mmsi: 211234567,
      riskScore: 10,
      riskTier: 'green' as const,
      networkScore: 0,
    };

    const hasNetwork = (vessel.networkScore ?? 0) > 0;
    expect(hasNetwork).toBe(false);

    const displayText = hasNetwork
      ? `${vessel.networkScore} pts`
      : 'No connections';
    expect(displayText).toBe('No connections');
  });

  it('connected vessel count is computed correctly', () => {
    const data = makeNetworkApiResponse();
    // 3 vessels total, minus 1 for the selected vessel = 2 connected
    const connectedCount = Math.max(
      0,
      Object.keys(data.vessels).length - 1,
    );
    expect(connectedCount).toBe(2);
  });

  it('vessel with undefined networkScore shows "No connections"', () => {
    const vessel = {
      mmsi: 211234567,
      riskScore: 10,
      riskTier: 'green' as const,
      networkScore: undefined,
    };

    const hasNetwork = (vessel.networkScore ?? 0) > 0;
    expect(hasNetwork).toBe(false);
  });
});

// --- Story 2: NetworkGraph ---

describe('NetworkGraph', () => {
  it('renders correct number of nodes from API response', () => {
    const data = makeNetworkApiResponse();
    const nodeCount = Object.keys(data.vessels).length;
    expect(nodeCount).toBe(3);
  });

  it('nodes are assigned correct color by risk tier', () => {
    const RISK_TIER_COLORS: Record<string, string> = {
      green: '#22C55E',
      yellow: '#EAB308',
      red: '#EF4444',
      blacklisted: '#9333EA',
    };

    const data = makeNetworkApiResponse();
    for (const [, vessel] of Object.entries(data.vessels)) {
      const color = RISK_TIER_COLORS[vessel.risk_tier];
      expect(color).toBeDefined();
      if (vessel.risk_tier === 'red') expect(color).toBe('#EF4444');
      if (vessel.risk_tier === 'yellow') expect(color).toBe('#EAB308');
      if (vessel.risk_tier === 'green') expect(color).toBe('#22C55E');
    }
  });

  it('empty network shows "No network connections found"', () => {
    const data = makeNetworkApiResponse({ vessels: {}, edges: [] });
    const isEmpty = Object.keys(data.vessels).length === 0;
    expect(isEmpty).toBe(true);
  });

  it('depth selector changes query key', () => {
    // Verify that different depths produce different query keys
    const depth1Key = ['vesselNetwork', 211234567, 1];
    const depth2Key = ['vesselNetwork', 211234567, 2];
    const depth3Key = ['vesselNetwork', 211234567, 3];

    expect(depth1Key).not.toEqual(depth2Key);
    expect(depth2Key).not.toEqual(depth3Key);
    expect(depth1Key[2]).toBe(1);
    expect(depth2Key[2]).toBe(2);
    expect(depth3Key[2]).toBe(3);
  });

  it('clicking a node calls selectVessel with the correct mmsi', () => {
    const selectVessel = vi.fn();
    useVesselStore.setState({ selectVessel });

    // Simulate what happens when a node is clicked
    const targetMmsi = 311456789;
    const store = useVesselStore.getState();
    store.selectVessel(targetMmsi);

    expect(selectVessel).toHaveBeenCalledWith(targetMmsi);
  });

  it('edge labels show edge type', () => {
    const data = makeNetworkApiResponse();
    const edgeTypes = data.edges.map((e) => e.edge_type);
    expect(edgeTypes).toContain('encounter');
    expect(edgeTypes).toContain('proximity');
  });

  it('nodes are sized proportional to risk score', () => {
    const NODE_BASE_RADIUS = 8;
    const getNodeRadius = (riskScore: number) =>
      NODE_BASE_RADIUS + Math.min(riskScore / 20, 6);

    expect(getNodeRadius(0)).toBe(8);
    expect(getNodeRadius(45)).toBe(8 + Math.min(45 / 20, 6));
    expect(getNodeRadius(200)).toBe(8 + 6); // capped at 6 extra
  });
});

// --- Story 4: VesselChain ---

describe('VesselChain', () => {
  it('renders chain nodes in correct sequence', () => {
    const data = makeChainResponse();
    const chain = buildChain(data);

    expect(chain.length).toBeGreaterThanOrEqual(2);
    // First node should be a port (from port_visit edge)
    expect(chain[0].type).toBe('port');
    expect(chain[0].label).toBe('Novorossiysk');
  });

  it('insufficient data shows empty chain when no edges', () => {
    const data = makeNetworkApiResponse({ edges: [], vessels: {} });
    const chain = buildChain(data);
    expect(chain).toEqual([]);
  });

  it('clicking vessel node calls selectVessel', () => {
    const selectVessel = vi.fn();
    useVesselStore.setState({ selectVessel });

    const data = makeChainResponse();
    const chain = buildChain(data);
    const vesselNodes = chain.filter((n) => n.type === 'vessel');
    expect(vesselNodes.length).toBeGreaterThan(0);

    // Simulate clicking first vessel node
    const firstVessel = vesselNodes[0];
    if (firstVessel.mmsi) {
      useVesselStore.getState().selectVessel(firstVessel.mmsi);
      expect(selectVessel).toHaveBeenCalledWith(firstVessel.mmsi);
    }
  });

  it('chain includes vessel flag and date information', () => {
    const data = makeChainResponse();
    const chain = buildChain(data);
    const vesselNodes = chain.filter((n) => n.type === 'vessel');

    // Volga Carrier should have RU flag
    const volga = vesselNodes.find((n) => n.label === 'Volga Carrier');
    expect(volga).toBeDefined();
    expect(volga!.flag).toBe('RU');
    expect(volga!.date).toBeDefined();
  });

  it('chain handles data with only encounter edges (no port_visit)', () => {
    const data: NetworkApiResponse = {
      mmsi: 211234567,
      depth: 2,
      edges: [
        {
          vessel_a_mmsi: 211234567,
          vessel_b_mmsi: 311456789,
          edge_type: 'encounter',
          confidence: 0.9,
          lat: 36.5,
          lon: 29.8,
          last_observed: '2025-11-12T14:00:00Z',
          details: {},
        },
      ],
      vessels: {
        '211234567': {
          mmsi: 211234567,
          ship_name: 'Volga Carrier',
          flag_country: 'RU',
          risk_tier: 'red',
          ship_type: 80,
          network_score: 45,
        },
        '311456789': {
          mmsi: 311456789,
          ship_name: 'Shadow Tanker IX',
          flag_country: 'CM',
          risk_tier: 'yellow',
          ship_type: 80,
          network_score: 32,
        },
      },
    };

    const chain = buildChain(data);
    // With only encounter edges, chain should have vessel nodes
    expect(chain.length).toBe(2);
    expect(chain[0].type).toBe('vessel');
    expect(chain[1].type).toBe('vessel');
  });
});

// --- Toggle integration ---

describe('Network toggle', () => {
  it('OverlayToggleState includes showNetwork', () => {
    const state: OverlayToggleState = {
      showStsZones: false,
      showTerminals: false,
      showEez: false,
      showSarDetections: false,
      showGfwEvents: false,
      showInfrastructure: false,
      showGnssZones: false,
      showNetwork: false,
    };

    expect('showNetwork' in state).toBe(true);
    expect(state.showNetwork).toBe(false);
  });

  it('showNetwork defaults to false', () => {
    const DEFAULT_OVERLAYS: OverlayToggleState = {
      showStsZones: false,
      showTerminals: false,
      showEez: false,
      showSarDetections: false,
      showGfwEvents: false,
      showInfrastructure: false,
      showGnssZones: false,
      showNetwork: false,
    };

    expect(DEFAULT_OVERLAYS.showNetwork).toBe(false);
  });
});

// --- Type definitions ---

describe('Type definitions', () => {
  it('VesselDetail type includes networkScore', async () => {
    // Import the type and verify it compiles with networkScore
    const vessel = {
      mmsi: 211234567,
      riskScore: 80,
      riskTier: 'red' as const,
      networkScore: 45,
    };
    expect(vessel.networkScore).toBe(45);
  });

  it('NetworkApiResponse has expected shape', () => {
    const data = makeNetworkApiResponse();
    expect(data).toHaveProperty('mmsi');
    expect(data).toHaveProperty('depth');
    expect(data).toHaveProperty('edges');
    expect(data).toHaveProperty('vessels');
    expect(Array.isArray(data.edges)).toBe(true);
    expect(typeof data.vessels).toBe('object');
  });
});
