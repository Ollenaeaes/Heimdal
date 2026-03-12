# Feature Spec: Scoring Engine

**Slug:** `scoring-engine`
**Created:** 2026-03-11
**Updated:** 2026-03-12 (GFW Integration — Update 001)
**Status:** completed
**Priority:** high
**Wave:** 4 (Intelligence Layer)

---

## Overview

Build the scoring engine service that subscribes to position events and enrichment-complete events from Redis, evaluates 13 scoring rules (5 GFW-sourced + 8 real-time) against each vessel, applies deduplication logic when GFW and real-time rules overlap, updates risk scores and tiers, writes anomaly events, and publishes risk-change events for the frontend. This is the intelligence core of Heimdal.

> **Update 001:** Added 5 GFW-sourced rules (higher confidence, ML-validated), downgraded ais_gap and sts_proximity real-time rules, removed terminal_loading (replaced by gfw_port_visit), and added dedup logic where GFW events suppress corresponding real-time rules for the same vessel/timewindow.

## Problem Statement

Raw AIS data alone doesn't identify shadow fleet activity. The scoring engine applies domain-specific behavioral rules to automatically classify vessels as green (normal), yellow (suspicious), or red (high risk). GFW-sourced rules provide higher-confidence detections based on ML-validated satellite and behavioral analysis.

## Out of Scope

- NOT: AIS data ingestion (see `04-ais-ingest`)
- NOT: Enrichment from external databases (see `08-enrichment-service`)
- NOT: Frontend display of scores (see `10-vessel-detail-panel`)
- NOT: Machine learning anomaly detection (future scope)

---

## User Stories

### Story 1: Rule Framework and Engine

**As a** developer
**I want to** have an extensible rule evaluation engine with two rule categories
**So that** new scoring rules can be added by creating a single file with no engine changes

**Acceptance Criteria:**

- GIVEN `rules/base.py` WHEN imported THEN abstract `ScoringRule` class is available with: `rule_id` property, `rule_category` property (one of: 'gfw_sourced', 'realtime'), `evaluate()` async method accepting (mmsi, profile, recent_positions, existing_anomalies, gfw_events) and returning Optional[RuleResult]
- GIVEN `engine.py` WHEN started THEN it auto-discovers all rule classes in `rules/` directory
- GIVEN the engine WHEN subscribing to Redis THEN it listens on both `heimdal:positions` and `heimdal:enrichment_complete` channels
- GIVEN a position batch event WHEN received THEN the engine loads profile + recent positions for each MMSI and evaluates all real-time rules
- GIVEN an enrichment_complete event WHEN received THEN the engine loads profile + gfw_events for each MMSI and evaluates all GFW-sourced rules
- GIVEN rule evaluation WHEN a rule fires THEN an anomaly_event row is created in the database

**Test Requirements:**

- [ ] Test: Engine discovers all 13 rule classes automatically (5 GFW + 8 realtime)
- [ ] Test: Engine evaluates all rules for a given MMSI
- [ ] Test: Fired rules create anomaly_event rows with correct fields
- [ ] Test: Non-fired rules create no anomaly events
- [ ] Test: Engine listens on both Redis channels

**Technical Notes:**

RuleResult dataclass: `{fired: bool, rule_id: str, severity: str, points: int, details: dict, source: str}`. The `source` field is either 'gfw' or 'realtime'. Use Python's `importlib` or `pkgutil` to auto-discover rule modules. Each module should export a class that extends ScoringRule.

---

### Story 2: Score Aggregation, Tier Calculation, and Dedup Logic

**As a** the scoring engine
**I want to** aggregate anomaly points into a risk score and tier with deduplication
**So that** each vessel gets a clear green/yellow/red classification without double-counting

**Acceptance Criteria:**

- GIVEN a vessel WHEN scoring THEN sum points from all unresolved anomalies, capping each rule at 2x its base points (MAX_PER_RULE from constants)
- GIVEN a total score >=100 WHEN calculating tier THEN tier is RED
- GIVEN a total score >=30 and <100 WHEN calculating tier THEN tier is YELLOW
- GIVEN a total score <30 WHEN calculating tier THEN tier is GREEN
- GIVEN a score change WHEN updating THEN update vessel_profiles.risk_score and risk_tier
- GIVEN a tier change WHEN detected THEN publish to Redis `heimdal:risk_changes` with: mmsi, old_tier, new_tier, score, trigger_rule, timestamp
- GIVEN a new anomaly WHEN created THEN publish to Redis `heimdal:anomalies` with: mmsi, rule_id, severity, points, details, timestamp
- GIVEN a GFW-sourced rule fires WHEN a corresponding real-time rule has also fired for the same vessel within the overlapping time window THEN suppress the real-time rule's anomaly (mark as resolved) and keep only the GFW-sourced anomaly
- GIVEN dedup pairs WHEN checking THEN: gfw_ais_disabling suppresses ais_gap, gfw_encounter suppresses sts_proximity, gfw_loitering suppresses sts_proximity, gfw_port_visit suppresses (formerly terminal_loading — now no real-time equivalent)

**Test Requirements:**

- [ ] Test: Score correctly sums multiple anomaly points
- [ ] Test: Per-rule cap prevents runaway scores (e.g., 10 AIS gap events don't give 10x points)
- [ ] Test: Tier thresholds are correct: 0-29=green, 30-99=yellow, 100+=red
- [ ] Test: Tier change triggers Redis publish with correct payload
- [ ] Test: No Redis publish when tier stays the same
- [ ] Test: GFW ais_disabling anomaly suppresses existing real-time ais_gap anomaly for same vessel/timewindow
- [ ] Test: After dedup, only the GFW anomaly contributes to score

**Technical Notes:**

Thresholds are configurable via config.yaml (scoring.yellow_threshold, scoring.red_threshold). MAX_PER_RULE is defined in shared/constants.py. Dedup window: if a GFW event's time range overlaps with a real-time anomaly's detection_time ±6 hours, they are considered the same behavior.

---

### Story 3: GFW AIS-Disabling Rule

**As a** the scoring engine
**I want to** score vessels with GFW-detected AIS-disabling events
**So that** intentional transponder shutoffs confirmed by satellite analysis are flagged at high confidence

**Acceptance Criteria:**

- GIVEN a GFW AIS_DISABLING event for a vessel WHEN the event location is in a sanctions corridor (STS zone or near Russian terminal) THEN fire with severity=critical, points=100
- GIVEN a GFW AIS_DISABLING event WHEN the location is elsewhere THEN fire with severity=high, points=40
- GIVEN this rule fires WHEN a real-time ais_gap anomaly exists for the same vessel/timewindow THEN the dedup logic suppresses the real-time anomaly

**Test Requirements:**

- [ ] Test: AIS-disabling in sanctions corridor fires critical (100)
- [ ] Test: AIS-disabling elsewhere fires high (40)
- [ ] Test: Dedup suppresses corresponding real-time ais_gap

---

### Story 4: GFW Encounter Rule

**As a** the scoring engine
**I want to** score vessels with GFW-detected encounter events
**So that** ship-to-ship meetings detected by satellite analysis are flagged

**Acceptance Criteria:**

- GIVEN a GFW ENCOUNTER event WHEN the encounter is in an STS zone OR the encounter partner (encounter_mmsi) is a sanctioned vessel THEN fire with severity=critical, points=100
- GIVEN a GFW ENCOUNTER event WHEN elsewhere and partner is not sanctioned THEN fire with severity=high, points=40

**Test Requirements:**

- [ ] Test: Encounter in STS zone fires critical (100)
- [ ] Test: Encounter with sanctioned vessel fires critical (100)
- [ ] Test: Encounter elsewhere with non-sanctioned vessel fires high (40)

---

### Story 5: GFW Loitering Rule

**As a** the scoring engine
**I want to** score vessels with GFW-detected loitering events
**So that** prolonged stationary behavior detected by satellite analysis is flagged

**Acceptance Criteria:**

- GIVEN a GFW LOITERING event WHEN the location is in an STS zone THEN fire with severity=high, points=40
- GIVEN a GFW LOITERING event WHEN in open ocean (not in any known zone) THEN fire with severity=moderate, points=15

**Test Requirements:**

- [ ] Test: Loitering in STS zone fires high (40)
- [ ] Test: Loitering in open ocean fires moderate (15)

---

### Story 6: GFW Port Visit Rule

**As a** the scoring engine
**I want to** score vessels with GFW-detected port visit events at Russian terminals
**So that** visits to sanctioned-origin ports are flagged (replaces old terminal_loading rule)

**Acceptance Criteria:**

- GIVEN a GFW PORT_VISIT event WHEN the port_name matches a known Russian terminal (from zones table, zone_type='terminal') THEN fire with severity=high, points=40
- GIVEN a GFW PORT_VISIT event WHEN the port is not a Russian terminal THEN do not fire

**Test Requirements:**

- [ ] Test: Port visit at Ust-Luga fires high (40)
- [ ] Test: Port visit at non-Russian port does not fire

---

### Story 7: GFW Dark SAR Rule

**As a** the scoring engine
**I want to** score vessels when GFW SAR detections correlate with AIS gaps
**So that** dark ship behavior confirmed by radar is flagged

**Acceptance Criteria:**

- GIVEN a SAR detection (is_dark=true) from the sar_detections table WHEN a real-time ais_gap anomaly exists for the same vessel within 48h of the SAR detection time THEN fire with severity=high, points=40
- GIVEN the correlation WHEN the SAR detection has no matching ais_gap THEN do not fire (SAR detection alone is handled by display, not scoring)

**Test Requirements:**

- [ ] Test: Dark SAR + AIS gap within 48h fires high (40)
- [ ] Test: Dark SAR without AIS gap does not fire

---

### Story 8: AIS Gap Detection Rule (Downgraded)

**As a** the scoring engine
**I want to** detect vessels that stop transmitting AIS
**So that** potential transponder shutoffs are flagged (at reduced severity since GFW provides higher-confidence AIS-disabling detection)

**Acceptance Criteria:**

- GIVEN a vessel with last position >48h ago WHEN scoring THEN fire with severity=high, points=40 (downgraded from critical/100)
- GIVEN a vessel with last position 12-48h ago WHEN scoring THEN fire with severity=moderate, points=15 (downgraded from high/40)
- GIVEN a vessel with last position 2-12h ago WHEN scoring THEN fire with severity=low, points=5 (downgraded from moderate/15)
- GIVEN an AIS gap rule WHEN it fired for this MMSI within 24h THEN do NOT fire again (cooldown)
- GIVEN the rule WHEN tracking last_seen THEN use Redis HSET `heimdal:last_seen` (mmsi → timestamp)

**Test Requirements:**

- [ ] Test: 49-hour gap fires high (40 points)
- [ ] Test: 13-hour gap fires moderate (15 points)
- [ ] Test: 3-hour gap fires low (5 points)
- [ ] Test: 1-hour gap does not fire
- [ ] Test: Cooldown prevents re-firing within 24h

---

### Story 9: STS Zone Proximity Rule (Downgraded)

**As a** the scoring engine
**I want to** detect vessels loitering in known ship-to-ship transfer zones
**So that** potential covert cargo transfers are flagged (at reduced severity since GFW encounter/loitering provides higher-confidence detection)

**Acceptance Criteria:**

- GIVEN a vessel within 10nm of an STS zone AND speed <3 knots AND duration >6 hours WHEN scoring THEN fire with severity=moderate, points=15 (downgraded from high/40)
- GIVEN a vessel enters an STS zone WHEN tracking THEN store entry timestamp in Redis `heimdal:sts_entry:{mmsi}`
- GIVEN a vessel leaves an STS zone WHEN tracking THEN clear the entry timestamp
- GIVEN PostGIS WHEN checking proximity THEN use ST_DWithin against zones table (zone_type='sts_zone')

**Test Requirements:**

- [ ] Test: Vessel inside STS zone, slow, >6h fires moderate (15)
- [ ] Test: Vessel inside STS zone but fast (>3 knots) does not fire
- [ ] Test: Vessel inside STS zone <6 hours does not fire

---

### Story 10: Destination Spoofing Rule

**As a** the scoring engine
**I want to** detect vessels reporting suspicious AIS destinations
**So that** vessels hiding their true destination are flagged

**Acceptance Criteria:**

- GIVEN destination matches 'FOR ORDERS', 'FOR ORDER', 'TBN', 'TBA' WHEN scoring THEN fire severity=high, points=40
- GIVEN destination matches sea area patterns ('CARIBBEAN SEA', 'MEDITERRANEAN', 'ATLANTIC', 'PACIFIC', 'INDIAN OCEAN') WHEN scoring THEN fire severity=high, points=40
- GIVEN destination changes >3 times in 7 days WHEN scoring THEN fire severity=moderate, points=15

**Test Requirements:**

- [ ] Test: 'FOR ORDERS' fires high
- [ ] Test: 'MEDITERRANEAN' fires high
- [ ] Test: Normal port name does not fire
- [ ] Test: 4 destination changes in 7 days fires moderate

---

### Story 11: Draft Change Detection Rule

**As a** the scoring engine
**I want to** detect anomalous draught increases while a vessel is at sea
**So that** covert at-sea loading operations are flagged

**Acceptance Criteria:**

- GIVEN draught increases by >2 meters WHEN vessel is anchored/drifting (nav_status 1 or 5, SOG <1 knot) AND not near a port THEN fire severity=high, points=40

**Test Requirements:**

- [ ] Test: 3m draught increase while drifting at sea fires high
- [ ] Test: 3m draught increase at port does not fire
- [ ] Test: 1m draught increase does not fire

---

### Story 12: Flag Hopping Rule

**As a** the scoring engine
**I want to** detect vessels that frequently change their flag state
**So that** potential flag manipulation is flagged

**Acceptance Criteria:**

- GIVEN a vessel with >=3 distinct flags in 12 months WHEN scoring THEN fire severity=high, points=40
- GIVEN a vessel with 2 distinct flags in 12 months WHEN scoring THEN fire severity=moderate, points=15
- GIVEN the rule WHEN tracking flags THEN maintain flag_history JSONB in vessel_profiles as [{flag, first_seen, last_seen}]
- GIVEN a position WHEN received THEN derive flag from MMSI MID digits using MID_TO_FLAG lookup

**Test Requirements:**

- [ ] Test: 3 flags in 12 months fires high
- [ ] Test: 2 flags in 12 months fires moderate
- [ ] Test: 1 flag does not fire
- [ ] Test: MID extraction correctly derives flag from MMSI

---

### Story 13: Remaining Rules (sanctions_match, vessel_age, speed_anomaly, identity_mismatch)

**As a** the scoring engine
**I want to** implement the remaining four scoring rules
**So that** the full behavioral detection suite is complete

**Acceptance Criteria:**

**Sanctions Match (sanctions_match.py):**
- GIVEN a vessel with sanctions_status confidence >0.8 (direct IMO/MMSI match) WHEN scoring THEN fire severity=critical, points=100
- GIVEN a fuzzy name match WHEN scoring THEN fire severity=high, points=40

**Vessel Age (vessel_age.py):**
- GIVEN a tanker (ship_type 80-89) with year_built making it >20 years old WHEN scoring THEN fire severity=high, points=40
- GIVEN a tanker 15-20 years old WHEN scoring THEN fire severity=low, points=5
- GIVEN a non-tanker WHEN scoring THEN do not fire

**Speed Anomaly (speed_anomaly.py):**
- GIVEN sustained slow steaming (<5 knots avg over 2 hours) outside port approach WHEN scoring THEN fire severity=moderate, points=15
- GIVEN abrupt speed change (>10 knot delta between consecutive positions) WHEN scoring THEN fire severity=moderate, points=15

**Identity Mismatch (identity_mismatch.py):**
- GIVEN MMSI-derived flag differs from self-reported flag WHEN scoring THEN investigate
- GIVEN IMO-based dimensions differ >20% from AIS-reported WHEN scoring THEN fire severity=critical, points=100

**Test Requirements:**

- [ ] Test: Direct sanctions match fires critical (100)
- [ ] Test: Fuzzy name match fires high (40)
- [ ] Test: 25-year-old tanker fires high (40)
- [ ] Test: 17-year-old tanker fires low (5)
- [ ] Test: Non-tanker does not trigger vessel_age
- [ ] Test: Sustained <5 knot speed fires moderate
- [ ] Test: >10 knot delta fires moderate
- [ ] Test: >20% dimension mismatch fires critical

---

### Story 14: Service Dockerfile and Entry Point

**As a** developer
**I want to** run the scoring engine as a Docker container
**So that** it integrates with Docker Compose

**Acceptance Criteria:**

- GIVEN the Dockerfile WHEN built THEN Python 3.12 container with shared base + `shapely>=2.0`
- GIVEN the container WHEN started THEN main.py subscribes to Redis and begins processing
- GIVEN `requirements.txt` WHEN read THEN includes shared base + shapely

**Test Requirements:**

- [ ] Test: Dockerfile builds without errors

---

## Technical Design

### Data Model Changes

Writes to: `anomaly_events` (new rows), `vessel_profiles` (risk_score, risk_tier, flag_history)
Reads from: `vessel_positions`, `vessel_profiles`, `anomaly_events`, `zones`, `gfw_events`, `sar_detections`

### Dependencies

- PostgreSQL with PostGIS (spatial queries for zones)
- Redis (subscription + state tracking)
- Shared library (models, config, constants, DB layer)

---

## Implementation Order

### Group 1 (sequential)
- Story 1 — Rule framework and engine (foundation for all rules)
- Story 2 — Score aggregation and dedup logic (depends on rule framework)

### Group 2 (parallel — after Group 1, GFW-sourced rules)
- Story 3 — GFW AIS-disabling
- Story 4 — GFW encounter
- Story 5 — GFW loitering
- Story 6 — GFW port visit
- Story 7 — GFW dark SAR

### Group 3 (parallel — after Group 1, real-time rules)
- Story 8 — AIS gap detection (downgraded)
- Story 9 — STS zone proximity (downgraded)
- Story 10 — Destination spoofing
- Story 11 — Draft change detection
- Story 12 — Flag hopping
- Story 13 — Remaining 4 rules (sanctions, age, speed, identity)

### Group 4 (after Groups 2-3)
- Story 14 — Dockerfile

---

## Verification Checklist

- [ ] All 13 scoring rules implemented and tested (5 GFW + 8 realtime)
- [ ] Score aggregation with per-rule caps working
- [ ] Dedup logic correctly suppresses real-time anomalies when GFW anomaly exists
- [ ] Tier transitions trigger Redis events
- [ ] Rules use PostGIS for spatial queries correctly
- [ ] Redis state tracking (last_seen, sts_entry) works
- [ ] Cooldown periods prevent duplicate alerts
- [ ] GFW-sourced rules fire on enrichment_complete events
- [ ] Container builds and runs
- [ ] Code committed with proper messages
- [ ] Ready for human review
