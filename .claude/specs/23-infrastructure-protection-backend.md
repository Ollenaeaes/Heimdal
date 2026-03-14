# Feature Spec: Infrastructure Protection Backend

**Slug:** `infrastructure-protection-backend`
**Created:** 2026-03-14
**Status:** draft
**Priority:** high

---

## Overview

Detect vessels exhibiting behavior consistent with subsea cable or pipeline sabotage — specifically the anchor-drag attack pattern used in every confirmed Baltic Sea infrastructure incident since 2023. Three new scoring rules evaluate vessel behavior within cable/pipeline corridors, backed by new database tables and Redis-based entry/exit state tracking.

## Problem Statement

Between October 2023 and December 2025, at least nine submarine telecommunications cables were cut in the Baltic Sea, along with a gas pipeline and an underwater power cable. The pattern is consistent: a vessel reduces speed over a cable route and drags its anchor along the seabed for an extended distance. No open-source tool currently provides automated detection of this pattern. Heimdal already has the AIS data, PostGIS spatial queries, and Redis state tracking needed — it just needs cable route geometries and rules to evaluate against them.

## Out of Scope

- NOT: Frontend visualization of cable routes, infrastructure overlays, or dashboard panels (separate spec)
- NOT: Real-time cable integrity monitoring (DAS/DTSS) — Heimdal approaches from the vessel side
- NOT: Copernicus Marine weather data integration for false positive reduction (future enhancement)
- NOT: Classified NATO infrastructure maps — public sources are sufficient
- NOT: Precise cable burial depth or condition data

---

## User Stories

### Story 1: Infrastructure Routes Database Table

**As a** system
**I want to** store subsea cable, pipeline, and other infrastructure route geometries
**So that** scoring rules can evaluate vessel proximity to critical infrastructure

**Acceptance Criteria:**

- GIVEN the database WHEN migration runs THEN an `infrastructure_routes` table exists with columns: id (SERIAL PK), name (VARCHAR 256), route_type (VARCHAR 32), operator (VARCHAR 256 nullable), geometry (GEOGRAPHY LINESTRING 4326), buffer_nm (REAL default 1.0), metadata (JSONB default '{}')
- GIVEN the table WHEN a GIST index on geometry is checked THEN it exists and is used by spatial queries
- GIVEN the database WHEN migration runs THEN an `infrastructure_events` table exists with columns: id (BIGSERIAL PK), mmsi (INTEGER FK vessel_profiles), route_id (INTEGER FK infrastructure_routes), entry_time (TIMESTAMPTZ), exit_time (TIMESTAMPTZ nullable), duration_minutes (REAL nullable), min_speed (REAL nullable), max_alignment (REAL nullable), risk_assessed (BOOLEAN default FALSE), details (JSONB default '{}')
- GIVEN the infrastructure_events table WHEN checked THEN a composite index on (mmsi, entry_time DESC) exists

**Test Requirements:**

- [ ] Test: Migration creates both tables with correct column types and constraints
- [ ] Test: infrastructure_routes FK constraint validates route_id in infrastructure_events
- [ ] Test: vessel_profiles FK constraint validates mmsi in infrastructure_events
- [ ] Test: GIST index on infrastructure_routes.geometry exists
- [ ] Test: Composite index on infrastructure_events (mmsi, entry_time DESC) exists
- [ ] Test: Default values work correctly (buffer_nm=1.0, metadata='{}', risk_assessed=FALSE)

**Technical Notes:**

- Migration file: `database/migrations/011_infrastructure_tables.sql`
- Uses GEOGRAPHY type (not GEOMETRY) for accurate distance calculations in metres
- The zones table is NOT modified — infrastructure_routes is a separate table because it stores LINESTRINGs, not POLYGONs

---

### Story 2: Infrastructure Data Loading Script

**As a** system operator
**I want to** load cable and pipeline route geometries from shapefiles into the database
**So that** the infrastructure scoring rules have route data to evaluate against

**Acceptance Criteria:**

- GIVEN EMODnet/HELCOM cable shapefile data WHEN the loading script runs THEN LINESTRING geometries are inserted into infrastructure_routes with correct route_type values
- GIVEN the loading script WHEN it processes a cable route THEN it sets route_type to one of: 'telecom_cable', 'power_cable', 'gas_pipeline', 'oil_pipeline'
- GIVEN duplicate data WHEN the script runs again THEN it upserts (updates existing, inserts new) based on name + route_type
- GIVEN the loading script WHEN it completes THEN it logs the count of routes loaded per type

**Test Requirements:**

- [ ] Test: Script inserts LINESTRING geometries that can be queried with ST_DWithin
- [ ] Test: Script correctly maps source data fields to route_type enum values
- [ ] Test: Upsert behavior — running twice with the same data doesn't create duplicates
- [ ] Test: Script handles empty/malformed geometries gracefully (skip with warning)
- [ ] Test: Loaded routes have valid buffer_nm defaults

**Technical Notes:**

- Script location: `scripts/load_infrastructure.py`
- Uses geopandas or ogr2ogr for shapefile reading
- Initial data sources: EMODnet Human Activities (cables + pipelines), HELCOM map service (Baltic cables)
- Include a sample GeoJSON fixture in `data/infrastructure/` for testing without full shapefiles
- The script should also support loading from GeoJSON (easier for manual additions)

---

### Story 3: Infrastructure Zone Helpers

**As a** scoring rule
**I want to** query whether a vessel position is within an infrastructure corridor and compute alignment angles
**So that** the three infrastructure rules can evaluate vessel behavior near cables/pipelines

**Acceptance Criteria:**

- GIVEN a lat/lon position WHEN `is_in_infrastructure_corridor()` is called THEN it returns a list of matching infrastructure route records (id, name, route_type, buffer_nm) where the position is within `buffer_nm` nautical miles of the route
- GIVEN a lat/lon position and a route geometry WHEN `compute_cable_bearing()` is called THEN it returns the bearing (degrees) of the nearest segment of the route linestring at the closest point to the vessel
- GIVEN a vessel COG and a cable bearing WHEN `angle_difference()` is called THEN it returns the minimum angular difference accounting for 360-degree wraparound (range: 0-180)
- GIVEN a lat/lon position WHEN `is_in_port_approach()` is called THEN it returns True if the position is within 10nm of any port in the ports table

**Test Requirements:**

- [ ] Test: Position directly on a cable route returns the route in corridor check (within default 1nm buffer)
- [ ] Test: Position 0.5nm from a cable route returns the route (within buffer)
- [ ] Test: Position 2nm from a cable route with 1nm buffer returns empty list
- [ ] Test: Cable bearing computation returns correct bearing for a simple N-S linestring
- [ ] Test: Cable bearing computation returns correct bearing for the nearest segment of a multi-segment linestring
- [ ] Test: Angle difference between COG=10 and bearing=350 returns 20 (wraparound)
- [ ] Test: Angle difference between COG=180 and bearing=0 returns 180
- [ ] Test: Port approach check returns True within 10nm, False outside

**Technical Notes:**

- File: `services/scoring/rules/infra_helpers.py` (similar pattern to `zone_helpers.py`)
- Corridor check uses `ST_DWithin(geometry, point, buffer_nm * 1852)` (convert nm to metres)
- Bearing computation uses `ST_LineLocatePoint` to find closest point on linestring, then calculates bearing of the segment at that point
- Port approach check reuses existing `is_near_port()` from zone_helpers.py with 10nm radius

---

### Story 4: Cable Corridor Slow Transit Rule

**As a** scoring engine
**I want to** detect vessels transiting through cable corridors at anomalously low speed for extended duration
**So that** potential anchor-drag sabotage patterns are flagged

**Acceptance Criteria:**

- GIVEN a vessel within a cable corridor buffer AND SOG < 7 knots AND not in a port approach zone AND not a cable-laying vessel AND duration > 30 minutes WHEN the rule evaluates THEN it fires
- GIVEN duration 30-60 minutes WHEN the rule fires THEN severity is "high" with 40 points
- GIVEN duration > 60 minutes WHEN the rule fires THEN severity is "critical" with 100 points
- GIVEN a vessel with existing shadow fleet indicators (Russian port history, sanctions match, flag changes, non-IG P&I) WHEN the rule fires THEN 40 additional points are added regardless of duration
- GIVEN a vessel in a port approach zone (within 10nm of port) WHEN in a cable corridor THEN the rule does NOT fire (false positive exclusion)
- GIVEN a cable-laying vessel (ship_type code 33 or MMSI in whitelist) WHEN in a cable corridor THEN the rule does NOT fire

**Test Requirements:**

- [ ] Test: Vessel at 5 knots in cable corridor for 45 minutes → fires high (40 points)
- [ ] Test: Vessel at 5 knots in cable corridor for 90 minutes → fires critical (100 points)
- [ ] Test: Vessel at 5 knots in cable corridor for 20 minutes → does NOT fire (under 30 min)
- [ ] Test: Vessel at 10 knots in cable corridor for 60 minutes → does NOT fire (speed above 7)
- [ ] Test: Vessel at 5 knots in cable corridor AND within port approach → does NOT fire
- [ ] Test: Ship type 33 at 5 knots in cable corridor for 60 minutes → does NOT fire
- [ ] Test: Vessel with sanctions_match anomaly + 45 min corridor transit → fires high (40 + 40 = 80 points)
- [ ] Test: Vessel with no shadow fleet indicators + 45 min → fires high (40 points, no escalation)
- [ ] Test: Entry/exit tracking via Redis correctly computes duration

**Technical Notes:**

- File: `services/scoring/rules/cable_slow_transit.py`
- Rule ID: `cable_slow_transit`
- Redis state: `heimdal:cable_entry:{mmsi}` → `{route_id, entry_time, entry_lat, entry_lon}`
- On each position: check if in corridor → if yes and no Redis entry, create entry. If yes and entry exists, compute duration. If no and entry exists, evaluate duration and write anomaly.
- Shadow fleet indicator check: query existing anomalies for rule_ids in [sanctions_match, gfw_port_visit, flag_hopping, insurance_class_risk]
- Must add `cable_slow_transit` to MAX_PER_RULE in constants.py (cap: 140 to accommodate escalation)

---

### Story 5: Cable Alignment Transit Rule

**As a** scoring engine
**I want to** detect vessels whose course runs parallel to a cable route rather than crossing it
**So that** the distinctive anchor-drag sabotage pattern is specifically identified

**Acceptance Criteria:**

- GIVEN a vessel in a cable corridor AND COG aligned within 20 degrees of cable bearing AND sustained for > 15 minutes WHEN the rule evaluates THEN it fires
- GIVEN parallel transit 15-60 minutes WHEN the rule fires THEN severity is "high" with 40 points
- GIVEN parallel transit > 60 minutes WHEN the rule fires THEN severity is "critical" with 100 points
- GIVEN angle difference > 30 degrees WHEN checking alignment THEN the parallel counter resets

**Test Requirements:**

- [ ] Test: COG=45, cable bearing=40 (5-degree difference) sustained 20 min → fires high (40 points)
- [ ] Test: COG=45, cable bearing=40 sustained 90 min → fires critical (100 points)
- [ ] Test: COG=45, cable bearing=40 sustained 10 min → does NOT fire (under 15 min)
- [ ] Test: COG=45, cable bearing=100 (55-degree difference) → does NOT fire (not parallel)
- [ ] Test: COG=5, cable bearing=355 → angle difference is 10 degrees (wraparound), counts as parallel
- [ ] Test: Parallel counter resets when angle exceeds 30 degrees between positions
- [ ] Test: Redis tracking correctly maintains consecutive parallel position count

**Technical Notes:**

- File: `services/scoring/rules/cable_alignment.py`
- Rule ID: `cable_alignment`
- Redis state: `heimdal:cable_align:{mmsi}` → `{route_id, first_parallel_time, consecutive_count}`
- Uses `compute_cable_bearing()` and `angle_difference()` from infra_helpers.py
- Reset when angle difference > 30 degrees (more permissive than the 20-degree trigger to avoid flip-flopping)
- Must add `cable_alignment` to MAX_PER_RULE in constants.py (cap: 100)

---

### Story 6: Open Water Speed Anomaly Near Infrastructure Rule

**As a** scoring engine
**I want to** detect vessels that decelerate significantly when passing over critical infrastructure
**So that** unexplained speed reductions near cables/pipelines are flagged as soft indicators

**Acceptance Criteria:**

- GIVEN a vessel entering an infrastructure proximity zone AND SOG drops by > 50% compared to average SOG over preceding 2 hours WHEN the rule evaluates THEN it fires with severity "moderate" (15 points)
- GIVEN the deceleration is within a port approach zone (10nm of port) WHEN the rule evaluates THEN it does NOT fire
- GIVEN a vessel with insufficient speed history (< 2 hours of positions) WHEN the rule evaluates THEN it does NOT fire

**Test Requirements:**

- [ ] Test: Vessel averaging 12 knots drops to 5 knots (58% drop) in cable corridor → fires moderate (15 points)
- [ ] Test: Vessel averaging 12 knots drops to 8 knots (33% drop) in cable corridor → does NOT fire (under 50%)
- [ ] Test: Vessel drops speed near infrastructure BUT within port approach → does NOT fire
- [ ] Test: Vessel with only 30 minutes of position history → does NOT fire (insufficient baseline)
- [ ] Test: Average SOG computation uses positions from preceding 2 hours only

**Technical Notes:**

- File: `services/scoring/rules/infra_speed_anomaly.py`
- Rule ID: `infra_speed_anomaly`
- This is a softer signal (15 points) — designed to add weight to other indicators, not stand alone
- 2-hour average computed from recent_positions passed to evaluate()
- Checks all infrastructure corridor types (cable, pipeline, wind farm buffer, platform buffer)
- Must add `infra_speed_anomaly` to MAX_PER_RULE in constants.py (cap: 15)

---

## Technical Design

### Data Model Changes

- New table: `infrastructure_routes` (LINESTRING geometries for cables, pipelines)
- New table: `infrastructure_events` (vessel entry/exit tracking for infrastructure corridors)
- New entries in MAX_PER_RULE: cable_slow_transit (140), cable_alignment (100), infra_speed_anomaly (15)

### API Changes

None in this spec. The existing anomaly endpoints will naturally return anomalies from the new rules. Infrastructure-specific API endpoints are deferred to the frontend spec.

### Dependencies

- PostGIS ST_DWithin, ST_Buffer, ST_LineLocatePoint for spatial queries
- Redis for entry/exit state tracking (existing infrastructure)
- Ports table (migration 007) for port approach exclusion
- Existing vessel_profiles for ship_type checks
- External: EMODnet/HELCOM shapefiles for initial cable route data

### Security Considerations

- Data loading script runs locally, not exposed via API
- No new API endpoints in this spec
- Infrastructure route data is public (EMODnet, HELCOM)

---

## Implementation Order

### Group 1 (parallel — no dependencies)
- Story 1 — DB migration: `database/migrations/011_infrastructure_tables.sql`
- Story 2 — Data loading script: `scripts/load_infrastructure.py`, `data/infrastructure/`

### Group 2 (sequential — after Group 1)
- Story 3 — Infrastructure zone helpers: `services/scoring/rules/infra_helpers.py`

### Group 3 (parallel — after Group 2)
- Story 4 — Cable slow transit rule: `services/scoring/rules/cable_slow_transit.py`
- Story 5 — Cable alignment rule: `services/scoring/rules/cable_alignment.py`
- Story 6 — Speed anomaly rule: `services/scoring/rules/infra_speed_anomaly.py`

**Parallel safety rules:**
- Stories in the same group touch DIFFERENT files/folders
- Stories 4, 5, 6 each create their own rule file but all update constants.py — the last story to merge adds all three rule entries to avoid conflicts (or each story adds its own entry since they're different keys)
- Migration (Story 1) must complete before helpers (Story 3) can be tested against real tables

---

## Development Approach

### Simplifications (what starts simple)

- Cable route data starts with a sample GeoJSON fixture for testing; full shapefile loading is a separate manual step
- Cable-laying vessel whitelist starts as ship_type==33 check only; MMSI whitelist is a config.yaml list populated manually later
- Weather-based false positive exclusion (Copernicus) is deferred — not implemented in this round

### Upgrade Path (what changes for production)

- "Integrate Copernicus Marine weather data" for weather-based speed change exclusion
- "Add Kartverket Norwegian cable data" as additional data source
- "Add TeleGeography global cable routes" for worldwide coverage beyond Baltic
- "Cable-laying vessel MMSI whitelist management" via API endpoint

### Architecture Decisions

- Separate `infrastructure_routes` table rather than extending `zones` table — routes are LINESTRINGs, zones are POLYGONs. Different geometry types, different query patterns.
- Redis-based entry/exit tracking rather than pure DB queries — matches existing patterns (dedup, metrics) and avoids per-position DB writes
- Three separate rule files rather than one combined rule — each has distinct logic and can be independently enabled/disabled

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled
- [ ] No regressions in existing tests
- [ ] Code committed with proper messages
- [ ] New rule_ids added to MAX_PER_RULE and ALL_RULE_IDS
- [ ] Sample infrastructure data loads correctly
- [ ] Rules auto-discovered by scoring engine (no engine changes needed)
- [ ] Ready for human review
