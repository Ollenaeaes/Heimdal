# Progress

This file is the implementation scratchpad. Read it at the start of every session. Update it after every completed story. It survives context resets and session changes.

## Notes for Next Session
- 39-local-dev-bootstrap: COMPLETED on feature/local-dev-bootstrap branch. Ready for human review.
- To use: `make dev-up` starts the stack, `make sync-data` pulls prod data, `make dev-reset` for clean slate.
- 36-spoofing-rethink: COMPLETED on feature/spoofing-rethink branch. Ready for human review.

### 39-local-dev-bootstrap (all 3 stories)
- Story 1: Fixed docker-compose.dev.yml — pgdata mount, Redis, auto-migration service
- Story 2: Extended sync_dev_data.py — added --with-iacs and --with-equasis flags
- Story 3: Makefile targets — dev-reset, dev-shell, dev-test, updated sync-data

## Current Feature

**Spec:** 42-graph-model-and-scoring
**Branch:** feat/signal-scoring-engine
**Status:** Story 6 completed

### 42-graph-model-and-scoring Story 6: Signal-Based Scoring Engine
- services/graph_builder/signal_scorer.py — SignalScorer class with evaluate_vessel(imo), evaluates A1-A11, B1-B7, C1-C5 signals from PostgreSQL, loads D signals from vessel_signals table
- services/graph_builder/score_calculator.py — pure function compute_score(signals, is_sanctioned) with classification thresholds (0-3 green, 4-5 yellow, 6-8 red, >=9 red) and override rules
- Old scoring rules moved to services/scoring/rules/legacy/ (git mv, not deleted)
- A10 and B4 are stubs (will be implemented in Story 7)
- Signal dataclass: signal_id, weight, details, source_data
- Constants: IACS_MEMBERS, PERMISSIVE_FLAG_STATES, HIGH_RISK_JURISDICTIONS
- 39 tests all passing (17 score_calculator + 11 signal evaluator + 4 helpers + 7 integration)

### 42-graph-model-and-scoring Story 5: Geographic Inference Engine
- Migration 026_vessel_signals.sql — vessel_signals table with dedup index
- services/geographic_inference/engine.py — GeographicInference class with evaluate_vessel(mmsi)
- Signals implemented: D1 (GoF loiter), D2 (Kola loiter), D3 (Baltic transit), D4 (Barents transit), D5 (MMSI/flag mismatch), D6 (STS with blacklisted), D7 (loiter-then-vanish)
- Geographic zones defined as WKT polygon constants (GoF approaches, Kola Bay, Baltic corridor, Barents corridor, non-Russian Baltic terminals, Melkøya)
- Uses sync psycopg2 pattern (same as graph_builder)
- 15 tests all passing

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

### 09-globe-rendering (all 5 stories)
- Story 1: WebSocket connection — useWebSocket hook with auto-reconnect (1s-60s exponential backoff), filter-based subscription, store integration
- Story 4: Geographic overlays — STS zones (6 amber polygons), Russian terminals (7 red markers), Norwegian EEZ (blue dashed polyline), toggle controls
- Story 2: Vessel markers — risk-tier colored billboards (green/yellow/red with opacity+scale), COG rotation, click-to-select, red pulsing effect
- Story 5: Track trails — position history ring buffer (500/vessel) in Zustand store, fading polylines colored by risk tier
- Story 3: Entity clustering — Cesium EntityCluster (50px range), highest-risk-tier color inheritance, count labels
- Integration: GlobeView updated with all components + overlay toggles
- Tests: 60 new (11 ws + 11 overlays + 18 markers + 13 trails + 10 cluster) = 91 total frontend
- Commits: `a365817`, `f0e3662`, `af0986b`, `02b5469`, `f07e9ec`

### 10-vessel-detail-panel (all 6 stories)
- Story 1: Panel container — 420px slide-in from right, close button, loading skeleton, TanStack Query data fetch
- Story 2: Identity section — vessel name, IMO, MMSI, flag emoji, risk tier badge, ship type labels, dimensions
- Story 3: Status section — real-time position/SOG/COG/heading from WebSocket store, nav status labels, fallback to API
- Story 4: Risk section — score bar (0-200 gradient), unresolved anomaly cards with rule names, severity colors
- Story 5: Voyage timeline — 7-day horizontal scrollable timeline, color-coded anomaly markers (ais=red, sts=amber, port=blue)
- Story 6: Sanctions + Ownership — sanctions match cards with confidence %, ownership chain display, empty states
- Supporting utils: shipTypes.ts, flagEmoji.ts, navStatus.ts, ruleNames.ts, severityColors.ts
- Tests: 97 panel tests
- Commits: `104fa38`, `1c930bc`, `0cd30f4`, `e6dd71b`

### 11-controls-and-filtering (all 6 stories)
- Story 1: Search bar — debounced (300ms) autocomplete, MMSI/IMO pattern detection, TanStack Query
- Story 2: Risk tier filter — three color toggles with live vessel counts, Zustand filter integration
- Story 3: Type filter — dropdown (All/Tankers/Cargo/Passenger), ship type code ranges
- Story 4: Time range filter — preset buttons (1h/6h/24h/7d/All), date-fns calculations, activeSince filter
- Story 5: Stats bar — polled every 30s, total vessels, tier counts, anomalies, ingestion rate
- Story 6: Health indicator — polled every 60s, green/yellow/red dot, AIS staleness detection (2min threshold)
- Tests: 38 control tests (18 + 20)
- Commits: `928add3`, `ebfa218`

### 12-manual-enrichment (all 3 stories)
- Story 1: EnrichmentForm UI — collapsible section with all fields (source dropdown, ownership, P&I insurer+tier, classification+IACS, PSC detentions/deficiencies, notes)
- Story 2: Form submission — TanStack Query useMutation, success/error toast notifications (3s auto-dismiss), query invalidation, loading state
- Story 3: Enrichment history — collapsible cards sorted newest-first, empty state message
- Supporting: ManualEnrichmentRecord type, EnrichmentPayload type, updated VesselDetail with manualEnrichments array
- Tests: 29 enrichment tests
- Commits: `5a4c10b`

### 13-watchlist-notifications (all 3 stories)
- Story 1: Watchlist store (Zustand) + TanStack Query mutations with optimistic updates, Watch/Unwatch toggle button in vessel panel header
- Story 2: WatchlistPanel dropdown in app header — watched vessels with name, risk tier dot, time-ago, click-to-select
- Story 3: Browser desktop notifications via alert WebSocket — risk_change and anomaly events for watched vessels, notification click focuses app and selects vessel
- Halo indicator on globe for watchlisted vessel markers (semi-transparent white circle billboard)
- Tests: 20 watchlist tests
- Commits: `165ff4a`

### 16-testing-and-docs (all 5 stories)
- Story 2: Test fixtures — enhanced AIS messages (28 valid position reports with shadow fleet MMSIs), plus 4 new fixture files: OpenSanctions NDJSON (10+5), vessel profiles (green/yellow/red), GFW events (all 4 types), SAR detections (dark+matched)
- Story 5: README.md — project overview, architecture diagram, prerequisites, installation, first-run walkthrough, configuration reference, API endpoints, scoring rules, troubleshooting
- Story 1: Fixture validation tests — 36 tests validating all fixture files parse to Pydantic models, structural integrity, shadow fleet coverage
- Story 3: Integration tests — 28 tests in tests/integration/ (pipeline, WebSocket delivery, enrichment pipeline, GFW scoring); auto-skip when Docker not running
- Story 4: Performance benchmarks — scripts/benchmark.py with ingest throughput (474K msg/sec), scoring latency (0.3ms p99), API response benchmarks
- Tests: 323 backend unit tests + 28 integration (skipped without Docker)
- Commits: `034fb09`, `895d24c`, `0d241b2`

### 14-sar-frontend (all 3 stories)
- Story 1: SAR detection markers — TanStack Query polling (5min), dark ship pulsing animation (white+red border), matched detections (gray), click popup with detection details
- Story 2: GFW event markers — color-coded by type (orange diamond=encounter, yellow circle=loitering, red triangle=AIS-disabling, blue square=port visit), click popup with event-specific details, per-type filtering
- Story 3: Dark ship filter — darkShipsOnly toggle in Zustand store, integrated with SAR marker layer and overlay controls
- New files: SarMarkers.tsx, GfwEventMarkers.tsx, eventIcons.ts, sarMarkers.test.ts, gfwEventMarkers.test.ts
- Updated: Overlays.tsx (SAR+GFW toggles), GlobeView.tsx, useVesselStore.ts (new filter fields), api.ts (SAR+GFW types)
- Tests: 27 new (13 SAR + 14 GFW)
- Commit: `5755f53`

### 15-stats-and-replay (all 3 stories)
- Story 1: Enhanced stats dashboard — expandable StatsBar with CSS bar charts for risk tiers, severity breakdown, GFW events by type
- Story 2: Track replay — play/pause/scrub controls, speed selector (0.5x-10x), AIS gap segments in red, GFW event markers on timeline, globe polyline+animated marker via ReplayOverlay
- Story 3: Vessel dossier export — JSON export with vessel profile, anomalies, GFW events, track, sanctions, enrichment; download as heimdal-dossier-{mmsi}-{date}.json
- New files: TrackReplay.tsx, DossierExport.tsx, ReplayOverlay.tsx, useTrackReplay.ts, useReplayStore.ts
- Tests: 52 new (15 stats + 20 replay + 17 export)
- Commit: `3356dbe`

### 17-event-scoring-model (all 6 stories)
- Story 1: Event lifecycle — migration 006 adds event_start/event_end/event_state to anomaly_events, Pydantic model updated
- Story 2: Port awareness — migration 007 creates ports table with 51 global tanker ports, is_near_port() via PostGIS ST_DWithin
- Story 3: Event boundaries — check_event_ended() for 5 realtime rules (speed_anomaly, sts_proximity, draft_change, destination_spoof, ais_gap)
- Story 4: Repeat event escalation — multipliers [1.0, 1.5, 2.0] with 30-day decay window in engine._create_anomaly()
- Story 5: GFW multi-event handling — evaluate_all() override for all 5 GFW rules, shared gfw_helpers.py with temporal dedup
- Story 6: Engine lifecycle loop — _check_and_end_active_events() at start of evaluate_realtime, aggregate_score filters by event_state
- Tests: 105 new tests
- Commits: `7e00ada`, `f0677d8`, `b76160d`, `a14f609`

### 18-enhanced-detection-rules (all 6 stories)
- Story 1: AIS spoofing rule — 4 patterns (position_jump, circle_spoofing, anchor_spoofing, slow_roll), all severity=critical, 30pts
- Story 2: Ownership risk rule — single-vessel company, recent incorporation, high-risk jurisdiction, frequent changes, opaque ownership
- Story 3: Insurance/classification risk — no IG P&I, non-IACS class, unclassed, Russian Maritime Register, recent class change, IACS fuzzy matching
- Story 4: Voyage pattern analysis — full_evasion_route (25pts), russian_port_to_sts (15pts), sts_to_destination (8pts), suspicious_ballast (8pts)
- Story 5: Extended STS hotspots — migration 008 adds 6 new zones (South China Sea, Gulf of Oman, Singapore Strait, Alboran Sea, Baltic/Primorsk, South of Crete)
- Story 6: Weight rebalancing — speed_anomaly 15→10, vessel_age/flag progressive scoring, new rule caps, fixed all pre-existing test failures
- Tests: 82 new tests
- Commits: `d1e4344`, `8fbaace`, `65b4f30`

### 19-logging-observability (all 5 stories)
- Story 1: Structured JSON logging — shared/logging.py with JsonFormatter, setup_logging() replaces basicConfig in all services, LOG_FORMAT/LOG_LEVEL env vars
- Story 2: API call duration tracking — GFW client timing with threshold-based WARNING/ERROR, call stats (count/duration/retries), enrichment cycle summary
- Story 3: Service heartbeats — shared/heartbeat.py HeartbeatPublisher class, Redis keys with TTL 120s, health endpoint reports healthy/degraded/down per service
- Story 4: Scoring pipeline performance — per-rule timing with slow_rule WARNING (>100ms), per-vessel summary, aggregate_score query timing, exception context
- Story 5: Database query performance — SQLAlchemy event listeners for query timing (WARNING >500ms, ERROR >5s), pool exhaustion logging, API request duration middleware
- Tests: 56 new tests
- Commits: `1b59be3`, `5041c60`, `79338ae`, `a10177a`, `253d916`

### 21-performance-optimization Story 1: CPU Profiling and Bottleneck Identification
- Profiling scripts: scripts/profile_scoring.py (aggregation + rule discovery), scripts/profile_ingest.py (parsing + JSON)
- Performance documentation: docs/PERFORMANCE.md with 6 prioritized bottlenecks, memory targets, next steps
- Tests: 10 new tests in tests/test_profiling_scripts.py (import checks, function existence, PERFORMANCE.md content)
- Key finding confirmed by profiling: json.loads inside aggregate_score consumes ~46% of scoring CPU time (5M calls for 10K iterations)
- Rule discovery overhead is minimal (~0.6s for 100 iterations, 19 rules discovered)

### 21-performance-optimization Story 2: Scoring Engine Debounce and Batching
- ScoringDebouncer class in services/scoring/debouncer.py — asyncio-based debounce with per-vessel timers
- New vessel → immediate evaluation; subsequent positions → debounced (timer resets on each new position)
- Red-tier vessels use shorter debounce (30s vs 60s default), configurable via config.yaml scoring.debounce section
- ScoringDebounceConfig added to shared/config.py, config.yaml updated with debounce settings
- main.py updated: positions channel uses debouncer.on_position(), enrichment channel evaluates immediately (no debounce)
- Concurrency limited via asyncio.Semaphore (max_concurrent configurable)
- shutdown() for clean timer cancellation on service stop
- Tests: 11 new tests in test_debounce.py; 415 total scoring tests pass

### 21-performance-optimization Story 3: Database Query Optimization
- aggregate_score_sql() in shared/db/repositories.py — SQL-based score aggregation with per-rule caps and escalation multiplier, equivalent to Python aggregate_score()
- list_anomalies_with_vessel() — JOIN-based anomaly listing with vessel_profiles (avoids N+1 queries)
- count_anomaly_events() — efficient count with optional severity/resolved filters
- Tests: 30 new tests in tests/test_db_optimization.py (8 SQL verification + 10 Python equivalence + 7 JOIN query + 6 count)
- All 415 existing scoring tests still pass

### 21-performance-optimization Story 5: Frontend Bundle Optimization
- Lazy-loaded GlobeView and VesselPanel via React.lazy() + Suspense in App.tsx
- Extracted getCesiumViewer + constants into cesiumViewer.ts to break static import chain (SearchBar, useOverlays no longer force GlobeView into main chunk)
- Added default exports to GlobeView.tsx and VesselPanel.tsx (keeping named exports for backward compat)
- Configured manual chunks in vite.config.ts (cesium+resium → separate chunk)
- Build now produces 4 chunks: index (254KB), cesium (60KB), VesselPanel (46KB), GlobeView (10KB)
- All 315 passing tests remain passing; 8 pre-existing failures unchanged
- Files changed: App.tsx, GlobeView.tsx, VesselPanel.tsx, vite.config.ts, SearchBar.tsx, useOverlays.ts, Globe/index.ts
- New file: cesiumViewer.ts

### 21-performance-optimization Story 6: Memory Usage Optimization
- Memory profiling script: scripts/profile_memory.py using tracemalloc
- Profiles: scoring engine (10K vessels), ingest buffer (500 positions), frontend store estimate (10K vessels)
- Results: scoring ~24 MB (target <200 MB), ingest ~0.2 MB (target <10 MB), frontend ~4.4 MB (target <100 MB)
- All targets met by large margins — no code changes needed
- OpenSanctions index documented as streaming (no full in-memory load)
- docs/PERFORMANCE.md updated with Memory Profiling Results section
- Tests: 8 new tests in tests/test_memory_optimization.py

### 23-infrastructure-protection-backend (all 6 stories)
- Story 1: DB migration 011_infrastructure_tables.sql — infrastructure_routes (LINESTRING + GIST) + infrastructure_events (FK + composite index)
- Story 2: Data loading script scripts/load_infrastructure.py + sample GeoJSON (5 Baltic Sea routes: NordBalt, EstLink 2, C-Lion1, Balticconnector, Nord Stream)
- Story 3: infra_helpers.py — is_in_infrastructure_corridor(), compute_cable_bearing(), angle_difference(), is_in_port_approach()
- Story 4: cable_slow_transit rule — SOG<7kt in corridor >30min (high/40pts), >60min (critical/100pts), +40pts shadow fleet escalation
- Story 5: cable_alignment rule — COG parallel to cable bearing within 20° for >15min, hysteresis reset at 30°
- Story 6: infra_speed_anomaly rule — >50% SOG drop vs 2h average near infrastructure (moderate/15pts)
- Tests: 92 new tests
- Commit: `c09df94`

### 24-spoofing-detection-backend (all 8 stories)
- Stories 1-2: DB migration 012_spoofing_tables.sql — land_mask (MULTIPOLYGON + GIST) + gnss_interference_zones (POLYGON + GIST + expires_at index)
- Story 1b: Land mask loading script + test GeoJSON fixture (Germany + France polygons)
- Story 3: spoof_land_position — ST_Intersects with 100m buffer exclusion, single=moderate/15pts, 3+ consecutive=critical/100pts
- Story 4: spoof_impossible_speed — ship-type thresholds (tanker 27kn, container 37.5kn, etc.), single=high/40pts, 2+ in 24h=critical/100pts
- Story 5: spoof_duplicate_mmsi — Redis last_pos tracking, same MMSI >10nm apart <5min = critical/100pts
- Story 6: spoof_frozen_position — identical coords >2h (high/40pts), box pattern 2-4 pairs >1h (high/40pts)
- Story 7: spoof_identity_mismatch — zombie vessel (critical/100pts), dimension >20% (high/40pts), flag-MID mismatch (high/40pts)
- Story 8: gnss_clustering.py — 3+ spoof events within 20nm/1h creates convex hull zone, 24h refresh
- Tests: 97 new tests
- Commit: `5c3aa29`

### 25-network-mapping-backend (all 7 stories)
- Story 1: DB migration 013_network_edges.sql — network_edges table (UNIQUE on vessel_a/b + type, MMSI normalization), vessel_profiles.network_score column
- Story 2: shared/db/network_repository.py — upsert_network_edge(), get_vessel_network(), get_connected_vessels(), get_network_cluster() (BFS max 5 hops)
- Story 3: Encounter edge creation — from GFW encounter events, confidence=1.0
- Story 4: Proximity edge creation — STS zone co-occurrence within ±24h, confidence=0.7
- Story 5: Ownership edge creation — shared registered_owner or commercial_manager, case-insensitive
- Story 6: Network scorer — BFS hop-decay (30/15/5 pts at 1/2/3+ hops from sanctioned), pattern bonus (20pts/vessel for 3+ vessel Russian+STS clusters)
- Story 7: API endpoints — GET /api/vessels/{mmsi}/network (depth 1-3), GET /api/network/clusters
- Tests: 59 new tests
- Commit: `ed68a36`

### 29-operations-centre-theme (all 7 stories)
- Story 1: Theme Foundation — Inter + JetBrains Mono fonts, CSS @theme variables (heimdal-bg/panel/border/accent/infra/sar), updated risk colors (green=#22C55E, amber=#F59E0B, red=#EF4444), updated severity palette
- Story 2: Globe Styling — dark navy ocean (#0A1628), fog density 0.0003, atmosphere brightness -0.4, scene background #0A0E17, Earth at Night imagery with fallback
- Story 3: Vessel Markers — chevron/arrow shapes, green faded (0.3 opacity), yellow amber glow billboard, red pulse 1.0-1.15x at ~1Hz, selected vessel white ring, watchlist halo preserved
- Story 4: Track Trails — risk-tier-colored at 0.6 alpha, 4-tier width tapering (0.5-2px), dashed segments for AIS gaps >10min
- Story 5: HUD Top Bar — 40px ops-centre bar, small-caps HEIMDAL label, inline stats with monospace numbers, clickable tier filter counts, semi-transparent backdrop-blur
- Story 6: Side Panel Restyle — sharp corners, heimdal-panel/border colors, monospace data fields, "● RED — 140pts" risk badge, severity-colored anomaly left borders, collapsible sections, inline label-value layout, text loading state
- Story 7: Controls Restyle — all controls restyled with heimdal palette, sharp corners, backdrop-blur, accent blue active states, updated overlay toggles
- Tests: 16 new tests
- Commits: 8 commits on feature/operations-centre-theme branch

### 26-infrastructure-protection-frontend (all 4 stories)
- Story 1: InfrastructureOverlay.tsx — cable/pipeline polylines color-coded (telecom=blue, power=yellow, pipeline=orange), TanStack Query fetch
- Story 2: Point features — route start/end markers (cables size 8, pipelines size 10)
- Story 3: Risk halos — yellow/red vessels near routes get amber/red semi-transparent overlay segments
- Story 4: InfrastructurePanel.tsx — asset list + corridor alert feed, click-to-fly, empty state
- Backend: GET /api/infrastructure/routes (GeoJSON), GET /api/infrastructure/alerts
- Toggle: showInfrastructure in OverlayToggles with cyan accent
- Tests: 29 frontend + 6 backend
- Commit: `ca7d258`

### 27-spoofing-detection-frontend (all 3 stories)
- Story 1: Spoof marker styling — SPOOF_INDICATOR_IMAGE dashed circle overlay, spoofedMmsis Set in Zustand store
- Story 2: DuplicateMmsiLines.tsx — dashed polylines between conflicting positions with "Duplicate MMSI" label
- Story 3: GnssZoneOverlay.tsx — semi-transparent red polygons with opacity scaling (0.15-0.5 by affected_count)
- Backend: GET /api/gnss-zones (GeoJSON, non-expired only)
- Toggle: showGnssZones shared by GNSS zones + duplicate lines
- Tests: 29 frontend + 4 backend
- Commit: `ca7d258`

### 28-network-mapping-frontend (all 4 stories)
- Story 1: Network score display in RiskSection — "Network: 45 pts · Connected to 2 vessels" or "No connections"
- Story 2: NetworkGraph.tsx — d3-force SVG graph, depth selector (1/2/3), risk-colored nodes, edge labels, click-to-select
- Story 3: NetworkOverlay.tsx — globe network mode, encounter/proximity lines, connected vessel highlights
- Story 4: VesselChain.tsx — horizontal scrollable chain flow, port_visit → encounter → destination
- Toggle: showNetwork in OverlayToggles with purple accent
- Dependencies: d3-force, @types/d3-force
- Tests: 25 frontend tests
- Commit: `85034f9`

### 30-lookback-and-export (all 8 stories)
- Story 1: CollapsibleSection.tsx — shared wrapper, applied to all 11 VesselPanel sections below IdentitySection
- Story 2: LookbackSection.tsx — vessel search, date range picker, network toggle, start playback button
  - useLookbackStore.ts — Zustand store for multi-vessel lookback state (vessel/area modes)
- Story 3: useLookbackTracks.ts — parallel multi-vessel track fetching with TanStack useQueries, network resolution
- Story 4: TimelineBar.tsx — full-width bottom bar with play/pause, speed controls (1x/5x/30x/100x), scrubber, time-based animation loop via requestAnimationFrame
- Story 5: LookbackOverlay.tsx — multi-vessel globe rendering with binary-search interpolation, progressive trails, network vessel dimming
- Story 6: TrackExportSection.tsx (frontend) + GET /api/vessels/{mmsi}/track/export (backend) — JSON/CSV export with cold Parquet storage support, semaphore rate limiting
- Story 7: Removed TrackReplay.tsx, ReplayOverlay.tsx, useTrackReplay.ts, useReplayStore.ts, trackReplay.test.ts — updated barrel exports
- Story 8: AreaLookbackTool.tsx (polygon drawing via ScreenSpaceEventHandler) + AreaLookbackPanel.tsx (search + results) + GET /api/vessels/area-history (PostGIS ST_Within)
- Frontend build: 4 chunks, total ~540KB gzipped
- All 15 pre-existing test failures unchanged, zero new regressions
- Commits: 5 commits on feature/lookback-and-export branch

### 42-graph-model-and-scoring (all 9 stories)
- Story 1: FalkorDB service in docker-compose.dev.yml (port 6380, persistent volume), FalkorDBConfig in shared/config.py, shared/db/graph.py client wrapper
- Story 2: Graph schema in services/graph_builder/schema.py — 6 node types (Vessel, Company, Person, ClassSociety, FlagState, PIClub), 7 edge types (OWNED_BY, MANAGED_BY, CLASSED_BY, FLAGGED_AS, INSURED_BY, DIRECTED_BY, STS_PARTNER), indexes, IG P&I Club seed data
- Story 3: GraphBuilder class — builds graph from Paris MoU (temporal transitions for class/flag/insurer changes), OpenSanctions (ownership chains, sanctions as Vessel attributes), IACS (class status updates). Idempotent via MERGE, batch Cypher with UNWIND
- Story 4: AIS enrichment — updates Vessel nodes with last_seen data from vessel_profiles, STS_PARTNER edges from GFW encounters and sts_proximity anomalies
- Story 5: Geographic inference engine — D1-D7 signals (staging loiter, Russian-origin transits, MMSI/flag mismatch, STS with blacklisted, loiter-then-vanish). Migration 026_vessel_signals.sql
- Story 6: Signal-based scoring engine — A1-A11, B1-B7, C1-C5 signal catalogue. Thresholds: 0-3 green, 4-5 yellow, 6-8 red. Override rules. Old rules moved to services/scoring/rules/legacy/
- Story 7: Fleet risk propagation — A10 (ISM company fleet, weight 2) and B4 (owner fleet, weight 3) via FalkorDB graph traversal. One-directional, no cascade
- Story 8: GraphPipeline class — 8-stage pipeline (build → AIS → inference → score → propagate → update). Full, incremental, and single-vessel modes
- Story 9: Export/import scripts for FalkorDB RDB dump + vessel_signals pg_dump. Makefile targets
- Tests: 107 passed, 1 skipped (redis-cli)
- Commits: 9 commits on feature/graph-model-and-scoring branch

## Current Feature

**Spec:** 42-graph-model-and-scoring
**Branch:** feature/graph-model-and-scoring
**Status:** completed

### What's next

Spec 42 complete. All 9 stories implemented. Ready for human review.

Remaining specs from original roadmap:
- Spec 31 (auth-backend): 7 stories — users table, SMTP, JWT, register/confirm/login, middleware, inactivity lifecycle
- Spec 32 (auth-frontend): 5 stories — auth store, login modal, confirm page, HUD menu, feature gating

Wave 16 — User-Scoped Watchlist & Email Notifications:
- Spec 33 (user-notifications): 6 stories — per-user watchlist, watch rules, notification engine, email alerts, UI

### Prerequisites (manual steps)
- Create `alerts@heimdalwatch.cloud` email account in Hostinger hPanel
- Set SMTP_PASS env var in production
- Set JWT_SECRET env var in production
- DB migration 014_users.sql must be applied via `psql -f` (prod DB safety rule)

## Previous Feature

Spec 30 complete. All stories implemented.

## Known Issues

- Frontend build now code-split into 4 chunks (GlobeView, VesselPanel, cesium, index) — Story 5 of spec 21
- Minor warnings in ws_positions tests (unawaited coroutines from AsyncMock) — cosmetic only, all tests pass
- identity_mismatch rule added as 14th rule (spec originally said 13 but had 14 distinct rules)
- Pre-existing TS errors in vesselPanel.test.ts (type narrowing on undefined) and VesselCluster.tsx (Cesium type mismatch) — cosmetic only
- Pre-existing test failures: test_config.py (singleton pollution), test_constants.py (rule count expectations), globe.test.ts (window not defined in Node)
- Pre-existing test_vessels.py::test_returns_full_profile_for_existing_vessel failure (mock session doesn't properly mock anomaly count)

## Decisions Made

- D1: 7 waves with 16 specs total. Waves run sequentially, specs within each wave run in parallel.
- D2: Replaced custom SAR processor with GFW API consumption in enrichment service.
- D3: Eliminated Copernicus+CFAR — GFW provides ML-validated SAR detections via API.
- D4: ~~No authentication for local deployment. Single-user workstation.~~ **REVERSED in Wave 15** — adding multi-user JWT auth with email registration via heimdalwatch.cloud. Globe remains public, expensive features gated behind login.
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
- D16: Structured logging uses custom JsonFormatter (no python-json-logger dependency).

### 22-equasis-upload (all 8 stories)
- Story 1: DB migration 010_equasis_data.sql — equasis_data table with JSONB columns, FK to vessel_profiles, indexes
  - Repository functions: insert, get_latest, list_uploads, get_by_id, update_vessel_profile_from_equasis
  - Tests: 31 tests
- Story 2: PDF Parser — pdfplumber-based parser for Equasis Ship Folder PDFs
  - Extracts all 11 data sections: ship particulars, management, classification status/surveys, safety certificates, PSC inspections, human element deficiencies, name/flag/company history, edition date
  - Tests: 13 tests against actual ShipFop.pdf fixture
- Story 3: API endpoint POST /api/equasis/upload — multipart PDF upload, validation, parsing, storage, vessel profile update, Redis re-scoring event
  - Also: GET /api/equasis/{mmsi}/history, GET /api/equasis/{mmsi}/upload/{id}
  - Tests: 13 tests
- Story 7: Vessel detail response extension — GET /api/vessels/{mmsi} now includes equasis object (latest, upload_count, uploads)
  - Tests: 4 tests
- Story 4: Vessel panel upload button — EquasisUpload.tsx with file picker, mutation, toast notifications, query invalidation
  - Tests: 21 tests
- Story 5: Standalone import button — EquasisImport.tsx in app header, uploads without mmsi, auto-selects vessel
  - Tests: 7 tests
- Story 6: Expanded vessel information display — EquasisSection.tsx with collapsible subsections for all data, FoC coloring, PSC detention highlighting, previous uploads dropdown
  - Tests: 45 tests
- Story 8: Scoring enhancements — insurance_class_risk uses equasis PSC/classification data, flag_hopping uses equasis flag_history with dated windowing
  - Tests: 19 tests
- Commits: 8 commits on feature/equasis-upload branch

### 40-paris-mou-pipeline (all 4 stories)
- Story 1: DB migration 024_psc_inspections.sql — psc_inspections, psc_deficiencies, psc_certificates, psc_flag_performance tables with 6 indexes and 87 flag state seed data
  - Tests: 15 tests
- Story 2: XML parser — lxml iterparse for 135MB+ THETIS XML, extracts inspections/deficiencies/certificates, derives detention and ISM flags, supports .xml and .xml.zip
  - Validated against real data: 16,418 inspections, 672 detained, 9,917 with deficiencies
  - Tests: 39 tests
- Story 3: Historical batch ingest script — CLI with --dry-run, --file, --download-only; DES API auth/download; ON CONFLICT upsert; commits per file
  - Tests: 19 tests
- Story 4: Incremental update service — weekly VPS job, psc_download_log tracking table, diffs API vs processed, Dockerfile for batch profile
  - Tests: 15 tests
- Tests: 88 total, all passing
- Commits: 4 commits on feature/paris-mou-pipeline branch

### 41-opensanctions-ownership-graph (all 4 stories)
- Story 1: DB migration 025_opensanctions_graph.sql — os_entities, os_relationships, os_vessel_links tables with GIN/B-tree indexes
  - Tests: 23 tests
- Story 2: FTM entity extractor — streaming NDJSON parser for Vessel/Company/Person/Organization/LegalEntity entities, Ownership/Directorship relationships, IMO/MMSI vessel links
  - Tests: 32 tests
- Story 3: Historical batch load script — scripts/load_opensanctions.py with psycopg2 upserts, --stats/--stats-only flags
  - Tests: 12 tests
- Story 4: Daily incremental sync — services/opensanctions/sync.py reuses download script + extractor, no deletion policy, Dockerfile for batch profile
  - Tests: 9 tests
- Tests: 76 total, all passing
- Commits: 4 commits on feature/opensanctions-ownership-graph branch

## Notes for Next Session

- Spec 41 opensanctions-ownership-graph COMPLETED on feature/opensanctions-ownership-graph branch. Ready for human review.
- Spec 40 paris-mou-pipeline COMPLETED on feature/paris-mou-pipeline branch. Ready for human review.
- Migration 025 must be applied via `psql -f` in prod (DB safety rule)
- To run historical load: `python3 scripts/load_opensanctions.py --file data/opensanctions/default.json --db-url $DATABASE_URL --stats`
- VPS daily sync: add `opensanctions-sync` service to docker-compose batch profile, cron daily at 04:00
- Sanction entities (single-endpoint) are captured via entity.target=True flag, not as relationship edges
- Spec 42 (graph model) will consume os_entities/os_relationships tables to build ownership chains
