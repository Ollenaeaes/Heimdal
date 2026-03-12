# Heimdal Build Wave Plan

**Created:** 2026-03-11
**Updated:** 2026-03-12 (GFW Integration — Update 001)
**Status:** draft
**Total Specs:** 16
**Total Waves:** 7

---

## Wave Overview

Specs within the same wave can be implemented in parallel (by separate sessions/agents).
Waves must run sequentially — each wave depends on the previous completing.

> **Update 001:** Replaced custom SAR processor (Copernicus + CFAR pipeline) with Global Fishing Watch API integration. SAR detections, AIS-disabling events, encounter/loitering detection, and vessel identity now consumed via GFW APIs through the enrichment service. This removes 1 container, 1 spec, and ~2-3 weeks from the build.

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

### Wave 7 — Polish (3 specs, parallel)
Depends on: Wave 6

| Spec | Slug | Scope |
|------|------|-------|
| 14 | `sar-frontend` | GFW SAR detection markers, GFW event markers, dark ship filter |
| 15 | `stats-and-replay` | Stats dashboard, health indicators, track replay animation |
| 16 | `testing-and-docs` | Unit tests (incl. GFW client/rules), integration tests, performance benchmarks, README |

---

## Build Order Diagram

```
Wave 1:  [01-infrastructure] [02-database] [03-shared-library]
              │                    │              │
              └────────────────────┴──────────────┘
                                   │
Wave 2:              [04-ais-ingest] [05-frontend-shell]
                          │              │
                          └──────────────┘
                                   │
Wave 3:                    [06-api-server]
                                   │
Wave 4:      [07-scoring-engine] [08-enrichment+GFW]
                       │                    │
                       └────────────────────┘
                                   │
Wave 5:  [09-globe-rendering] [10-vessel-detail] [11-controls-filtering]
              │                    │                    │
              └────────────────────┴────────────────────┘
                                   │
Wave 6:       [12-manual-enrichment] [13-watchlist]
                       │                    │
                       └────────────────────┘
                                   │
Wave 7:  [14-sar-frontend] [15-stats-replay] [16-testing-docs]
```

---

## Interface Contracts (fixed across all waves)

### Redis Channels
| Channel | Publisher | Subscriber | Payload |
|---------|-----------|------------|---------|
| `heimdal:positions` | ais-ingest | scoring, api-server | `{mmsis: [int], timestamp: str, count: int}` |
| `heimdal:risk_changes` | scoring | api-server | `{mmsi, old_tier, new_tier, score, trigger_rule, timestamp}` |
| `heimdal:anomalies` | scoring | api-server | `{mmsi, rule_id, severity, points, details, timestamp}` |
| `heimdal:enrichment_complete` | enrichment | scoring | `{mmsis: [int], gfw_events_count: int, sar_detections_count: int}` |

### Redis Keys
| Key Pattern | Owner | Type |
|-------------|-------|------|
| `heimdal:dedup:{mmsi}:{ts}` | ais-ingest | SET (TTL 10s) |
| `heimdal:last_seen` | scoring | HASH (mmsi → ts) |
| `heimdal:sts_entry:{mmsi}` | scoring | HASH |
| `heimdal:metrics:*` | ais-ingest | STRING |

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

### External API Dependencies
| API | Consumer | Auth | Rate Limits |
|-----|----------|------|-------------|
| aisstream.io WebSocket | ais-ingest | API key | None (streaming) |
| GFW 4Wings API | enrichment | GFW API token → JWT | 50K req/day, 1.55M/month |
| GFW Events API | enrichment | GFW API token → JWT | Same |
| GFW Vessel API | enrichment | GFW API token → JWT | Same |
| OpenSanctions bulk | enrichment | None (download) | N/A |
