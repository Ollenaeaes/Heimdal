# Progress

This file is the implementation scratchpad. Read it at the start of every session. Update it after every completed story. It survives context resets and session changes.

## Current Feature

**Spec:** Wave Plan — 16 specs across 7 waves (GFW Integration)
**Branch:** feature/wave-1-foundation
**Status:** Wave 1 complete, ready for Wave 2

## Stories Completed

### 01-infrastructure (all 3 stories)
- Story 3: Directory structure, .env.example, config.yaml — monorepo scaffolding
- Story 1: docker-compose.yml — 8 services with healthchecks, volume mounts, named volumes
- Story 2: Makefile — 12 targets (up, down, reset, logs, migrate, test, shell-db, shell-api, etc.)
- Also: .gitignore
- Commit: `262dfa5`

### 02-database (all 5 stories)
- Story 1: PostgreSQL Dockerfile (timescaledb-ha:pg16 + postgis-3) + init.sh
- Story 2: Migration 001 — schema (8 tables, 3 enums, gfw_events table)
- Story 3: Migration 002 — TimescaleDB hypertable, compression, retention, continuous aggregate
- Story 4: Migration 003 — 15 indexes (B-tree, GIST, GIN, partials)
- Story 5: Migration 004 — seed data (6 STS zones, 7 Russian terminals)
- Commit: `7bdb6f3`

### 03-shared-library (all 4 stories)
- Story 3: config.py — pydantic-settings + YAML merge, singleton settings
- Story 4: constants.py — MID_TO_FLAG (289 entries), MAX_PER_RULE (13 rules), SEVERITY_POINTS
- Story 1: Pydantic models — vessel, ais_message, anomaly, enrichment, sar, gfw_event (all with validators)
- Story 2: DB layer — async SQLAlchemy engine/session, repository functions for all 6 tables
- Also: requirements-base.txt, 80 tests all passing
- Commit: `aef222a`

## Current Story

Wave 1 complete. Ready for Wave 2 (04-ais-ingest, 05-frontend-shell).

## Known Issues

[none]

## Decisions Made

- D1: 7 waves with 16 specs total. Waves run sequentially, specs within each wave run in parallel.
- D2: Replaced custom SAR processor with GFW API consumption in enrichment service.
- D3: Eliminated Copernicus+CFAR — GFW provides ML-validated SAR detections via API.
- D4: No authentication for local deployment. Single-user workstation.
- D5: OpenSanctions via bulk download (free non-commercial), not API.
- D6: GFW APIs are the primary enrichment source. GISIS/MARS demoted to optional best-effort.
- D7: GFW-sourced rules have higher confidence than real-time rules. Dedup logic suppresses real-time when GFW covers same behavior.
- D8: ~3-5 day data delay for GFW data is acceptable (compensated by higher detection quality).
- D9: Removed obsolete `version: "3.8"` from docker-compose.yml (Compose V2 ignores it).

## Notes for Next Session

- Wave 1 is fully implemented and tested on branch `feature/wave-1-foundation`
- Wave 2 can start: 04-ais-ingest and 05-frontend-shell (parallel, depend on Wave 1)
- Each Wave 2 service needs its own Dockerfile and service-specific code
- The shared library, database, and infrastructure are ready for services to build on
