# Feature Spec: Performance Optimization

**Slug:** `performance-optimization`
**Created:** 2026-03-13
**Status:** draft
**Priority:** medium

---

## Overview

Profile and optimize the system's CPU and memory usage. The current Python implementation works but uses significantly more CPU than necessary. This spec covers profiling to identify hot paths, optimizing the most expensive operations, and evaluating whether critical paths should be rewritten in a compiled language. Changes should be incremental and measured.

## Problem Statement

The system uses "a LOT of CPU" (user report). Likely causes based on architecture review:

1. **Scoring engine evaluates 14+ rules per vessel on every position update** — with potentially 10,000+ active vessels, this is millions of rule evaluations per hour, each involving database queries.
2. **No scoring debounce** — every position update triggers full rule evaluation. A vessel reporting every 3 seconds generates 20 evaluations per minute × 14 rules = 280 rule evaluations per minute per vessel.
3. **Enrichment fetches are synchronous per-vessel** — despite using async, the GFW rate limit (2 req/sec) serialises operations.
4. **Frontend CesiumJS bundle is 4.6MB** — large initial download, no code-splitting.
5. **Database queries may lack optimisation** — N+1 queries in anomaly aggregation, full-table scans for vessel listing.
6. **Python GIL** — CPU-bound operations (JSON parsing, spatial calculations) are GIL-limited in a single process.

## Out of Scope

- NOT: Rewriting the entire system in another language (this spec evaluates and implements targeted optimisations)
- NOT: Horizontal scaling / load balancing (single-node deployment)
- NOT: CDN setup or deployment infrastructure
- NOT: Major architectural refactoring (keep the existing service structure)

---

## User Stories

### Story 1: CPU Profiling and Bottleneck Identification

**As a** developer
**I want to** profile all services under realistic load
**So that** I can identify the actual CPU bottlenecks before optimising

**Acceptance Criteria:**

- GIVEN a profiling script WHEN run against the scoring engine with 1000 vessels THEN it produces a flamegraph showing CPU time distribution per function
- GIVEN profiling results WHEN analysed THEN the top 5 CPU consumers are identified with percentage of total CPU time
- GIVEN profiling of ais-ingest WHEN processing 10,000 messages/sec THEN bottlenecks in parsing, dedup, and batching are identified
- GIVEN profiling of enrichment WHEN running a full cycle THEN time spent in API calls vs. data processing vs. database writes is quantified
- GIVEN profiling results WHEN documented THEN a `PERFORMANCE.md` report is written with findings and prioritised recommendations

**Test Requirements:**

- [ ] Test: Profiling script runs without errors on all services
- [ ] Test: Flamegraph output is generated as SVG
- [ ] Test: PERFORMANCE.md is created with quantified bottlenecks

**Technical Notes:**

- Use `py-spy` for sampling profiler (no code changes needed): `py-spy record --output profile.svg --pid <pid>`
- Alternative: `cProfile` + `snakeviz` for deterministic profiling
- Create `scripts/profile_scoring.py` that simulates 1000 vessels with realistic position data
- Create `scripts/profile_ingest.py` that replays AIS messages from test fixtures at high rate
- Write results to `docs/PERFORMANCE.md`

---

### Story 2: Scoring Engine Debounce and Batching

**As a** scoring engine
**I want to** debounce position updates and batch rule evaluations
**So that** I don't evaluate 14 rules on every single position report (which can be every 3 seconds)

**Acceptance Criteria:**

- GIVEN a vessel sends positions every 3 seconds WHEN the scoring engine processes them THEN it evaluates rules at most once every 60 seconds per vessel (configurable)
- GIVEN multiple positions arrive in the debounce window WHEN the window expires THEN the engine evaluates using the most recent position data
- GIVEN 50 vessels need evaluation in the same window WHEN the batch triggers THEN they are evaluated concurrently (asyncio.gather with semaphore)
- GIVEN the debounce mechanism WHEN a position arrives for a vessel not previously seen THEN the first evaluation happens immediately (no debounce for new vessels)
- GIVEN the debounce window WHEN the vessel's risk tier is red THEN the debounce is shorter (30 seconds) for more responsive monitoring

**Test Requirements:**

- [ ] Test: 20 positions in 60 seconds → 1 evaluation (not 20)
- [ ] Test: Debounce timer resets on each new position within the window
- [ ] Test: New vessel → immediate evaluation on first position
- [ ] Test: Red vessel → 30-second debounce (not 60)
- [ ] Test: Batch evaluation of 50 vessels completes within 5 seconds
- [ ] Test: Debounce interval is configurable in config.yaml

**Technical Notes:**

- Add a `_pending_evaluations: dict[int, asyncio.TimerHandle]` to the scoring engine
- On position receive: cancel existing timer, set new timer for debounce_seconds
- When timer fires: add MMSI to evaluation batch queue
- Process batch queue every second with `asyncio.gather` (max concurrency = 10)
- Config:
  ```yaml
  scoring:
    debounce:
      default_seconds: 60
      red_tier_seconds: 30
      max_batch_size: 50
      max_concurrent: 10
  ```
- This is the single biggest CPU optimization — reduces rule evaluations by 95%+ for frequently-reporting vessels

---

### Story 3: Database Query Optimization

**As a** system
**I want to** optimise the most expensive database queries
**So that** database CPU usage drops and query latency improves

**Acceptance Criteria:**

- GIVEN `list_anomaly_events_by_mmsi` is called WHEN it queries THEN it uses the existing partial index on `(mmsi, rule_id) WHERE resolved=false` for active anomaly queries
- GIVEN `get_vessel_track` is called with a 48-hour window WHEN it queries THEN it uses the composite index `(mmsi, timestamp)` efficiently
- GIVEN the api-server lists vessels with filters WHEN the query executes THEN it uses prepared statements (not string interpolation)
- GIVEN the scoring engine recalculates scores WHEN it fetches anomalies THEN it fetches only unresolved active anomalies (not full history)
- GIVEN aggregate_score needs anomaly data WHEN queried THEN a single query fetches sum(points) grouped by rule_id with caps applied in SQL (not Python)
- GIVEN vessel listing with risk_tier filter WHEN queried THEN response time < 50ms for 10,000 vessels

**Test Requirements:**

- [ ] Test: Anomaly query uses partial index (EXPLAIN shows index scan, not seq scan)
- [ ] Test: Vessel track query uses composite index
- [ ] Test: Score aggregation query returns correct results matching Python implementation
- [ ] Test: Vessel listing with filter < 50ms with 10,000 rows (benchmark test)
- [ ] Test: No N+1 queries in anomaly endpoint (single JOIN, not loop)

**Technical Notes:**

- Move `aggregate_score` calculation to a SQL query where possible:
  ```sql
  SELECT rule_id, LEAST(SUM(points), cap) as capped_points
  FROM anomaly_events ae
  JOIN (VALUES ('ais_gap', 40), ('speed_anomaly', 15), ...) AS caps(rule_id, cap)
    ON ae.rule_id = caps.rule_id
  WHERE ae.mmsi = :mmsi AND ae.resolved = false AND ae.event_state = 'active'
  GROUP BY ae.rule_id, caps.cap
  ```
- Add `EXPLAIN ANALYZE` tests for critical queries
- Ensure all WHERE clauses on `resolved` field use the partial index
- Consider materialised view for vessel risk stats (updated on tier change)

---

### Story 4: AIS Ingest Pipeline Optimization

**As a** ais-ingest service
**I want to** process AIS messages with minimal CPU overhead
**So that** the ingest pipeline can handle high message rates without bottlenecking

**Acceptance Criteria:**

- GIVEN AIS messages arrive at 10,000/sec WHEN processing THEN CPU usage stays below 50% of a single core
- GIVEN message parsing WHEN JSON decoding THEN use `orjson` instead of stdlib `json` for 3-5x speedup
- GIVEN the dedup check WHEN checking Redis THEN use pipelining for batch dedup checks (not individual SETNX per message)
- GIVEN the batch writer WHEN flushing to PostgreSQL THEN use `COPY` protocol where possible, falling back to `executemany` only for PostGIS types
- GIVEN the metrics publisher WHEN updating counters THEN use Redis INCR atomically (not GET+SET)

**Test Requirements:**

- [ ] Test: orjson parsing benchmark is > 2x faster than stdlib json for AIS messages
- [ ] Test: Redis pipeline dedup handles 1000 messages in single round-trip
- [ ] Test: Batch write of 500 positions completes in < 100ms
- [ ] Test: CPU benchmark: 10,000 msg/sec sustained < 50% single core
- [ ] Test: All existing ingest tests still pass with new dependencies

**Technical Notes:**

- Add `orjson` to requirements (`pip install orjson`)
- Replace `json.loads()` and `json.dumps()` with `orjson.loads()` and `orjson.dumps()` in hot paths
- Redis pipelining for dedup:
  ```python
  async with redis.pipeline() as pipe:
      for msg in batch:
          pipe.set(f"heimdal:dedup:{msg.mmsi}:{msg.ts}", 1, nx=True, ex=10)
      results = await pipe.execute()
  ```
- Batch writer already uses `executemany` — check if PostGIS works with asyncpg COPY (Decision D10 says it doesn't, but worth re-checking with recent asyncpg versions)
- Profile parser.py — if regex-heavy, consider pre-compiled patterns

---

### Story 5: Frontend Bundle Optimization

**As a** frontend
**I want to** reduce the initial bundle size and load time
**So that** the application loads faster and uses less memory

**Acceptance Criteria:**

- GIVEN the current build WHEN analysed THEN the CesiumJS chunk is identified as the largest (4.6MB)
- GIVEN code splitting WHEN implemented THEN CesiumJS is loaded lazily (not in the initial bundle)
- GIVEN the vessel detail panel WHEN not open THEN its code is not loaded
- GIVEN the stats dashboard WHEN collapsed THEN its chart code is not loaded
- GIVEN the optimised build WHEN measured THEN the initial bundle is < 1MB (excluding lazy-loaded chunks)
- GIVEN the application WHEN first load THEN Time to Interactive is < 3 seconds on a fast connection

**Test Requirements:**

- [ ] Test: Build produces multiple chunks (not single bundle)
- [ ] Test: Initial chunk < 1MB
- [ ] Test: CesiumJS chunk loaded on demand
- [ ] Test: All existing frontend tests pass
- [ ] Test: Lazy-loaded components render correctly after load

**Technical Notes:**

- Use `React.lazy()` + `Suspense` for:
  - `GlobeView` (loads CesiumJS)
  - `VesselDetailPanel` (loads on vessel select)
  - `TrackReplay` (loads on replay activation)
  - `DossierExport` (loads on export action)
- Configure Vite manual chunks in `vite.config.ts`:
  ```js
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          cesium: ['cesium', 'resium'],
          charts: ['chart-library-if-any'],
        }
      }
    }
  }
  ```
- Add loading skeletons for lazy components
- Consider `vite-plugin-compression` for gzip/brotli pre-compression

---

### Story 6: Memory Usage Optimization

**As a** system
**I want to** reduce memory usage across services
**So that** the system can run on smaller infrastructure

**Acceptance Criteria:**

- GIVEN the scoring engine WHEN holding vessel evaluation state THEN memory usage for 10,000 vessels stays below 200MB
- GIVEN the frontend vessel store WHEN tracking 10,000 vessels THEN memory usage stays below 100MB
- GIVEN the AIS ingest batch buffer WHEN holding 500 positions THEN memory usage for the buffer stays below 10MB
- GIVEN the enrichment service OpenSanctions index WHEN loaded THEN memory usage is profiled and optimised (current: unknown, target: < 500MB)
- GIVEN memory profiling WHEN results are documented THEN peak memory per service is recorded in PERFORMANCE.md

**Test Requirements:**

- [ ] Test: Scoring engine memory stays below 200MB with 10,000 simulated vessels
- [ ] Test: Frontend store memory usage for 10,000 vessels (measured via test utility)
- [ ] Test: OpenSanctions index loading doesn't exceed 500MB
- [ ] Test: Memory profiling results documented

**Technical Notes:**

- Use `tracemalloc` for Python memory profiling
- Frontend: use Chrome DevTools Memory tab in profiling mode
- OpenSanctions: consider streaming NDJSON parser instead of loading full index into memory
- Scoring engine: clear per-vessel caches after evaluation, don't hold all positions in memory
- Frontend: implement virtual scrolling for vessel lists if not already present
- Consider `__slots__` for frequently-instantiated Python objects

---

## Technical Design

### Data Model Changes

None.

### API Changes

None.

### Dependencies

- `orjson` — fast JSON parsing (add to requirements-base.txt)
- `py-spy` — profiling tool (dev dependency only)
- Vite configuration changes for code splitting

### Security Considerations

- Profiling scripts must not be included in production Docker images
- orjson is a well-maintained Rust-backed library with no known security issues

---

## Implementation Order

### Group 1 (sequential — must profile before optimising)
- Story 1 — CPU profiling and bottleneck identification

### Group 2 (parallel — after profiling, based on findings)
- Story 2 — Scoring engine debounce and batching (`services/scoring/engine.py`, `services/scoring/main.py`)
- Story 4 — AIS ingest pipeline optimization (`services/ais-ingest/`)
- Story 5 — Frontend bundle optimization (`frontend/`)

### Group 3 (parallel — after Group 2)
- Story 3 — Database query optimization (`shared/db/repositories.py`, `services/scoring/aggregator.py`)
- Story 6 — Memory usage optimization (all services)

**Parallel safety rules:**
- Group 1: Must complete first — profiling results inform which optimisations matter most
- Group 2: Scoring, ingest, and frontend are completely independent services
- Group 3: DB query optimisation and memory work touch different aspects

**Note:** After profiling (Story 1), the priority order of Stories 2-6 may change. If profiling reveals that the dominant bottleneck is database queries (not scoring), then Story 3 should be promoted to Group 2. The implementation agent should read PERFORMANCE.md after Story 1 and adjust priorities.

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled
- [ ] No regressions in existing tests
- [ ] Performance improvements measured and documented in PERFORMANCE.md
- [ ] Code committed with proper messages
- [ ] Ready for human review
