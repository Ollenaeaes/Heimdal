# Feature Spec: AIS Spoofing Detection Backend

**Slug:** `spoofing-detection-backend`
**Created:** 2026-03-14
**Status:** draft
**Priority:** high

---

## Overview

Five new scoring rules that detect AIS data manipulation: position on land, physically impossible speed, duplicate MMSI, positional repetition/freezing, and MMSI-IMO cross-reference mismatch. Plus GNSS interference zone detection as a byproduct of clustering spoofing events. These rules stack with (not replace) the existing `ais_spoofing` rule which covers position_jump, circle_spoofing, anchor_spoofing, and slow_roll patterns.

## Problem Statement

The shadow fleet increasingly uses AIS spoofing because going dark triggers immediate alerts in modern monitoring systems. The existing `ais_spoofing` rule detects four patterns but misses several important spoofing signatures: positions reported on land, ship-type-specific impossible speeds, duplicate MMSIs broadcasting from incompatible locations, frozen/repeating positions, and identity theft from scrapped vessels. These new rules cover the gaps.

## Out of Scope

- NOT: Frontend visualization of spoofed vessels, GNSS zones, or duplicate MMSI lines (separate spec)
- NOT: RF signal direction-finding (TDOA) for position confirmation
- NOT: Satellite imagery cross-referencing (GFW SAR partially covers this)
- NOT: Modifying the existing `ais_spoofing` rule — new rules stack alongside it
- NOT: Modifying the existing `identity_mismatch` rule — new `spoof_identity_mismatch` adds zombie vessel detection on top

---

## User Stories

### Story 1: Land Mask Reference Table and GSHHG Data Loading

**As a** system
**I want to** store a simplified global coastline polygon for land/sea discrimination
**So that** the position-on-land spoofing rule can check whether reported positions are on land

**Acceptance Criteria:**

- GIVEN the database WHEN migration runs THEN a `land_mask` reference table exists with a single row containing a GEOGRAPHY MULTIPOLYGON of global coastlines
- GIVEN the GSHHG crude-resolution shapefile WHEN the loading script runs THEN the land polygon is inserted into the land_mask table
- GIVEN the land_mask table WHEN queried with ST_Intersects for a point in the middle of the ocean THEN it returns FALSE
- GIVEN the land_mask table WHEN queried with ST_Intersects for a point in central Germany THEN it returns TRUE

**Test Requirements:**

- [ ] Test: Migration creates land_mask table with geometry column
- [ ] Test: Loading script inserts a valid multipolygon (can use a simplified test fixture)
- [ ] Test: ST_Intersects returns TRUE for known land coordinates (e.g., 52.52, 13.405 — Berlin)
- [ ] Test: ST_Intersects returns FALSE for known ocean coordinates (e.g., 45.0, -30.0 — mid-Atlantic)
- [ ] Test: Points within 100m of coastline are handled (buffer exclusion for GPS inaccuracy)

**Technical Notes:**

- Migration file: `database/migrations/012_land_mask.sql`
- Loading script: `scripts/load_land_mask.py`
- GSHHG (Global Self-consistent Hierarchical High-resolution Geography) available from NOAA at crude resolution (~50MB)
- Use crude resolution (GSHHS_c) — sufficient for land/sea discrimination, much smaller than full resolution
- Store as a single MULTIPOLYGON row, not one row per landmass
- For testing, include a tiny simplified GeoJSON fixture covering a small area

---

### Story 2: GNSS Interference Zones Table

**As a** system
**I want to** store detected GNSS interference zones with geometry and expiration
**So that** spatial clustering of spoofing events can be tracked and displayed

**Acceptance Criteria:**

- GIVEN the database WHEN migration runs THEN a `gnss_interference_zones` table exists with columns: id (BIGSERIAL PK), detected_at (TIMESTAMPTZ), expires_at (TIMESTAMPTZ), geometry (GEOGRAPHY POLYGON 4326), affected_count (INTEGER), details (JSONB default '{}')
- GIVEN the table WHEN checked THEN GIST index on geometry exists
- GIVEN the table WHEN checked THEN index on expires_at exists (for cleanup queries)

**Test Requirements:**

- [ ] Test: Migration creates table with correct column types
- [ ] Test: GIST index on geometry exists
- [ ] Test: expires_at index exists
- [ ] Test: Can insert and query zones with ST_Intersects

**Technical Notes:**

- This can be in the same migration as Story 1 (`012_land_mask.sql`) or a separate `012_gnss_zones.sql`
- Zones expire after 24 hours without refresh — the expires_at field enables cleanup

---

### Story 3: Position on Land Rule

**As a** scoring engine
**I want to** detect vessels reporting geographic positions that are on land
**So that** spoofed or malfunctioning AIS transmitters are flagged

**Acceptance Criteria:**

- GIVEN a vessel position that intersects the land mask polygon AND is > 100m from the coastline WHEN the rule evaluates THEN it records the event
- GIVEN a single position on land WHEN the rule evaluates THEN severity is "moderate" (15 points) — could be a GPS glitch
- GIVEN 3+ consecutive positions on land WHEN the rule evaluates THEN severity is "critical" (100 points) — almost certainly spoofed
- GIVEN a position within 100m of the coastline WHEN the rule evaluates THEN it does NOT fire (GPS inaccuracy in port)

**Test Requirements:**

- [ ] Test: Position at (52.52, 13.405) — Berlin → fires (land)
- [ ] Test: Position at (45.0, -30.0) — mid-Atlantic → does NOT fire (ocean)
- [ ] Test: Single land position → fires moderate (15 points)
- [ ] Test: Three consecutive land positions → fires critical (100 points)
- [ ] Test: Position just offshore (within 100m of coast) → does NOT fire
- [ ] Test: Position deep inland → fires regardless of coastline buffer
- [ ] Test: Rule handles missing land_mask data gracefully (returns None, logs warning)

**Technical Notes:**

- File: `services/scoring/rules/spoof_land_position.py`
- Rule ID: `spoof_land_position`
- Uses `ST_Intersects(land_mask.geometry, ST_MakePoint(lon, lat))` with a 100m buffer exclusion via `ST_Buffer`
- Consecutive position tracking: count positions in recent_positions that are on land
- Consider caching the land mask check result per-position to avoid repeated DB queries — but since this runs per-vessel evaluation, the DB query is already efficient with the GIST index
- Add to MAX_PER_RULE (cap: 100)

---

### Story 4: Physically Impossible Speed Rule

**As a** scoring engine
**I want to** detect positions implying travel speeds physically impossible for the vessel's ship type
**So that** spoofed position data is identified with ship-type-specific thresholds

**Acceptance Criteria:**

- GIVEN consecutive positions where computed speed exceeds the vessel type's maximum plausible speed by > 50% WHEN the rule evaluates THEN it fires
- GIVEN a crude oil tanker with computed speed > 27 knots (18 * 1.5) WHEN the rule fires THEN severity is "high" (40 points) for single occurrence
- GIVEN repeated impossible speeds (2+) within 24 hours WHEN the rule fires THEN severity is "critical" (100 points)
- GIVEN an unknown ship type WHEN checking speed THEN use default max of 30 knots (threshold: 45 knots)

**Plausible maximum speeds (1.5x threshold in parentheses):**
- Crude oil tanker: 18 kn (27 kn)
- Product tanker: 18 kn (27 kn)
- Bulk carrier: 16 kn (24 kn)
- Container ship: 25 kn (37.5 kn)
- General cargo: 16 kn (24 kn)
- Tug: 14 kn (21 kn)
- Default: 30 kn (45 kn)

**Test Requirements:**

- [ ] Test: Tanker with computed speed 30 knots → fires high (40 points) — exceeds 27 kn threshold
- [ ] Test: Tanker with computed speed 20 knots → does NOT fire — within threshold
- [ ] Test: Container ship with computed speed 40 knots → fires high (40 points) — exceeds 37.5 kn
- [ ] Test: Unknown ship type with computed speed 50 knots → fires high — exceeds 45 kn default
- [ ] Test: Two impossible speed events in 24h → fires critical (100 points)
- [ ] Test: Speed computed correctly from great-circle distance / time delta
- [ ] Test: Zero or negative time delta → skip (message reordering)
- [ ] Test: Missing lat/lon in either position → skip gracefully

**Technical Notes:**

- File: `services/scoring/rules/spoof_impossible_speed.py`
- Rule ID: `spoof_impossible_speed`
- Different from existing `ais_spoofing` position_jump: that uses a fixed 500nm/1hr threshold; this uses ship-type-specific speeds with lower thresholds
- Ship type mapping uses AIS ship type codes (ranges: 70-79 = cargo, 80-89 = tanker, etc.)
- Speed computation uses haversine_nm (can import from ais_spoofing.py or extract to shared utility)
- Add to MAX_PER_RULE (cap: 100)

---

### Story 5: Duplicate MMSI Rule

**As a** scoring engine
**I want to** detect the same MMSI broadcasting from two geographically incompatible positions simultaneously
**So that** identity spoofing or MMSI collision is flagged immediately

**Acceptance Criteria:**

- GIVEN a new position for an MMSI AND a position for the same MMSI was received within 5 minutes from > 10nm away WHEN the rule evaluates THEN it fires with severity "critical" (100 points)
- GIVEN positions from the same MMSI within 5 minutes but < 10nm apart WHEN the rule evaluates THEN it does NOT fire (normal movement)
- GIVEN positions from the same MMSI > 5 minutes apart WHEN the rule evaluates THEN it does NOT fire (vessel could have moved)

**Test Requirements:**

- [ ] Test: Same MMSI, 2 minutes apart, 50nm apart → fires critical (100 points)
- [ ] Test: Same MMSI, 2 minutes apart, 5nm apart → does NOT fire
- [ ] Test: Same MMSI, 10 minutes apart, 50nm apart → does NOT fire (time window exceeded)
- [ ] Test: Redis last_pos hash is updated after each evaluation
- [ ] Test: First position ever for an MMSI → does NOT fire (no prior position to compare)
- [ ] Test: Distance computation is correct for edge cases (crossing dateline, polar regions)

**Technical Notes:**

- File: `services/scoring/rules/spoof_duplicate_mmsi.py`
- Rule ID: `spoof_duplicate_mmsi`
- Redis state: `heimdal:last_pos:{mmsi}` → JSON hash `{lat, lon, timestamp}`
- This runs on each incoming position — could optionally be evaluated in ais-ingest for lowest latency, but for consistency, keep it in the scoring engine
- The rule checks the LAST known position from Redis, not from recent_positions (which are per-vessel from DB)
- Add to MAX_PER_RULE (cap: 100)

---

### Story 6: Positional Repetition / Frozen Position Rule

**As a** scoring engine
**I want to** detect vessels reporting identical positions for extended periods while claiming to be underway
**So that** frozen/replayed AIS data is identified

**Acceptance Criteria:**

- GIVEN lat, lon, COG, SOG all identical (within 0.001 deg and 0.1 knots) for > 2 hours AND nav_status is NOT "at anchor" or "moored" WHEN the rule evaluates THEN it fires with severity "high" (40 points)
- GIVEN identical positions but nav_status is "at anchor" or "moored" WHEN the rule evaluates THEN it does NOT fire
- GIVEN a "box pattern" — positions oscillating between exactly 2-4 coordinate pairs WHEN detected over > 1 hour THEN the rule fires with severity "high" (40 points)

**Test Requirements:**

- [ ] Test: 12 identical positions over 3 hours, nav_status "underway" → fires high (40 points)
- [ ] Test: 12 identical positions over 3 hours, nav_status "at anchor" → does NOT fire
- [ ] Test: Positions with tiny variations (0.0005 deg) over 3 hours → fires (within tolerance)
- [ ] Test: Positions with larger variations (0.01 deg) → does NOT fire (real movement)
- [ ] Test: Box pattern — 10 positions alternating between 2 coordinate pairs over 2 hours → fires
- [ ] Test: Only 30 minutes of repeated positions → does NOT fire (under 2h threshold)
- [ ] Test: SOG variation > 0.1 knots → does NOT fire (not truly frozen)

**Technical Notes:**

- File: `services/scoring/rules/spoof_frozen_position.py`
- Rule ID: `spoof_frozen_position`
- Different from existing `anchor_spoofing` pattern: that requires 48h and checks nav_status claiming underway; this uses 2h threshold and adds box pattern detection
- Box pattern detection: group positions by rounded coordinates (0.001 deg), if positions cluster into exactly 2-4 groups, it's a box pattern
- Uses recent_positions from the scoring engine (already available, no Redis needed)
- Add to MAX_PER_RULE (cap: 40)

---

### Story 7: MMSI-IMO Cross-Reference Mismatch Rule

**As a** scoring engine
**I want to** detect vessels broadcasting MMSI+IMO combinations that don't match known vessel registries or belong to scrapped vessels
**So that** identity theft and "zombie vessel" patterns are flagged

**Acceptance Criteria:**

- GIVEN a vessel whose IMO is associated with a vessel of dramatically different dimensions (length or beam differs > 20%) WHEN the rule evaluates THEN it fires with severity "high" (40 points) with reason "dimension_mismatch"
- GIVEN a vessel whose IMO belongs to a vessel recorded as scrapped/broken up/lost WHEN the rule evaluates THEN it fires with severity "critical" (100 points) with reason "zombie_vessel"
- GIVEN a vessel whose MMSI MID (country code) does not match the registered flag state for that IMO WHEN the rule evaluates THEN it fires with severity "high" (40 points) with reason "flag_mid_mismatch"
- GIVEN no GFW vessel data available for cross-referencing WHEN the rule evaluates THEN it does NOT fire (insufficient data)

**Test Requirements:**

- [ ] Test: Vessel broadcasting IMO of a ship 50% longer → fires high (dimension_mismatch, 40 points)
- [ ] Test: Vessel broadcasting IMO of a ship 10% longer → does NOT fire (within 20% tolerance)
- [ ] Test: Vessel broadcasting IMO of scrapped vessel → fires critical (zombie_vessel, 100 points)
- [ ] Test: MMSI MID=273 (Russia) but IMO registered flag=Panama → fires high (flag_mid_mismatch, 40 points)
- [ ] Test: MMSI MID=273 (Russia) and IMO registered flag=Russia → does NOT fire
- [ ] Test: No GFW data available → does NOT fire, returns None
- [ ] Test: Multiple mismatches (zombie + MID mismatch) → fires with highest severity

**Technical Notes:**

- File: `services/scoring/rules/spoof_identity_mismatch.py`
- Rule ID: `spoof_identity_mismatch`
- This stacks with existing `identity_mismatch` rule — the existing rule checks dimensions and flag; this adds zombie vessel detection and uses GFW vessel data for cross-referencing
- Zombie detection: check if GFW vessel data shows the IMO has recent AIS activity under a DIFFERENT MMSI (suggesting original vessel was scrapped and identity reused)
- MID extraction: first 3 digits of MMSI, lookup in MID_TO_FLAG from constants.py
- Evaluates on profile data (not positions), so runs on enrichment_complete channel
- Add to MAX_PER_RULE (cap: 100)

---

### Story 8: GNSS Interference Zone Clustering

**As a** scoring engine
**I want to** detect spatial and temporal clustering of spoofing events and create GNSS interference zone records
**So that** areas of probable GPS jamming are identified from aggregate AIS anomalies

**Acceptance Criteria:**

- GIVEN 3+ spoofing events (from any spoof_* rule) within 20nm and 1 hour WHEN clustering logic runs THEN a GNSS interference zone record is created with a convex hull geometry
- GIVEN an existing GNSS zone WHEN a new spoofing event occurs within it within 24 hours THEN the zone's expires_at is refreshed (extended by 24 hours) and affected_count is incremented
- GIVEN a GNSS zone with no new detections for 24 hours WHEN cleanup runs THEN the zone is considered expired (not deleted, but expires_at < now())

**Test Requirements:**

- [ ] Test: 3 spoofing events within 15nm and 30 minutes → creates zone with convex hull geometry
- [ ] Test: 2 spoofing events within 20nm → does NOT create zone (below threshold)
- [ ] Test: 3 spoofing events within 1 hour but 50nm apart → does NOT create zone (too spread)
- [ ] Test: New event within existing zone → refreshes expires_at, increments affected_count
- [ ] Test: Convex hull geometry contains all affected positions
- [ ] Test: Zone expires_at is set to detected_at + 24 hours initially

**Technical Notes:**

- Logic lives in a new module: `services/scoring/gnss_clustering.py`
- Called after each spoof_* rule fires with the event's position
- Clustering: query recent spoof anomaly events (last 1 hour) within 20nm of the new event's position using ST_DWithin on anomaly_events joined with vessel_positions
- Convex hull: PostGIS `ST_ConvexHull(ST_Collect(points))`
- This is a post-scoring step, not a scoring rule itself — triggered by the engine after spoof rules fire
- Add to MAX_PER_RULE is NOT needed (this creates gnss_interference_zones records, not anomaly_events)

---

## Technical Design

### Data Model Changes

- New table: `land_mask` (single row MULTIPOLYGON for coastline)
- New table: `gnss_interference_zones` (detected GNSS jamming areas)
- New entries in MAX_PER_RULE: spoof_land_position (100), spoof_impossible_speed (100), spoof_duplicate_mmsi (100), spoof_frozen_position (40), spoof_identity_mismatch (100)

### API Changes

None in this spec. Existing anomaly endpoints serve the new rule_ids. GNSS zone API endpoints deferred to frontend spec.

### Dependencies

- GSHHG coastline shapefile from NOAA (free, ~50MB)
- PostGIS ST_Intersects, ST_ConvexHull, ST_Collect
- Redis for duplicate MMSI last_pos tracking
- GFW Vessel API data for IMO cross-referencing (already available via enrichment)
- MID_TO_FLAG from constants.py (already exists)
- Existing ais_spoofing.py haversine_nm function (import or extract)

### Security Considerations

- GSHHG data is public domain
- No new API endpoints exposed
- Redis keys follow existing naming convention

---

## Implementation Order

### Group 1 (parallel — no dependencies)
- Story 1 — Land mask table + GSHHG loading: `database/migrations/012_land_mask.sql`, `scripts/load_land_mask.py`
- Story 2 — GNSS zones table: `database/migrations/012_gnss_zones.sql` (or combined with Story 1)

### Group 2 (parallel — after Group 1)
- Story 3 — Position on land rule: `services/scoring/rules/spoof_land_position.py`
- Story 4 — Impossible speed rule: `services/scoring/rules/spoof_impossible_speed.py`
- Story 5 — Duplicate MMSI rule: `services/scoring/rules/spoof_duplicate_mmsi.py`
- Story 6 — Frozen position rule: `services/scoring/rules/spoof_frozen_position.py`
- Story 7 — Identity mismatch rule: `services/scoring/rules/spoof_identity_mismatch.py`

### Group 3 (sequential — after Group 2)
- Story 8 — GNSS clustering: `services/scoring/gnss_clustering.py` (depends on spoof rules existing to produce events)

**Parallel safety rules:**
- All 5 rules in Group 2 are in separate files — safe to parallelize
- Each rule adds its own entry to MAX_PER_RULE in constants.py — merge carefully
- GNSS clustering depends on spoof rules being in place to generate the events it clusters

---

## Development Approach

### Simplifications (what starts simple)

- Land mask uses GSHHG crude resolution — accuracy is sufficient for land/sea discrimination
- Zombie vessel detection checks GFW data only — no Equasis scrapping database lookup
- GNSS zone clustering uses simple distance threshold — no ML-based anomaly detection
- Duplicate MMSI uses Redis in scoring engine — not moved to ais-ingest for lowest latency yet

### Upgrade Path (what changes for production)

- "Integrate Equasis casualty data" for more comprehensive zombie vessel detection
- "Move duplicate MMSI check to ais-ingest" for sub-second detection latency
- "Add SAR cross-referencing" — vessel at position X on AIS but detected by SAR at position Y
- "Higher resolution coastline" — upgrade from GSHHG crude to low/intermediate if needed

### Architecture Decisions

- Five separate rules rather than extending existing ais_spoofing — these are distinct detection patterns with different data requirements and false positive profiles. Stacking allows independent tuning.
- Land mask as single-row reference table — simpler than a multi-row approach, and the GIST index on a single large multipolygon is efficient for point-in-polygon queries
- GNSS clustering as post-scoring step rather than a rule — it produces zone records, not anomaly events. Different output type warrants different code path.

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled (dateline crossing, polar regions, missing data)
- [ ] No regressions in existing tests (especially existing ais_spoofing and identity_mismatch rules)
- [ ] Code committed with proper messages
- [ ] New rule_ids added to MAX_PER_RULE and ALL_RULE_IDS
- [ ] Land mask data loads correctly from test fixture
- [ ] Rules auto-discovered by scoring engine
- [ ] GNSS clustering creates valid zone geometries
- [ ] Ready for human review
