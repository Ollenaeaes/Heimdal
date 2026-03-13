# Feature Spec: Event-Based Scoring Model

**Slug:** `event-scoring-model`
**Created:** 2026-03-13
**Status:** draft
**Priority:** critical

---

## Overview

Refactor the scoring engine from fire-and-forget anomaly creation to an event-based model where each anomaly has a lifecycle (start, ongoing, end). This eliminates duplicate scoring for continuous situations (slow steaming in ports, persistent loitering), enables score escalation for repeat events, and adds port/anchorage awareness to prevent false positives.

## Problem Statement

The current scoring engine evaluates rules on every position update but has no concept of event boundaries. Issues:

1. **Slow steaming in ports** — vessels approaching or departing ports naturally slow down. The `speed_anomaly` rule only checks `nav_status` (moored/anchored) but misses port approach manoeuvres where status is still "underway". This floods the system with false positives for in-port vessels.
2. **No event lifecycle** — anomalies are fire-and-forget. A vessel slow-steaming for 48 hours generates one anomaly (thanks to the engine dedup that skips if an unresolved anomaly for the same `rule_id` exists), but there's no "event ended" marker. When the anomaly is eventually resolved, the rule immediately re-fires if conditions persist.
3. **No repeat-event escalation** — if a vessel slow-steams, stops, then slow-steams again, the second event should score higher. Currently `MAX_PER_RULE` for `speed_anomaly` is 15, meaning even two events can't exceed 15 points total.
4. **Continuous-state rules spam** — `sts_proximity`, `destination_spoof`, and `draft_change` all have similar issues where persistent conditions should be scored as a single event, not repeated firings.
5. **GFW rules take only first event** — all GFW rules evaluate `events[0]`, ignoring subsequent events of the same type.

## Out of Scope

- NOT: Changing the fundamental rule framework or `ScoringRule` base class signature
- NOT: Adding new scoring rules (that's spec 18)
- NOT: Frontend changes to display event lifecycle
- NOT: Changing the database schema for `anomaly_events` beyond adding lifecycle columns
- NOT: Changing tier thresholds (green/yellow/red)

---

## User Stories

### Story 1: Anomaly Event Lifecycle Schema

**As a** system
**I want to** track when anomaly events start, end, and their current state
**So that** we can distinguish between active and completed events and score accordingly

**Acceptance Criteria:**

- GIVEN an anomaly_events table WHEN migration runs THEN columns `event_start`, `event_end` (nullable timestamp), `event_state` (enum: active/ended/superseded) are added
- GIVEN existing anomaly rows WHEN migration runs THEN `event_start` defaults to `created_at`, `event_state` defaults to `active` for unresolved, `ended` for resolved
- GIVEN an anomaly with `event_state = active` WHEN the condition ceases THEN `event_end` is set and `event_state` becomes `ended`
- GIVEN an anomaly with `event_state = ended` WHEN a NEW occurrence of the same rule fires THEN a NEW anomaly row is created (not updating the old one)

**Test Requirements:**

- [ ] Test: Migration adds columns with correct defaults for existing data
- [ ] Test: Active anomalies can transition to ended
- [ ] Test: Ended anomalies are not reactivated — new rows are created instead
- [ ] Test: Pydantic AnomalyEvent model includes new fields with proper validation

**Technical Notes:**

- New migration file `005_anomaly_lifecycle.sql`
- Add `event_start TIMESTAMPTZ DEFAULT NOW()`, `event_end TIMESTAMPTZ NULL`, `event_state VARCHAR(20) DEFAULT 'active'`
- Update the shared `AnomalyEvent` Pydantic model
- Update `create_anomaly_event` repository function to set `event_start`
- Add `end_anomaly_event(session, anomaly_id)` repository function

---

### Story 2: Port and Anchorage Awareness

**As a** scoring engine
**I want to** know when a vessel is near a port or anchorage
**So that** I can suppress or downweight behavioural anomalies that are normal near ports

**Acceptance Criteria:**

- GIVEN a vessel position within 5 nm of a known port or anchorage WHEN speed_anomaly evaluates THEN slow steaming is NOT flagged (port approach/departure is normal)
- GIVEN a vessel position within 5 nm of a known port WHEN sts_proximity evaluates THEN the proximity is downweighted (STS near ports is often legitimate bunkering)
- GIVEN a vessel position within 5 nm of a port WHEN draft_change evaluates THEN draught changes are NOT flagged (loading/unloading is normal in port)
- GIVEN a vessel position NOT near any port WHEN rules evaluate THEN scoring proceeds as normal

**Test Requirements:**

- [ ] Test: Vessel at 3 nm from Rotterdam port → speed_anomaly returns `fired=False`
- [ ] Test: Vessel at 3 nm from Kalamata STS zone but also 3 nm from Kalamata port → sts_proximity downweighted
- [ ] Test: Vessel at 50 nm from nearest port with SOG 3 knots → speed_anomaly fires normally
- [ ] Test: Vessel in port area with draught change → draft_change returns `fired=False`
- [ ] Test: Port database contains at least the top 50 global tanker ports

**Technical Notes:**

- Add a `ports` table or seed data with known port coordinates (top 50 global tanker ports + all ports near existing STS zones)
- Create `zone_helpers.is_near_port(lat, lon, radius_nm=5)` function using PostGIS ST_DWithin
- Alternative simpler approach: use a static list of port polygons from World Port Index data, stored in config.yaml or a seed migration
- The port list should include: Rotterdam, Fujairah, Singapore, Piraeus, Kalamata, Ceuta, Lome, Novorossiysk, Primorsk, Ust-Luga, Kozmino, Murmansk + major global tanker ports

---

### Story 3: Event Boundary Detection in Realtime Rules

**As a** scoring engine
**I want to** detect when an anomalous condition starts and ends
**So that** continuous situations are scored as a single event, not repeated firings

**Acceptance Criteria:**

- GIVEN `speed_anomaly` fires for slow steaming WHEN the vessel's speed exceeds 5 knots for 30+ minutes THEN the existing anomaly is marked `event_state=ended` with `event_end` timestamp
- GIVEN `sts_proximity` fires for STS zone loitering WHEN the vessel exits the STS zone buffer THEN the anomaly is ended
- GIVEN `draft_change` fires WHEN the vessel's draught returns to within 0.5m of original THEN the anomaly is ended
- GIVEN `destination_spoof` fires for a placeholder destination WHEN the destination field changes to a real port name THEN the anomaly is ended
- GIVEN `ais_gap` fires WHEN the vessel resumes transmitting THEN the anomaly is ended
- GIVEN any rule with an active anomaly WHEN conditions still persist THEN no new anomaly is created (existing dedup maintained)

**Test Requirements:**

- [ ] Test: speed_anomaly event starts at t=0 (SOG 3kn), vessel speeds up at t=3h (SOG 12kn) → anomaly ended at ~t=3.5h
- [ ] Test: speed_anomaly event starts at t=0, vessel stays at 3kn for 48h → single anomaly, not 24 re-firings
- [ ] Test: sts_proximity loitering starts, vessel departs zone → anomaly ended
- [ ] Test: ais_gap starts when signal lost, ends when signal resumes → single event with duration
- [ ] Test: destination_spoof fires for "FOR ORDERS", destination changes to "ROTTERDAM" → anomaly ended

**Technical Notes:**

- Add an `end_active_events(session, mmsi, rule_id)` method to the engine
- In `evaluate_realtime`, after rule evaluation, check if conditions have CEASED for any active anomalies of that rule
- The engine currently only checks "did the rule fire?" — add a check for "did an active anomaly's condition end?"
- Each rule needs a new method `check_event_ended(mmsi, profile, recent_positions, active_anomaly) -> bool`
- Add this as an optional method on `ScoringRule` base class with default returning `False` (backward-compatible)

---

### Story 4: Repeat Event Escalation

**As a** scoring engine
**I want to** score repeat occurrences of the same anomaly type higher than the first occurrence
**So that** vessels with recurring suspicious behaviour are flagged more aggressively

**Acceptance Criteria:**

- GIVEN a vessel has 1 ended `speed_anomaly` event WHEN a second slow steaming event starts THEN the new anomaly gets 1.5x base points (23 instead of 15)
- GIVEN a vessel has 2+ ended events for the same rule WHEN a third event starts THEN 2x base points
- GIVEN escalation multiplier applies WHEN `MAX_PER_RULE` cap is checked THEN the cap is also adjusted (e.g., speed_anomaly cap goes from 15 to 30 for repeat offenders)
- GIVEN a vessel has old ended events (>30 days) WHEN a new event starts THEN old events don't count toward escalation (decay window)
- GIVEN escalation applies WHEN the aggregate score is calculated THEN it uses the escalated points correctly

**Test Requirements:**

- [ ] Test: First speed_anomaly event = 15 points, second = 23 points (1.5x), third = 30 points (2x)
- [ ] Test: First sts_proximity event = 15 points, second = 23 points
- [ ] Test: Events older than 30 days don't escalate score
- [ ] Test: MAX_PER_RULE cap adjusts with escalation (speed_anomaly: 15 → 30 → 45 for 1st/2nd/3rd events)
- [ ] Test: Escalation multiplier is configurable in config.yaml
- [ ] Test: Aggregate score correctly sums escalated points with per-rule cap

**Technical Notes:**

- Add escalation config to `config.yaml`:
  ```yaml
  scoring:
    escalation:
      multipliers: [1.0, 1.5, 2.0]  # 1st, 2nd, 3rd+ occurrence
      decay_days: 30  # events older than this don't count
      cap_multiplier: true  # also adjust MAX_PER_RULE
  ```
- In `engine._create_anomaly`, count ended events for the same `(mmsi, rule_id)` within the decay window
- Apply multiplier to `result.points` before persisting
- Update `MAX_PER_RULE` logic in `aggregator.aggregate_score` to account for escalated caps
- Store the `occurrence_number` and `escalation_multiplier` in the anomaly `details` JSONB

---

### Story 5: GFW Multi-Event Handling

**As a** scoring engine
**I want to** score all distinct GFW events, not just the first one
**So that** vessels with multiple AIS-disabling events or encounters are scored proportionally

**Acceptance Criteria:**

- GIVEN a vessel has 3 GFW ENCOUNTER events WHEN gfw_encounter evaluates THEN each event creates a separate anomaly (with dedup against existing ones)
- GIVEN a vessel has 2 GFW AIS_DISABLING events WHEN gfw_ais_disabling evaluates THEN each creates a separate anomaly
- GIVEN multiple GFW events of the same type within 24 hours WHEN evaluated THEN they are treated as a single event (temporal dedup)
- GIVEN a GFW event that overlaps an existing anomaly's time window WHEN evaluated THEN the existing anomaly is updated rather than duplicated

**Test Requirements:**

- [ ] Test: 3 GFW encounter events → 3 anomaly rows (distinct event IDs)
- [ ] Test: 2 GFW encounter events 1 hour apart → 1 anomaly (temporal dedup)
- [ ] Test: 2 GFW encounter events 48 hours apart → 2 anomalies
- [ ] Test: GFW event matching existing anomaly time window → no duplicate
- [ ] Test: Aggregate score sums all GFW anomalies with per-rule cap

**Technical Notes:**

- Change GFW rules from `events[0]` pattern to iterating ALL events
- Add temporal dedup: events of same type within 24h window = single event (use the longer/more severe one)
- Track `gfw_event_id` in anomaly details to prevent re-processing the same GFW event
- The engine's existing dedup (`existing_rule_ids`) prevents only by rule_id — need finer dedup by rule_id + event_id

---

### Story 6: Engine Event Lifecycle Loop

**As a** scoring engine
**I want to** run an event lifecycle check alongside rule evaluation
**So that** active anomalies are properly ended when conditions cease

**Acceptance Criteria:**

- GIVEN the engine processes a position update WHEN it evaluates realtime rules THEN it ALSO checks all active anomalies for that MMSI to see if they should be ended
- GIVEN an active `speed_anomaly` anomaly and current SOG > 8 knots sustained for 30min THEN the anomaly is ended
- GIVEN an active `sts_proximity` anomaly and vessel is now outside all STS zones THEN the anomaly is ended
- GIVEN an active `ais_gap` anomaly and a new position is received THEN the anomaly is ended (signal resumed)
- GIVEN an active anomaly is ended WHEN score is recalculated THEN the ended anomaly no longer contributes to the aggregate score
- GIVEN the event lifecycle runs WHEN it ends anomalies THEN it logs the event duration for monitoring

**Test Requirements:**

- [ ] Test: Engine evaluate_realtime calls lifecycle check for all active anomalies
- [ ] Test: Active speed_anomaly ended when vessel speeds up → score drops
- [ ] Test: Active ais_gap ended when position received → score recalculated
- [ ] Test: Active sts_proximity ended when vessel exits zone → score recalculated
- [ ] Test: Ended anomalies have correct event_end timestamp and duration in details
- [ ] Test: Score aggregate only includes active anomalies (not ended ones)

**Technical Notes:**

- Add `_check_and_end_active_events(session, mmsi, recent_positions)` to `ScoringEngine`
- Call it at the START of `evaluate_realtime` (before rule evaluation)
- Fetch active anomalies: `SELECT * FROM anomaly_events WHERE mmsi=:mmsi AND event_state='active'`
- For each active anomaly, call the corresponding rule's `check_event_ended()` method
- If ended: set `event_end = NOW()`, `event_state = 'ended'`, `resolved = true`
- Update `aggregate_score` to only sum anomalies where `event_state = 'active'` (backward compat: treat NULL event_state as active)

---

## Technical Design

### Data Model Changes

**New migration 005_anomaly_lifecycle.sql:**
```sql
ALTER TABLE anomaly_events ADD COLUMN event_start TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE anomaly_events ADD COLUMN event_end TIMESTAMPTZ;
ALTER TABLE anomaly_events ADD COLUMN event_state VARCHAR(20) DEFAULT 'active';

-- Backfill existing data
UPDATE anomaly_events SET event_start = created_at;
UPDATE anomaly_events SET event_state = CASE WHEN resolved THEN 'ended' ELSE 'active' END;

-- Index for lifecycle queries
CREATE INDEX idx_anomaly_events_lifecycle ON anomaly_events (mmsi, rule_id, event_state) WHERE event_state = 'active';
```

**New seed data migration 006_ports.sql:**
```sql
CREATE TABLE ports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(2) NOT NULL,
    position GEOGRAPHY(POINT, 4326) NOT NULL,
    port_type VARCHAR(50) DEFAULT 'tanker',
    radius_nm FLOAT DEFAULT 5.0
);

CREATE INDEX idx_ports_position ON ports USING GIST (position);
-- Seed with top 50 global tanker ports
```

### API Changes

None — this is engine-internal. The existing `/api/anomalies` endpoint will naturally return the new fields.

### Dependencies

- PostgreSQL migration system (existing)
- PostGIS for port proximity checks (existing)
- `zone_helpers.py` — add `is_near_port()` function

### Security Considerations

None — engine-internal changes only.

---

## Implementation Order

### Group 1 (parallel — no dependencies)
- Story 1 — Migration + Pydantic model updates (`db/migrations/`, `shared/models/anomaly.py`)
- Story 2 — Port awareness (`db/migrations/006_ports.sql`, `services/scoring/zone_helpers.py`)

### Group 2 (parallel — after Group 1)
- Story 3 — Event boundary detection in realtime rules (`services/scoring/rules/*.py`, `services/scoring/rules/base.py`)
- Story 5 — GFW multi-event handling (`services/scoring/rules/gfw_*.py`)

### Group 3 (sequential — after Group 2)
- Story 6 — Engine lifecycle loop (`services/scoring/engine.py`)
- Story 4 — Repeat event escalation (`services/scoring/engine.py`, `services/scoring/aggregator.py`, `config.yaml`)

**Parallel safety rules:**
- Group 1: Migration files are numbered sequentially (005, 006) but touch different tables
- Group 2: Realtime rules and GFW rules are in separate files
- Group 3: Engine and aggregator are tightly coupled — must be sequential

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled
- [ ] No regressions in existing tests (all 1045 tests still pass)
- [ ] Code committed with proper messages
- [ ] Ready for human review
