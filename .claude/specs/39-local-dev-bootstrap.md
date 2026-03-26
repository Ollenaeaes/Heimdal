# Feature Spec: Local Development Bootstrap & Data Sync

**Slug:** `local-dev-bootstrap`
**Created:** 2026-03-26
**Status:** completed
**Priority:** high
**Depends on:** Nothing — this is the foundation for testing all graph scoring specs locally.

---

## Overview

Set up a local development environment on the MacBook M4 that can run the full Heimdal stack with real production data. The local environment needs: 2 days of AIS position data, all vessel_profiles for vessels seen in those 2 days, all IACS data, and all Equasis data. This provides the base dataset for testing the graph scoring pipeline locally before deploying to the VPS.

## Problem Statement

The graph scoring overhaul (specs 40-43) is a major change that must be developed and validated locally before touching production. Currently `sync_dev_data.py` exists but may not cover all required data. The local environment needs to be self-contained with enough real data to exercise the full scoring pipeline.

## Out of Scope

- NOT: Paris MoU historical data (that's a separate batch job in spec 40)
- NOT: OpenSanctions ownership graph (spec 41 handles extraction)
- NOT: FalkorDB setup (spec 42)
- NOT: Network edges from the old system (being replaced)
- NOT: Production deployment

---

## User Stories

### Story 1: Local Docker Environment

**As a** developer
**I want to** spin up the full Heimdal stack locally with one command
**So that** I can develop and test the graph scoring pipeline

**Acceptance Criteria:**

- GIVEN a fresh clone WHEN I run `make dev-up` THEN PostgreSQL (TimescaleDB+PostGIS), Redis, and the API server start locally
- GIVEN the local stack WHEN postgres is ready THEN all migrations (001-023) are applied automatically
- GIVEN docker-compose.dev.yml WHEN it starts THEN it uses local volume mounts for code (hot-reload) and persistent pgdata volume
- GIVEN the local stack WHEN I run `make dev-down` THEN all containers stop cleanly and data persists in volumes

**Test Requirements:**

- [ ] Test: `make dev-up` brings up postgres, redis, api-server within 30 seconds
- [ ] Test: All 23 migrations apply without errors on a fresh database
- [ ] Test: `make dev-down && make dev-up` preserves data across restarts

**Technical Notes:**

- Check if `docker-compose.dev.yml` or dev overrides already exist — extend, don't duplicate
- Local postgres should have the same extensions as production (timescaledb, postgis)
- Use the same image: `timescaledb/timescaledb-ha:pg16`

---

### Story 2: Production Data Sync Script

**As a** developer
**I want to** fetch recent production data into my local database
**So that** I have realistic data to test scoring against

**Acceptance Criteria:**

- GIVEN `sync_dev_data.py` exists WHEN I run `python scripts/sync_dev_data.py --hours 48` THEN it fetches 2 days of AIS positions from the production database via SSH tunnel
- GIVEN the sync WHEN it completes THEN it also fetches all vessel_profiles for any MMSI that appears in the fetched positions
- GIVEN the sync WHEN run with `--with-iacs` THEN it fetches all rows from iacs_vessels_current and iacs_vessels_changes
- GIVEN the sync WHEN run with `--with-equasis` THEN it fetches all rows from equasis_data and equasis_company_uploads
- GIVEN a full local sync WHEN I run `python scripts/sync_dev_data.py --hours 48 --with-iacs --with-equasis` THEN all four data sets are synced in one command
- GIVEN the sync WHEN it encounters existing local data THEN it upserts (does not duplicate)

**Test Requirements:**

- [ ] Test: Sync fetches vessel_positions for the last 48 hours
- [ ] Test: Sync fetches vessel_profiles only for MMSIs present in the fetched positions
- [ ] Test: IACS sync fetches all iacs_vessels_current rows
- [ ] Test: Equasis sync fetches all equasis_data rows
- [ ] Test: Running sync twice does not create duplicates

**Technical Notes:**

- `sync_dev_data.py` already exists — read it first and extend rather than rewrite
- SSH tunnel connection details should come from `.env` or config
- Batch inserts for performance (vessel_positions can be millions of rows for 48h)
- Consider using COPY for bulk position data instead of INSERT

---

### Story 3: Local Dev Convenience Targets

**As a** developer
**I want to** have Makefile targets for common local development tasks
**So that** I don't have to remember complex commands

**Acceptance Criteria:**

- GIVEN the Makefile WHEN I run `make sync-data` THEN it runs the full sync (48h positions + profiles + IACS + equasis)
- GIVEN the Makefile WHEN I run `make dev-reset` THEN it drops and recreates the local database, applies migrations, and runs sync
- GIVEN the Makefile WHEN I run `make dev-shell` THEN it opens a psql shell to the local database
- GIVEN the Makefile WHEN I run `make dev-test` THEN it runs the test suite against the local database

**Test Requirements:**

- [ ] Test: `make sync-data` completes without errors when prod is reachable
- [ ] Test: `make dev-reset` results in a clean database with synced data
- [ ] Test: `make dev-shell` opens an interactive psql session

**Technical Notes:**

- Extend the existing Makefile — don't overwrite existing targets
- These targets should work independently of the VPS deployment targets

---

## Implementation Order

1. Story 1 (local Docker env) — foundation
2. Story 2 (data sync) — depends on story 1
3. Story 3 (Makefile targets) — depends on stories 1-2

Sequential execution — each story depends on the previous.

## Architecture Decisions

- **No new infrastructure** — this spec just sets up the local dev loop
- **Real production data** — not synthetic fixtures; the scoring pipeline needs realistic data
- **Persistent volumes** — local database survives container restarts
- **SSH tunnel for sync** — same approach as existing `sync_dev_data.py`
