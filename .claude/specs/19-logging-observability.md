# Feature Spec: Structured Logging & Observability

**Slug:** `logging-observability`
**Created:** 2026-03-13
**Status:** draft
**Priority:** high

---

## Overview

Replace the current basic text logging with structured JSON logging, add API call duration tracking, service heartbeat monitoring, and alerting for slow operations. Currently the system has no visibility into API latency, service health degradation, or scoring pipeline performance — operating blind in production.

## Problem Statement

The current logging is "driving in the dark":

1. **Plain text logs** — `"%(asctime)s %(name)s %(levelname)s %(message)s"` format provides no structured data for log aggregation, searching, or alerting.
2. **No API call timing** — GFW API calls, database queries, and rule evaluations have no duration tracking. If an API becomes slow or rate-limited, there's no visibility.
3. **No service heartbeats** — if the scoring engine or enrichment service hangs, there's no detection mechanism beyond the basic health endpoint checking Redis/DB connectivity.
4. **No performance baselines** — scoring latency is benchmarked at 0.3ms p99 but not tracked in production. Degradation goes unnoticed.
5. **No alerting thresholds** — even with the health endpoint, there's no mechanism to flag when things are slow vs. down.

## Out of Scope

- NOT: External log aggregation setup (ELK, Grafana, Datadog) — just produce the structured logs
- NOT: APM (Application Performance Monitoring) agents
- NOT: Distributed tracing (OpenTelemetry) — too complex for single-node deployment
- NOT: Alerting infrastructure (PagerDuty, OpsGenie) — just log warnings for slow operations
- NOT: Frontend logging/error tracking

---

## User Stories

### Story 1: Structured JSON Logging

**As a** system operator
**I want to** all services to produce structured JSON logs
**So that** I can search, filter, and aggregate logs programmatically

**Acceptance Criteria:**

- GIVEN any service starts WHEN logging is configured THEN all log output is JSON format with fields: `timestamp`, `level`, `service`, `logger`, `message`, `extra` (dict)
- GIVEN a log message with context WHEN emitted THEN context fields (mmsi, rule_id, etc.) appear as top-level JSON keys, not embedded in the message string
- GIVEN the JSON log format WHEN read by `docker compose logs` THEN each line is a valid JSON object
- GIVEN development mode (`LOG_FORMAT=text` env var) WHEN logging THEN fallback to human-readable format for local debugging
- GIVEN existing logger.info/warning/error calls WHEN JSON logging is active THEN they work unchanged (backward compatible)

**Test Requirements:**

- [ ] Test: Log output is valid JSON with required fields
- [ ] Test: Extra context fields appear at top level
- [ ] Test: LOG_FORMAT=text produces human-readable output
- [ ] Test: Existing log calls work without modification
- [ ] Test: Exception logging includes traceback in JSON `exc_info` field

**Technical Notes:**

- Create `shared/logging.py` with `setup_logging(service_name: str)` function
- Use `python-json-logger` library (or implement a custom `logging.Formatter`)
- Standard fields: `{"timestamp": "ISO8601", "level": "INFO", "service": "scoring", "logger": "scoring.engine", "message": "...", ...extra}`
- Replace `logging.basicConfig()` in each service's `main.py` with `setup_logging()`
- Add `LOG_FORMAT` and `LOG_LEVEL` env vars to `.env.example`

---

### Story 2: API Call Duration Tracking

**As a** system operator
**I want to** track the duration of all external API calls
**So that** I can identify slow endpoints and rate-limiting issues before they cascade

**Acceptance Criteria:**

- GIVEN a GFW API call WHEN it completes THEN a log entry includes `duration_ms`, `url`, `status_code`, `method`
- GIVEN a GFW API call takes > 5 seconds WHEN it completes THEN a WARNING-level log is emitted with `slow_api_call=true`
- GIVEN a GFW API call takes > 30 seconds WHEN it completes THEN an ERROR-level log is emitted
- GIVEN the enrichment cycle runs WHEN it completes THEN a summary log includes total duration, number of API calls made, average call duration, number of rate-limit retries
- GIVEN the GFW client makes a retry WHEN the retry completes THEN the log includes `retry_attempt`, `retry_reason`, original duration

**Test Requirements:**

- [ ] Test: GFW API call logs include duration_ms and status_code
- [ ] Test: Slow API call (> 5s) triggers WARNING log
- [ ] Test: Very slow API call (> 30s) triggers ERROR log
- [ ] Test: Enrichment cycle summary includes correct total_duration and call_count
- [ ] Test: Retry attempts are logged with attempt number and reason

**Technical Notes:**

- Add a timing decorator/context manager to `shared/logging.py`:
  ```python
  @contextmanager
  def log_api_call(logger, url, method="GET"):
      start = time.monotonic()
      yield
      duration_ms = (time.monotonic() - start) * 1000
      logger.info("api_call", extra={"url": url, "duration_ms": duration_ms, ...})
  ```
- Wrap GFW client methods (`_request`, `get_events`, etc.) with the timer
- Add thresholds to `config.yaml`:
  ```yaml
  observability:
    slow_api_threshold_ms: 5000
    error_api_threshold_ms: 30000
  ```
- Update `services/enrichment/gfw_client.py` to use the timer
- Add summary statistics to `services/enrichment/runner.py` cycle completion

---

### Story 3: Service Heartbeat & Health Monitoring

**As a** system operator
**I want to** each service to publish periodic heartbeats
**So that** I can detect when a service has hung or stopped processing

**Acceptance Criteria:**

- GIVEN ais-ingest is running WHEN 60 seconds pass THEN it publishes a heartbeat to Redis key `heimdal:heartbeat:ais-ingest` with TTL 120s containing `{service, timestamp, uptime_seconds, messages_processed}`
- GIVEN scoring-engine is running WHEN 60 seconds pass THEN heartbeat to `heimdal:heartbeat:scoring` with `{service, timestamp, evaluations_count, last_evaluation_ms}`
- GIVEN enrichment is running WHEN 60 seconds pass THEN heartbeat to `heimdal:heartbeat:enrichment` with `{service, timestamp, cycle_state, vessels_enriched}`
- GIVEN the health endpoint WHEN checking service health THEN it reads heartbeat keys and reports services as degraded if heartbeat is > 120s stale
- GIVEN a service heartbeat expires (TTL) WHEN health endpoint checks THEN the service is reported as `down`

**Test Requirements:**

- [ ] Test: Heartbeat published every 60 seconds with correct TTL
- [ ] Test: Heartbeat contains required fields (service, timestamp, metrics)
- [ ] Test: Health endpoint reports service as `healthy` when heartbeat is fresh
- [ ] Test: Health endpoint reports service as `degraded` when heartbeat is > 90s old
- [ ] Test: Health endpoint reports service as `down` when heartbeat key is missing
- [ ] Test: Heartbeat continues even during service idle periods

**Technical Notes:**

- Create `shared/heartbeat.py` with `HeartbeatPublisher` class
- Use `asyncio.create_task` for background heartbeat loop in each service
- Redis key pattern: `heimdal:heartbeat:{service_name}` with TTL 120s
- Value: JSON string with service metrics
- Update `services/api-server/routes/health.py` to check heartbeat keys
- Health response now includes per-service status:
  ```json
  {
    "status": "degraded",
    "services": {
      "ais-ingest": {"status": "healthy", "last_heartbeat": "2026-03-13T..."},
      "scoring": {"status": "degraded", "last_heartbeat": "2026-03-13T...", "age_seconds": 95},
      "enrichment": {"status": "down", "last_heartbeat": null}
    }
  }
  ```

---

### Story 4: Scoring Pipeline Performance Logging

**As a** system operator
**I want to** track scoring pipeline performance metrics
**So that** I can detect degradation in rule evaluation speed and database query latency

**Acceptance Criteria:**

- GIVEN a vessel is evaluated WHEN all realtime rules complete THEN a log entry includes `total_evaluation_ms`, `rules_evaluated`, `rules_fired`, `mmsi`
- GIVEN a single rule evaluation WHEN it takes > 100ms THEN a WARNING log is emitted with `slow_rule=true`, `rule_id`, `duration_ms`
- GIVEN the scoring engine WHEN processing a position batch THEN summary log includes `batch_size`, `total_ms`, `avg_per_vessel_ms`
- GIVEN aggregate score calculation WHEN it queries the database THEN query duration is logged
- GIVEN a rule evaluation fails with an exception WHEN logged THEN the log includes `rule_id`, `mmsi`, `error`, `traceback`

**Test Requirements:**

- [ ] Test: Vessel evaluation logs include total_evaluation_ms and rules_evaluated count
- [ ] Test: Slow rule (> 100ms) triggers WARNING with rule_id
- [ ] Test: Batch processing summary includes correct metrics
- [ ] Test: Rule exception logging includes all context fields
- [ ] Test: Performance logs don't significantly impact evaluation speed (< 1ms overhead)

**Technical Notes:**

- Wrap rule evaluation loop in `engine.evaluate_realtime` with timing
- Add per-rule timing within the loop
- Thresholds in `config.yaml`:
  ```yaml
  observability:
    slow_rule_threshold_ms: 100
    slow_evaluation_threshold_ms: 500
  ```
- Use `time.monotonic()` for accurate timing (not `time.time()`)
- Add metrics accumulator in engine for batch processing summaries
- Log at INFO for normal operations, WARNING for slow, ERROR for failures

---

### Story 5: Database Query Performance Logging

**As a** system operator
**I want to** track slow database queries across all services
**So that** I can identify N+1 queries, missing indexes, and table scans

**Acceptance Criteria:**

- GIVEN any database query WHEN it takes > 500ms THEN a WARNING log is emitted with `slow_query=true`, `duration_ms`, `query` (first 200 chars), `service`
- GIVEN any database query WHEN it takes > 5000ms THEN an ERROR log is emitted
- GIVEN the shared DB layer WHEN a connection pool is exhausted THEN an ERROR log is emitted with `pool_exhausted=true`
- GIVEN the scoring engine fetches vessel track WHEN the query completes THEN duration is logged at DEBUG level
- GIVEN the api-server handles a request WHEN the response is sent THEN total request duration is logged

**Test Requirements:**

- [ ] Test: Slow query (> 500ms) triggers WARNING with query snippet
- [ ] Test: Very slow query (> 5s) triggers ERROR
- [ ] Test: Normal-speed queries log at DEBUG level only
- [ ] Test: Connection pool events are logged
- [ ] Test: API request duration is logged for each endpoint

**Technical Notes:**

- Add SQLAlchemy event listeners for query timing:
  ```python
  @event.listens_for(engine, "before_cursor_execute")
  @event.listens_for(engine, "after_cursor_execute")
  ```
- Add FastAPI middleware for request duration logging in api-server
- Thresholds in `config.yaml`:
  ```yaml
  observability:
    slow_query_threshold_ms: 500
    error_query_threshold_ms: 5000
  ```
- Query text truncated to 200 chars in logs (no sensitive data exposure)
- Pool exhaustion: listen for SQLAlchemy pool events

---

## Technical Design

### Data Model Changes

None — this is infrastructure/logging only.

### API Changes

**Updated health endpoint response:**
```json
{
  "status": "healthy|degraded|down",
  "services": {
    "ais-ingest": {"status": "healthy", "last_heartbeat": "...", "messages_processed": 12345},
    "scoring": {"status": "healthy", "last_heartbeat": "...", "evaluations_count": 456},
    "enrichment": {"status": "healthy", "last_heartbeat": "...", "cycle_state": "idle"}
  },
  "database": {"status": "up", "pool_size": 10, "pool_available": 8},
  "redis": {"status": "up"},
  "ais_websocket": {"status": "connected", "last_message_age_seconds": 5}
}
```

### Dependencies

- `python-json-logger` library (add to `requirements-base.txt`)
- Existing Redis connection (for heartbeats)
- SQLAlchemy event system (existing)

### Security Considerations

- Query text in logs is truncated to prevent leaking sensitive data
- Heartbeat keys in Redis have short TTL (120s) to prevent stale data accumulation
- No PII in structured log fields

---

## Implementation Order

### Group 1 (parallel — no dependencies)
- Story 1 — JSON logging (`shared/logging.py`, update all `main.py` files)
- Story 3 — Heartbeat system (`shared/heartbeat.py`, update all service `main.py` files, update health endpoint)

### Group 2 (parallel — after Group 1)
- Story 2 — API call timing (`services/enrichment/gfw_client.py`, `services/enrichment/runner.py`)
- Story 4 — Scoring performance logging (`services/scoring/engine.py`)
- Story 5 — Database query logging (`shared/db/connection.py`, `services/api-server/main.py`)

**Parallel safety rules:**
- Group 1: shared/logging.py and shared/heartbeat.py are separate files; main.py updates are small and independent
- Group 2: Each story touches different service files

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled
- [ ] No regressions in existing tests
- [ ] Code committed with proper messages
- [ ] Ready for human review
