# Feature Spec: AIS Spoofing & Scoring False Positive Rethink

**Slug:** `spoofing-rethink`
**Created:** 2026-03-24
**Status:** completed
**Priority:** critical
**Supersedes:** Specs 24 (spoofing-detection-backend) and 27 (spoofing-detection-frontend) — those specs treated spoofing as vessel-level blame signals. This spec rethinks the approach: vessels are victims of area-based GNSS interference, not suspects.

---

## Overview

The current spoofing detection flags ~8,000+ vessels with false positive anomalies (frozen position, circle spoofing, impossible speed, speed anomalies). Investigation shows these are caused by GPS noise (ferries stopping at terminals, null-island glitches) and area-based GNSS interference (e.g., Kaliningrad spoofing affecting all vessels in the area simultaneously). This spec removes vessel-level spoofing blame, introduces area-based GNSS interference zone detection, builds a time-windowed heatmap layer, fixes IACS scoring for domestic vessels, and bulk-clears all existing false positive anomalies.

## Problem Statement

1. **8,287 vessels** flagged for frozen position, **4,986** for AIS spoofing, **4,348** for impossible speed — almost all false positives from GPS noise and area-based GNSS jamming/spoofing
2. Norwegian ferries (and similar domestic vessels) get 25-point CRITICAL findings for having a national maritime authority as class society instead of IACS member — completely normal for domestic passenger/small vessels
3. Real GNSS spoofing (Kaliningrad, Eastern Med, Persian Gulf) is **area-based** — multiple vessels simultaneously show impossible speeds/positions — but our rules blame each vessel individually
4. The existing GNSS heatmap time controls don't let operators investigate a specific historical moment effectively (point-in-time slider misses events)

## Out of Scope

- NOT: RF signal direction-finding (TDOA) for position confirmation
- NOT: Satellite imagery cross-referencing
- NOT: Real-time alerting for new GNSS interference zones (future feature)
- NOT: Land mask / position-on-land detection (keep from spec 24 if implemented separately)
- NOT: Duplicate MMSI connector lines (keep from spec 27 if implemented separately)
- NOT: Manual MMSI whitelist management

---

## User Stories

### Story 1: Bulk-Resolve Existing False Positive Anomalies

**As a** system operator
**I want to** clear all existing spoof/speed anomaly events and recalculate affected vessel scores
**So that** the system reflects accurate risk without historical noise

**Acceptance Criteria:**

- GIVEN the database has active anomaly events with rule_id in ('ais_spoofing', 'spoof_frozen_position', 'spoof_impossible_speed', 'speed_anomaly') WHEN the migration runs THEN all such events are set to event_state='resolved', resolved=TRUE with a resolution note 'bulk_resolved: false_positive_rethink_2026-03'
- GIVEN vessels whose risk_score included points from these rules WHEN the migration runs THEN their risk_score is recalculated from remaining active anomalies and risk_tier is re-derived from the new score
- GIVEN the migration WHEN it completes THEN a summary is logged: count of resolved anomalies, count of vessels rescored, count of tier changes

**Test Requirements:**

- [ ] Test: Migration resolves all active ais_spoofing, spoof_frozen_position, spoof_impossible_speed, speed_anomaly events
- [ ] Test: Vessel that had risk_score=35 from only iacs_class_status(25) + speed_anomaly(10) is rescored to 25 and drops from yellow to green
- [ ] Test: Vessel with sanctions_match(100) + spoof_impossible_speed(0) keeps score=100 and stays blacklisted (spoof was already 0-cap, but verify no side effects)
- [ ] Test: Migration is idempotent — running twice doesn't error or double-resolve

**Technical Notes:**

- SQL migration file in `db/migrations/`
- Must recalculate scores by summing remaining active anomaly points (respecting MAX_PER_RULE caps)
- Apply to prod via `psql -f` per production database rules — never rebuild postgres container
- Back up database before running: `pg_dump -U heimdal -Fc heimdal > backup_before_spoof_rethink.dump`

---

### Story 2: Remove Vessel-Level Spoofing Scoring Rules

**As a** system
**I want to** disable the four vessel-level spoofing/speed rules from the scoring engine
**So that** vessels are never again penalized for GPS noise or area-based GNSS interference

**Acceptance Criteria:**

- GIVEN the scoring engine discovers rules at startup WHEN it loads rules from the rules/ directory THEN it does NOT load ais_spoofing, spoof_frozen_position, spoof_impossible_speed, or speed_anomaly
- GIVEN a vessel receives AIS positions WHEN the scoring engine evaluates in real-time THEN none of the four removed rules fire
- GIVEN the rule files WHEN checked THEN they are moved to a `rules/disabled/` directory (not deleted — preserved for reference)
- GIVEN MAX_PER_RULE in constants.py WHEN checked THEN the four entries are removed

**Test Requirements:**

- [ ] Test: Scoring engine startup does not load rules from `rules/disabled/`
- [ ] Test: A vessel with frozen position data does not generate a spoof_frozen_position anomaly
- [ ] Test: A vessel with impossible speed between positions does not generate a spoof_impossible_speed anomaly
- [ ] Test: Existing rules (iacs_class_status, sanctions_match, etc.) continue to function normally

**Technical Notes:**

- Move files to `services/scoring/rules/disabled/`: ais_spoofing.py, spoof_frozen_position.py, spoof_impossible_speed.py, speed_anomaly.py
- The engine auto-discovers rules via importlib from the rules/ directory — moving them out is sufficient
- Remove entries from MAX_PER_RULE in shared/constants.py
- Keep the base ScoringRule class and engine unchanged

---

### Story 3: IACS Class Exemption for Domestic Vessels

**As a** system
**I want to** exempt passenger vessels and small vessels (<60m) classed by national maritime authorities from IACS class scoring
**So that** Norwegian ferries and similar domestic vessels don't get false critical findings

**Acceptance Criteria:**

- GIVEN a vessel with ship_type 60-69 (passenger) AND iacs_data.class_society is a known national maritime authority WHEN iacs_class_status rule evaluates THEN it returns no finding (fired=False)
- GIVEN a vessel with dimensions showing length < 60m AND iacs_data.class_society is a known national maritime authority WHEN iacs_class_status rule evaluates THEN it returns no finding (fired=False)
- GIVEN a vessel with ship_type 80 (tanker) AND iacs_data.class_society is "NV" WHEN iacs_class_status rule evaluates THEN it still fires normally (tankers should have IACS class regardless)
- GIVEN the known national maritime authorities list WHEN checked THEN it includes at minimum: NV (Norway), DMA (Denmark), Transportstyrelsen (Sweden), Traficom (Finland), ISA (Ireland), MCA (UK Maritime and Coastguard Agency)
- GIVEN a vessel that was previously scored for iacs_class_status and now qualifies for the exemption WHEN the rule re-evaluates THEN the existing anomaly is ended via check_event_ended

**Test Requirements:**

- [ ] Test: Passenger vessel (type 60) with class_society "NV" and status "Withdrawn" → rule does NOT fire
- [ ] Test: Small vessel (55m length) with class_society "DMA" and status "NO_IACS_CLASS" → rule does NOT fire
- [ ] Test: Tanker (type 80) with class_society "NV" and status "Withdrawn" → rule FIRES normally (25 pts)
- [ ] Test: Large cargo vessel (120m) with class_society "NV" and status "Withdrawn" → rule FIRES normally
- [ ] Test: Passenger vessel with class_society "DNV" (IACS member, not national authority) and status "Withdrawn" → rule FIRES normally
- [ ] Test: check_event_ended returns True for previously-flagged vessel that now qualifies for exemption

**Technical Notes:**

- Modify `services/scoring/rules/iacs_class_status.py`
- Add a constant `NATIONAL_MARITIME_AUTHORITIES` set with known codes
- Vessel length comes from `profile.get('length')` or dimension parsing — check what's available in vessel_profiles
- The exemption check should be an early return at the top of `evaluate()`, before any finding logic
- National authority list will need expansion over time — keep it as a simple set in the rule file for now

---

### Story 4: Area-Based GNSS Interference Zone Detection

**As a** system
**I want to** detect GNSS interference zones by correlating anomalous position data across multiple vessels in the same area and time window
**So that** spoofing/jamming is attributed to geographic areas, not individual vessels

**Acceptance Criteria:**

- GIVEN 3+ vessels within a 15nm radius all reporting impossible speeds (>45kn implied) within a 1-hour window WHEN the detector runs THEN a gnss_interference_zone record is created with a convex hull polygon around the affected positions
- GIVEN the detector creates a zone WHEN checked THEN the zone record includes: detected_at, expires_at (detected_at + 24h), geometry (convex hull buffered by 5nm), affected_mmsis (list), affected_count, event_type ('spoofing' or 'jamming'), peak_severity, details (sample of anomalous positions)
- GIVEN new anomalous positions arrive that fall within an existing active zone's geometry and time window WHEN the detector runs THEN the existing zone is updated (affected_count incremented, affected_mmsis extended, expires_at pushed forward) rather than creating a duplicate
- GIVEN a zone's expires_at has passed AND no new anomalous positions have arrived in the zone WHEN checked THEN the zone is considered expired (no cleanup needed — just filter by expires_at in queries)
- GIVEN the detector WHEN it identifies vessels affected by a zone THEN those vessels are tagged in vessel_profiles with a jsonb field `gnss_affected` containing zone_id and detected_at (or null when zone expires)

**Test Requirements:**

- [ ] Test: 3 vessels with impossible speeds within 15nm and 1 hour → zone created with correct convex hull
- [ ] Test: 2 vessels with impossible speeds (below threshold) → no zone created
- [ ] Test: Vessels spread across 50nm (too far apart) → no zone created even if 5+ vessels
- [ ] Test: New anomalous position in existing zone → zone updated, not duplicated
- [ ] Test: Zone geometry is convex hull of affected positions buffered by 5nm
- [ ] Test: affected_mmsis list contains all contributing vessel MMSIs
- [ ] Test: Zone correctly classified as 'spoofing' (position displacement pattern) vs 'jamming' (signal loss pattern)

**Technical Notes:**

- New service: `services/scoring/gnss_zone_detector.py`
- Runs as a periodic task (every 5 minutes) or triggered by position ingestion
- Uses the `gnss_interference_zones` table (already defined in spec 24's migration — create if not exists)
- Detection algorithm:
  1. Query recent positions (last 1 hour) where implied speed between consecutive positions > 45kn
  2. Spatial clustering: group anomalous positions within 15nm using DBSCAN or simple distance grouping via PostGIS `ST_ClusterDBSCAN`
  3. For each cluster with 3+ distinct MMSIs: create or update zone
- Distinguishing spoofing vs jamming:
  - Spoofing: positions are displaced but still being reported (vessels appear to teleport or spiral)
  - Jamming: positions stop entirely (AIS gap) — correlate with ais_gap events in same area
- The implied speed calculation reuses logic from the now-disabled spoof_impossible_speed rule
- Subscribe to the same Redis `heimdal:positions` channel as the scoring engine for triggering

---

### Story 5: GNSS Interference Zone API Endpoint

**As a** frontend
**I want to** query GNSS interference zones for a time window
**So that** the heatmap layer can display historical and current interference data

**Acceptance Criteria:**

- GIVEN `GET /api/gnss/zones?center=2026-03-21T17:00:00Z&window=12h` WHEN called THEN returns all zones where the zone's time range (detected_at to expires_at) overlaps with the query window (center ± window/2)
- GIVEN the response WHEN checked THEN each zone includes: id, detected_at, expires_at, geometry (GeoJSON), affected_count, affected_mmsis, event_type, peak_severity
- GIVEN `GET /api/gnss/zones?center=2026-03-21T17:00:00Z&window=12h&bbox=54,18,57,22` WHEN called THEN only zones intersecting the bounding box are returned
- GIVEN no zones exist for the queried time window WHEN called THEN returns an empty array with 200 status

**Test Requirements:**

- [ ] Test: Query with center + window returns zones that overlap the time range
- [ ] Test: Zone that started before the window but expires during it is included
- [ ] Test: Zone completely outside the time window is excluded
- [ ] Test: bbox filter correctly limits spatial results
- [ ] Test: Response geometry is valid GeoJSON
- [ ] Test: Empty result returns [] not error

**Technical Notes:**

- New route in `services/api-server/routes/gnss.py` (or extend existing if gnss routes exist)
- Time overlap: zone overlaps window when `zone.detected_at <= window_end AND zone.expires_at >= window_start`
- Use PostGIS `ST_Intersects` for bbox filtering
- Return geometry as GeoJSON using `ST_AsGeoJSON`
- Keep response lean — don't include full position samples in list endpoint, only in detail endpoint if needed

---

### Story 6: GNSS Heatmap Layer with Time-Window Visualization

**As an** operator
**I want to** see GNSS interference zones rendered as a heatmap on the map with intensity based on affected vessel count
**So that** I can visually identify areas of active or historical GNSS interference

**Acceptance Criteria:**

- GIVEN GNSS interference zones exist for the current time window WHEN the GNSS layer is enabled THEN zones are rendered as filled polygons with opacity/color intensity proportional to affected_count
- GIVEN a zone with affected_count=3 WHEN rendered THEN it appears at low intensity (light orange/amber)
- GIVEN a zone with affected_count=15+ WHEN rendered THEN it appears at high intensity (bright red)
- GIVEN the event_type is 'spoofing' WHEN rendered THEN the zone color is in the red/orange spectrum
- GIVEN the event_type is 'jamming' WHEN rendered THEN the zone color is in the purple/blue spectrum
- GIVEN zones from different time points within the window WHEN rendered THEN more recent zones appear more opaque and older zones fade toward transparent
- GIVEN no zones for the current window WHEN the layer is enabled THEN the map shows no heatmap overlay (clean state)

**Test Requirements:**

- [ ] Test: Zone polygon renders on map when layer enabled
- [ ] Test: Higher affected_count → more intense color
- [ ] Test: Spoofing zones use red/orange palette, jamming zones use purple/blue
- [ ] Test: Temporal fade — zone from 10 hours ago is more transparent than zone from 1 hour ago
- [ ] Test: Layer toggle on/off works correctly
- [ ] Test: No zones → clean map, no errors

**Technical Notes:**

- Replace/refactor existing `GnssHeatmap.tsx` component
- Use MapLibre `fill-extrusion` or `fill` layer with data-driven styling
- Color ramp: interpolate between low (amber, 0.3 opacity) and high (red, 0.8 opacity) based on `affected_count`
- Temporal fade: multiply opacity by `1 - (age_hours / window_hours)` where age is distance from center time
- Source: GeoJSON from the `/api/gnss/zones` endpoint
- Re-fetch when time window changes (reactive query key on center + window)

---

### Story 7: Time-Window Control Bar

**As an** operator
**I want to** select a center time and see GNSS interference within a configurable window around it
**So that** I can investigate historical spoofing/jamming events at any point in time

**Acceptance Criteria:**

- GIVEN the GNSS layer is enabled WHEN the time bar appears THEN it shows: a draggable timeline spanning the last 30 days, a center-time indicator, a visible window highlight showing the active range, window size presets (6h, 12h, 24h, 3d, 7d), and a "Now" button to jump to current time
- GIVEN the operator drags the center indicator to March 21 at 17:00 with window=12h WHEN released THEN the heatmap shows all interference zones overlapping 11:00-23:00 on March 21
- GIVEN the operator clicks a window preset (e.g., "24h") WHEN the heatmap updates THEN the visible window highlight expands/contracts to ±12h around the center time
- GIVEN the operator clicks "Now" WHEN the time bar updates THEN the center jumps to current UTC time and the heatmap shows current/recent interference
- GIVEN the time bar WHEN the center or window changes THEN the heatmap data re-fetches with the new parameters (debounced, not on every pixel of drag)
- GIVEN the time bar WHEN displayed THEN it shows the center time in human-readable UTC format (e.g., "2026-03-21 17:00 UTC")
- GIVEN the GNSS layer is disabled WHEN checked THEN the time bar is hidden

**Test Requirements:**

- [ ] Test: Time bar appears when GNSS layer is enabled
- [ ] Test: Time bar hidden when GNSS layer is disabled
- [ ] Test: Dragging center time updates the displayed time and triggers data refetch
- [ ] Test: Window presets (6h, 12h, 24h, 3d, 7d) correctly change the query window
- [ ] Test: "Now" button sets center to current time
- [ ] Test: Debounce prevents excessive API calls during drag
- [ ] Test: Displayed window highlight visually matches the actual query range
- [ ] Test: Timeline spans 30 days back from now

**Technical Notes:**

- Replace existing `SpoofingTimeControls.tsx` entirely
- The timeline bar should sit at the bottom-center of the map (same position as existing controls)
- Visual design: dark translucent bar matching the ops-centre theme, with a highlighted "active window" segment in amber/orange
- Debounce data fetches by 300ms during drag operations
- Store state in a Zustand store or local component state — center (ISO timestamp) and window (duration string)
- The "window highlight" on the timeline visually shows the range being queried — wider for 7d, narrow for 6h
- Keyboard support: arrow keys to nudge center ±1 hour, shift+arrow for ±6 hours

---

## Technical Design

### Data Model Changes

**Existing table (create if not exists):**
```sql
CREATE TABLE IF NOT EXISTS gnss_interference_zones (
    id BIGSERIAL PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    geometry GEOGRAPHY(POLYGON, 4326) NOT NULL,
    affected_count INTEGER NOT NULL DEFAULT 0,
    affected_mmsis INTEGER[] NOT NULL DEFAULT '{}',
    event_type TEXT NOT NULL DEFAULT 'spoofing',  -- 'spoofing' or 'jamming'
    peak_severity TEXT DEFAULT 'high',
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gnss_zones_geometry ON gnss_interference_zones USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_gnss_zones_time ON gnss_interference_zones(detected_at, expires_at);
```

**vessel_profiles changes:**
- Add `gnss_affected JSONB DEFAULT NULL` — set to `{"zone_id": N, "detected_at": "..."}` when vessel is in an active zone, NULL otherwise

**Migration for bulk resolve:**
```sql
-- Resolve all false positive spoofing/speed anomalies
UPDATE anomaly_events
SET event_state = 'resolved', resolved = TRUE,
    details = details || '{"resolution": "bulk_resolved: false_positive_rethink_2026-03"}'
WHERE event_state = 'active'
AND rule_id IN ('ais_spoofing', 'spoof_frozen_position', 'spoof_impossible_speed', 'speed_anomaly');

-- Recalculate vessel scores (done in Python script after migration)
```

### API Changes

- **New:** `GET /api/gnss/zones?center=<iso>&window=<duration>&bbox=<s,w,n,e>` — query interference zones
- **Modified:** `GET /api/vessels/{mmsi}` — include `gnss_affected` field in response
- **Removed:** Existing GNSS spoofing events endpoint replaced by zones endpoint

### Dependencies

- PostGIS `ST_ClusterDBSCAN` for spatial clustering (available in PostGIS 2.3+, TimescaleDB includes this)
- Existing Redis pub/sub for triggering zone detection
- MapLibre GL for polygon rendering

### Production Database Rules (CRITICAL)

- **ALL schema and data changes MUST be SQL migration files applied with `psql -f`**
- **The postgres container MUST NEVER be recreated** — it holds irreplaceable data
- When deploying updated services, ALWAYS use `docker compose up -d --no-deps --build <service>` to avoid touching postgres
- Before running the bulk-resolve migration: `docker compose exec postgres pg_dump -U heimdal -Fc heimdal > /data/raw/backup_before_spoof_rethink.dump`
- The gnss_interference_zones table creation is a SQL migration, not a Docker entrypoint script

### Security Considerations

- No auth changes — GNSS data is read-only for all operators
- Zone detection runs server-side only — no client-side position data processing
- Bulk migration requires prod DB access (existing SSH + psql workflow)

---

## Implementation Order

### Group 1 (parallel — no dependencies)
- **Story 1** — Bulk-resolve migration: `db/migrations/`, Python rescore script
- **Story 2** — Remove scoring rules: `services/scoring/rules/`, `shared/constants.py`
- **Story 3** — IACS exemption: `services/scoring/rules/iacs_class_status.py`

### Group 2 (parallel — after Group 1)
- **Story 4** — GNSS zone detector: `services/scoring/gnss_zone_detector.py` (new file)
- **Story 5** — API endpoint: `services/api-server/routes/gnss.py`

### Group 3 (parallel — after Group 2)
- **Story 6** — Heatmap layer: `frontend/src/components/Map/GnssHeatmap.tsx`
- **Story 7** — Time-window control bar: `frontend/src/components/Map/` (new component, replaces SpoofingTimeControls.tsx)

**Parallel safety rules:**
- Group 1 stories touch completely different files — safe to parallelize
- Story 4 creates the data that Story 5 serves — must be sequential
- Stories 6 and 7 are separate components but both in the Map directory — they can be parallel as long as they share the same query hook interface defined in Story 5

---

## Development Approach

### Simplifications (what starts simple)

- Zone detection uses simple spatial clustering (DBSCAN) rather than ML-based anomaly detection
- Spoofing vs jamming classification is heuristic (positions present = spoofing, positions absent = jamming) rather than signal-analysis-based
- National maritime authority list is a hardcoded set — not a database-managed reference table
- Time bar is a custom component, not a third-party timeline library

### Upgrade Path (what changes for production)

- "Add real-time alerting for new GNSS interference zones" — separate story, WebSocket push
- "Add ML-based zone detection" — train on the Kaliningrad/Eastern Med/Persian Gulf ground truth data
- "Add national authority management UI" — let operators add/remove authority codes
- "Correlate GNSS zones with known military exercises or geopolitical events" — future intelligence layer

### Architecture Decisions

- **Area-based, not vessel-based**: The fundamental shift. Spoofing is something that happens TO vessels in an area, not something vessels DO. The zone is the entity, not the vessel.
- **Convex hull + buffer**: Zone geometry uses the convex hull of affected positions buffered by 5nm, giving a clean polygon that covers the interference area without jagged edges.
- **24-hour expiry with extension**: Zones expire 24h after last activity. New activity pushes expiry forward. This handles both short bursts (Kaliningrad) and sustained interference (Eastern Med).
- **Replace, don't layer**: The old SpoofingTimeControls and vessel-level spoof signals are replaced entirely, not supplemented. This avoids confusion about which system is "correct."
- **Bulk resolve as migration**: One-time cleanup as a SQL migration rather than code-based re-evaluation. Simpler, faster, auditable, and doesn't require the scoring engine to run.

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled
- [ ] No regressions in existing tests
- [ ] Bulk migration tested on dev before prod
- [ ] Existing vessel scores verified correct after migration
- [ ] FLOROY (MMSI 257077580) drops to green tier after migration + IACS exemption
- [ ] Kaliningrad area shows as interference zone in heatmap
- [ ] Time bar allows investigating March 21 17:00 UTC event
- [ ] Code committed with proper messages
- [ ] Ready for human review
