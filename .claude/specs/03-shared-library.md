# Feature Spec: Shared Python Library

**Slug:** `shared-library`
**Created:** 2026-03-11
**Status:** draft
**Priority:** critical
**Wave:** 1 (Foundation)

---

## Overview

Create the shared Python library used by all backend services: Pydantic models for all data types, async SQLAlchemy database connection layer, YAML/env configuration loading, and constants (scoring weights, MID-to-flag lookup, zone definitions).

## Problem Statement

All Python services (ais-ingest, scoring, enrichment, api-server) need common models, database access, and configuration. Without a shared library, each service would duplicate these definitions, leading to inconsistencies.

## Out of Scope

- NOT: Service-specific business logic
- NOT: Database migrations (see `02-database`)
- NOT: Docker Compose or infrastructure (see `01-infrastructure`)
- NOT: Individual service entry points

---

## User Stories

### Story 1: Pydantic Data Models

**As a** service developer
**I want to** import shared Pydantic models for all domain types
**So that** all services use the same data structures for serialization and validation

**Acceptance Criteria:**

- GIVEN `shared/models/vessel.py` WHEN imported THEN VesselProfile and VesselPosition Pydantic models are available with all fields matching the database schema
- GIVEN `shared/models/ais_message.py` WHEN imported THEN PositionReport and ShipStaticData models are available with validation rules (MMSI 9-digit, lat -90 to 90, lon -180 to 180, etc.)
- GIVEN `shared/models/anomaly.py` WHEN imported THEN AnomalyEvent and RuleResult models are available
- GIVEN `shared/models/enrichment.py` WHEN imported THEN ManualEnrichment model with all fields including pi_tier enum
- GIVEN `shared/models/sar.py` WHEN imported THEN SarDetection model is available with GFW-sourced fields (gfw_detection_id, matching_score, fishing_score)
- GIVEN `shared/models/gfw_event.py` WHEN imported THEN GfwEvent model is available with event_type enum (AIS_DISABLING, ENCOUNTER, LOITERING, PORT_VISIT), required fields (gfw_event_id, event_type, mmsi, start_time, end_time, lat, lon), and optional fields (details JSONB, encounter_mmsi, port_name)
- GIVEN any model WHEN invalid data is passed THEN Pydantic raises ValidationError with clear messages

**Test Requirements:**

- [ ] Test: VesselPosition rejects MMSI with <9 or >9 digits
- [ ] Test: VesselPosition rejects latitude outside -90 to 90 range
- [ ] Test: VesselPosition rejects longitude outside -180 to 180 (reject 181 as unknown)
- [ ] Test: VesselPosition rejects SOG of 102.3 (not available marker)
- [ ] Test: ShipStaticData correctly computes length from Dimension.A + B
- [ ] Test: AnomalyEvent severity must be one of: critical, high, moderate, low
- [ ] Test: RuleResult dataclass has fields: fired, rule_id, severity, points, details

**Technical Notes:**

Use Pydantic v2. Models should closely mirror the database columns but use Python types (datetime, float, Optional fields). Include `model_config = ConfigDict(from_attributes=True)` for ORM compatibility.

PositionReport field mapping from aisstream.io:
- timestamp: MetaData.time_utc (ISO 8601, reject >5min future)
- mmsi: MetaData.MMSI (9 digits, reject 000000000)
- longitude: Message.PositionReport.Longitude (-180 to 180, reject 181)
- latitude: Message.PositionReport.Latitude (-90 to 90, reject 91)
- sog: 0-102.2 (102.3 = not available)
- cog: 0-359.9 (360 = not available)
- heading: 0-359 (511 = not available)
- nav_status: 0-15
- rot: -127 to 127 (-128 = not available)

---

### Story 2: Database Connection Layer

**As a** service developer
**I want to** import a pre-configured async SQLAlchemy engine and session factory
**So that** I can access the database without configuring connections in each service

**Acceptance Criteria:**

- GIVEN `shared/db/connection.py` WHEN imported THEN `get_engine()` returns an async SQLAlchemy engine configured from DATABASE_URL env var
- GIVEN `shared/db/connection.py` WHEN imported THEN `get_session()` returns an async session factory
- GIVEN `shared/db/repositories.py` WHEN imported THEN CRUD functions are available for: vessel_profiles (upsert, get by mmsi, list with filters), vessel_positions (bulk insert, get track), anomaly_events (create, list by mmsi, list with filters), manual_enrichment (create, get by mmsi), gfw_events (bulk upsert, list by mmsi, list with filters), sar_detections (bulk upsert, list with filters)
- GIVEN a repository function WHEN called THEN it uses async/await with asyncpg driver

**Test Requirements:**

- [ ] Test: Engine creation with valid DATABASE_URL succeeds
- [ ] Test: Session factory produces working async sessions
- [ ] Test: Repository functions have correct signatures and type hints

**Technical Notes:**

Use `sqlalchemy[asyncio]` with `asyncpg` driver. Engine should use `create_async_engine`. Use `GeoAlchemy2` for PostGIS column types. The repository layer should use raw SQL or SQLAlchemy Core (not ORM) for performance-critical operations like bulk inserts. Keep the ORM-style for simple CRUD.

---

### Story 3: Configuration Loading

**As a** service developer
**I want to** import a centralized config object that loads from both `.env` and `config.yaml`
**So that** all services use consistent configuration values

**Acceptance Criteria:**

- GIVEN `shared/config.py` WHEN imported THEN a Settings class (Pydantic Settings) loads from environment variables
- GIVEN `shared/config.py` WHEN `config.yaml` exists THEN YAML config is loaded and merged with env settings
- GIVEN config WHEN scoring thresholds are accessed THEN yellow_threshold (default 30) and red_threshold (default 100) are available
- GIVEN config WHEN ingest settings are accessed THEN batch_size (500), flush_interval (2s), reconnect_max (60s), stale_connection (120s) are available
- GIVEN config WHEN enrichment settings are accessed THEN rate limits and fuzzy thresholds are available

**Test Requirements:**

- [ ] Test: Config loads with defaults when no .env or config.yaml exists
- [ ] Test: Config correctly overrides defaults from environment variables
- [ ] Test: Config correctly loads YAML sections for scoring, ingest, enrichment, gfw, retention, frontend

**Technical Notes:**

Use `pydantic-settings` for env var loading. Use `pyyaml` for config.yaml. Create a singleton config instance importable as `from shared.config import settings`.

---

### Story 4: Constants and Reference Data

**As a** service developer
**I want to** import constants for scoring weights, MID-to-flag lookups, and zone definitions
**So that** scoring rules and enrichment services use consistent reference data

**Acceptance Criteria:**

- GIVEN `shared/constants.py` WHEN imported THEN `MID_TO_FLAG` dict maps 3-digit MID codes to ISO 3166-1 alpha-2 country codes (at least 200 entries)
- GIVEN `shared/constants.py` WHEN imported THEN `MAX_PER_RULE` dict maps rule_ids to their maximum point caps
- GIVEN `shared/constants.py` WHEN imported THEN scoring constants are available: point values for each severity level, threshold values
- GIVEN `shared/constants.py` WHEN imported THEN key MID entries exist: 273 (RU), 351-354 (PA), 355-357 (LR), 374-375 (MH), 538 (CM), 636-637 (IR), 477 (HK), 572 (TV)

**Test Requirements:**

- [ ] Test: MID_TO_FLAG contains key shadow fleet entries (273=RU, 351=PA, etc.)
- [ ] Test: MAX_PER_RULE has entries for all 13 scoring rules (5 GFW-sourced + 8 real-time)
- [ ] Test: All constants are immutable (frozen dataclass or module-level constants)

**Technical Notes:**

MID-to-flag table is published by ITU. Include at minimum the ~50 most common maritime registries plus all shadow fleet-relevant flags. Rule IDs — GFW-sourced: gfw_ais_disabling, gfw_encounter, gfw_loitering, gfw_port_visit, gfw_dark_sar. Real-time: ais_gap, sts_proximity, destination_spoof, draft_change, flag_hopping, sanctions_match, vessel_age, speed_anomaly, identity_mismatch.

---

## Technical Design

### Data Model Changes

No database changes — this spec defines Python representations of the database schema.

### API Changes

None.

### Dependencies

- pydantic >= 2.6
- pydantic-settings >= 2.2
- sqlalchemy[asyncio] >= 2.0
- asyncpg >= 0.29
- geoalchemy2 >= 0.14
- redis[hiredis] >= 5.0
- pyyaml >= 6.0

Create `shared/requirements-base.txt` with these pinned versions.

### Security Considerations

- DATABASE_URL contains credentials — loaded from env, never logged
- Config object should not expose secrets in `__repr__`

---

## Implementation Order

### Group 1 (parallel)
- Story 3 — config.py (no dependencies on other shared modules)
- Story 4 — constants.py (no dependencies)

### Group 2 (parallel — after Group 1)
- Story 1 — models/ (may reference constants for enums)
- Story 2 — db/ (uses models and config)

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Models validate and reject bad data correctly
- [ ] DB connection layer works with asyncpg
- [ ] Config loads from both .env and config.yaml
- [ ] MID-to-flag lookup has comprehensive coverage
- [ ] Code committed with proper messages
- [ ] Ready for human review
