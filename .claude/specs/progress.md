# Progress

This file is the implementation scratchpad. Read it at the start of every session. Update it after every completed story. It survives context resets and session changes.

## Current Feature

**Spec:** Wave Plan — 16 specs across 7 waves (GFW Integration)
**Branch:** feature/wave-4-intelligence
**Status:** Wave 4 complete, ready for Wave 5

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
- Story 4: constants.py — MID_TO_FLAG (289 entries), MAX_PER_RULE (14 rules), SEVERITY_POINTS
- Story 1: Pydantic models — vessel, ais_message, anomaly, enrichment, sar, gfw_event (all with validators)
- Story 2: DB layer — async SQLAlchemy engine/session, repository functions for all 6 tables
- Also: requirements-base.txt, 80 tests all passing
- Commit: `aef222a`

### 04-ais-ingest (all 6 stories)
- Story 2: AIS message parser — parses PositionReport and ShipStaticData from aisstream.io JSON, sentinel value handling (SOG 102.3, COG 360, heading 511, ROT -128 → None), validation via Pydantic
- Story 4: Redis deduplication — SET NX EX 10, key format `heimdal:dedup:{mmsi}:{ts}`
- Story 5: Metrics publisher — ingest_rate (60s rolling), last_message_at, total_vessels in Redis
- Story 3: Batch writer — asyncpg executemany with PostGIS ST_MakePoint, periodic + size-based flush, vessel profile upserts, Redis publish on flush
- Story 1: WebSocket connection — persistent auto-reconnecting to aisstream.io, exponential backoff 1s-60s, stale connection detection at 120s
- Story 6: Dockerfile — Python 3.12-slim, asyncpg + websockets deps
- Tests: 97 backend tests (56 parser + 9 dedup + 9 metrics + 14 websocket + 9 writer)
- Commits: `59580e8`, `6530188`, `f49895c`

### 05-frontend-shell (all 6 stories)
- Story 1: Vite + React 18 + TypeScript 5 project with CesiumJS 1.115+, Resium, Zustand 4, TanStack Query 5, Tailwind CSS v4, date-fns 3
- Story 3: TypeScript interfaces (VesselState, AnomalyEvent, PaginatedResponse, VesselDetail, TrackPoint), Zustand store skeleton (vessels Map, selectedMmsi, filters, actions)
- Story 6: Risk colors (green/yellow/red hex), formatters (DMS coords, speed, course, timestamps), STS zones GeoJSON (6 zones), terminals GeoJSON (7 Russian terminals), vessel SVG icons
- Story 2: CesiumJS GlobeView component — Resium Viewer, Norwegian EEZ camera (lat 68, lon 15, 5000km), all widgets disabled, real-time mode
- Story 4: App layout — dark theme, header bar, full-height globe, hidden vessel panel slot, QueryClientProvider
- Story 5: Dockerfile — multi-stage (node:20-alpine build → nginx:alpine serve), nginx.conf with SPA fallback, /api/ and /ws/ proxy, Cesium asset caching
- Tests: 28 frontend tests (5 store + 20 utils + 2 globe + 1 app)
- Commits: `5aad300`, `f4011b0`, `71f2016`

### 06-api-server (all 8 stories)
- Story 1: FastAPI app factory with lifespan (DB + Redis init/shutdown), Dockerfile, CORS middleware
- Story 6: Health endpoint (DB/Redis connectivity, AIS state, vessel/anomaly counts, 503 on failure), Stats endpoint (risk tier breakdown, anomalies by severity, dark ship count, ingestion rate, storage estimate)
- Story 2: Vessel REST endpoints — GET /api/vessels (paginated, filters: risk_tier, bbox, ship_type, sanctions_hit, active_since), GET /api/vessels/{mmsi} (full profile + anomaly count + latest enrichment), GET /api/vessels/{mmsi}/track (time range, ST_Simplify)
- Story 3: Anomaly REST endpoint — GET /api/anomalies (paginated, filters: severity, time range, bbox, resolved; JOIN with vessel_profiles for vessel_name and risk_tier)
- Story 4: SAR detections (GET /api/sar/detections with is_dark, bbox), GFW events (GET /api/gfw/events with event_type, mmsi, time range), Watchlist CRUD (GET/POST/DELETE /api/watchlist)
- Story 5: Enrichment POST — POST /api/vessels/{mmsi}/enrich (Pydantic validation, maps to manual_enrichment table, publishes re-scoring event to Redis)
- Story 7: WebSocket position streaming — /ws/positions with per-client subscription filters (bbox, risk_tiers, ship_types, mmsi_list) via Redis pub/sub
- Story 8: WebSocket alert streaming — /ws/alerts broadcasting risk_change and anomaly events from two Redis channels
- Tests: 110 api-server tests (8 app + 11 health + 17 vessels + 12 anomalies + 6 sar + 5 gfw + 7 watchlist + 7 enrichment + 26 ws_positions + 11 ws_alerts)
- Commits: `68da694`, `6825d0a`, `207af4e`

### 07-scoring-engine (all 14 stories)
- Story 1: Rule framework — abstract ScoringRule base class, engine with auto-discovery via pkgutil, Redis subscription on positions + enrichment_complete channels
- Story 2: Score aggregation — per-rule caps (MAX_PER_RULE), tier calculation (green <30, yellow 30-99, red 100+), Redis publishing for tier changes + new anomalies, GFW dedup logic (suppresses real-time anomalies when GFW covers same behavior within ±6h window)
- Stories 3-7: GFW-sourced rules — gfw_ais_disabling (critical/high by location), gfw_encounter (STS zone or sanctioned partner), gfw_loitering (STS zone vs open ocean), gfw_port_visit (Russian terminals), gfw_dark_sar (SAR + AIS gap correlation)
- Stories 8-13: Realtime rules — ais_gap (with 24h cooldown), sts_proximity (slow speed + 6h duration), destination_spoof (placeholders/sea areas/frequency), draft_change (at-sea draught increase), flag_hopping (MID-based), sanctions_match (direct/fuzzy confidence), vessel_age (tankers), speed_anomaly (slow steaming/abrupt change), identity_mismatch (dimensions/flag)
- Story 14: Dockerfile + requirements.txt
- Shared: zone_helpers.py for PostGIS spatial queries
- Tests: 148 scoring tests (19 engine + 27 aggregator + 49 gfw_rules + 53 realtime_rules)
- Commits: `bd587a4`, `47ac217`, `c0984d4`, `5ee7a56`, `5054685`

### 08-enrichment-service (all 9 stories)
- Story 1: GFW API client — JWT auth with auto-refresh, rate limiting, exponential backoff retry on 429/5xx, offset + cursor pagination
- Stories 2-4: GFW data fetchers — SAR detections from 4Wings API, behavioral events from Events API (4 types), vessel identity from Vessel API with Redis caching
- Story 6: OpenSanctions bulk matching — IMO (1.0), MMSI (0.9), fuzzy name Levenshtein (0.7) confidence levels, NDJSON index loading
- Story 8: Flag state derivation — MID-to-flag lookup, multi-source flag comparison, flag_history tracking
- Story 7: GISIS/MARS optional lookups — stub clients with rate limiting, graceful failure, GFW priority merge
- Story 5: Service runner — 6-hour cycle loop, Redis-based enrichment tracking, pipeline orchestration (GFW → OpenSanctions → optional GISIS/MARS), batch processing, enrichment_complete publishing
- Story 9: Dockerfile + requirements.txt
- Also: download-opensanctions.sh script
- Tests: 192 enrichment tests (28 gfw_client + 17 sar + 26 events + 23 vessel + 30 sanctions + 30 flags + 18 gisis_mars + 20 runner)
- Commits: `f248903`, `3315335`, `3b699f9`, `0056364`, `5054685`

## Current Story

Wave 4 complete. Ready for Wave 5 (09-globe-rendering, 10-vessel-detail-panel, 11-controls-and-filtering).

## Known Issues

- Frontend build produces a large chunk (4.6MB) from CesiumJS — consider code-splitting in a future wave
- Minor warnings in ws_positions tests (unawaited coroutines from AsyncMock) — cosmetic only, all tests pass
- identity_mismatch rule added as 14th rule (spec originally said 13 but had 14 distinct rules)

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
- D10: Used asyncpg executemany (not COPY) for position inserts — PostGIS GEOGRAPHY type doesn't work with raw COPY protocol.
- D11: AIS ingest directory is `services/ais-ingest/` (hyphen) on disk; Python imports use sys.path manipulation.
- D12: Added identity_mismatch as 14th scoring rule (dimensions + flag mismatch detection).
- D13: Enrichment tracking uses Redis hash `heimdal:enriched` instead of DB column (avoids migration).
- D14: Flag history stored in vessel profile ownership_data JSONB (no schema migration needed).
- D15: GISIS/MARS implemented as stubs with proper interfaces — ready for real scraping later.

## Notes for Next Session

- Wave 4 is fully implemented and tested on branch `feature/wave-4-intelligence`
- Wave 5 can start: 09-globe-rendering, 10-vessel-detail-panel, 11-controls-and-filtering (parallel, frontend specs)
- Backend tests: 627 total (287 pre-Wave-4 + 148 scoring + 192 enrichment)
- Frontend tests: 28 total
- Scoring engine has 14 rules (5 GFW + 9 realtime) with zone_helpers for PostGIS spatial queries
- Enrichment service has full GFW integration, OpenSanctions matching, flag derivation, and GISIS/MARS stubs
- Both services have Dockerfiles and docker-compose entries
- All Docker images build configuration is complete
