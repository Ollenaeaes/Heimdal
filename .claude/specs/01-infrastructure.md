# Feature Spec: Project Infrastructure

**Slug:** `infrastructure`
**Created:** 2026-03-11
**Status:** completed
**Priority:** critical
**Wave:** 1 (Foundation)

---

## Overview

Set up the project root scaffolding: Docker Compose orchestration, Makefile developer interface, environment configuration, and YAML operational config. This is the foundation everything else builds on.

## Problem Statement

Every service in Heimdal runs as a Docker container. Without the orchestration layer, no service can start. The Makefile, .env, and config.yaml define the canonical developer interface.

## Out of Scope

- NOT: Database migrations or schema (see `02-database`)
- NOT: Shared Python library code (see `03-shared-library`)
- NOT: Individual service Dockerfiles (each service spec owns its own)
- NOT: Application code for any service

---

## User Stories

### Story 1: Docker Compose Configuration

**As a** developer
**I want to** run `docker compose up -d` and have all core containers start
**So that** the full platform is orchestrated from a single command

**Acceptance Criteria:**

- GIVEN a fresh clone WHEN I run `docker compose up -d` THEN postgres, redis, ais-ingest, scoring, enrichment, api-server, and frontend containers are defined (6 services + 2 infrastructure)
- GIVEN the compose file WHEN postgres starts THEN it uses a named volume `pgdata` for persistence
- GIVEN the compose file WHEN ais-ingest, scoring, enrichment, api-server start THEN they mount `./shared:/app/shared:ro` and `./config.yaml:/app/config.yaml:ro`
- GIVEN the compose file WHEN services depend on postgres/redis THEN they use `condition: service_healthy` with healthchecks

**Test Requirements:**

- [ ] Test: `docker-compose.yml` is valid YAML and passes `docker compose config` validation
- [ ] Test: All service definitions include correct environment variables, volumes, and dependency declarations

**Technical Notes:**

Docker Compose file uses version 3.8 format. Services:
- `postgres`: build from `./db`, env vars for DB credentials, healthcheck via `pg_isready`, port 5432
- `redis`: image `redis:7-alpine`, healthcheck via `redis-cli ping`
- `ais-ingest`: build `./services/ais-ingest`, depends on postgres+redis healthy, env: AIS_API_KEY, DATABASE_URL, REDIS_URL
- `scoring`: build `./services/scoring`, depends on postgres+redis healthy, env: DATABASE_URL, REDIS_URL
- `enrichment`: build `./services/enrichment`, depends on postgres healthy, env: DATABASE_URL, REDIS_URL, GFW_API_TOKEN, OPENSANCTIONS_DATA_PATH, additional volume `opensanctions-data`
- `api-server`: build `./services/api-server`, depends on postgres+redis healthy, env: DATABASE_URL, REDIS_URL
- `frontend`: build `./frontend`, depends on api-server, port mapping `${FRONTEND_PORT:-3000}:80`
- Volumes: `pgdata`, `opensanctions-data`

---

### Story 2: Makefile Developer Interface

**As a** developer
**I want to** use `make <target>` for all common operations
**So that** I don't need to remember Docker Compose incantations

**Acceptance Criteria:**

- GIVEN the Makefile WHEN I run `make help` THEN I see all targets with descriptions
- GIVEN the Makefile WHEN I run `make up` THEN `docker compose up -d` executes
- GIVEN the Makefile WHEN I run `make reset` THEN volumes are destroyed and containers rebuilt
- GIVEN the Makefile WHEN I run `make test` THEN tests run inside the api-server container
- GIVEN the Makefile WHEN I run `make shell-db` THEN I get a psql shell

**Test Requirements:**

- [ ] Test: Makefile contains all required targets: up, down, logs, logs-ingest, logs-scoring, reset, migrate, fetch-sanctions, test, shell-db, shell-api, help
- [ ] Test: `make help` outputs a formatted target list

**Technical Notes:**

Targets: up, down, logs, logs-ingest, logs-scoring, reset, migrate, fetch-sanctions, test, shell-db, shell-api. Default target is `help`. Self-documenting via grep pattern.

---

### Story 3: Environment Configuration

**As a** developer
**I want to** configure the platform via `.env` and `config.yaml`
**So that** I can customize behavior without editing code

**Acceptance Criteria:**

- GIVEN `.env.example` WHEN I copy it to `.env` THEN it documents all required and optional variables with defaults
- GIVEN `config.yaml` WHEN loaded THEN it contains sections for scoring, ingest, enrichment, gfw, retention, and frontend
- GIVEN the project root WHEN I look at directory structure THEN it matches the monorepo layout from the build spec

**Test Requirements:**

- [ ] Test: `.env.example` contains all required keys with documentation comments
- [ ] Test: `config.yaml` is valid YAML with all config sections

**Technical Notes:**

`.env.example` keys: AIS_API_KEY (required), DB_PASSWORD (default: heimdal_dev), DB_PORT (default: 5432), FRONTEND_PORT (default: 3000), CESIUM_ION_TOKEN, GFW_API_TOKEN (required for enrichment), ENRICHMENT_INTERVAL (default: 6), GFW_EVENTS_LOOKBACK_DAYS (default: 30), AIS_BOUNDING_BOXES (default: worldwide), AIS_SHIP_TYPES.

`config.yaml` sections: scoring (thresholds, rule configs), ingest (batch_size, flush_interval, reconnect), enrichment (rate limits, fuzzy threshold), gfw (base_url, rate_limit_per_second, events_lookback_days, sar_lookback_days, vessel_cache_ttl_hours), retention (positions_days, compression), frontend (initial_camera, track_trail_hours, cluster_pixel_range).

Create the full directory structure (empty directories with .gitkeep where needed):
```
heimdal/
├── docker-compose.yml
├── .env.example
├── config.yaml
├── Makefile
├── shared/
│   ├── models/
│   ├── db/
│   ├── config.py
│   └── constants.py
├── services/
│   ├── ais-ingest/
│   ├── scoring/
│   ├── enrichment/
│   └── api-server/
├── frontend/
├── db/
│   └── migrations/
├── scripts/
└── tests/
    └── fixtures/
```

---

## Technical Design

### Data Model Changes

None — this spec creates no database objects.

### API Changes

None.

### Dependencies

- Docker Engine 24+ with Compose v2
- GNU Make

### Security Considerations

- `.env` must be in `.gitignore` (only `.env.example` is committed)
- Database password defaults to `heimdal_dev` for local development only
- API keys are environment variables, never hardcoded

---

## Implementation Order

### Group 1 (parallel)
- Story 3 — creates directory structure, .env.example, config.yaml (root scaffolding)

### Group 2 (parallel — after Group 1)
- Story 1 — docker-compose.yml (references directory structure)
- Story 2 — Makefile (references docker-compose.yml targets)

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Directory structure matches build spec
- [ ] docker-compose.yml validates with `docker compose config`
- [ ] No regressions in existing tests
- [ ] Code committed with proper messages
- [ ] Ready for human review
