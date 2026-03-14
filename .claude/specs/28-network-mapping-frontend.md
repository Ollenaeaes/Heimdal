# Feature Spec: Network Mapping Frontend

**Slug:** `network-mapping-frontend`
**Created:** 2026-03-14
**Status:** draft
**Priority:** high

---

## Overview

Network graph visualization in the vessel detail panel (d3-force directed graph), network score display alongside individual risk score, globe network mode that highlights connected vessels and draws encounter lines, and a vessel chain view showing the linear cargo path from terminal to discharge port.

## Problem Statement

The network mapping backend (spec 25) builds the encounter/ownership graph and computes network risk scores, but operators need to see and explore these connections visually. A table of edges is not actionable — an interactive force-directed graph where clicking a node navigates to that vessel, with edges labeled by encounter type and date, makes the network tangible and explorable. The globe network mode turns individual dots into visible logistics chains.

## Out of Scope

- NOT: Backend network edge construction or scoring (spec 25)
- NOT: Betweenness centrality or advanced graph analytics visualization
- NOT: OpenCorporates corporate graph visualization
- NOT: Network analytics dashboard with hub detection (future enhancement)
- NOT: Exportable network reports

---

## User Stories

### Story 1: Network Score Display in Vessel Panel

**As an** operator
**I want to** see a vessel's network risk score alongside its individual risk score
**So that** I understand both the vessel's own risk and its guilt-by-association risk

**Acceptance Criteria:**

- GIVEN a vessel with a network_score > 0 WHEN the vessel detail panel is open THEN the risk section shows: "Individual: X pts (Tier) | Network: Y pts"
- GIVEN a vessel with network_score = 0 WHEN the panel is open THEN the network score line shows "Network: No connections" or is hidden
- GIVEN a vessel connected to a network of N vessels WHEN displayed THEN include "Connected to N vessels" context

**Test Requirements:**

- [ ] Test: Vessel with network_score=45 → displays "Network: 45 pts"
- [ ] Test: Vessel with network_score=0 → displays "No connections" or hides network score
- [ ] Test: Connected vessel count is accurate
- [ ] Test: Network score updates when API data refreshes

**Technical Notes:**

- Modify existing risk section in VesselPanel (`RiskSection.tsx` or equivalent)
- network_score comes from the vessel detail API response (added in spec 25)
- Connected vessel count from `GET /api/vessels/{mmsi}/network` (count unique MMSIs in edges)
- Minimal UI change — add one line below the existing risk score bar

---

### Story 2: Network Tab with Force-Directed Graph

**As an** operator
**I want to** see an interactive network graph showing the selected vessel's connections
**So that** I can explore which vessels are linked and how they're connected

**Acceptance Criteria:**

- GIVEN a vessel with network edges WHEN the Network tab is opened in the detail panel THEN a force-directed graph renders with the selected vessel at center
- GIVEN the graph WHEN rendered THEN nodes are colored by risk tier (green/yellow/red), sized proportionally to their risk score
- GIVEN the graph WHEN rendered THEN edges are labeled with type and date (e.g., "Encounter — Malta OPL — 14 Feb 2026")
- GIVEN a node in the graph WHEN clicked THEN the vessel detail panel navigates to that vessel
- GIVEN a vessel with no network edges WHEN the Network tab is opened THEN it shows "No network connections found"
- GIVEN depth control WHEN the user selects depth 1/2/3 THEN the graph expands to show connections at that depth

**Test Requirements:**

- [ ] Test: Graph renders with correct number of nodes for depth=1
- [ ] Test: Nodes colored correctly by risk tier
- [ ] Test: Edge labels show type, location, and date
- [ ] Test: Clicking a node selects that vessel (updates selectedMmsi in store)
- [ ] Test: Empty network → "No network connections found" message
- [ ] Test: Depth selector changes the graph (depth=2 shows more nodes than depth=1)

**Technical Notes:**

- Component: `frontend/src/components/VesselPanel/NetworkGraph.tsx`
- Use d3-force for layout: d3.forceSimulation with forceLink, forceManyBody, forceCenter
- Render in an SVG or Canvas element within the panel (420px wide panel constrains the graph)
- Data from `GET /api/vessels/{mmsi}/network?depth=N`
- Tab added to vessel detail panel alongside existing tabs (Identity, Status, Risk, Voyage, Sanctions)
- Node hover: tooltip with vessel name, MMSI, flag, risk tier
- Edge styling by type: encounter = solid line, proximity = dashed line, ownership = dotted line

---

### Story 3: Globe Network Mode

**As an** operator
**I want to** see all connected vessels highlighted on the globe when I select a vessel
**So that** I can see the spatial distribution of the entire logistics chain

**Acceptance Criteria:**

- GIVEN a vessel is selected AND has network edges WHEN network mode is toggled on THEN all connected vessels are highlighted on the globe with a bright outline
- GIVEN network mode is on WHEN rendered THEN lines are drawn on the globe between vessels that have encounter edges, at the encounter location
- GIVEN network mode is on WHEN a vessel is deselected THEN the highlights and lines disappear
- GIVEN the network mode toggle WHEN toggled off THEN only the standard vessel markers are shown

**Test Requirements:**

- [ ] Test: Toggle on with selected vessel → connected vessels get highlight outline
- [ ] Test: Encounter edge lines render at correct geographic positions
- [ ] Test: Deselecting vessel removes all network highlights
- [ ] Test: Toggle off removes network visualization
- [ ] Test: Non-connected vessels are NOT highlighted

**Technical Notes:**

- Component: `frontend/src/components/Globe/NetworkOverlay.tsx`
- Uses network edge data from the API (same as NetworkGraph, can share cache)
- Highlight: additional billboard or outline around connected vessel markers
- Encounter lines: CesiumJS PolylineGraphics between encounter locations (from edge.location)
- Line color: match edge type (encounter=white solid, proximity=white dashed)
- Add toggle to Overlays.tsx or as a button in the vessel detail panel header
- Performance: only active when a vessel is selected and network mode is on

---

### Story 4: Vessel Chain View

**As an** operator
**I want to** see the linear cargo chain from terminal to discharge port for a vessel's network
**So that** I can trace the sanctions evasion logistics path end-to-end

**Acceptance Criteria:**

- GIVEN a vessel in a network with identifiable chain segments WHEN the chain view is opened THEN it shows a linear flow: Terminal → Feeder → STS Zone → Destination Tanker → Discharge Port
- GIVEN chain nodes WHEN rendered THEN each node shows vessel name (or zone/port name), flag, and date
- GIVEN a vessel node in the chain WHEN clicked THEN it selects that vessel in the detail panel
- GIVEN a vessel with insufficient data to build a chain WHEN the view is opened THEN it shows "Insufficient data for chain analysis"

**Test Requirements:**

- [ ] Test: Chain renders with correct node sequence
- [ ] Test: Terminal and discharge port nodes show port names
- [ ] Test: Vessel nodes show names and flags
- [ ] Test: Clicking a vessel node selects it
- [ ] Test: Insufficient data → shows appropriate message

**Technical Notes:**

- Component: `frontend/src/components/VesselPanel/VesselChain.tsx`
- This is a simplified, linear view of the network — displayed below or as an alternative to the force graph
- Chain construction logic (frontend): from the network edges, find the path that starts at a Russian terminal port visit and ends at a destination port visit, passing through encounter/STS nodes
- If no clear linear chain exists (complex mesh), show a message suggesting the full graph view instead
- Render as a horizontal scrollable flow diagram (similar to a pipeline visualization)
- Could use a simple SVG or HTML/CSS flexbox layout

---

## Technical Design

### Data Model Changes

None — consumes data from spec 25 API endpoints.

### API Changes

None — uses endpoints defined in spec 25:
- `GET /api/vessels/{mmsi}/network?depth=N`
- `GET /api/network/clusters`
- `GET /api/vessels/{mmsi}` (includes network_score)

### Dependencies

- Spec 25 (network-mapping-backend) must be implemented first
- d3-force for graph layout (new frontend dependency)
- Existing vessel detail panel tab structure
- Existing globe overlay pattern

### Security Considerations

- Read-only visualization of existing data
- d3-force is a well-maintained, trusted library

---

## Implementation Order

### Group 1 (parallel — independent components)
- Story 1 — Network score display: modifies `RiskSection.tsx` in VesselPanel
- Story 3 — Globe network mode: new `NetworkOverlay.tsx`

### Group 2 (after Group 1)
- Story 2 — Network graph tab: new `NetworkGraph.tsx` (benefits from Story 1's data flow being in place)

### Group 3 (after Group 2)
- Story 4 — Vessel chain view: new `VesselChain.tsx` (depends on network data patterns from Story 2)

**Parallel safety rules:**
- Story 1 modifies existing panel component, Story 3 creates new globe component — no conflicts
- Story 2 adds a new tab — independent file but benefits from understanding data shape from Story 1
- Story 4 is the most complex layout and benefits from Story 2's d3 integration being proven

---

## Development Approach

### Simplifications (what starts simple)

- d3-force with default force parameters — tuning can happen later
- Vessel chain view uses simple heuristic path-finding, not full graph algorithm
- Globe network mode shows direct connections only (depth=1), not full cluster
- No export or sharing of network visualizations

### Upgrade Path (what changes for production)

- "Network analytics dashboard" with cluster summaries, hub detection, bridge vessel identification
- "Animated cargo flow" showing temporal progression of transfers along the chain
- "Network comparison" to highlight changes in network structure over time
- "Exportable network report" as PDF/JSON for intelligence sharing

### Architecture Decisions

- d3-force over other graph libraries (vis.js, cytoscape.js) — d3 is already widely used, well-documented, and gives fine-grained control over layout. The graph sizes (typically 5-20 nodes) don't need the performance optimizations of WebGL-based graph renderers.
- SVG rendering over Canvas for the network graph — at 5-20 nodes, SVG provides easier event handling (click, hover) and styling. Canvas would be better for 100+ node graphs, which we don't expect.
- Horizontal flow diagram for vessel chain — operators think linearly about cargo movement (terminal → STS → destination). A flow diagram is more intuitive than the graph for this specific view.

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Network score displays correctly in vessel panel
- [ ] Force-directed graph renders and is interactive
- [ ] Globe network mode highlights connected vessels
- [ ] Vessel chain view shows linear cargo path when data available
- [ ] All interactions work (click node → select vessel, depth control, toggles)
- [ ] No regressions in existing vessel panel or globe rendering
- [ ] d3-force dependency added correctly
- [ ] Ready for human review
