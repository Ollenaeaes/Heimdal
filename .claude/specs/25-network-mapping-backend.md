# Feature Spec: Sanctions Evasion Network Mapping Backend

**Slug:** `network-mapping-backend`
**Created:** 2026-03-14
**Status:** draft
**Priority:** high

---

## Overview

Build the relationship graph between shadow fleet vessels from GFW encounter/loitering events and manual ownership enrichment. Store vessel-to-vessel edges in a `network_edges` table, compute network risk scores that propagate through connected clusters, and expose network data via API endpoints. This transforms Heimdal from individual vessel analysis to fleet-level pattern recognition.

## Problem Statement

The shadow fleet operates as a coordinated logistics system: feeder tankers load at Russian terminals, transfer cargo via STS to intermediary vessels, which carry it to buyers in India, China, and Turkey. Analyzing vessels individually misses these connections. By building a graph from encounter events, proximity correlations, and ownership links, Heimdal can reveal the logistics chains and propagate risk through the network — a clean vessel that regularly meets sanctioned tankers at STS zones is not truly clean.

## Out of Scope

- NOT: Frontend network graph visualization (d3-force), network tab, or globe network mode (separate spec)
- NOT: OpenCorporates integration for corporate ownership data (Phase 4+)
- NOT: Commercial STS databases (Windward, Lloyd's List Intelligence)
- NOT: Cargo tracking data (Kpler, Vortexa) — Heimdal infers from draft changes and port sequences
- NOT: Graph database — PostgreSQL with proper indexing handles the query patterns needed

---

## User Stories

### Story 1: Network Edges Database Table

**As a** system
**I want to** store vessel-to-vessel relationship edges with type, confidence, and temporal data
**So that** the network graph can be built incrementally and queried efficiently

**Acceptance Criteria:**

- GIVEN the database WHEN migration runs THEN a `network_edges` table exists with columns: id (BIGSERIAL PK), vessel_a_mmsi (INTEGER FK vessel_profiles), vessel_b_mmsi (INTEGER FK vessel_profiles), edge_type (VARCHAR 32), confidence (REAL default 1.0), first_observed (TIMESTAMPTZ), last_observed (TIMESTAMPTZ), observation_count (INTEGER default 1), location (GEOGRAPHY POINT 4326 nullable), details (JSONB default '{}')
- GIVEN the table WHEN checked THEN a UNIQUE constraint on (vessel_a_mmsi, vessel_b_mmsi, edge_type) exists
- GIVEN the table WHEN checked THEN indexes on vessel_a_mmsi, vessel_b_mmsi, and edge_type exist
- GIVEN an edge insertion with an existing (vessel_a, vessel_b, type) WHEN upserting THEN last_observed is updated and observation_count is incremented

**Test Requirements:**

- [ ] Test: Migration creates table with correct column types and constraints
- [ ] Test: FK constraints validate both MMSIs exist in vessel_profiles
- [ ] Test: UNIQUE constraint prevents duplicate edges (same vessel pair + type)
- [ ] Test: Upsert updates last_observed and increments observation_count
- [ ] Test: All three indexes exist (vessel_a, vessel_b, edge_type)
- [ ] Test: Location column accepts NULL (for ownership edges) and valid POINT values
- [ ] Test: Edge types accepted: 'encounter', 'proximity', 'ownership'

**Technical Notes:**

- Migration file: `database/migrations/013_network_edges.sql`
- UNIQUE constraint enables ON CONFLICT DO UPDATE for upsert pattern
- vessel_a_mmsi is always the lower MMSI to normalize edge direction (avoids duplicate A→B and B→A)

---

### Story 2: Network Edge Repository Functions

**As a** service
**I want to** create, update, and query network edges via repository functions
**So that** edge creation and network traversal are abstracted from the scoring/enrichment logic

**Acceptance Criteria:**

- GIVEN two MMSIs and an edge type WHEN `upsert_network_edge()` is called THEN an edge is created or updated (last_observed, observation_count, location)
- GIVEN an MMSI WHEN `get_vessel_network()` is called THEN all edges connected to that vessel are returned (both as vessel_a and vessel_b)
- GIVEN an MMSI WHEN `get_connected_vessels()` is called THEN a set of all MMSIs connected to it (direct neighbors) is returned
- GIVEN an MMSI WHEN `get_network_cluster()` is called THEN all MMSIs in the connected component (multi-hop) are returned via recursive traversal
- GIVEN optional filters (edge_type, min_confidence, since_date) WHEN querying edges THEN results are filtered accordingly

**Test Requirements:**

- [ ] Test: upsert_network_edge creates new edge with correct fields
- [ ] Test: upsert_network_edge on existing edge updates last_observed and increments count
- [ ] Test: get_vessel_network returns edges where MMSI is vessel_a OR vessel_b
- [ ] Test: get_connected_vessels returns correct set of direct neighbor MMSIs
- [ ] Test: get_network_cluster traverses multi-hop connections (A→B→C returns {A, B, C} from any starting point)
- [ ] Test: get_network_cluster handles cycles without infinite loops
- [ ] Test: Edge type filter works (e.g., only 'encounter' edges)
- [ ] Test: Date filter excludes old edges
- [ ] Test: MMSI normalization — edge between (123, 456) and (456, 123) are the same edge

**Technical Notes:**

- File: `shared/db/network_repository.py`
- MMSI normalization: always store min(mmsi_a, mmsi_b) as vessel_a_mmsi
- Cluster traversal: iterative BFS with a max depth limit (default 5 hops) to prevent runaway queries
- Keep functions async, matching existing repository pattern

---

### Story 3: Encounter Edge Creation

**As a** scoring engine
**I want to** create ENCOUNTER edges from GFW encounter events
**So that** confirmed two-vessel rendezvous are recorded in the network graph

**Acceptance Criteria:**

- GIVEN a GFW encounter event with two vessel MMSIs WHEN processed THEN an ENCOUNTER edge is created/updated between the two vessels with confidence 1.0
- GIVEN the encounter event has a location WHEN creating the edge THEN the location is stored as a POINT geometry
- GIVEN an encounter between two vessels that already have an ENCOUNTER edge WHEN processed THEN observation_count increments and last_observed updates
- GIVEN a GFW encounter event where one or both vessels are not in vessel_profiles WHEN processed THEN the edge is NOT created (FK constraint)

**Test Requirements:**

- [ ] Test: GFW encounter with both MMSIs in vessel_profiles → creates ENCOUNTER edge
- [ ] Test: Edge has confidence=1.0, correct first/last_observed, location point
- [ ] Test: Second encounter between same pair → observation_count=2, last_observed updated
- [ ] Test: Encounter with unknown MMSI → edge not created, logged as warning
- [ ] Test: Location stored correctly as GEOGRAPHY POINT

**Technical Notes:**

- Integration point: `services/scoring/rules/gfw_encounter.py` — add edge creation call after encounter event is scored
- Alternatively, create a dedicated `services/scoring/network_builder.py` that subscribes to scored events and creates edges
- The GFW encounter event contains both vessel MMSIs in the event data (vessel.ssvid and encounter.vessel.ssvid)

---

### Story 4: Proximity Edge Creation

**As a** scoring engine
**I want to** create PROXIMITY edges when two vessels loiter at the same STS zone within 24 hours of each other
**So that** sequential STS operations (where both vessels don't appear simultaneously) are captured

**Acceptance Criteria:**

- GIVEN a GFW loitering event in an STS zone WHEN another vessel loitered in the same zone within ±24 hours THEN a PROXIMITY edge is created between all pairs with confidence 0.7
- GIVEN the temporal window is > 24 hours apart WHEN checking THEN no PROXIMITY edge is created
- GIVEN the loitering is NOT in an STS zone WHEN checking THEN no PROXIMITY edge is created (open ocean loitering is not relevant)
- GIVEN multiple vessels loitered in the same zone within 24 hours WHEN processed THEN edges are created between ALL pairs

**Test Requirements:**

- [ ] Test: Vessel A loiters at Malta OPL at T, vessel B loiters at Malta OPL at T+12h → PROXIMITY edge created
- [ ] Test: Vessel A loiters at Malta OPL at T, vessel B loiters at Malta OPL at T+30h → no edge (> 24h)
- [ ] Test: Vessel A loiters in open ocean → no proximity edges created
- [ ] Test: Three vessels (A, B, C) loiter at same zone within 24h → 3 edges (A-B, A-C, B-C)
- [ ] Test: Confidence is 0.7 for proximity edges (lower than encounter)
- [ ] Test: Repeated proximity events between same pair → observation_count increments

**Technical Notes:**

- Integration point: after GFW loitering events are processed
- Query: find other loitering events in the same zone (ST_DWithin) within ±24h window
- STS zone detection: reuse `is_in_sts_zone()` from zone_helpers.py
- Edge type: 'proximity'

---

### Story 5: Ownership Edge Creation

**As a** enrichment system
**I want to** create OWNERSHIP edges when vessels share the same registered owner or commercial manager
**So that** shell company networks connecting fleet vessels are captured

**Acceptance Criteria:**

- GIVEN a vessel profile update with ownership data (registered_owner or commercial_manager) WHEN another vessel has matching ownership THEN an OWNERSHIP edge is created with confidence 1.0
- GIVEN ownership matching WHEN comparing names THEN case-insensitive comparison is used
- GIVEN an ownership edge WHEN the edge is created THEN location is NULL (ownership is not location-specific)
- GIVEN no matching ownership data WHEN checking THEN no edge is created

**Test Requirements:**

- [ ] Test: Two vessels with same registered_owner → OWNERSHIP edge created
- [ ] Test: Two vessels with same commercial_manager but different owners → OWNERSHIP edge created
- [ ] Test: Case-insensitive matching ("ABC Shipping" == "abc shipping") → edge created
- [ ] Test: No other vessels with matching ownership → no edge created
- [ ] Test: Ownership edge has location=NULL
- [ ] Test: Confidence is 1.0 for ownership edges

**Technical Notes:**

- Integration point: triggered on manual enrichment (POST /api/vessels/{mmsi}/enrich) and on Equasis upload
- Ownership data is in vessel_profiles.ownership_data (JSONB) — fields: registered_owner, commercial_manager
- Query: search vessel_profiles for matching ownership fields when enrichment is submitted
- Edge type: 'ownership'

---

### Story 6: Network Risk Score Calculation

**As a** scoring engine
**I want to** compute a network risk score for each connected component of vessels
**So that** risk propagates through encounter/ownership links and clean intermediaries are flagged

**Acceptance Criteria:**

- GIVEN a vessel connected to a sanctioned vessel (1 hop) WHEN network score is computed THEN the vessel's network score increases by 30 points
- GIVEN a cluster with 3+ vessels that all visited Russian terminals AND STS zones WHEN network score is computed THEN the cluster receives a pattern bonus of 20 points per vessel
- GIVEN a vessel with no network edges WHEN network score is computed THEN network score is 0
- GIVEN a vessel WHEN querying its risk THEN both individual risk_score and network_score are available

**Test Requirements:**

- [ ] Test: Vessel A (sanctioned, 100pts) → Vessel B (clean, 0pts): B gets network_score=30
- [ ] Test: Vessel A (sanctioned) → Vessel B → Vessel C (2 hops): C gets network_score=15 (decays with distance)
- [ ] Test: Cluster of 4 vessels all with Russian port + STS visits → pattern bonus applied
- [ ] Test: Isolated vessel (no edges) → network_score=0
- [ ] Test: Network score updates when new edges are added
- [ ] Test: Network score is stored separately from individual risk_score (does not modify it)

**Technical Notes:**

- File: `services/scoring/network_scorer.py`
- Network score is stored in vessel_profiles as a new column `network_score` (INTEGER default 0) — add via migration
- Calculation: BFS from the target vessel, decaying score contribution with hop distance (1 hop: 30pts, 2 hops: 15pts, 3+ hops: 5pts per sanctioned vessel)
- Pattern bonus: if cluster has ≥3 vessels with gfw_port_visit (Russian) + sts_proximity/gfw_encounter anomalies
- Recalculation triggered when: new edge created, vessel risk tier changes, enrichment updates
- Consider batch recalculation on a timer (every 30 minutes) rather than per-event to avoid cascade storms

---

### Story 7: Network API Endpoints

**As an** API consumer
**I want to** query network data for a vessel
**So that** the frontend can display network graphs and the operator can explore connections

**Acceptance Criteria:**

- GIVEN a vessel MMSI WHEN `GET /api/vessels/{mmsi}/network` is called THEN return the vessel's direct edges (neighbors) with edge type, confidence, observation count, first/last observed, and location
- GIVEN a vessel MMSI WHEN `GET /api/vessels/{mmsi}/network?depth=2` is called THEN return edges up to 2 hops from the vessel (the subgraph)
- GIVEN an optional edge_type filter WHEN querying THEN only edges of that type are returned
- GIVEN the response WHEN returned THEN each edge includes basic profile data for the connected vessel (name, flag, risk_tier, ship_type)
- GIVEN `GET /api/network/clusters` WHEN called THEN return a summary of the largest connected components (cluster_size, max_risk_tier, sanctioned_count)

**Test Requirements:**

- [ ] Test: GET /api/vessels/{mmsi}/network returns direct edges with correct structure
- [ ] Test: depth=2 returns 2-hop subgraph (edges of edges)
- [ ] Test: edge_type=encounter filter returns only encounter edges
- [ ] Test: Response includes vessel profile data for connected vessels
- [ ] Test: Unknown MMSI returns 404
- [ ] Test: Vessel with no edges returns empty list
- [ ] Test: GET /api/network/clusters returns cluster summaries sorted by size descending
- [ ] Test: Cluster summary includes sanctioned_count (vessels with sanctions_match anomalies)

**Technical Notes:**

- Routes file: `services/api-server/routes/network.py`
- Register in api-server app factory
- Depth parameter capped at 3 to prevent expensive traversals
- Cluster endpoint uses get_network_cluster for each vessel, deduplicating clusters by smallest MMSI in the set
- Include vessel_name, flag, risk_tier, ship_type in edge response via JOIN with vessel_profiles

---

## Technical Design

### Data Model Changes

- New table: `network_edges` (vessel-to-vessel relationship graph)
- New column: `vessel_profiles.network_score` (INTEGER default 0) — added via migration
- New entries in MAX_PER_RULE: none (network scoring produces network_score, not anomaly events)

### API Changes

- `GET /api/vessels/{mmsi}/network` — vessel's network edges with optional depth and type filters
- `GET /api/network/clusters` — summary of connected components
- `GET /api/vessels/{mmsi}` response extended with `network_score` field

### Dependencies

- GFW Events API encounter and loitering data (already available via Update 001 / spec 08)
- Manual enrichment ownership data (spec 12)
- Existing zone_helpers.py for STS zone checks
- vessel_profiles table for FK constraints and profile data

### Security Considerations

- Network endpoints are read-only
- No new external data sources
- Cluster traversal is depth-limited to prevent DoS via deep graph queries

---

## Implementation Order

### Group 1 (sequential — migration first)
- Story 1 — DB migration: `database/migrations/013_network_edges.sql`

### Group 2 (sequential — after Group 1)
- Story 2 — Repository functions: `shared/db/network_repository.py`

### Group 3 (parallel — after Group 2)
- Story 3 — Encounter edge creation: integration in scoring engine
- Story 4 — Proximity edge creation: integration in scoring engine
- Story 5 — Ownership edge creation: integration in enrichment/API

### Group 4 (parallel — after Group 3)
- Story 6 — Network risk scoring: `services/scoring/network_scorer.py`
- Story 7 — Network API endpoints: `services/api-server/routes/network.py`

**Parallel safety rules:**
- Stories 3, 4, 5 all call upsert_network_edge from different integration points — no file conflicts
- Story 6 and 7 touch different services (scoring vs api-server)
- Repository functions (Story 2) must exist before any edge creation stories

---

## Development Approach

### Simplifications (what starts simple)

- Network score recalculation runs on a 30-minute timer, not per-event
- Cluster traversal limited to 5 hops max (sufficient for real-world shadow fleet chains)
- Ownership matching is exact string comparison (case-insensitive) — no fuzzy matching
- No graph database — PostgreSQL handles the join patterns needed

### Upgrade Path (what changes for production)

- "Add OpenCorporates integration" for corporate ownership graph enrichment
- "Add fuzzy ownership matching" using Levenshtein distance for company name variations
- "Real-time network score updates" triggered per-event instead of timer-based
- "Betweenness centrality calculation" to identify key intermediary vessels
- "Network analytics dashboard" with hub detection, bridge vessel identification

### Architecture Decisions

- PostgreSQL over graph database — the query patterns (direct neighbors, BFS traversal up to 5 hops, cluster detection) are well-served by recursive CTEs. Adding Neo4j/DGraph would increase operational complexity for marginal query benefit at current scale.
- MMSI normalization (min/max) — ensures each vessel pair has exactly one edge per type, simplifying queries
- Separate network_score column rather than incorporating into risk_score — network risk is a different signal that should be displayed separately. A vessel can be individually clean but network-connected to sanctioned vessels.
- Timer-based recalculation — avoids cascade storms where one new edge triggers recalculations across an entire cluster, which triggers more recalculations, etc.

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (edge traversal, score propagation, cluster detection)
- [ ] Edge cases handled (isolated vessels, cycles, large clusters)
- [ ] No regressions in existing tests
- [ ] Code committed with proper messages
- [ ] Network endpoints return correct data structures
- [ ] MMSI normalization prevents duplicate edges
- [ ] Network score calculation is bounded (no infinite loops or cascade storms)
- [ ] Ready for human review
