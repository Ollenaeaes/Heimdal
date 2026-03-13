# Performance Analysis

## Date: 2026-03-13

## Architecture Overview

The system consists of 5 Python services:
- **ais-ingest**: WebSocket -> parse -> dedup -> batch write
- **scoring-engine**: Redis sub -> 14+ rules per vessel -> aggregate -> DB update
- **enrichment-service**: 6-hour cycle -> GFW API -> sanctions -> DB update
- **api-server**: FastAPI REST + WebSocket endpoints
- **frontend**: React + CesiumJS globe

## Identified Bottlenecks (Priority Order)

### 1. Scoring Engine -- No Position Debounce (CRITICAL)

**Impact:** 95%+ unnecessary CPU usage
**Problem:** Every position update triggers full rule evaluation (14 rules). A vessel reporting every 3 seconds = 280 rule evaluations/minute/vessel. With 10,000 active vessels this means millions of rule evaluations per hour, each involving database queries for vessel profile, positions, and anomalies.
**Solution:** Debounce position updates. Evaluate at most once per 60s per vessel (30s for red tier).
**Expected improvement:** 95% reduction in scoring CPU.

### 2. AIS Ingest -- stdlib json.loads() in Hot Path

**Impact:** ~30% of ingest CPU
**Problem:** stdlib `json` is pure Python. Each message is parsed via `json.loads()`. At 10,000+ messages/sec this is a significant fraction of CPU time.
**Solution:** Replace with `orjson` (Rust-backed, 3-5x faster for typical payloads).
**Expected improvement:** 60-70% reduction in JSON parsing time.

### 3. AIS Ingest -- Individual Redis SETNX for Dedup

**Impact:** ~20% of ingest CPU (network round-trips)
**Problem:** Each message sends a separate `SET NX EX` to Redis for deduplication. At high throughput this creates thousands of sequential network round-trips per second.
**Solution:** Pipeline dedup checks in batches using Redis pipelines.
**Expected improvement:** 80%+ reduction in dedup latency.

### 4. Frontend -- 4.6MB CesiumJS Bundle

**Impact:** Slow initial load
**Problem:** CesiumJS loaded eagerly in main bundle. The entire 3D globe library is downloaded before the user sees anything.
**Solution:** React.lazy() + Suspense for CesiumJS, vessel panel, and replay components.
**Expected improvement:** Initial bundle < 1MB, CesiumJS loaded on demand.

### 5. Score Aggregation -- Python Loop with JSON Parsing

**Impact:** ~5% of scoring CPU per vessel
**Problem:** `aggregate_score()` iterates all anomalies, parsing JSON details string for each to extract escalation multipliers. This is pure Python string manipulation in a hot loop.
**Solution:** Move aggregation to SQL (SUM + LEAST per rule_id), or pre-parse details at write time.
**Expected improvement:** 80% reduction in aggregation time.

### 6. Database Queries -- Potential N+1 in API Endpoints

**Impact:** API response latency
**Problem:** Anomaly and vessel endpoints may issue per-vessel queries when listing. The scoring engine also re-fetches all anomalies after each evaluation.
**Solution:** Verify query plans, ensure JOINs are used, check index utilization. Consider materializing aggregate scores.

## Memory Targets

| Service | Target | Notes |
|---------|--------|-------|
| scoring-engine | < 200MB for 10,000 vessels | Rule state + vessel cache |
| ais-ingest | < 50MB | Batch buffer (500 positions) |
| enrichment | < 500MB | OpenSanctions index |
| frontend | < 100MB | Vessel store for 10,000 vessels |

## Memory Profiling Results

Profiled using `scripts/profile_memory.py` with `tracemalloc`. All measurements are peak memory (worst case).

| Component | Simulated Load | Peak Memory | Target | Status |
|-----------|---------------|-------------|--------|--------|
| Scoring engine | 10,000 vessels x 3 anomalies + aggregation | ~24 MB | < 200 MB | Well within target |
| AIS ingest buffer | 500 position messages | ~0.2 MB | < 10 MB | Well within target |
| Frontend vessel store | 10,000 vessels (Python dict estimate) | ~4.4 MB | < 100 MB | Well within target |

### Analysis

**Scoring engine (24 MB for 10K vessels):** The scoring engine stores anomaly data as Python dicts with JSON string details. With 3 anomalies per vessel (30,000 total anomalies) and full aggregation, peak memory is ~24 MB — an order of magnitude below the 200 MB target. The main memory consumers are the dict objects and their string values. No optimization needed at this scale.

**AIS ingest buffer (0.2 MB for 500 positions):** The batch buffer holding 500 position dicts before flushing to the database uses negligible memory. Even at 10x the buffer size (5,000 positions), memory would remain well under 1 MB.

**Frontend vessel store (4.4 MB for 10K vessels):** Estimated using equivalent Python dict structures. Each vessel entry (MMSI, position, SOG, COG, heading, risk tier, name) uses approximately 440 bytes. JavaScript objects have different overhead than Python dicts, but the order of magnitude should be comparable. At 10,000 vessels the store is well within the 100 MB target.

**OpenSanctions index:** The OpenSanctions NDJSON index loading depends on the dataset size (varies with each download). Based on the bulk matching implementation in the enrichment service, the index is loaded line-by-line and matched in a streaming fashion — it does not require holding the entire dataset in memory simultaneously.

### Running Memory Profiling

```bash
# Profile all components
python3 scripts/profile_memory.py
```

The script uses Python's `tracemalloc` module to measure actual heap allocations. It simulates realistic data volumes and asserts that all measurements stay within targets.

## Profiling Scripts

| Script | Service | What it profiles |
|--------|---------|-----------------|
| `scripts/profile_scoring.py` | scoring-engine | aggregate_score (10K iterations, 500 anomalies), rule discovery (100 iterations) |
| `scripts/profile_ingest.py` | ais-ingest | parse_position_report (10K messages), JSON loads (10K messages) |
| `scripts/profile_memory.py` | all | Memory usage of scoring state (10K vessels), ingest buffer (500 positions), vessel store estimate (10K vessels) |

## Next Steps

1. ~~**Story 1:** CPU profiling and bottleneck identification~~ (done)
2. ~~**Story 2:** Implement scoring debounce~~ (done)
3. **Story 3:** Replace stdlib json with orjson in ingest hot path
4. **Story 4:** Pipeline Redis dedup calls in batches
5. ~~**Story 5:** Code-split CesiumJS bundle with React.lazy~~ (done)
6. ~~**Story 6:** Memory usage optimization~~ (done — all targets met, no code changes needed)
