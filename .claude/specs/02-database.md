# Feature Spec: Database Schema and Setup

**Slug:** `database`
**Created:** 2026-03-11
**Status:** completed
**Priority:** critical
**Wave:** 1 (Foundation)

---

## Overview

Create the PostgreSQL database container with PostGIS and TimescaleDB extensions, all migration files (schema, hypertable setup, indexes, seed data), and the initialization script. This is the persistent data layer for the entire platform.

## Problem Statement

All services need a properly configured PostgreSQL database with geospatial (PostGIS) and time-series (TimescaleDB) capabilities. The schema must be created automatically on first startup.

## Out of Scope

- NOT: Application-level database access code (see `03-shared-library`)
- NOT: Docker Compose service definition (see `01-infrastructure`)
- NOT: Data writing from any service

---

## User Stories

### Story 1: PostgreSQL Docker Image

**As a** developer
**I want to** build a custom PostgreSQL image with PostGIS and TimescaleDB
**So that** both extensions are available immediately on startup

**Acceptance Criteria:**

- GIVEN the Dockerfile WHEN built THEN it extends `timescale/timescaledb-ha:pg16-latest`
- GIVEN the Dockerfile WHEN built THEN `postgresql-16-postgis-3` is installed
- GIVEN the container WHEN started THEN `SELECT extname FROM pg_extension` includes `postgis` and `timescaledb`
- GIVEN the container WHEN started THEN migrations run automatically via `init.sh`

**Test Requirements:**

- [ ] Test: Dockerfile builds successfully
- [ ] Test: Both extensions are available after container starts

**Technical Notes:**

```dockerfile
FROM timescale/timescaledb-ha:pg16-latest
RUN apt-get update && apt-get install -y postgresql-16-postgis-3 && rm -rf /var/lib/apt/lists/*
COPY migrations/ /docker-entrypoint-initdb.d/migrations/
COPY init.sh /docker-entrypoint-initdb.d/
```

`init.sh` iterates over migration files in order and executes them.

---

### Story 2: Core Schema Migration (001)

**As a** developer
**I want to** create all database tables with correct types and constraints
**So that** services can store vessel positions, profiles, anomalies, SAR detections, GFW events, and enrichment data

**Acceptance Criteria:**

- GIVEN migration 001 WHEN executed THEN these extensions exist: `postgis`, `timescaledb`
- GIVEN migration 001 WHEN executed THEN enum types exist: `risk_tier` (green/yellow/red), `anomaly_severity` (critical/high/moderate/low), `pi_tier` (ig_member/non_ig_western/russian_state/unknown/fraudulent/none)
- GIVEN migration 001 WHEN executed THEN `vessel_positions` table exists with columns: timestamp (TIMESTAMPTZ NOT NULL), mmsi (INTEGER NOT NULL), position (GEOGRAPHY POINT 4326 NOT NULL), sog, cog, heading, nav_status, rot, draught (all REAL)
- GIVEN migration 001 WHEN executed THEN `vessel_profiles` table exists with mmsi as PK, all specified columns, and correct defaults (risk_score=0, risk_tier='green', sanctions_status='{}', etc.)
- GIVEN migration 001 WHEN executed THEN `anomaly_events` table exists with FK to vessel_profiles(mmsi)
- GIVEN migration 001 WHEN executed THEN `sar_detections` table exists with FK to vessel_profiles(mmsi), including GFW-sourced columns: gfw_detection_id (TEXT UNIQUE), matching_score (REAL), fishing_score (REAL)
- GIVEN migration 001 WHEN executed THEN `gfw_events` table exists with columns: id (SERIAL PK), gfw_event_id (TEXT UNIQUE NOT NULL), event_type (TEXT NOT NULL — one of: AIS_DISABLING, ENCOUNTER, LOITERING, PORT_VISIT), mmsi (INTEGER FK to vessel_profiles), start_time (TIMESTAMPTZ NOT NULL), end_time (TIMESTAMPTZ), lat (DOUBLE PRECISION), lon (DOUBLE PRECISION), details (JSONB DEFAULT '{}'), encounter_mmsi (INTEGER), port_name (TEXT), ingested_at (TIMESTAMPTZ DEFAULT NOW())
- GIVEN migration 001 WHEN executed THEN `manual_enrichment` table exists with FK to vessel_profiles(mmsi)
- GIVEN migration 001 WHEN executed THEN `watchlist` table exists with PK FK to vessel_profiles(mmsi)
- GIVEN migration 001 WHEN executed THEN `zones` table exists with GEOGRAPHY POLYGON column

**Test Requirements:**

- [ ] Test: Migration SQL executes without errors on a fresh database
- [ ] Test: All tables exist with correct column types (check via `information_schema.columns`)
- [ ] Test: Foreign key constraints are properly defined
- [ ] Test: Default values are correct for all columns that have them

**Technical Notes:**

Full SQL is specified in the build spec. Use `CREATE EXTENSION IF NOT EXISTS` for idempotency. All JSONB columns default to `'{}'` or `'[]'`.

---

### Story 3: TimescaleDB Setup Migration (002)

**As a** developer
**I want to** convert vessel_positions to a hypertable with compression and retention policies
**So that** time-series data is efficiently stored and automatically managed

**Acceptance Criteria:**

- GIVEN migration 002 WHEN executed THEN `vessel_positions` is a hypertable with 7-day chunks
- GIVEN migration 002 WHEN executed THEN compression is configured: segment by mmsi, order by timestamp DESC
- GIVEN migration 002 WHEN executed THEN compression policy compresses chunks older than 30 days
- GIVEN migration 002 WHEN executed THEN retention policy drops chunks older than 365 days
- GIVEN migration 002 WHEN executed THEN `vessel_hourly` continuous aggregate exists with hourly bucketing by mmsi

**Test Requirements:**

- [ ] Test: `vessel_positions` appears in `timescaledb_information.hypertables`
- [ ] Test: Compression and retention policies are configured

**Technical Notes:**

Continuous aggregate includes: time_bucket('1 hour'), mmsi, AVG(sog), MAX(sog), AVG(draught), COUNT(*), ST_Collect(position::geometry) AS track. Refresh policy: start_offset 2 hours, end_offset 1 hour, schedule 1 hour.

---

### Story 4: Index Migration (003)

**As a** developer
**I want to** create performance indexes for all query patterns
**So that** API queries and scoring lookups are fast

**Acceptance Criteria:**

- GIVEN migration 003 WHEN executed THEN `idx_positions_mmsi` exists on vessel_positions(mmsi, timestamp DESC)
- GIVEN migration 003 WHEN executed THEN `idx_positions_geo` GIST index exists on vessel_positions(position)
- GIVEN migration 003 WHEN executed THEN `idx_profiles_imo`, `idx_profiles_risk`, `idx_profiles_type`, `idx_profiles_sanctions` indexes exist
- GIVEN migration 003 WHEN executed THEN `idx_anomalies_vessel`, `idx_anomalies_severity`, `idx_anomalies_unresolved` (partial) indexes exist
- GIVEN migration 003 WHEN executed THEN `idx_sar_geo` GIST and `idx_sar_dark` (partial) indexes exist on sar_detections
- GIVEN migration 003 WHEN executed THEN `idx_gfw_events_mmsi` (mmsi, start_time DESC), `idx_gfw_events_type` (event_type), and UNIQUE constraint on gfw_event_id exist on gfw_events
- GIVEN migration 003 WHEN executed THEN `idx_zones_geo` GIST and `idx_zones_type` indexes exist

**Test Requirements:**

- [ ] Test: All named indexes exist in `pg_indexes`
- [ ] Test: Partial indexes have correct WHERE clauses

**Technical Notes:**

`idx_profiles_sanctions` uses GIN for JSONB. `idx_anomalies_unresolved` is a partial index WHERE `resolved = FALSE`. `idx_sar_dark` is partial WHERE `is_dark = TRUE`.

---

### Story 5: Seed Data Migration (004)

**As a** developer
**I want to** load reference geographic data (STS zones, Russian terminals) into the zones table
**So that** scoring rules can use PostGIS spatial queries against known locations

**Acceptance Criteria:**

- GIVEN migration 004 WHEN executed THEN 6 STS zones exist in zones table with zone_type='sts_zone': Malta OPL, Augusta, Lomé, Kalamata, Ceuta, Yeosu
- GIVEN migration 004 WHEN executed THEN 7 Russian terminals exist with zone_type='terminal': Ust-Luga, Primorsk, Novorossiysk, Kozmino, Murmansk, Taman, Vysotsk
- GIVEN each zone WHEN queried THEN its geometry is a valid PostGIS POLYGON
- GIVEN each zone WHEN queried THEN ST_IsValid(geometry::geometry) returns TRUE

**Test Requirements:**

- [ ] Test: `SELECT COUNT(*) FROM zones WHERE zone_type='sts_zone'` returns 6
- [ ] Test: `SELECT COUNT(*) FROM zones WHERE zone_type='terminal'` returns 7
- [ ] Test: All geometries are valid polygons at the correct approximate locations

**Technical Notes:**

STS zone coordinates (SW, NE corners):
- Malta OPL: (35.5, 13.8) to (36.1, 14.8)
- Augusta: (36.9, 14.8) to (37.5, 15.6)
- Lomé: (5.7, 0.8) to (6.5, 1.8)
- Kalamata: (36.3, 22.0) to (37.1, 22.8)
- Ceuta: (35.6, -5.8) to (36.2, -4.8)
- Yeosu: (34.1, 127.2) to (34.9, 128.2)

Terminal coordinates (create ~5nm radius polygon approximation):
- Ust-Luga: 59.680, 28.400
- Primorsk: 60.350, 28.680
- Novorossiysk: 44.660, 37.810
- Kozmino: 42.730, 132.910
- Murmansk: 68.970, 33.080
- Taman: 45.220, 36.620
- Vysotsk: 60.630, 28.570

---

## Technical Design

### Data Model Changes

Creates the entire database schema (all tables, types, indexes, policies, seed data).

### API Changes

None.

### Dependencies

- TimescaleDB HA image (pg16-latest)
- PostGIS 3

### Security Considerations

- Database credentials via environment variables only
- No default superuser — uses dedicated `heimdal` user

---

## Implementation Order

### Group 1 (sequential — migrations must be ordered)
- Story 1 — Dockerfile and init.sh
- Story 2 — Migration 001 (schema)
- Story 3 — Migration 002 (TimescaleDB)
- Story 4 — Migration 003 (indexes)
- Story 5 — Migration 004 (seed data)

**Note:** While migrations are sequential files, they can be written in parallel since they don't share code — just ensure file naming order is correct.

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] PostgreSQL container builds and starts
- [ ] Both extensions (PostGIS, TimescaleDB) are active
- [ ] All tables created with correct schema
- [ ] Hypertable, compression, and retention policies active
- [ ] All indexes created
- [ ] Seed data loaded (6 STS zones, 7 terminals)
- [ ] Code committed with proper messages
- [ ] Ready for human review
