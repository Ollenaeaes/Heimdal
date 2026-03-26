# Feature Spec: Graph Visualization — Sigma.js Fleet View & Temporal Playback

**Slug:** `graph-visualization`
**Created:** 2026-03-26
**Status:** approved
**Priority:** high
**Depends on:** 42-graph-model-and-scoring (graph must exist before it can be visualized)

---

## Overview

Build the graph visualization layer using Sigma.js v3 + Graphology + ForceAtlas2. The core interaction model: clicking "See Graph" on a vessel opens a full-page graph view showing the vessel's **sub-fleet** — the connected component through ownership/management chains. This is not "the shadow fleet" as a whole — it's how one particular cluster of vessels was assembled under common control. The graph supports temporal playback where vessel colors change dynamically as their score accumulates over time (green → yellow → red → purple), letting the analyst visually verify that the scoring logic tracks reality.

This replaces the current depth-1 MapLibre-based network overlay with a dedicated full-page graph view.

## Problem Statement

The current network visualization shows depth-1 neighbors on the map with simple lines. It cannot:
1. Show multi-hop ownership chains (vessel → owner → parent → beneficial owner)
2. Show fleet structure (all vessels under common ownership/management)
3. Animate temporal transitions (when did the flag change? when was the company created?)
4. Distinguish between entity types visually (companies, persons, class societies, flags)
5. Support investigation workflows (hover, click, drill-down on any entity)
6. Show vessel risk classification changing over time as signals accumulate — the human needs to see "this vessel went from green to yellow when the class dropped, then to red when P&I disappeared" to verify the scoring logic is working

## Out of Scope

- NOT: Full-graph analysis view (/networks endpoint showing all flagged fleets) — future enhancement
- NOT: Graph dump export endpoint for local analysis — future enhancement
- NOT: Custom Sigma.js edge programs for line-drawing animation — v2 enhancement
- NOT: Community detection or centrality measures — analyst tooling
- NOT: Replacing the map view — the graph is a parallel view, not a replacement

---

## User Stories

### Story 1: API Endpoints for Fleet Graph

**As a** frontend
**I want to** fetch a vessel's complete fleet graph from the API
**So that** I can render the fleet visualization

**Acceptance Criteria:**

- GIVEN `GET /api/graph/fleet/{imo}` WHEN called THEN it returns the sub-fleet connected component containing the vessel: all nodes reachable through ownership, management, and directorship chains. The connected component does NOT include SanctionProgramme nodes — sanctions status is an attribute on the Vessel node, not a shared hub.
- GIVEN the response WHEN formatted THEN it is Graphology-compatible JSON:
  ```json
  {
    "nodes": [{"key": "vessel:9876543", "attributes": {"type": "Vessel", "name": "...", "imo": 9876543, "classification": "red", "signal_timeline": [{"date": "2022-10", "signals": ["A1", "C1"], "score": 6, "classification": "red"}], ...}}],
    "edges": [{"key": "e1", "source": "vessel:9876543", "target": "company:gulf-maritime", "attributes": {"type": "OWNED_BY", "from_date": "2022-09", ...}}],
    "events": [{"type": "ownership_transferred", "timestamp": "2022-09-01", "source_node": "vessel:9876543", "target_node": "company:gulf-maritime", "description": "Ownership transferred"}],
    "truncated": false
  }
  ```
- GIVEN each Vessel node WHEN returned THEN it includes a `signal_timeline` array: a chronological list of score snapshots showing which signals were active at each point in time and the resulting classification. This drives the dynamic vessel color during temporal playback.
- GIVEN a fleet with >200 nodes WHEN `max_nodes` param is provided THEN the response truncates to core ownership/management skeleton, sets `truncated: true`
- GIVEN the events array WHEN populated THEN it contains all temporal events (company_created, ownership_transferred, flag_changed, class_changed, class_lost, insurance_changed, insurance_lost, sts_event, staging_area_loiter, sanctioned, detained) ordered by timestamp
- GIVEN `GET /api/graph/fleet/{imo}/events` WHEN called THEN it returns only the events array (lighter endpoint for timeline refresh)

**Test Requirements:**

- [ ] Test: Fleet endpoint returns all nodes in the connected component
- [ ] Test: Response format is valid Graphology JSON
- [ ] Test: Events array is ordered by timestamp ascending
- [ ] Test: Truncation works when fleet exceeds max_nodes
- [ ] Test: Vessel not in graph returns 404

**Technical Notes:**

- FalkorDB Cypher for connected component:
  ```cypher
  MATCH (v:Vessel {imo: $imo})-[*1..6]-(connected)
  WITH collect(DISTINCT connected) + [v] AS all_nodes
  UNWIND all_nodes AS n
  MATCH (n)-[r]-(m) WHERE m IN all_nodes
  RETURN DISTINCT n, r, m
  ```
- Events are derived from edge from_date/to_date values + node creation dates
- Node keys use prefixed IDs: `vessel:{imo}`, `company:{id}`, `person:{id}`, etc.

---

### Story 2: Sigma.js Graph Component

**As a** user
**I want to** see an interactive force-directed graph of a vessel's fleet
**So that** I can understand the ownership structure and risk connections

**Acceptance Criteria:**

- GIVEN the VesselPanel "See Graph" button WHEN clicked THEN a **full-page** graph view opens (replaces the map entirely, not a panel or overlay)
- GIVEN the full-page graph view WHEN rendered THEN a "Back to map" button (or back arrow) is visible in the top-left, returning the user to the map with the same vessel selected
- GIVEN the graph data WHEN loaded THEN Graphology loads all nodes and edges, ForceAtlas2 runs as a web worker for 3-5 seconds, and Sigma.js renders the result
- GIVEN the rendered graph WHEN displayed THEN nodes are visually encoded:
  - Vessel: circle, **color reflects current classification at the timeline position** (green/yellow/red/purple), size proportional to gross_tonnage
  - Company: square, blue-grey (owner) or diamond, dark grey (ISM manager)
  - Person: triangle, light grey
  - ClassSociety: hexagon, teal
  - FlagState: small circle
  - PIClub: rounded square, green (IG member) or orange (non-IG)
- GIVEN vessel nodes WHEN the timeline position changes THEN each vessel's color updates dynamically based on its `signal_timeline` — the classification at that point in time. A vessel starts green, turns yellow when it accumulates enough signals (e.g., class drops), turns red when more signals fire (e.g., P&I disappears), and turns purple when sanctioned. This lets the analyst visually verify the scoring logic tracks reality.
- GIVEN edges WHEN rendered THEN they are styled:
  - OWNED_BY: solid, medium weight
  - MANAGED_BY: solid, thick
  - CLASSED_BY: dashed, thin
  - STS_PARTNER: solid orange, thick
  - FLAGGED_AS: dotted, thin
  - INSURED_BY: dotted, medium
  - DIRECTED_BY: thin grey
- GIVEN a node WHEN hovered THEN all its edges highlight, everything else dims, and a tooltip shows the node's key attributes:
  - Vessel: name, IMO, classification, score, triggered signals, and if blacklisted: the sanctions programmes (e.g., "EU Shadow Fleet List", "OFAC SDN", "UA National Sanctions"). It matters *why* a vessel is purple — UA sanctions vs G7 shadow fleet designation are different enforcement contexts.
  - Company: name, jurisdiction, incorporation_date, company_type
  - Person: name, nationality
  - ClassSociety: name, IACS member status
  - FlagState: name, ISO code, Paris MoU list (white/grey/black)
  - PIClub: name, IG member status
- GIVEN a node WHEN clicked THEN a detail panel shows all attributes (for vessels: risk card with score, triggered signals, classification at current timeline position)
- GIVEN a vessel node WHEN clicked THEN the detail panel includes "Go to vessel on map" which closes the graph view and navigates the map to that vessel's position
- GIVEN the graph WHEN rendered THEN zoom/pan works via scroll and drag
- GIVEN a node WHEN dragged THEN it repositions and ForceAtlas2 respects the pinned position
- GIVEN the selected vessel (entry point) WHEN the graph renders THEN it is visually highlighted (glow or ring)

**Test Requirements:**

- [ ] Test: Graph component renders without errors for a sample fleet JSON
- [ ] Test: All 6 node types render with correct shapes and colors (Vessel, Company, Person, ClassSociety, FlagState, PIClub)
- [ ] Test: Vessel node color reflects classification at current timeline position
- [ ] Test: Vessel node color updates when timeline position changes (e.g., green → yellow when class drops)
- [ ] Test: Hover on a node highlights connected edges
- [ ] Test: Click on a vessel node shows risk card with signals at current timeline position
- [ ] Test: "Go to vessel on map" closes graph and navigates map
- [ ] Test: ForceAtlas2 layout completes within 5 seconds for 100-node graph

**Technical Notes:**

- NPM packages: `sigma` (v3), `graphology`, `graphology-layout-forceatlas2`, `@react-sigma/core`
- ForceAtlas2 runs in a web worker — use `graphology-layout-forceatlas2/worker`
- Custom node renderers needed for non-circle shapes (square, diamond, triangle, hexagon) — use Sigma.js custom programs or the `@sigma/node-square`, `@sigma/node-triangle` packages
- The current NetworkGraph.tsx (D3-force based) is replaced by this component
- State management: graph data in a React context or zustand store
- **No SanctionProgramme nodes** — sanctions status is a vessel attribute (turns purple), not a shared node. A SanctionProgramme hub would connect all sanctioned vessels into one giant component, which defeats the purpose of showing individual sub-fleets.
- **Dynamic vessel colors** — each vessel's color is computed from its `signal_timeline` at the current timeline position. The color function maps score→classification→color at each point in time.

---

### Story 3: Temporal Playback

**As a** user
**I want to** play back the fleet's assembly over time
**So that** I can see the pattern: shell companies forming, vessels acquired, flags changed, class dropped

**Acceptance Criteria:**

- GIVEN the fleet graph WHEN first loaded THEN it shows the **current state** (all active nodes and edges). The timeline slider is at "now."
- GIVEN the timeline slider WHEN dragged backward THEN edges with to_date < slider date disappear. Edges with from_date > slider date disappear. Nodes with no visible edges disappear (except Vessel nodes, which are always visible once they enter the fleet).
- GIVEN the Play button WHEN pressed THEN the slider rewinds to the earliest event and advances automatically through time
- GIVEN playback WHEN an event occurs at the current timestamp THEN the appropriate visual effect happens:
  - New node: fades in at graph periphery
  - New edge: opacity animates from 0 to 1 over 0.5s
  - Edge ends (replacement): old edge fades out, new edge fades in
  - Edge ends (loss, no replacement): edge flashes red briefly (0.3s) then disappears
  - **Vessel classification changes**: node color smoothly transitions to the new color (e.g., green→yellow when class drops, yellow→red when P&I disappears, red→purple when sanctioned). This is the key visual payoff — the analyst watches the fleet degrade in real time.
  - Staging area loiter: vessel node pulses briefly
- GIVEN each vessel WHEN the timeline advances past a score change point in its `signal_timeline` THEN the vessel's color updates to reflect the classification at that moment. The color progression green→yellow→red→purple is the scoring engine's output made visible.
- GIVEN the Pause button WHEN pressed THEN playback freezes but the graph remains **fully interactive** — hover, click, drag, zoom all work
- GIVEN the scrub control WHEN the slider is dragged to any date THEN the graph snaps to the correct state instantly (no animation)
- GIVEN speed controls WHEN set to 1x/2x/5x THEN playback speed adjusts accordingly
- GIVEN step controls WHEN step-forward/step-back is clicked THEN the slider moves to the next/previous event
- GIVEN the timeline WHEN rendered THEN tick marks below the slider show where events cluster in time (dense clusters = rapid change periods)

**Test Requirements:**

- [ ] Test: Initial load shows current state with slider at max date
- [ ] Test: Dragging slider backward hides future edges
- [ ] Test: Play rewinds and advances through events in chronological order
- [ ] Test: Pause freezes playback but allows hover/click
- [ ] Test: Step forward advances to next event
- [ ] Test: Scrubbing to a specific date shows correct graph state
- [ ] Test: Graph interaction works at any point during playback

**Technical Notes:**

- Playback is client-side only — no server calls during animation. All data loaded upfront.
- Graph state at any date = filter on `hidden` attribute of nodes/edges based on from_date/to_date comparison. This is O(edges) and takes <1ms for fleet-sized graphs.
- ForceAtlas2 during playback: use high gravity + barnesHutOptimize to keep existing nodes stable when new nodes appear
- Event tick marks: render as a simple SVG or canvas row below the slider
- Speed: at 5x, an 18-month fleet build-out plays in ~20 seconds
- All state is client-side — VPS load during playback: zero

---

### Story 4: Graph View Integration

**As a** user
**I want to** seamlessly navigate between the map view and graph view
**So that** I can investigate vessels in both spatial and relational context

**Acceptance Criteria:**

- GIVEN the VesselPanel WHEN a vessel has an IMO and graph data THEN a "See Graph" button is visible
- GIVEN the "See Graph" button WHEN clicked THEN the browser navigates to `/graph/{imo}` — a **full-page** view that replaces the map entirely
- GIVEN the graph page WHEN rendered THEN a "Back to map" button (back arrow + text) is visible in the top-left corner
- GIVEN the "Back to map" button WHEN clicked THEN the browser navigates back to the map view with the original vessel selected
- GIVEN a vessel node in the graph WHEN "Go to vessel on map" is clicked THEN the browser navigates to the map view centered on that vessel
- GIVEN the graph page WHEN first loaded THEN it shows a loading state ("Computing layout...") while ForceAtlas2 runs in the web worker
- GIVEN the URL `/graph/{imo}` WHEN loaded directly (bookmark or shared link) THEN the graph renders correctly without needing to come from the map first

**Test Requirements:**

- [ ] Test: "See Graph" button appears for vessels with IMO numbers
- [ ] Test: "See Graph" navigates to `/graph/{imo}` full-page view
- [ ] Test: "Back to map" returns to map with original vessel selected
- [ ] Test: "Go to vessel on map" from a different vessel navigates map to that vessel
- [ ] Test: Direct URL load `/graph/{imo}` works without coming from map
- [ ] Test: Loading state shows during layout computation

**Technical Notes:**

- Use React Router for the graph route: `/graph/:imo`
- Full-page route — not a modal or overlay. The map unmounts (or hides) when the graph is active.
- The "See Graph" button should only appear for vessels that have an IMO (no IMO = no graph data)
- Loading state: show graph container with "Computing layout..." text while ForceAtlas2 web worker runs
- Browser back button should work naturally (graph → map)

---

## Implementation Order

1. Story 1 (API endpoints) — backend, independent
2. Story 2 (Sigma.js component) — frontend, depends on story 1 API format
3. Story 3 (temporal playback) — depends on story 2
4. Story 4 (integration) — depends on stories 2-3

Sequential execution.

## Architecture Decisions

- **Sigma.js v3 + Graphology** — WebGL rendering handles thousands of nodes. All rendering is client-side — zero server CPU during graph interaction.
- **Sub-fleet, not shadow fleet** — clicking "See Graph" loads the connected component through ownership/management chains. This shows one operation's fleet, not the entire shadow fleet. SanctionProgramme is NOT a node type — it would create a hub connecting all sanctioned vessels into one mega-component, which is meaningless. Sanctions status lives as an attribute on the Vessel node.
- **Dynamic vessel colors** — vessel classification is computed at each point in the timeline based on the signal_timeline. The visual progression green→yellow→red→purple is the scoring engine made visible — the analyst can verify "yes, the score makes sense at each transition."
- **Current state as default** — graph loads showing "now" state. User scrubs backward to explore history. This matches the investigation workflow: "what's happening?" then "how did we get here?"
- **Client-side playback** — all data loaded in one API call. Animation, filtering, and interaction are local. The VPS serves JSON once, then does nothing.
- **Replace existing NetworkGraph.tsx** — the D3-force component is superseded by Sigma.js. The MapLibre network layer (NetworkLayer.tsx) can be kept as a lightweight overview or removed.
- **No full-graph view yet** — the /networks endpoint (all flagged fleets) is a future enhancement. Start with per-fleet views accessed from individual vessels.
