# Feature Spec: Graph Data Model, FalkorDB & Scoring Engine

**Slug:** `graph-model-and-scoring`
**Created:** 2026-03-26
**Status:** approved
**Priority:** critical
**Depends on:** 39-local-dev-bootstrap, 40-paris-mou-pipeline, 41-opensanctions-ownership-graph
**Replaces:** Existing scoring system (services/scoring/), existing network_edges table, existing network_scorer.py, existing network_builder.py

---

## Overview

This is the core spec. It introduces FalkorDB as a graph database, defines the node/edge schema from the original graph scoring specification, builds the graph construction pipeline that joins all four data sources (Paris MoU, OpenSanctions, IACS, AIS), implements the new signal-based scoring engine (replacing the existing rule-based scorer), and adds geographic inference for AIS-derived signals.

The existing scoring engine (14+ rules, thresholds at 30/80/500) is **replaced entirely** by the new signal catalogue (A1-A11, B1-B7, C1-C5, D1-D7) with thresholds at 4/6/9. The existing `services/scoring/` directory, `network_edges` table, `network_scorer.py`, and `network_builder.py` are superseded.

## Problem Statement

The current scoring system was built incrementally — individual rules that each assign points. It lacks:
1. A unified graph model connecting vessels to owners, managers, class societies, flags, and insurers
2. Temporal edges that record *when* relationships changed (class transitions, flag changes, ownership transfers)
3. Geographic inference (Baltic/Barents origin detection, staging area patterns)
4. Fleet-level risk propagation through ownership/management chains
5. Cross-source signal correlation (Paris MoU inspection history + IACS class status + OpenSanctions ownership = combined evidence chain)

## Out of Scope

- NOT: Graph visualization frontend (spec 43)
- NOT: Paris MoU or OpenSanctions data ingestion (specs 40-41)
- NOT: Changes to AIS data capture or vessel_positions table
- NOT: Equasis automation (remains manual per the original spec)
- NOT: Full-graph analysis tools (Jupyter/NetworkX — analyst tooling, not production)

---

## User Stories

### Story 1: FalkorDB Infrastructure

**As a** system
**I want to** run FalkorDB as a Docker service
**So that** graph queries can be served efficiently

**Acceptance Criteria:**

- GIVEN docker-compose.yml WHEN updated THEN it includes a falkordb service using `falkordb/falkordb:latest` image
- GIVEN the FalkorDB service WHEN started THEN it persists data to a named volume
- GIVEN the FalkorDB service WHEN configured THEN it has appropriate CPU/memory limits (0.5 CPU, 1GB for VPS; unconstrained for local dev)
- GIVEN the shared config WHEN updated THEN it includes FalkorDB connection settings (host, port, graph name)
- GIVEN a Python client WHEN connecting THEN it uses the `falkordb` Python package to execute Cypher queries
- GIVEN the Makefile WHEN `make dev-up` runs THEN FalkorDB starts alongside postgres and redis

**Test Requirements:**

- [ ] Test: FalkorDB container starts and accepts connections
- [ ] Test: Python client can create a node and query it back
- [ ] Test: Data persists across container restarts (volume mount)

**Technical Notes:**

- FalkorDB is Redis-compatible — runs on port 6380 (avoid conflict with existing Redis on 6379)
- Python package: `falkordb` (pip install falkordb)
- Graph name: `heimdal`
- FalkorDB supports Cypher queries natively
- Memory: FalkorDB holds the entire graph in memory. Expected size: ~2000 vessels, ~500 companies, ~200 persons + edges = well under 500MB

---

### Story 2: Graph Node & Edge Schema

**As a** system
**I want to** define the graph schema with typed nodes and temporal edges
**So that** the graph faithfully represents vessel relationships over time

**Acceptance Criteria:**

- GIVEN the graph schema WHEN defined THEN it supports these node types with their attributes:
  - **Vessel**: imo (PK), name, mmsi, ship_type, gross_tonnage, build_year, score (computed), classification (green/yellow/red/blacklisted), last_psc_date, last_psc_port, deficiency_count, ism_deficiency, detained, last_seen_date, last_seen_lat, last_seen_lon
  - **Company**: name, jurisdiction, incorporation_date, ism_company_number, company_type (owner/ism_manager/operator), opensanctions_id
  - **Person**: name, nationality, date_of_birth, opensanctions_id
  - **ClassSociety**: name, iacs_member (boolean)
  - **FlagState**: name, iso_code, paris_mou_list (white/grey/black)
  - **PIClub**: name, ig_member (boolean)
- GIVEN the graph schema WHEN defined THEN it does NOT include SanctionProgramme as a node type. Sanctions status is an attribute on the Vessel node (classification='blacklisted', sanctions_programs=[] array). A SanctionProgramme node would act as a hub connecting all sanctioned vessels into one mega-component, defeating the sub-fleet structure.
- GIVEN the graph schema WHEN defined THEN it supports these edge types with temporal attributes:
  - **OWNED_BY** (Vessel→Company, Company→Company, Company→Person): from_date, to_date
  - **MANAGED_BY** (Vessel→Company): from_date, to_date
  - **CLASSED_BY** (Vessel→ClassSociety): from_date, to_date, status (active/suspended/withdrawn)
  - **FLAGGED_AS** (Vessel→FlagState): from_date, to_date
  - **INSURED_BY** (Vessel→PIClub): from_date, to_date
  - **DIRECTED_BY** (Company→Person): from_date, to_date
  - **STS_PARTNER** (Vessel→Vessel): event_date, latitude, longitude, duration_hours
- GIVEN a temporal edge WHEN to_date is null THEN the relationship is current (active)
- GIVEN a graph initialization script WHEN run THEN it creates node labels and indexes in FalkorDB

**Test Requirements:**

- [ ] Test: Create a Vessel node with all attributes, query it back
- [ ] Test: Create a temporal CLASSED_BY edge with from_date and to_date, query active edges at a specific date
- [ ] Test: Create OWNED_BY chain: Vessel→Company→Company→Person, query full chain
- [ ] Test: FalkorDB indexes on imo, opensanctions_id enable fast lookups

**Technical Notes:**

- FalkorDB is schema-less — "schema" here means conventions enforced by the graph builder code
- Create indexes: `CREATE INDEX FOR (v:Vessel) ON (v.imo)`, etc.
- Graph initialization script: `scripts/init_graph.py` or part of the graph builder
- This story defines the schema; stories 3-5 populate it

---

### Story 3: Graph Builder — Static Data Sources

**As a** system
**I want to** construct the graph from Paris MoU, OpenSanctions, and IACS data
**So that** all vessel relationships are represented with temporal edges

**Acceptance Criteria:**

- GIVEN Paris MoU inspection data in psc_inspections WHEN the graph builder runs THEN for each vessel (by IMO):
  - A Vessel node is created/updated with last_psc_date, deficiency_count, ism_deficiency, detained from the most recent inspection
  - A CLASSED_BY edge is created from Vessel to ClassSociety (the RO at inspection) with from_date=inspection_date
  - A FLAGGED_AS edge is created from Vessel to FlagState with from_date=inspection_date
  - An INSURED_BY edge is created from Vessel to PIClub (if P&I identified) with from_date=inspection_date
  - A MANAGED_BY edge is created from Vessel to Company (ISM company) with from_date=inspection_date
  - When a subsequent inspection shows a DIFFERENT class society, flag, P&I, or ISM company, the old edge gets to_date=new_inspection_date and a new edge is created — recording the transition

- GIVEN OpenSanctions data in os_entities/os_relationships WHEN the graph builder runs THEN:
  - Vessel entities matched to IMO (via os_vessel_links) update existing Vessel nodes or create new ones
  - Company and Person entities become Company and Person nodes
  - Ownership relationships become OWNED_BY edges with dates from the relationship properties
  - Directorship relationships become DIRECTED_BY edges
  - Sanction relationships set attributes on the Vessel node: sanctions_programs (array of programme names), sanctioned_date (earliest listing date). No SanctionProgramme nodes are created.
  - Vessel topics (shadow_fleet, sanction, etc.) are stored as Vessel node attributes

- GIVEN IACS data in iacs_vessels_current WHEN the graph builder runs THEN:
  - For each vessel (by IMO): if in IACS with status='Delivered' (in class), create/update CLASSED_BY edge with status='active'
  - If status='Suspended', update CLASSED_BY edge status='suspended'
  - If status='Withdrawn', set CLASSED_BY to_date and status='withdrawn'
  - If vessel NOT in IACS CSV but has a CLASSED_BY edge to an IACS member from Paris MoU — the absence is recorded (no active IACS CLASSED_BY edge)

- GIVEN all data sources WHEN the graph builder completes THEN it logs: nodes created by type, edges created by type, transitions detected, elapsed time

**Test Requirements:**

- [ ] Test: Paris MoU inspection creates Vessel node with correct attributes
- [ ] Test: Two Paris MoU inspections for same vessel with different RO creates two CLASSED_BY edges (old one with to_date, new one without)
- [ ] Test: OpenSanctions Company→Person ownership chain creates correct nodes and edges
- [ ] Test: IACS withdrawn status sets CLASSED_BY to_date
- [ ] Test: Vessel present in Paris MoU + OpenSanctions + IACS has merged data from all three sources
- [ ] Test: Graph builder is idempotent — running twice produces same graph

**Technical Notes:**

- Script/service: `services/graph-builder/builder.py` or `scripts/build_graph.py`
- Process order: Paris MoU first (creates the most Vessel nodes and temporal edges), then OpenSanctions (adds ownership chains), then IACS (updates class status)
- Use batch Cypher operations for performance: `UNWIND $batch AS row CREATE (v:Vessel {imo: row.imo, ...})`
- ClassSociety and FlagState nodes are created as needed (upsert pattern)
- PIClub nodes: create the 13 IG members as seed data, create others as encountered
- Company nodes from Paris MoU (ISM companies) and OpenSanctions may overlap — match on ism_company_number or opensanctions_id

---

### Story 4: Graph Builder — AIS-Derived Data

**As a** system
**I want to** enrich the graph with AIS-derived attributes and STS events
**So that** vessel positions, last-seen data, and behavioral patterns are in the graph

**Acceptance Criteria:**

- GIVEN vessel_positions and vessel_profiles in PostgreSQL WHEN the AIS enrichment runs THEN each Vessel node is updated with: last_seen_date, last_seen_lat, last_seen_lon, mmsi (from vessel_profiles)
- GIVEN GFW encounter events in gfw_events WHEN processed THEN STS_PARTNER edges are created between Vessel nodes with event_date, latitude, longitude, duration
- GIVEN existing anomaly_events with rule_id='sts_proximity' WHEN processed THEN STS_PARTNER edges are created (if not already from GFW)
- GIVEN the AIS enrichment WHEN it runs THEN it does NOT modify vessel_positions or vessel_profiles tables (read-only)

**Test Requirements:**

- [ ] Test: Vessel node updated with last_seen coordinates from vessel_profiles
- [ ] Test: GFW encounter event creates STS_PARTNER edge between two vessels
- [ ] Test: AIS enrichment does not write to PostgreSQL tables

**Technical Notes:**

- AIS data stays in PostgreSQL (TimescaleDB) — it's too large for FalkorDB
- Only summary data goes into the graph (last seen position, STS events)
- The geographic inference engine (story 6) reads from vessel_positions directly

---

### Story 5: Geographic Inference Engine

**As a** system
**I want to** detect Baltic/Barents Russian-origin transits, staging area loitering, and loiter-then-vanish patterns from AIS data
**So that** AIS-derived signals (D1-D7) can be computed for scoring

**Acceptance Criteria:**

- GIVEN vessel_positions for a tanker transiting south in the Baltic WHEN the inference engine evaluates THEN it checks for port call footprints at non-Russian terminals (Gdańsk, Butinge, Nynäshamn, Finnish refineries). If no footprint exists → signal D3 fires (Russian-origin transit)
- GIVEN vessel_positions for a tanker heading south past Finnmark WHEN evaluated THEN it checks for Melkøya origin. If no Melkøya footprint → signal D4 fires (Barents Russian-origin)
- GIVEN a vessel at anchor (nav_status=1 or SOG<1.0) in the Gulf of Finland approaches for >12h WHEN detected THEN signal D1 fires (staging area loiter)
- GIVEN a vessel at anchor in Kola Bay approaches for >12h WHEN detected THEN signal D2 fires
- GIVEN a vessel that loiters in a staging area and then goes dark (no AIS for >6h toward a Russian port) WHEN detected THEN signal D7 fires (loiter-then-vanish)
- GIVEN a vessel's MMSI MID WHEN it maps to a different flag than recorded in OpenSanctions or latest Paris MoU inspection THEN signal D5 fires (MMSI/flag mismatch)
- GIVEN an STS event between a vessel and a blacklisted/red vessel WHEN detected THEN signal D6 fires
- GIVEN the inference engine WHEN it stores results THEN they are stored in a PostgreSQL table `vessel_signals` (not in FalkorDB — these are scoring inputs, not graph relationships)

**Test Requirements:**

- [ ] Test: D3 fires for a vessel transiting Baltic with no non-Russian port call
- [ ] Test: D3 does NOT fire for a vessel with port call footprint at Gdańsk
- [ ] Test: D1 fires for vessel anchored in Gulf of Finland approaches for 14 hours
- [ ] Test: D1 does NOT fire for vessel anchored for 6 hours (under threshold)
- [ ] Test: D5 fires when MMSI MID=273 (Russia) but flag is recorded as Gabon
- [ ] Test: D5 does NOT fire when MMSI MID matches recorded flag
- [ ] Test: D7 requires both staging area loiter AND subsequent AIS gap toward Russian port

**Technical Notes:**

- Geographic zones defined as PostGIS polygons in the `zones` table (some already exist — Russian terminals, STS zones)
- Need to add: non-Russian Baltic terminal zones, Gulf of Finland staging area, Kola Bay staging area, Melkøya terminal zone, Skagen/Kattegat approaches
- Port call footprint = cluster of positions with nav_status=5 (moored) or SOG<0.5 within terminal zone radius
- "Goes dark toward Russian port" = last known heading/COG pointing toward Russian terminal + no subsequent positions for 6+ hours
- This reads from vessel_positions (PostgreSQL) — does NOT require FalkorDB
- The MID-to-flag mapping already exists in `shared/constants.py` (MID_TO_FLAG, 289 entries)

---

### Story 6: Signal-Based Scoring Engine

**As a** system
**I want to** compute vessel risk scores using the signal catalogue (A1-D7) and classify vessels as green/yellow/red/blacklisted
**So that** every vessel has a defensible, multi-source risk classification

**Acceptance Criteria:**

- GIVEN the signal catalogue WHEN evaluated for a vessel THEN each signal produces a weight:
  - **A signals (Paris MoU):** A1(3), A2(4), A3(2), A4(1), A5(2), A6(2), A7(3), A8(3), A9(2), A10(2), A11(3)
  - **B signals (OpenSanctions):** B1(4), B2(2), B3(2), B4(3), B5(1), B6(2), B7(1)
  - **C signals (IACS):** C1(3), C2(3), C3(4), C4(2), C5(3)
  - **D signals (AIS):** D1(3), D2(3), D3(4), D4(4), D5(2), D6(4), D7(4)
- GIVEN a vessel's total score WHEN classified THEN:
  - 0-3 → green
  - 4-5 → yellow
  - 6-8 → red
  - ≥9 → red (strong multi-source pattern)
- GIVEN a vessel matched in OpenSanctions with a linked Sanction entity WHEN classified THEN → blacklisted (regardless of score). This uses the existing sanctions_matcher.py result.
- GIVEN override rules WHEN evaluated THEN:
  - B1 alone → minimum yellow
  - (D3 or D4) + (A7 or A6) → minimum red
  - D6 (STS with blacklisted/red) → minimum red
  - C3 + A1 → minimum yellow
  - A10 or B4 → minimum yellow
- GIVEN a vessel's score and triggered signals WHEN stored THEN they update `vessel_profiles.risk_score` and `vessel_profiles.risk_tier` AND store per-signal details in a new `vessel_signals` table
- GIVEN the scoring engine WHEN it replaces the old system THEN the old scoring rules in `services/scoring/rules/` are moved to `services/scoring/rules/legacy/` (preserved, not deleted)

**Test Requirements:**

- [ ] Test: Vessel with no signals scores 0 → green
- [ ] Test: Vessel with A1(3) only scores 3 → green
- [ ] Test: Vessel with A1(3) + B5(1) scores 4 → yellow
- [ ] Test: Vessel with A1(3) + C1(3) scores 6 → red
- [ ] Test: Vessel with B1(4) alone → yellow (override)
- [ ] Test: Vessel with D3(4) + A7(3) → red (override, even though score=7 would already be red)
- [ ] Test: Vessel with D6(4) → red (override)
- [ ] Test: Sanctioned vessel → blacklisted regardless of score
- [ ] Test: Signal A1 only fires for tankers with GT ≥ 50,000
- [ ] Test: Signal A8 requires ≥2 Paris MoU inspections showing different RO
- [ ] Test: Signal C5 cross-references Paris MoU historical RO with current IACS status

**Technical Notes:**

- New table: `vessel_signals` with columns: mmsi, imo, signal_id (text, e.g. 'A1'), weight (real), triggered_at (timestamptz), details (jsonb), source_data (text — which data source triggered it)
- Migration: `db/migrations/026_vessel_signals.sql`
- The scoring engine reads from: psc_inspections (Paris MoU), os_entities/os_relationships (OpenSanctions), iacs_vessels_current (IACS), vessel_positions + geographic inference results (AIS)
- Signal evaluation can be done per-vessel — no graph traversal needed for most signals
- Signals A10 and B4 (fleet-level propagation) DO require graph traversal: find all vessels with MANAGED_BY→same Company or OWNED_BY→same Company, check if any sibling is blacklisted/red
- Move old rules to `services/scoring/rules/legacy/` — don't delete, preserve for reference
- The batch-pipeline stages (SCORE, ENRICH) need to be updated to call the new scoring engine

---

### Story 7: Graph-Based Fleet Risk Propagation

**As a** system
**I want to** propagate risk through the ownership/management graph
**So that** signals A10 (ISM company fleet risk) and B4 (owner fleet risk) work

**Acceptance Criteria:**

- GIVEN a vessel that is blacklisted WHEN the fleet propagation runs THEN all vessels with MANAGED_BY edges to the same Company node receive signal A10 (weight 2)
- GIVEN a vessel that is blacklisted WHEN the fleet propagation runs THEN all vessels with OWNED_BY edges to the same Company node (or Company→Company→Vessel chain) receive signal B4 (weight 3)
- GIVEN a Company node WHEN queried for its fleet THEN the query returns all vessels reachable via OWNED_BY or MANAGED_BY edges (one hop from company)
- GIVEN fleet propagation WHEN a sibling vessel is rescored THEN the propagation does NOT cascade infinitely (a vessel flagged due to propagation does not itself trigger propagation to others)
- GIVEN the propagation WHEN run as part of scoring THEN it runs AFTER individual vessel scoring and BEFORE final classification

**Test Requirements:**

- [ ] Test: Vessel B under same ISM company as blacklisted Vessel A gets signal A10
- [ ] Test: Vessel C owned by same Company as blacklisted Vessel A gets signal B4
- [ ] Test: Vessel D owned by a different Company does NOT get B4 from Vessel A
- [ ] Test: Propagation does not cascade (B4 on Vessel B does not propagate further to Vessel B's siblings)
- [ ] Test: Removing a vessel's blacklisted status removes A10/B4 from siblings on next scoring run

**Technical Notes:**

- FalkorDB Cypher query for fleet siblings:
  ```cypher
  MATCH (v:Vessel {imo: $imo})-[:MANAGED_BY|OWNED_BY]->(c:Company)<-[:MANAGED_BY|OWNED_BY]-(sibling:Vessel)
  WHERE sibling.imo <> $imo
  RETURN sibling
  ```
- Propagation is one-directional: blacklisted/red vessels propagate TO siblings, not FROM
- Run fleet propagation as a batch step, not real-time — it's O(fleets * vessels_per_fleet)

---

### Story 8: Batch Pipeline Integration

**As a** system operator
**I want to** run the full graph build and scoring pipeline as a batch job
**So that** the graph and scores stay current

**Acceptance Criteria:**

- GIVEN the batch pipeline WHEN it runs on the MacBook (initial bootstrap) THEN it executes in order:
  1. Build graph from Paris MoU data (story 3)
  2. Build graph from OpenSanctions data (story 3)
  3. Build graph from IACS data (story 3)
  4. Enrich graph with AIS data (story 4)
  5. Run geographic inference (story 5)
  6. Run per-vessel signal scoring (story 6)
  7. Run fleet risk propagation (story 7)
  8. Update vessel_profiles with final scores and classifications
- GIVEN the batch pipeline WHEN it runs on the VPS (incremental) THEN it only re-processes vessels with updated source data since last run
- GIVEN the pipeline WHEN complete THEN it logs per-stage timing and counts
- GIVEN a `--vessel` flag WHEN provided THEN it runs scoring for a single vessel (debugging mode)

**Test Requirements:**

- [ ] Test: Full pipeline runs end-to-end on local data without errors
- [ ] Test: Pipeline updates vessel_profiles.risk_score and risk_tier
- [ ] Test: Incremental mode only processes recently-updated vessels
- [ ] Test: Single-vessel mode produces correct score for a known vessel

**Technical Notes:**

- The existing batch-pipeline stages (LOAD, SCORE, ENRICH, BOOKKEEP) are refactored:
  - LOAD stays the same (AIS data loading)
  - SCORE is replaced by the new signal-based scorer
  - ENRICH is updated to trigger graph updates after enrichment
  - BOOKKEEP stays the same
- For the initial local bootstrap: the pipeline runs once over ALL data (not incremental)
- For VPS daily ops: the pipeline runs incrementally (only vessels with new data)

---

### Story 9: Graph Export for VPS Transfer

**As a** developer
**I want to** export the locally-built graph and transfer it to the VPS
**So that** the VPS loads a pre-built graph instead of rebuilding from scratch

**Acceptance Criteria:**

- GIVEN a locally-built graph WHEN I run `python scripts/export_graph.py` THEN it exports the FalkorDB graph to a dump file
- GIVEN a dump file WHEN transferred to the VPS and loaded THEN the VPS FalkorDB has the identical graph
- GIVEN the export WHEN run THEN it also exports the vessel_signals table as a SQL dump
- GIVEN the import script on VPS WHEN run THEN it loads the graph dump and vessel_signals into the VPS databases

**Test Requirements:**

- [ ] Test: Export produces a non-empty dump file
- [ ] Test: Import on a fresh FalkorDB instance restores all nodes and edges
- [ ] Test: Node and edge counts match between local and VPS after transfer

**Technical Notes:**

- FalkorDB supports `GRAPH.COPY` or RDB persistence — use `redis-cli --rdb` to dump the FalkorDB data file
- Transfer via SCP/rsync (same as existing deploy pattern)
- vessel_signals export: `pg_dump --table=vessel_signals -Fc > vessel_signals.dump`
- The VPS then runs incremental updates from daily/weekly data source syncs

---

## Implementation Order

**Group 1 (parallel):**
- Story 1 (FalkorDB infrastructure)
- Story 2 (graph schema)

**Group 2 (sequential, after group 1):**
- Story 3 (graph builder — static sources)
- Story 4 (graph builder — AIS)
- Story 5 (geographic inference)

**Group 3 (sequential, after group 2):**
- Story 6 (scoring engine)
- Story 7 (fleet propagation)

**Group 4 (after group 3):**
- Story 8 (batch pipeline integration)
- Story 9 (graph export)

## Architecture Decisions

- **FalkorDB as graph store** — the graph will grow with ownership chains, temporal edges, and fleet-level analysis. PostgreSQL relational tables hit their limits for multi-hop traversal, connected component detection, and fleet-centric queries.
- **PostgreSQL stays for time-series and source data** — vessel_positions (TimescaleDB), psc_inspections, os_entities, iacs_vessels_current stay in PostgreSQL. FalkorDB is a derived view constructed by the graph builder.
- **Scoring replaces, not extends** — the new signal catalogue (A1-D7) replaces the old 14+ rules entirely. Old rules moved to legacy/ for reference. The risk_tier enum stays (green/yellow/red/blacklisted) but thresholds change.
- **No changes to AIS capture** — vessel_positions and ais-ingest are untouched. AIS data is read-only input to the geographic inference engine.
- **Blacklisted = Purple** — same concept, "blacklisted" is the tier name, purple is the UI color for sanctioned vessels.
- **Geographic inference runs on PostgreSQL** — PostGIS spatial queries against vessel_positions. Results feed into scoring, not the graph.
- **Permissive flag list as constant** — Gabon, Cameroon, Comoros, Palau, Cook Islands, Djibouti, Gambia, Saint Kitts and Nevis, Sierra Leone, Mongolia, Malawi. Reviewed quarterly.
