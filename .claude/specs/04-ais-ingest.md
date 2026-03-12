# Feature Spec: AIS Ingest Service

**Slug:** `ais-ingest`
**Created:** 2026-03-11
**Status:** draft
**Priority:** critical
**Wave:** 2 (Data Pipeline)

---

## Overview

Build the AIS ingest service that maintains a persistent WebSocket connection to aisstream.io, parses incoming AIS messages (position reports and static data), validates and deduplicates them, batch-inserts positions into TimescaleDB, upserts vessel profiles, and publishes events to Redis for downstream consumers.

## Problem Statement

Heimdal needs a continuous stream of real-time AIS data. The ingest service is the single entry point for all vessel position and identity data flowing into the platform.

## Out of Scope

- NOT: Scoring or risk assessment (see `07-scoring-engine`)
- NOT: API endpoints to query the data (see `06-api-server`)
- NOT: Frontend rendering of positions (see `05-frontend-shell`)
- NOT: Satellite AIS or alternate AIS providers

---

## User Stories

### Story 1: WebSocket Connection Management

**As a** platform operator
**I want to** maintain a persistent, auto-reconnecting WebSocket connection to aisstream.io
**So that** AIS data flows continuously even through network interruptions

**Acceptance Criteria:**

- GIVEN the service starts WHEN connecting to aisstream.io THEN it sends a subscription message with API key, bounding boxes from config, optional MMSI filter, and message type filter (PositionReport, ShipStaticData)
- GIVEN a connection drop WHEN reconnecting THEN exponential backoff is used: 1s, 2s, 4s, 8s, 16s, max 60s
- GIVEN a successful message received WHEN backoff is active THEN backoff timer resets
- GIVEN an active connection WHEN no message received for 120 seconds THEN force reconnect (stale connection detection)
- GIVEN connection state changes WHEN logging THEN state (connected, disconnected, reconnecting) is logged with timestamps

**Test Requirements:**

- [ ] Test: Subscription message format matches aisstream.io API spec
- [ ] Test: Exponential backoff doubles correctly and caps at max
- [ ] Test: Backoff resets on successful message
- [ ] Test: Stale connection detection triggers after configurable timeout

**Technical Notes:**

Use `websockets` Python library for async WebSocket. The connection URL and API key come from environment variables. Bounding boxes and message type filters come from config.yaml.

---

### Story 2: AIS Message Parser

**As a** the ingest pipeline
**I want to** parse PositionReport and ShipStaticData messages from aisstream.io JSON
**So that** only valid, normalized data enters the database

**Acceptance Criteria:**

- GIVEN a PositionReport JSON message WHEN parsed THEN timestamp, mmsi, lat, lon, sog, cog, heading, nav_status, rot, draught are extracted using the field mapping from the build spec
- GIVEN a ShipStaticData JSON message WHEN parsed THEN imo, name, call_sign, ship_type, destination, eta, draught, length (A+B), beam (C+D) are extracted
- GIVEN an invalid MMSI (not 9 digits, or 000000000) WHEN parsing THEN the message is rejected and logged
- GIVEN out-of-range coordinates (lat=91, lon=181) WHEN parsing THEN the message is rejected
- GIVEN SOG=102.3 or COG=360 or heading=511 WHEN parsing THEN those fields are set to None (not available)
- GIVEN ROT=-128 WHEN parsing THEN ROT is set to None (not available)

**Test Requirements:**

- [ ] Test: Parse valid PositionReport from sample fixture, verify all fields extracted
- [ ] Test: Parse valid ShipStaticData, verify length = dimension.A + dimension.B
- [ ] Test: Reject message with MMSI 000000000
- [ ] Test: Reject message with latitude 91
- [ ] Test: Set SOG to None when value is 102.3
- [ ] Test: Parse all message types from sample_ais_messages.json fixture

**Technical Notes:**

Create `tests/fixtures/sample_ais_messages.json` with 50+ real-format messages covering all edge cases. The Pydantic models from `shared/models/ais_message.py` handle validation — the parser maps aisstream.io JSON paths to model fields.

---

### Story 3: Batch Writer with COPY Protocol

**As a** the ingest pipeline
**I want to** batch-insert positions into TimescaleDB using the COPY protocol
**So that** high-throughput ingestion is possible (target: >2000 positions/sec)

**Acceptance Criteria:**

- GIVEN incoming positions WHEN buffered THEN flush to PostgreSQL when buffer reaches 500 records OR 2 seconds elapsed, whichever comes first
- GIVEN a flush WHEN inserting positions THEN use asyncpg COPY protocol for bulk insert into vessel_positions
- GIVEN a flush WHEN updating vessels THEN upsert vessel_profiles using INSERT ON CONFLICT DO UPDATE for new MMSIs or static data updates
- GIVEN a successful flush WHEN publishing events THEN publish to Redis channel `heimdal:positions` with payload `{mmsis: [int], timestamp: str, count: int}`
- GIVEN the service WHEN running THEN it updates `last_position_at` on vessel_profiles for each position

**Test Requirements:**

- [ ] Test: Buffer flushes at 500 records (size trigger)
- [ ] Test: Buffer flushes at 2 seconds (time trigger)
- [ ] Test: Positions are correctly inserted into vessel_positions table
- [ ] Test: vessel_profiles are created on first MMSI encounter
- [ ] Test: vessel_profiles are updated on subsequent static data messages
- [ ] Test: Redis event is published on each flush with correct MMSI list

**Technical Notes:**

asyncpg COPY is the fastest PostgreSQL insert method for TimescaleDB. Use `connection.copy_records_to_table()`. For vessel profile upserts, use a prepared INSERT ON CONFLICT statement.

---

### Story 4: Redis Deduplication

**As a** the ingest pipeline
**I want to** deduplicate AIS messages using Redis
**So that** multiple terrestrial receivers reporting the same message don't create duplicate positions

**Acceptance Criteria:**

- GIVEN an incoming message WHEN checking dedup THEN create Redis key `heimdal:dedup:{mmsi}:{timestamp_rounded_to_second}` as a SET with TTL 10 seconds
- GIVEN the dedup key exists WHEN a duplicate arrives THEN skip the message
- GIVEN the dedup key does not exist WHEN a new message arrives THEN process it and set the key

**Test Requirements:**

- [ ] Test: First message with a given MMSI+timestamp is processed
- [ ] Test: Second message with same MMSI+timestamp within 10s is rejected
- [ ] Test: Message with same MMSI but different timestamp is processed
- [ ] Test: After TTL expiry, same key can be reused

**Technical Notes:**

Use Redis SET NX with EX 10. Key format: `heimdal:dedup:{mmsi}:{ts}` where ts is the AIS timestamp rounded to nearest second.

---

### Story 5: Metrics Publishing

**As a** a platform operator
**I want to** monitor ingestion health via Redis metrics
**So that** I can verify the system is receiving and processing AIS data

**Acceptance Criteria:**

- GIVEN the service is running WHEN positions are ingested THEN `heimdal:metrics:ingest_rate` is updated with positions/sec (rolling 60s average)
- GIVEN the service is running WHEN messages arrive THEN `heimdal:metrics:last_message_at` is updated with ISO timestamp
- GIVEN the service is running WHEN tracking vessels THEN `heimdal:metrics:total_vessels` reflects unique MMSI count this session

**Test Requirements:**

- [ ] Test: ingest_rate updates correctly after a batch of positions
- [ ] Test: last_message_at updates on each message
- [ ] Test: total_vessels increments on new MMSI, stays same on existing

**Technical Notes:**

Use Redis SET for simple string values. Calculate rolling average using a sliding window in memory.

---

### Story 6: Dockerfile and Entry Point

**As a** developer
**I want to** build and run the AIS ingest service as a Docker container
**So that** it integrates with the Docker Compose orchestration

**Acceptance Criteria:**

- GIVEN the Dockerfile WHEN built THEN it creates a Python 3.12 container with all dependencies from requirements.txt
- GIVEN the container WHEN started THEN `main.py` runs and connects to aisstream.io
- GIVEN `requirements.txt` WHEN read THEN it includes the shared base requirements plus `websockets>=12.0,<13`

**Test Requirements:**

- [ ] Test: Dockerfile builds without errors
- [ ] Test: requirements.txt includes all needed packages

**Technical Notes:**

Standard Python Dockerfile: FROM python:3.12-slim, COPY requirements, pip install, COPY app code, CMD python main.py. Mount shared/ as volume.

---

## Technical Design

### Data Model Changes

Writes to: `vessel_positions` (bulk insert), `vessel_profiles` (upsert)

### API Changes

None — this service has no API.

### Dependencies

- aisstream.io API key (env: AIS_API_KEY)
- PostgreSQL with TimescaleDB (from `02-database`)
- Redis for dedup and pub/sub
- Shared library models and config (from `03-shared-library`)

### Security Considerations

- API key stored in env variable, never logged
- Database credentials in DATABASE_URL env var

---

## Implementation Order

### Group 1 (parallel)
- Story 2 — Parser (pure logic, no I/O dependencies)
- Story 4 — Deduplication (Redis only, independent)
- Story 5 — Metrics (Redis only, independent)

### Group 2 (sequential — after Group 1)
- Story 3 — Batch writer (needs parser output format)
- Story 1 — WebSocket connection (needs parser + writer)

### Group 3 (after Group 2)
- Story 6 — Dockerfile (needs all source files)

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] Parser handles all AIS message types and edge cases
- [ ] Batch writer achieves >2000 positions/sec on COPY protocol
- [ ] Deduplication prevents duplicate inserts
- [ ] Metrics update in real-time
- [ ] Container builds and runs in Docker Compose
- [ ] Code committed with proper messages
- [ ] Ready for human review
