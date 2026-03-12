# Feature Spec: Enrichment Service

**Slug:** `enrichment-service`
**Created:** 2026-03-11
**Updated:** 2026-03-12 (GFW Integration — Update 001)
**Status:** draft
**Priority:** high
**Wave:** 4 (Intelligence Layer)

---

## Overview

Build the enrichment service that periodically batch-processes vessel profiles against external data sources: Global Fishing Watch APIs (4Wings SAR detections, behavioral events, vessel identity), OpenSanctions bulk dataset matching, and optional IMO GISIS/ITU MARS lookups. Updates vessel profiles, stores GFW events and SAR detections, and publishes enrichment-complete events for scoring.

> **Update 001:** GFW APIs are now the primary enrichment source, replacing the custom Copernicus SAR pipeline. Pipeline order: GFW Events → GFW SAR → GFW Vessel Identity → OpenSanctions → optional GISIS/MARS. GISIS and MARS are demoted to optional best-effort fallback.

## Problem Statement

AIS data alone doesn't tell you if a vessel is sanctioned, who owns it, or where it was detected by satellite radar. The enrichment service fills these gaps by consuming Global Fishing Watch's ML-validated satellite analysis and cross-referencing sanctions databases.

## Out of Scope

- NOT: Manual enrichment form (see `12-manual-enrichment`)
- NOT: Scoring rules that consume enrichment data (see `07-scoring-engine`)
- NOT: Custom Copernicus SAR processing (replaced by GFW 4Wings API)
- NOT: Equasis integration (manual-only per ToS)

---

## User Stories

### Story 1: GFW API Client

**As a** the enrichment service
**I want to** authenticate and communicate with Global Fishing Watch APIs
**So that** I can fetch SAR detections, behavioral events, and vessel identity data

**Acceptance Criteria:**

- GIVEN `gfw_client.py` WHEN initialized THEN authenticate using GFW_API_TOKEN env var to obtain a JWT access token
- GIVEN the JWT WHEN expired THEN automatically refresh before making requests
- GIVEN rate limiting WHEN making requests THEN enforce configurable rate limit (default: 50 requests/second, configurable via `config.yaml: gfw.rate_limit_per_second`)
- GIVEN a transient failure (429, 500, 502, 503) WHEN making requests THEN retry with exponential backoff (max 3 retries)
- GIVEN paginated responses WHEN fetching THEN automatically handle pagination to retrieve all results
- GIVEN the GFW API base URL WHEN configured THEN use `config.yaml: gfw.base_url` (default: `https://gateway.api.globalfishingwatch.org`)

**Test Requirements:**

- [ ] Test: JWT token acquisition from GFW API token
- [ ] Test: Automatic token refresh on expiry
- [ ] Test: Rate limiting enforces configured limit
- [ ] Test: Retry logic handles 429 and 5xx errors
- [ ] Test: Pagination fetches all pages

**Technical Notes:**

Use `httpx` for async HTTP. GFW auth: POST token endpoint with API token → receive JWT. Store JWT with expiry tracking. Rate limiting via `asyncio.Semaphore` or token bucket. GFW API limits: 50K requests/day, 1.55M/month.

---

### Story 2: GFW SAR Detections (4Wings API)

**As a** the enrichment pipeline
**I want to** fetch SAR vessel detections from the GFW 4Wings API
**So that** radar-detected vessels (including those not transmitting AIS) are stored

**Acceptance Criteria:**

- GIVEN the 4Wings API WHEN querying THEN fetch SAR detections for configured AOIs within the lookback window (default: 7 days, configurable via `config.yaml: gfw.sar_lookback_days`)
- GIVEN each detection WHEN received THEN extract: gfw_detection_id, position (lat/lon), timestamp, estimated_length, is_dark (AIS-unmatched), matched_mmsi (if matched), matching_score, fishing_score
- GIVEN detections WHEN storing THEN upsert into `sar_detections` table using gfw_detection_id as unique key (no duplicates)
- GIVEN the 4Wings API WHEN no data exists for an AOI THEN handle gracefully (empty result, no error)

**Test Requirements:**

- [ ] Test: 4Wings API query builds correct request with AOI and date range
- [ ] Test: Detections are correctly parsed and mapped to SarDetection model
- [ ] Test: Upsert prevents duplicate gfw_detection_id entries
- [ ] Test: Empty response handled gracefully

**Technical Notes:**

4Wings API endpoint for SAR: `GET /v3/4wings/tile` or equivalent vessel detection endpoint. AOIs come from config.yaml. Detection data includes vessel presence/absence info that maps to is_dark flag.

---

### Story 3: GFW Events (Events API)

**As a** the enrichment pipeline
**I want to** fetch behavioral events from the GFW Events API
**So that** AIS-disabling, encounters, loitering, and port visits are stored for scoring

**Acceptance Criteria:**

- GIVEN the Events API WHEN querying THEN fetch events for all tracked MMSIs within the lookback window (default: 30 days, configurable via `config.yaml: gfw.events_lookback_days`)
- GIVEN event types WHEN filtering THEN request: AIS_DISABLING, ENCOUNTER, LOITERING, PORT_VISIT
- GIVEN each event WHEN received THEN extract: gfw_event_id, event_type, mmsi, start_time, end_time, lat, lon, details (full event JSON), encounter_mmsi (for encounters), port_name (for port visits)
- GIVEN events WHEN storing THEN upsert into `gfw_events` table using gfw_event_id as unique key
- GIVEN the Events API WHEN querying for a specific vessel THEN use the vessel's MMSI to filter

**Test Requirements:**

- [ ] Test: Events API query builds correct request with MMSI and date range
- [ ] Test: All 4 event types are correctly parsed
- [ ] Test: Upsert prevents duplicate gfw_event_id entries
- [ ] Test: encounter_mmsi is extracted for ENCOUNTER events
- [ ] Test: port_name is extracted for PORT_VISIT events

**Technical Notes:**

Events API endpoint: `GET /v3/events` with filters for datasets, event types, and vessel IDs. Process vessels in batches to stay within rate limits. Store the full event details JSON for future reference.

---

### Story 4: GFW Vessel Identity (Vessel API)

**As a** the enrichment pipeline
**I want to** fetch vessel identity and registry data from the GFW Vessel API
**So that** official vessel data (owner, flag, dimensions) from GFW's combined registries is available

**Acceptance Criteria:**

- GIVEN the Vessel API WHEN querying THEN search by MMSI or IMO number
- GIVEN the response WHEN parsed THEN extract: vessel name, flag state, ship type, gross tonnage, deadweight, year built, registered owner, operator, length, beam
- GIVEN the extracted data WHEN storing THEN update `ownership_data` JSONB on vessel_profiles
- GIVEN GFW vessel data WHEN available THEN prefer it over GISIS/MARS data (GFW combines multiple registries)
- GIVEN the Vessel API WHEN caching THEN cache responses for configurable TTL (default: 24 hours, configurable via `config.yaml: gfw.vessel_cache_ttl_hours`)

**Test Requirements:**

- [ ] Test: Vessel API query by MMSI returns identity data
- [ ] Test: ownership_data is updated with extracted fields
- [ ] Test: Cache prevents redundant API calls within TTL

**Technical Notes:**

Vessel API endpoint: `GET /v3/vessels/search` with query parameter. GFW combines AIS, national registries, and other sources into a unified vessel record. Cache in Redis with TTL to reduce API calls.

---

### Story 5: Enrichment Service Runner

**As a** the platform
**I want to** run enrichment in scheduled batch cycles with GFW as primary source
**So that** vessel profiles are periodically updated with intelligence data

**Acceptance Criteria:**

- GIVEN the service WHEN started THEN it runs in a continuous loop with configurable sleep interval (default: 6 hours)
- GIVEN each cycle WHEN triggered THEN query vessel_profiles for vessels where `last_enriched_at IS NULL` or `last_enriched_at < NOW() - interval`
- GIVEN each vessel WHEN enriching THEN run pipeline in order: GFW Events → GFW SAR → GFW Vessel Identity → OpenSanctions → optional GISIS → optional MARS
- GIVEN enrichment completes WHEN updating THEN set `last_enriched_at = NOW()` on vessel_profiles
- GIVEN enrichment completes for a batch WHEN publishing THEN publish to Redis `heimdal:enrichment_complete` with: `{mmsis: [int], gfw_events_count: int, sar_detections_count: int}`
- GIVEN GISIS or MARS WHEN unavailable or failing THEN skip gracefully (these are optional best-effort sources)

**Test Requirements:**

- [ ] Test: Service queries for unenriched vessels correctly
- [ ] Test: Pipeline runs in correct order (GFW first, then OpenSanctions, then optional GISIS/MARS)
- [ ] Test: last_enriched_at is updated after enrichment
- [ ] Test: enrichment_complete event published to Redis with correct payload
- [ ] Test: GISIS/MARS failures don't block the pipeline

**Technical Notes:**

Use `asyncio.sleep()` for the cycle interval. Process vessels in batches (e.g., 50 at a time) to avoid memory issues. Configurable via `config.yaml: enrichment.interval_hours`. The enrichment_complete Redis event triggers scoring engine re-evaluation of GFW-sourced rules.

---

### Story 6: OpenSanctions Bulk Matching

**As a** the enrichment pipeline
**I want to** match vessels against the OpenSanctions bulk dataset
**So that** sanctioned vessels are identified automatically

**Acceptance Criteria:**

- GIVEN the OpenSanctions `default.json` dataset WHEN loaded THEN parse into an in-memory lookup index keyed by IMO, MMSI, and vessel name (normalized)
- GIVEN a vessel with a known IMO WHEN matching THEN check exact IMO match first (highest confidence: 1.0)
- GIVEN a vessel with a known MMSI WHEN matching THEN check exact MMSI match (confidence: 0.9)
- GIVEN a vessel name WHEN matching THEN check fuzzy match using Levenshtein distance <=2 on normalized names (confidence: 0.7)
- GIVEN matches found WHEN storing THEN update `sanctions_status` JSONB with array of matches, each with: entity_id, program, confidence, matched_field
- GIVEN no matches WHEN storing THEN set sanctions_status to empty object

**Test Requirements:**

- [ ] Test: Exact IMO match returns confidence 1.0
- [ ] Test: Exact MMSI match returns confidence 0.9
- [ ] Test: Fuzzy name match with Levenshtein <=2 returns confidence 0.7
- [ ] Test: Name normalization handles case, special characters, spaces
- [ ] Test: No match returns empty sanctions_status

**Technical Notes:**

OpenSanctions bulk download is handled by `scripts/download-opensanctions.sh`. The data is stored in the `opensanctions-data` Docker volume. Re-download weekly. Use `python-Levenshtein` for fast fuzzy matching. Name normalization: lowercase, strip special chars, collapse whitespace.

Create the download script:
```bash
#!/bin/bash
# scripts/download-opensanctions.sh
curl -L https://data.opensanctions.org/datasets/latest/default/entities.ftm.json \
  -o ${OPENSANCTIONS_DATA_PATH:-./data/opensanctions}/default.json
```

---

### Story 7: IMO GISIS and ITU MARS Lookups (Optional Best-Effort)

**As a** the enrichment pipeline
**I want to** optionally look up vessel data from GISIS and MARS as fallback sources
**So that** additional identity verification data is available when GFW data is insufficient

**Acceptance Criteria:**

- GIVEN GISIS WHEN enabled and vessel has IMO THEN query gisis.imo.org for vessel particulars (owner, manager, tonnage, year built)
- GIVEN MARS WHEN enabled and vessel has MMSI THEN query ITU MARS for call sign and flag verification
- GIVEN either service WHEN unavailable or rate-limited THEN skip silently (these are best-effort)
- GIVEN GISIS rate limiting WHEN querying THEN wait at least 5 seconds between requests
- GIVEN MARS rate limiting WHEN querying THEN wait at least 3 seconds between requests
- GIVEN GFW vessel data already populates ownership_data WHEN GISIS returns data THEN merge (GFW takes priority, GISIS fills gaps)

**Test Requirements:**

- [ ] Test: GISIS lookup works when available and vessel has IMO
- [ ] Test: MARS lookup works when available and vessel has MMSI
- [ ] Test: Both services fail gracefully without blocking pipeline
- [ ] Test: GFW data takes priority over GISIS data in ownership_data

**Technical Notes:**

GISIS and MARS are web interfaces (no formal APIs). Rate limiting is critical. These are optional — the platform works fully without them. Configure enable/disable via `config.yaml: enrichment.gisis_enabled` and `enrichment.mars_enabled` (default: false).

---

### Story 8: Flag State Derivation

**As a** the enrichment pipeline
**I want to** derive and compare flag states from multiple sources
**So that** flag manipulation can be detected

**Acceptance Criteria:**

- GIVEN an MMSI WHEN deriving flag THEN extract MID (first 3 digits) and look up in MID_TO_FLAG table
- GIVEN GFW flag, GISIS flag (if available), and MID-derived flag WHEN comparing THEN flag any mismatches
- GIVEN a flag change WHEN detected THEN update flag_history JSONB array on vessel_profiles with {flag, first_seen, last_seen}

**Test Requirements:**

- [ ] Test: MID 273 correctly maps to Russia
- [ ] Test: MID 351 correctly maps to Panama
- [ ] Test: Flag mismatch is detected and recorded

**Technical Notes:**

The MID_TO_FLAG lookup comes from `shared/constants.py`. Flag history is maintained as a JSONB array of objects.

---

### Story 9: Dockerfile and Entry Point

**As a** developer
**I want to** run the enrichment service as a Docker container
**So that** it operates on schedule within Docker Compose

**Acceptance Criteria:**

- GIVEN the Dockerfile WHEN built THEN Python 3.12 with shared base + httpx, python-Levenshtein
- GIVEN the container WHEN started THEN main.py begins the enrichment cycle loop
- GIVEN `requirements.txt` WHEN read THEN includes shared base + `httpx>=0.27` + `python-Levenshtein>=0.25`

**Test Requirements:**

- [ ] Test: Dockerfile builds without errors

---

## Technical Design

### Data Model Changes

Writes to: `sar_detections` (GFW 4Wings data), `gfw_events` (GFW Events API data), `vessel_profiles` (sanctions_status, ownership_data, flag_history, last_enriched_at)
Reads from: `vessel_profiles`

### Dependencies

- Global Fishing Watch APIs (4Wings, Events, Vessel) — primary enrichment source
- OpenSanctions bulk dataset (downloaded via script)
- IMO GISIS (web interface, rate-limited, optional)
- ITU MARS (web interface, rate-limited, optional)
- Shared library (models, config, constants, DB layer)

### External API Dependencies

| API | Auth | Rate Limits | Data Delay |
|-----|------|-------------|------------|
| GFW 4Wings API | GFW API token → JWT | 50K req/day, 1.55M/month | ~3-5 days |
| GFW Events API | GFW API token → JWT | Same pool | ~3-5 days |
| GFW Vessel API | GFW API token → JWT | Same pool | Near real-time |
| OpenSanctions | None (bulk download) | N/A | Weekly updates |
| IMO GISIS | None (web scraping) | 5s between requests | N/A |
| ITU MARS | None (web scraping) | 3s between requests | N/A |

---

## Implementation Order

### Group 1 (sequential — GFW client is foundation)
- Story 1 — GFW API client (auth, rate limiting, pagination)

### Group 2 (parallel — after Group 1)
- Story 2 — GFW SAR detections (uses GFW client)
- Story 3 — GFW events (uses GFW client)
- Story 4 — GFW vessel identity (uses GFW client)
- Story 6 — OpenSanctions matching (independent, no GFW dependency)
- Story 8 — Flag state derivation (uses constants, independent logic)

### Group 3 (after Group 2)
- Story 7 — GISIS/MARS optional lookups (may use flag derivation results)
- Story 5 — Service runner (orchestrates all enrichment steps)

### Group 4 (after Group 3)
- Story 9 — Dockerfile

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] GFW API client authenticates and handles rate limiting
- [ ] GFW SAR detections fetched and stored in sar_detections table
- [ ] GFW events fetched and stored in gfw_events table
- [ ] GFW vessel identity data updates ownership_data
- [ ] OpenSanctions matching works with bulk dataset
- [ ] GISIS/MARS are optional and fail gracefully
- [ ] enrichment_complete event published to Redis
- [ ] Failures handled gracefully (skip + retry)
- [ ] Container builds and runs
- [ ] Code committed with proper messages
- [ ] Ready for human review
