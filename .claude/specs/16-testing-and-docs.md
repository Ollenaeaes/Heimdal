# Feature Spec: Testing and Documentation

**Slug:** `testing-and-docs`
**Created:** 2026-03-11
**Updated:** 2026-03-12 (GFW Integration — Update 001)
**Status:** draft
**Priority:** low
**Wave:** 7 (Polish)

---

## Overview

Create the complete test suite (unit tests, integration tests, performance benchmarks), test fixtures, and project documentation (README, architecture overview).

> **Update 001:** Added GFW client tests, GFW scoring rule tests, GFW event/SAR detection fixtures, and updated README API key section (GFW replaces Copernicus).

## Problem Statement

A comprehensive test suite validates that all components work correctly individually and together. Documentation enables other developers and operators to deploy and use Heimdal.

## Out of Scope

- NOT: Playwright/browser E2E tests (future scope)
- NOT: CI/CD pipeline configuration
- NOT: Community contribution guidelines (post-launch)

---

## User Stories

### Story 1: Unit Test Suite

**As a** developer
**I want to** run unit tests for all backend services
**So that** I can verify individual components work correctly

**Acceptance Criteria:**

- GIVEN `test_parser.py` WHEN run THEN tests AIS message parsing against sample fixtures: all message types (1, 2, 3, 5), invalid MMSI, out-of-range coordinates, missing fields, deduplication logic
- GIVEN `test_rules.py` WHEN run THEN tests each scoring rule individually with mocked profiles and positions: correct firing, severity, point assignment, cooldown periods, threshold edge cases — including all 5 GFW-sourced rules and 8 real-time rules
- GIVEN `test_scoring_engine.py` WHEN run THEN tests aggregation: green/yellow/red thresholds, per-rule capping, tier transitions, and dedup logic (GFW rules suppress corresponding real-time rules)
- GIVEN `test_gfw_client.py` WHEN run THEN tests GFW API client: JWT auth, token refresh, rate limiting, pagination, error handling with retries
- GIVEN `test_enrichment.py` WHEN run THEN tests OpenSanctions matching: exact IMO, MMSI match, fuzzy name match, no-match scenarios. Tests GFW event ingestion, GFW SAR detection ingestion, GFW vessel identity updates
- GIVEN `test_api_endpoints.py` WHEN run THEN tests all REST endpoints using FastAPI TestClient: filtering, pagination, enrichment POST validation, error responses, GFW events endpoint

**Test Requirements:**

- [ ] Test: All test files pass with `pytest`
- [ ] Test: Coverage >80% on critical modules (parser, rules, engine, GFW client, API routes)

**Technical Notes:**

Use pytest with pytest-asyncio for async tests. Mock database and Redis for unit tests. Use FastAPI TestClient for endpoint tests. Place all tests in `tests/` directory.

---

### Story 2: Test Fixtures

**As a** developer
**I want to** have realistic test fixtures
**So that** tests use representative data rather than trivial stubs

**Acceptance Criteria:**

- GIVEN `tests/fixtures/sample_ais_messages.json` WHEN loaded THEN contains 50+ real-format AIS messages covering: position reports (types 1, 2, 3), static data (type 5), edge cases, known shadow fleet MMSIs
- GIVEN `tests/fixtures/sample_opensanctions.json` WHEN loaded THEN contains subset of OpenSanctions format: 10 sanctioned vessels, 5 non-sanctioned for positive/negative matching
- GIVEN `tests/fixtures/sample_vessel_profiles.json` WHEN loaded THEN contains pre-built profiles at various risk levels: green vessels (score 0-29), yellow (30-99), red (100+), with varying anomaly combinations
- GIVEN `tests/fixtures/sample_gfw_events.json` WHEN loaded THEN contains sample GFW events for all 4 types: AIS_DISABLING (in and out of sanctions corridors), ENCOUNTER (in STS zone, with sanctioned vessel, normal), LOITERING (in STS zone, open ocean), PORT_VISIT (Russian terminal, non-Russian port)
- GIVEN `tests/fixtures/sample_gfw_sar_detections.json` WHEN loaded THEN contains sample GFW SAR detections: dark ships (is_dark=true), matched ships (is_dark=false), with gfw_detection_id, matching_score, fishing_score fields

**Test Requirements:**

- [ ] Test: All fixture files are valid JSON
- [ ] Test: Fixture data passes Pydantic model validation

**Technical Notes:**

Use realistic vessel names, MMSIs, and positions. Include known shadow fleet patterns: vessels near STS zones, vessels at Russian terminals, vessels with AIS gaps. Fixtures should cover both positive cases (should trigger rules) and negative cases (should not trigger). GFW event fixtures should include realistic gfw_event_id values and complete details JSONB.

---

### Story 3: Integration Tests

**As a** developer
**I want to** verify the full pipeline works end-to-end
**So that** I know all components work together correctly

**Acceptance Criteria:**

- GIVEN Docker Compose up with test fixtures WHEN running integration tests THEN verify: mock AIS message → ingest → scoring → API response with correct risk tier
- GIVEN a WebSocket connection to /ws/positions WHEN injecting a position via ingest THEN verify receipt within 5 seconds
- GIVEN the enrichment pipeline WHEN run against test fixtures THEN verify sanctions matches are correct
- GIVEN GFW events in the database WHEN scoring runs THEN verify GFW-sourced rules fire correctly and dedup suppresses real-time rules

**Test Requirements:**

- [ ] Test: End-to-end pipeline produces correct risk tier for a known bad vessel
- [ ] Test: WebSocket delivers position update within 5 seconds of ingestion
- [ ] Test: Enrichment produces correct sanctions status from test data
- [ ] Test: GFW scoring rules produce correct anomalies from GFW event fixtures

**Technical Notes:**

Integration tests require running Docker Compose. Use `docker compose run --rm` to execute tests inside containers. Pre-load fixtures (including GFW event fixtures) into PostgreSQL before running.

---

### Story 4: Performance Benchmarks

**As a** developer
**I want to** verify the platform meets performance targets
**So that** operators can rely on timely data processing

**Acceptance Criteria:**

- GIVEN the ingest service WHEN benchmarking THEN measure positions/sec at sustained load, target: >2000 pos/sec on 4 cores
- GIVEN the scoring engine WHEN benchmarking THEN measure time from new position to updated risk score, target: <100ms p99
- GIVEN `/api/vessels` WHEN benchmarking with 50K vessels THEN response time target: <200ms p99
- GIVEN the frontend WHEN benchmarking with 10K/25K/50K markers THEN target: >30fps at 25K

**Test Requirements:**

- [ ] Test: Ingest throughput exceeds 2000 pos/sec
- [ ] Test: Scoring latency <100ms p99
- [ ] Test: API response <200ms p99 at 50K vessels

**Technical Notes:**

Create `scripts/benchmark.py` for backend benchmarks. Use `ab` or `wrk` for API load testing. Frontend FPS testing can be manual or use CesiumJS performance monitoring.

---

### Story 5: README and Documentation

**As a** new operator
**I want to** read documentation to deploy and use Heimdal
**So that** I can get the platform running without reading source code

**Acceptance Criteria:**

- GIVEN `README.md` WHEN read THEN covers: project overview, prerequisites (Docker, API keys), installation steps (git clone → docker compose up), first-run walkthrough, architecture diagram, configuration reference, troubleshooting
- GIVEN the README WHEN following installation THEN a user can go from git clone to live globe in <10 minutes
- GIVEN the README WHEN referencing API keys THEN explains how to get: aisstream.io key (free), Cesium Ion token (free), GFW API token (free registration at globalfishingwatch.org)
- GIVEN the README WHEN describing architecture THEN includes ASCII or Mermaid diagram showing all 6 containers and data flow including GFW API integration

**Test Requirements:**

- [ ] Test: README covers all required sections
- [ ] Test: Installation steps work from a fresh clone (manual verification)

**Technical Notes:**

Architecture diagram should show: aisstream.io → ais-ingest → PostgreSQL → scoring → Redis → api-server → frontend. Also show: GFW APIs → enrichment → PostgreSQL (gfw_events + sar_detections). Include the data flow for all pipelines (AIS, GFW enrichment, OpenSanctions, manual).

---

## Implementation Order

### Group 1 (parallel — all independent)
- Story 2 — Test fixtures (needed by other test stories but can be created independently)
- Story 5 — README and documentation

### Group 2 (parallel — after Group 1)
- Story 1 — Unit test suite (uses fixtures)
- Story 3 — Integration tests

### Group 3 (after Group 2)
- Story 4 — Performance benchmarks (needs working system)

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] All unit tests pass (including GFW client and GFW scoring rule tests)
- [ ] Integration tests pass (including GFW event scoring flow)
- [ ] Performance benchmarks meet targets
- [ ] README enables fresh deployment in <10 minutes
- [ ] Test coverage >80% on critical modules
- [ ] Code committed with proper messages
- [ ] Ready for human review
