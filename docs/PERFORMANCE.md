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

## Profiling Scripts

| Script | Service | What it profiles |
|--------|---------|-----------------|
| `scripts/profile_scoring.py` | scoring-engine | aggregate_score (10K iterations, 500 anomalies), rule discovery (100 iterations) |
| `scripts/profile_ingest.py` | ais-ingest | parse_position_report (10K messages), JSON loads (10K messages) |

### Running Profiling Scripts

```bash
# Profile scoring engine
python3 scripts/profile_scoring.py

# Profile AIS ingest
python3 scripts/profile_ingest.py
```

Both scripts use Python's built-in `cProfile` module and print the top 20 functions by cumulative time.

## Memory Targets

| Service | Target | Notes |
|---------|--------|-------|
| scoring-engine | < 200MB for 10,000 vessels | Rule state + vessel cache |
| ais-ingest | < 50MB | Batch buffer (500 positions) |
| enrichment | < 500MB | OpenSanctions index |
| frontend | < 100MB | Vessel store for 10,000 vessels |

## Next Steps

1. **Story 2:** Implement scoring debounce (Redis-based, per-vessel cooldown)
2. **Story 3:** Replace stdlib json with orjson in ingest hot path
3. **Story 4:** Pipeline Redis dedup calls in batches
4. **Story 5:** Code-split CesiumJS bundle with React.lazy
5. **Story 6:** Evaluate SQL-based score aggregation
