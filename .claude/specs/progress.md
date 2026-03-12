# Progress

This file is the implementation scratchpad. Read it at the start of every session. Update it after every completed story. It survives context resets and session changes.

## Current Feature

**Spec:** Wave Plan created with 16 specs across 7 waves (updated for GFW Integration)
**Branch:** claude/gifted-shaw
**Status:** Specs drafted + GFW Update 001 applied, awaiting approval

## GFW Integration Update (2026-03-12)

Applied Update 001: Replaced custom Copernicus SAR processor with Global Fishing Watch API integration.

**Key changes:**
- Removed `14-sar-processor` spec entirely (custom Copernicus+CFAR pipeline eliminated)
- Added GFW API client + GFW SAR/Events/Vessel fetching to `08-enrichment-service`
- Added 5 GFW-sourced scoring rules to `07-scoring-engine` (gfw_ais_disabling, gfw_encounter, gfw_loitering, gfw_port_visit, gfw_dark_sar)
- Downgraded real-time ais_gap rule (Critical→High, High→Moderate, Moderate→Low)
- Downgraded real-time sts_proximity rule (High→Moderate)
- Removed terminal_loading rule (replaced by gfw_port_visit)
- Added dedup logic: GFW rules suppress corresponding real-time rules
- Added `gfw_events` table to database schema
- Updated sar_detections table with GFW fields
- Renumbered specs: 15→14, 16→15, 17→16
- Replaced Copernicus registration with GFW registration in agent setup
- Total: 16 specs (was 17), 13 scoring rules (5 GFW + 8 realtime, was 10)

## Specs Created

All 16 specs + wave plan + agent prompt created and updated for GFW:

### Wave 1 — Foundation Infrastructure (parallel, no deps)
- [x] `01-infrastructure` — Docker Compose (6 services), Makefile, .env (GFW_API_TOKEN), config.yaml (gfw section)
- [x] `02-database` — PostgreSQL + PostGIS + TimescaleDB, migrations (incl. gfw_events table), seed data
- [x] `03-shared-library` — Pydantic models (incl. GFW event models), DB layer, config, constants

### Wave 2 — Data Pipeline (parallel, depends on Wave 1)
- [x] `04-ais-ingest` — WebSocket consumer, parser, batch writer, dedup, metrics
- [x] `05-frontend-shell` — Vite + React + CesiumJS, basic globe, app layout

### Wave 3 — API Layer (depends on Wave 2)
- [x] `06-api-server` — FastAPI REST + WebSocket, all endpoints (incl. GFW events)

### Wave 4 — Intelligence Layer (parallel, depends on Wave 3)
- [x] `07-scoring-engine` — 13 rules (5 GFW + 8 realtime), dedup logic, aggregation, tier calculation
- [x] `08-enrichment-service` — GFW API client (4Wings, Events, Vessel), OpenSanctions, optional GISIS/MARS

### Wave 5 — Frontend Features (parallel, depends on Waves 3-4)
- [x] `09-globe-rendering` — Vessel markers, clustering, overlays, track trails
- [x] `10-vessel-detail-panel` — Side panel with all sections
- [x] `11-controls-and-filtering` — Search, filters, stats bar, health

### Wave 6 — Advanced Features (parallel, depends on Wave 5)
- [x] `12-manual-enrichment` — Enrichment form, submission, history
- [x] `13-watchlist-notifications` — Watchlist CRUD, browser notifications

### Wave 7 — Polish (parallel, depends on Wave 6)
- [x] `14-sar-frontend` — GFW SAR markers, GFW event markers, dark ship filter
- [x] `15-stats-and-replay` — Stats dashboard, track replay (with GFW event overlay), dossier export
- [x] `16-testing-and-docs` — Test suite (incl. GFW tests), fixtures (incl. GFW fixtures), benchmarks, README

### Supporting
- [x] `wave-plan.md` — Overall wave plan with dependency diagram and interface contracts
- [x] `agent-api-key-setup.md` — Chrome agent prompt for API key registration (GFW replaces Copernicus)

## Stories Completed

[none yet — specs pending approval]

## Current Story

[none — waiting for spec approval]

## Known Issues

[none]

## Decisions Made

- D1: 7 waves with 16 specs total. Waves run sequentially, specs within each wave run in parallel.
- D2: ~~SAR processor is optional (Docker Compose profile).~~ **Replaced by GFW API consumption in enrichment service.**
- D3: ~~Using Python CFAR for SAR detection.~~ **Eliminated — GFW provides ML-validated SAR detections via API.**
- D4: No authentication for local deployment. Single-user workstation.
- D5: OpenSanctions via bulk download (free non-commercial), not API.
- D6: GFW APIs are the primary enrichment source. GISIS/MARS demoted to optional best-effort.
- D7: GFW-sourced rules have higher confidence than real-time rules. Dedup logic suppresses real-time when GFW covers same behavior.
- D8: ~3-5 day data delay for GFW data is acceptable (compensated by higher detection quality).

## Notes for Next Session

- All specs need human review and approval before implementation begins
- Start with Wave 1 (infrastructure, database, shared-library) — these are the foundation
- The API key registration agent can run in parallel with Wave 1
- GFW API token is now REQUIRED (not optional like Copernicus was)
