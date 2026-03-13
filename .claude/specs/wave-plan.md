# Heimdal Build Wave Plan

**Created:** 2026-03-11
**Updated:** 2026-03-13 (Equasis Upload — Update 003)
**Status:** draft
**Total Specs:** 22
**Total Waves:** 10

---

## Wave Overview

Specs within the same wave can be implemented in parallel (by separate sessions/agents).
Waves must run sequentially — each wave depends on the previous completing.

> **Update 001:** Replaced custom SAR processor (Copernicus + CFAR pipeline) with Global Fishing Watch API integration. SAR detections, AIS-disabling events, encounter/loitering detection, and vessel identity now consumed via GFW APIs through the enrichment service. This removes 1 container, 1 spec, and ~2-3 weeks from the build.

> **Update 002:** Added Wave 8 (Scoring Overhaul + Observability) and Wave 9 (Enrichment Escalation + Performance). Wave 8 fixes critical scoring issues: event lifecycle model (anomalies with start/end), port awareness to eliminate false positives, repeat-event escalation, and 4 new detection rules based on CREA/Windward/Kpler/S&P Global shadow fleet intelligence (AIS spoofing, ownership risk, insurance/classification risk, voyage patterns). Also adds structured JSON logging and service health monitoring. Wave 9 adds tier-triggered enrichment (yellow vessels get immediate ownership/classification deep-dive) and performance optimization (profiling, scoring debounce, bundle splitting).

> **Update 003:** Added Wave 10 (Equasis PDF Upload). Operators can upload Equasis Ship Folder PDFs to enrich vessels with comprehensive registry data: management chain, classification status/surveys, PSC inspection history, flag history, name history, company history, and safety certificates. Server-side PDF parsing with pdfplumber, two upload entry points (vessel panel + standalone toolbar button), expandable vessel information display, and scoring rule enhancements for PSC detentions and classification withdrawals.

### Wave 1 — Foundation Infrastructure (3 specs, parallel)
No dependencies. Start here.

| Spec | Slug | Scope |
|------|------|-------|
| 01 | `infrastructure` | Docker Compose, Makefile, .env.example, config.yaml, project root scaffolding |
| 02 | `database` | PostgreSQL Dockerfile, migrations 001–004, init.sh (includes gfw_events table) |
| 03 | `shared-library` | Pydantic models (incl. GFW event models), async DB connection, config loading, constants |

### Wave 2 — Data Pipeline (2 specs, parallel)
Depends on: Wave 1

| Spec | Slug | Scope |
|------|------|-------|
| 04 | `ais-ingest` | WebSocket consumer, AIS message parser, batch writer, Redis dedup, metrics |
| 05 | `frontend-shell` | Vite + React + CesiumJS scaffold, basic globe, app layout, Dockerfile, nginx.conf |

### Wave 3 — API Layer (1 spec)
Depends on: Wave 2

| Spec | Slug | Scope |
|------|------|-------|
| 06 | `api-server` | FastAPI app, all REST endpoints (incl. GFW events), both WebSocket endpoints, Dockerfile |

### Wave 4 — Intelligence Layer (2 specs, parallel)
Depends on: Wave 3

| Spec | Slug | Scope |
|------|------|-------|
| 07 | `scoring-engine` | Rule framework, 5 GFW-sourced rules + 8 real-time rules, dedup logic, score aggregation, tier calculation |
| 08 | `enrichment-service` | GFW API client (4Wings SAR, Events, Vessel), OpenSanctions, optional GISIS/MARS fallback |

### Wave 5 — Frontend Features (3 specs, parallel)
Depends on: Waves 3–4

| Spec | Slug | Scope |
|------|------|-------|
| 09 | `globe-rendering` | Vessel markers, clustering, geographic overlays, track trails |
| 10 | `vessel-detail-panel` | Side panel: identity, status, risk, voyage timeline, sanctions, ownership, GFW events |
| 11 | `controls-and-filtering` | Search bar, risk/type/time filters, stats bar, health indicator |

### Wave 6 — Advanced Features (2 specs, parallel)
Depends on: Wave 5

| Spec | Slug | Scope |
|------|------|-------|
| 12 | `manual-enrichment` | Enrichment form in detail panel, POST integration, re-scoring trigger |
| 13 | `watchlist-notifications` | Watchlist CRUD, browser desktop notifications, alert WebSocket |

### Wave 7 — Polish (3 specs, parallel) [COMPLETED]
Depends on: Wave 6

| Spec | Slug | Scope |
|------|------|-------|
| 14 | `sar-frontend` | GFW SAR detection markers, GFW event markers, dark ship filter |
| 15 | `stats-and-replay` | Stats dashboard, health indicators, track replay animation |
| 16 | `testing-and-docs` | Unit tests (incl. GFW client/rules), integration tests, performance benchmarks, README |

### Wave 8 — Scoring Overhaul & Observability (3 specs, parallel)
Depends on: Wave 7

| Spec | Slug | Scope |
|------|------|-------|
| 17 | `event-scoring-model` | Event lifecycle (start/end) for anomalies, port awareness, repeat-event escalation, GFW multi-event handling, scoring debounce |
| 18 | `enhanced-detection-rules` | 4 new rules (AIS spoofing, ownership risk, insurance/classification, voyage patterns), extended STS hotspots, rule weight rebalancing |
| 19 | `logging-observability` | Structured JSON logging, API call duration tracking, service heartbeats, scoring pipeline performance metrics, DB query monitoring |

### Wave 9 — Enrichment Escalation & Performance (2 specs, parallel)
Depends on: Wave 8

| Spec | Slug | Scope |
|------|------|-------|
| 20 | `yellow-enrichment-path` | Tier-change triggered enrichment, enhanced ownership/classification lookup, adaptive enrichment frequency, enrichment status tracking |
| 21 | `performance-optimization` | CPU profiling, scoring engine debounce+batching, DB query optimization, AIS ingest pipeline optimization, frontend bundle splitting |

### Wave 10 — Equasis PDF Upload (1 spec)
Depends on: Wave 6 (manual-enrichment), Wave 8 (enhanced-detection-rules)

| Spec | Slug | Scope |
|------|------|-------|
| 22 | `equasis-upload` | Equasis Ship Folder PDF parsing, upload API, vessel panel + standalone upload UI, expanded vessel information display, scoring enhancements for PSC/classification/flag history |

---

## Build Order Diagram

```
Wave 1:  [01-infrastructure] [02-database] [03-shared-library]           ← COMPLETED
              │                    │              │
              └────────────────────┴──────────────┘
                                   │
Wave 2:              [04-ais-ingest] [05-frontend-shell]                  ← COMPLETED
                          │              │
                          └──────────────┘
                                   │
Wave 3:                    [06-api-server]                                ← COMPLETED
                                   │
Wave 4:      [07-scoring-engine] [08-enrichment+GFW]                     ← COMPLETED
                       │                    │
                       └────────────────────┘
                                   │
Wave 5:  [09-globe-rendering] [10-vessel-detail] [11-controls-filtering] ← COMPLETED
              │                    │                    │
              └────────────────────┴────────────────────┘
                                   │
Wave 6:       [12-manual-enrichment] [13-watchlist]                      ← COMPLETED
                       │                    │
                       └────────────────────┘
                                   │
Wave 7:  [14-sar-frontend] [15-stats-replay] [16-testing-docs]           ← COMPLETED
                       │                    │
                       └────────────────────┘
                                   │
Wave 8:  [17-event-scoring] [18-detection-rules] [19-logging-observability]
                       │              │                    │
                       └──────────────┴────────────────────┘
                                   │
Wave 9:       [20-yellow-enrichment] [21-performance-optimization]
                       │                    │
                       └────────────────────┘
                                   │
Wave 10:                  [22-equasis-upload]
```

---

## Interface Contracts (fixed across all waves)

### Redis Channels
| Channel | Publisher | Subscriber | Payload |
|---------|-----------|------------|---------|
| `heimdal:positions` | ais-ingest | scoring, api-server | `{mmsis: [int], timestamp: str, count: int}` |
| `heimdal:risk_changes` | scoring | api-server, enrichment (Wave 8+) | `{mmsi, old_tier, new_tier, score, trigger_rule, timestamp}` |
| `heimdal:anomalies` | scoring | api-server | `{mmsi, rule_id, severity, points, details, timestamp}` |
| `heimdal:enrichment_complete` | enrichment | scoring | `{mmsis: [int], gfw_events_count: int, sar_detections_count: int}` |

### Redis Keys
| Key Pattern | Owner | Type |
|-------------|-------|------|
| `heimdal:dedup:{mmsi}:{ts}` | ais-ingest | SET (TTL 10s) |
| `heimdal:last_seen` | scoring | HASH (mmsi → ts) |
| `heimdal:sts_entry:{mmsi}` | scoring | HASH |
| `heimdal:metrics:*` | ais-ingest | STRING |
| `heimdal:heartbeat:{service}` | all services (Wave 8+) | STRING (TTL 120s) |
| `heimdal:enrichment_triggered` | enrichment (Wave 9+) | HASH (mmsi → ts) |
| `heimdal:scoring_debounce:{mmsi}` | scoring (Wave 9+) | STRING (TTL configurable) |

### Database Table Ownership
| Table | Primary Writer | Readers |
|-------|---------------|---------|
| vessel_positions | ais-ingest | scoring, api-server |
| vessel_profiles | ais-ingest (create), enrichment (update), scoring (risk fields) | api-server, scoring |
| anomaly_events | scoring | api-server |
| sar_detections | enrichment (from GFW 4Wings API) | api-server, scoring |
| gfw_events | enrichment (from GFW Events API) | api-server, scoring |
| manual_enrichment | api-server | scoring, api-server |
| watchlist | api-server | api-server |
| zones | seed data (init.sh) | scoring, api-server |
| ports | seed data (Wave 8+) | scoring |
| equasis_data | api-server (Wave 10+) | api-server, scoring |

### External API Dependencies
| API | Consumer | Auth | Rate Limits |
|-----|----------|------|-------------|
| aisstream.io WebSocket | ais-ingest | API key | None (streaming) |
| GFW 4Wings API | enrichment | GFW API token → JWT | 50K req/day, 1.55M/month |
| GFW Events API | enrichment | GFW API token → JWT | Same |
| GFW Vessel API | enrichment | GFW API token → JWT | Same |
| OpenSanctions bulk | enrichment | None (download) | N/A |
