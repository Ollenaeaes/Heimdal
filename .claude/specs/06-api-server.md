# Feature Spec: API Server

**Slug:** `api-server`
**Created:** 2026-03-11
**Status:** completed
**Priority:** critical
**Wave:** 3 (API Layer)

---

## Overview

Build the FastAPI API server with all REST endpoints (vessels, anomalies, SAR detections, GFW events, health, stats) and both WebSocket endpoints (live positions, alerts). This is the bridge between backend services and the frontend.

## Problem Statement

The frontend and external consumers need a unified API to query vessel data, anomalies, SAR detections, GFW events, and system health. The WebSocket endpoints stream real-time position updates and alert events from Redis to connected clients.

## Out of Scope

- NOT: Scoring logic or rule evaluation (see `07-scoring-engine`)
- NOT: AIS data ingestion (see `04-ais-ingest`)
- NOT: Manual enrichment form UI (see `12-manual-enrichment`)
- NOT: Frontend components consuming these endpoints

---

## User Stories

### Story 1: FastAPI App Factory and Dockerfile

**As a** developer
**I want to** have a FastAPI application with proper startup/shutdown hooks and containerization
**So that** the API server runs as a service in Docker Compose

**Acceptance Criteria:**

- GIVEN `main.py` WHEN started THEN FastAPI app starts with Uvicorn on port 8000
- GIVEN the app WHEN starting THEN it connects to PostgreSQL and Redis during lifespan startup
- GIVEN the app WHEN stopping THEN it cleanly closes database and Redis connections
- GIVEN the Dockerfile WHEN built THEN Python 3.12 container with fastapi, uvicorn, and dependencies
- GIVEN `requirements.txt` WHEN read THEN includes shared base + `fastapi>=0.110`, `uvicorn[standard]>=0.29`

**Test Requirements:**

- [ ] Test: App starts without errors when database and Redis are available
- [ ] Test: Health endpoint responds immediately after startup

**Technical Notes:**

Use FastAPI lifespan context manager for startup/shutdown. Include CORS middleware for local development. Mount routes from separate route modules.

---

### Story 2: Vessel REST Endpoints

**As a** frontend developer
**I want to** query vessel data via REST endpoints
**So that** I can display vessel lists, details, and tracks

**Acceptance Criteria:**

- GIVEN `GET /api/vessels` WHEN called with no params THEN return paginated vessel list (default page=1, per_page=100, max 1000)
- GIVEN `GET /api/vessels` WHEN called with `risk_tier=red` THEN only red-tier vessels returned
- GIVEN `GET /api/vessels` WHEN called with `bbox=sw_lat,sw_lon,ne_lat,ne_lon` THEN only vessels within bbox returned (using last_position)
- GIVEN `GET /api/vessels` WHEN called with `ship_type=80,81,82` THEN only those types returned
- GIVEN `GET /api/vessels` WHEN called with `sanctions_hit=true` THEN only vessels with non-empty sanctions_status
- GIVEN `GET /api/vessels` WHEN called with `active_since=<datetime>` THEN only vessels with positions after that time
- GIVEN `GET /api/vessels/{mmsi}` WHEN called with valid MMSI THEN return full vessel profile including last position, active anomaly count, latest manual enrichment, sanctions details
- GIVEN `GET /api/vessels/{mmsi}` WHEN called with nonexistent MMSI THEN return 404
- GIVEN `GET /api/vessels/{mmsi}/track` WHEN called THEN return array of {timestamp, lat, lon, sog, cog, draught} chronologically ordered
- GIVEN `GET /api/vessels/{mmsi}/track` WHEN called with `simplify=0.001` THEN apply PostGIS ST_Simplify to reduce points
- GIVEN `GET /api/vessels/{mmsi}/track` WHEN called with `start` and `end` params THEN filter by time range (default: last 24h)
- GIVEN each vessel summary WHEN returned THEN includes: mmsi, imo, name, flag_state, ship_type, risk_tier, risk_score, last_position (lat, lon, sog, cog, timestamp)

**Test Requirements:**

- [ ] Test: GET /api/vessels returns paginated results with total count
- [ ] Test: Risk tier filter returns only matching vessels
- [ ] Test: Bbox filter works with PostGIS spatial query
- [ ] Test: GET /api/vessels/{mmsi} returns full profile for existing vessel
- [ ] Test: GET /api/vessels/{mmsi} returns 404 for nonexistent vessel
- [ ] Test: GET /api/vessels/{mmsi}/track returns chronologically ordered positions
- [ ] Test: Track simplification reduces point count compared to full resolution
- [ ] Test: Pagination params (page, per_page) work correctly

**Technical Notes:**

Use async SQLAlchemy queries. For bbox filtering, use PostGIS ST_Within or ST_Intersects on the latest vessel position. Track simplification uses ST_Simplify on the geography column (cast to geometry first).

---

### Story 3: Anomaly REST Endpoint

**As a** frontend developer
**I want to** query anomaly events globally and per-vessel
**So that** I can display the anomaly feed and vessel risk breakdowns

**Acceptance Criteria:**

- GIVEN `GET /api/anomalies` WHEN called THEN return paginated anomaly feed
- GIVEN `GET /api/anomalies` WHEN called with `severity=critical` THEN only critical anomalies returned
- GIVEN `GET /api/anomalies` WHEN called with `start` and `end` THEN filter by time range
- GIVEN `GET /api/anomalies` WHEN called with `bbox` THEN filter by vessel position at anomaly time
- GIVEN `GET /api/anomalies` WHEN called with `resolved=false` THEN only unresolved anomalies
- GIVEN each anomaly WHEN returned THEN includes full event plus vessel_name and risk_tier

**Test Requirements:**

- [ ] Test: GET /api/anomalies returns paginated results
- [ ] Test: Severity filter works
- [ ] Test: Time range filter works
- [ ] Test: Each anomaly includes joined vessel name and tier

**Technical Notes:**

Join anomaly_events with vessel_profiles to include vessel name and current risk tier in each result.

---

### Story 4: SAR, GFW Events, and Watchlist REST Endpoints

**As a** frontend developer
**I want to** query SAR detections, GFW events, and manage the watchlist
**So that** dark ship data, GFW behavioral events, and vessel monitoring are accessible

**Acceptance Criteria:**

- GIVEN `GET /api/sar/detections` WHEN called THEN return paginated SAR detection list (sourced from GFW 4Wings API via enrichment service)
- GIVEN `GET /api/sar/detections` WHEN called with `is_dark=true` THEN only unmatched detections
- GIVEN `GET /api/sar/detections` WHEN called with `bbox` THEN spatial filter applies
- GIVEN `GET /api/gfw/events` WHEN called THEN return paginated GFW events list
- GIVEN `GET /api/gfw/events` WHEN called with `event_type=ENCOUNTER` THEN only events of that type returned
- GIVEN `GET /api/gfw/events` WHEN called with `mmsi=<mmsi>` THEN only events for that vessel
- GIVEN `GET /api/gfw/events` WHEN called with `start` and `end` THEN filter by time range
- GIVEN `GET /api/watchlist` WHEN called THEN return all watchlisted vessels with notes
- GIVEN `POST /api/watchlist/{mmsi}` WHEN called THEN add vessel to watchlist (body: optional notes)
- GIVEN `DELETE /api/watchlist/{mmsi}` WHEN called THEN remove vessel from watchlist
- GIVEN `POST /api/watchlist/{mmsi}` WHEN vessel not in vessel_profiles THEN return 404

**Test Requirements:**

- [ ] Test: GET /api/sar/detections returns results filtered by is_dark
- [ ] Test: GET /api/gfw/events returns paginated results
- [ ] Test: GET /api/gfw/events filters by event_type
- [ ] Test: GET /api/gfw/events filters by mmsi
- [ ] Test: POST /api/watchlist adds vessel and GET returns it
- [ ] Test: DELETE /api/watchlist removes vessel
- [ ] Test: POST returns 404 for nonexistent MMSI

**Technical Notes:**

Watchlist is simple CRUD against the watchlist table. SAR detections are sourced from GFW 4Wings API and stored by the enrichment service — they may be empty until enrichment runs. GFW events include AIS-disabling, encounters, loitering, and port visits.

---

### Story 5: Enrichment POST Endpoint

**As a** operator
**I want to** submit manual enrichment data for a vessel
**So that** manually researched information is stored and triggers re-scoring

**Acceptance Criteria:**

- GIVEN `POST /api/vessels/{mmsi}/enrich` WHEN called with valid body THEN insert into manual_enrichment table
- GIVEN the POST body WHEN validated THEN it accepts: source (required), ownership_chain (JSONB), pi_insurer, pi_insurer_tier (enum), classification_society, classification_iacs (bool), psc_detentions (int), psc_deficiencies (int), notes (text)
- GIVEN a successful POST WHEN responding THEN return the updated vessel profile (including new enrichment data)
- GIVEN a successful POST WHEN enrichment stored THEN publish re-scoring event to Redis for the vessel
- GIVEN invalid MMSI WHEN posting THEN return 404

**Test Requirements:**

- [ ] Test: POST with valid data creates manual_enrichment row
- [ ] Test: POST with invalid pi_insurer_tier returns 422
- [ ] Test: Response includes updated vessel profile
- [ ] Test: POST for nonexistent MMSI returns 404

**Technical Notes:**

The re-scoring event publishes to `heimdal:positions` with the MMSI to trigger scoring engine re-evaluation.

---

### Story 6: Health and Stats Endpoints

**As a** operator
**I want to** check system health and view platform statistics
**So that** I can verify everything is running and see activity metrics

**Acceptance Criteria:**

- GIVEN `GET /api/health` WHEN called THEN return JSON with: database connectivity (bool), redis connectivity (bool), ais websocket state (from Redis metrics), last position timestamp, vessel count, anomaly count
- GIVEN `GET /api/health` WHEN database is down THEN return 503 with database: false
- GIVEN `GET /api/stats` WHEN called THEN return: total vessels tracked, breakdown by risk tier (green/yellow/red counts), active anomalies by severity, dark ship candidate count, ingestion rate (from Redis), storage usage estimate

**Test Requirements:**

- [ ] Test: GET /api/health returns 200 when all services healthy
- [ ] Test: GET /api/stats returns correct vessel count by tier
- [ ] Test: Stats include ingestion rate from Redis metrics

**Technical Notes:**

Health endpoint checks: `SELECT 1` to PostgreSQL, `PING` to Redis, read `heimdal:metrics:last_message_at` from Redis. Stats endpoint: aggregate queries on vessel_profiles and anomaly_events tables.

---

### Story 7: WebSocket Position Streaming

**As a** frontend client
**I want to** receive real-time vessel position updates via WebSocket
**So that** the globe shows live vessel movement

**Acceptance Criteria:**

- GIVEN `ws://localhost:8000/ws/positions` WHEN connected THEN client can send a subscription filter message with optional: bbox, risk_tiers, ship_types, mmsi_list
- GIVEN a subscription WHEN new positions arrive from Redis channel `heimdal:positions` THEN server filters per client subscription and forwards matching updates
- GIVEN each position update WHEN sent THEN message contains: mmsi, lat, lon, sog, cog, risk_tier, risk_score, timestamp
- GIVEN multiple clients WHEN connected with different filters THEN each receives only their filtered subset

**Test Requirements:**

- [ ] Test: WebSocket connection accepts and holds open
- [ ] Test: Subscription filter message is parsed correctly
- [ ] Test: Position updates are filtered by bbox when specified
- [ ] Test: Position updates are filtered by risk_tier when specified

**Technical Notes:**

Use FastAPI WebSocket support. Subscribe to Redis channel `heimdal:positions` using aioredis. For each Redis message, look up the vessel data and forward to matching clients. Maintain a list of connected clients with their filter preferences.

---

### Story 8: WebSocket Alert Streaming

**As a** frontend client
**I want to** receive real-time risk change and anomaly events via WebSocket
**So that** the UI can show notifications and update risk badges

**Acceptance Criteria:**

- GIVEN `ws://localhost:8000/ws/alerts` WHEN connected THEN client receives all risk_change and anomaly events (no client-side filtering)
- GIVEN a risk_change event from Redis `heimdal:risk_changes` WHEN received THEN forward to all connected alert clients
- GIVEN an anomaly event from Redis `heimdal:anomalies` WHEN received THEN forward to all connected alert clients
- GIVEN the alert payload WHEN sent THEN it includes: type (risk_change or anomaly), mmsi, vessel_name, and event-specific fields

**Test Requirements:**

- [ ] Test: WebSocket connection stays open
- [ ] Test: Risk change events are forwarded to all clients
- [ ] Test: Anomaly events are forwarded to all clients

**Technical Notes:**

Subscribe to both `heimdal:risk_changes` and `heimdal:anomalies` Redis channels. Forward all events to all connected alert clients. No filtering — the frontend decides what to show.

---

## Technical Design

### Data Model Changes

Writes to: `manual_enrichment` (via POST), `watchlist` (via POST/DELETE)
Reads from: all tables

### API Changes

Creates all REST and WebSocket endpoints as specified.

### Dependencies

- FastAPI, Uvicorn
- PostgreSQL (async SQLAlchemy)
- Redis (aioredis for pub/sub)
- Shared library models, config, DB layer

### Security Considerations

- No authentication for local deployment (single-user)
- Input validation via Pydantic models on all POST endpoints
- SQL injection prevention via parameterized queries (SQLAlchemy)

---

## Implementation Order

### Group 1 (parallel)
- Story 1 — App factory and Dockerfile (foundation)
- Story 6 — Health and stats (simple, standalone endpoints)

### Group 2 (parallel — after Group 1)
- Story 2 — Vessel REST endpoints
- Story 3 — Anomaly REST endpoint
- Story 4 — SAR and watchlist endpoints
- Story 5 — Enrichment POST endpoint

### Group 3 (parallel — after Group 1)
- Story 7 — WebSocket position streaming
- Story 8 — WebSocket alert streaming

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All REST endpoints return correct data with proper status codes
- [ ] Pagination works correctly on all list endpoints
- [ ] Filters work correctly (risk_tier, bbox, severity, etc.)
- [ ] WebSocket connections stay open and stream data
- [ ] Health endpoint accurately reports service status
- [ ] Container builds and runs in Docker Compose
- [ ] Code committed with proper messages
- [ ] Ready for human review
