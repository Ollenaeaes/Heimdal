# Heimdal Build Wave Plan

**Created:** 2026-03-11
**Updated:** 2026-03-19 (User Auth & Notifications — Update 006)
**Status:** draft
**Total Specs:** 34
**Total Waves:** 16

---

## Wave Overview

Specs within the same wave can be implemented in parallel (by separate sessions/agents).
Waves must run sequentially — each wave depends on the previous completing.

> **Update 001:** Replaced custom SAR processor (Copernicus + CFAR pipeline) with Global Fishing Watch API integration. SAR detections, AIS-disabling events, encounter/loitering detection, and vessel identity now consumed via GFW APIs through the enrichment service. This removes 1 container, 1 spec, and ~2-3 weeks from the build.

> **Update 002:** Added Wave 8 (Scoring Overhaul + Observability) and Wave 9 (Enrichment Escalation + Performance). Wave 8 fixes critical scoring issues: event lifecycle model (anomalies with start/end), port awareness to eliminate false positives, repeat-event escalation, and 4 new detection rules based on CREA/Windward/Kpler/S&P Global shadow fleet intelligence (AIS spoofing, ownership risk, insurance/classification risk, voyage patterns). Also adds structured JSON logging and service health monitoring. Wave 9 adds tier-triggered enrichment (yellow vessels get immediate ownership/classification deep-dive) and performance optimization (profiling, scoring debounce, bundle splitting).

> **Update 003:** Added Wave 10 (Equasis PDF Upload). Operators can upload Equasis Ship Folder PDFs to enrich vessels with comprehensive registry data: management chain, classification status/surveys, PSC inspection history, flag history, name history, company history, and safety certificates. Server-side PDF parsing with pdfplumber, two upload entry points (vessel panel + standalone toolbar button), expandable vessel information display, and scoring rule enhancements for PSC detentions and classification withdrawals.

> **Update 005:** Inserted Wave 12 (Operations Centre Visual Theme) before capability module frontends. Full frontend restyle to maritime VTS aesthetic: dark navy globe, chevron vessel markers with tier-differentiated glow/pulse, HUD status bar, dense sharp-cornered panels, Inter + JetBrains Mono typography. Former Waves 12-13 renumbered to 13-14. Total: 29 specs across 14 waves.

> **Update 004:** Added Waves 11–13 (Capability Modules). Three modules extending Heimdal from sanctions compliance into maritime domain awareness: (1) Critical Infrastructure Protection — 3 rules detecting anchor-drag sabotage patterns near subsea cables/pipelines, with globe overlays and dashboard panel; (2) AIS Spoofing Detection — 5 new rules (stacking with existing ais_spoofing) covering position-on-land, impossible speed, duplicate MMSI, frozen positions, and zombie vessel identity theft, plus GNSS interference zone clustering; (3) Sanctions Evasion Network Mapping — encounter/ownership graph construction, network risk score propagation, d3-force network visualization. Backend and frontend split into separate specs per module (6 specs total). New DB tables: infrastructure_routes, infrastructure_events, land_mask, gnss_interference_zones, network_edges.

> **Update 006:** Added Waves 15–16 (User Auth & Email Notifications). Major pivot from D4 ("no auth, single-user workstation") to multi-user with email-based registration via heimdalwatch.cloud. Wave 15 adds JWT auth backend (users table, SMTP email, registration/confirmation/login, endpoint protection, inactivity lifecycle) and auth frontend (login modal, feature gating, session management). Wave 16 migrates watchlist to per-user, adds geofence watch rules ("alert me when sanctioned vessel enters this bbox"), and email notification engine via alerts@heimdalwatch.cloud. 3 new specs, 2 new waves. Total: 33 specs across 16 waves.

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

### Wave 11 — Capability Modules: Backend (3 specs, parallel)
Depends on: Wave 8 (scoring engine with event lifecycle), Wave 4 (GFW enrichment)

| Spec | Slug | Scope |
|------|------|-------|
| 23 | `infrastructure-protection-backend` | infrastructure_routes + infrastructure_events tables, data loading script, infra_helpers.py, 3 rules (cable_slow_transit, cable_alignment, infra_speed_anomaly) |
| 24 | `spoofing-detection-backend` | land_mask + gnss_interference_zones tables, GSHHG data loading, 5 rules (spoof_land_position, spoof_impossible_speed, spoof_duplicate_mmsi, spoof_frozen_position, spoof_identity_mismatch), GNSS clustering |
| 25 | `network-mapping-backend` | network_edges table, network_repository, encounter/proximity/ownership edge creation, network risk scoring, network API endpoints |

### Wave 12 — Operations Centre Visual Theme (1 spec)
Depends on: Wave 5 (frontend components exist to restyle)

| Spec | Slug | Scope |
|------|------|-------|
| 29 | `operations-centre-theme` | Dark navy globe, chevron vessel markers with tier-differentiated glow/pulse, HUD top bar, dense sharp-cornered panels, Inter + JetBrains Mono typography, updated colour palette, track trail tapering with AIS gap dashes |

### Wave 13 — Capability Modules: Frontend — Infrastructure & Spoofing (2 specs, parallel)
Depends on: Wave 11 (specs 23, 24), Wave 12 (visual theme established)

| Spec | Slug | Scope |
|------|------|-------|
| 26 | `infrastructure-protection-frontend` | Cable/pipeline globe overlay, point features (landing stations, wind farms, platforms), infrastructure risk halos, infrastructure dashboard panel |
| 27 | `spoofing-detection-frontend` | Dashed spoof marker borders, duplicate MMSI connector lines, GNSS interference zone overlay |

### Wave 14 — Capability Modules: Frontend — Network (1 spec)
Depends on: Wave 11 (spec 25), Wave 13 (for consistent frontend patterns)

| Spec | Slug | Scope |
|------|------|-------|
| 28 | `network-mapping-frontend` | Network score display, d3-force network graph tab, globe network mode, vessel chain view |

### Wave 15 — User Authentication (2 specs, sequential with parallel stories)
Depends on: Wave 3 (api-server), Wave 6 (watchlist), Wave 12 (frontend theme)

| Spec | Slug | Scope |
|------|------|-------|
| 31 | `auth-backend` | Users table, JWT auth, email registration/confirmation/login, SMTP via Hostinger, auth middleware, inactivity lifecycle (6mo disable + 2wk warning), endpoint protection |
| 32 | `auth-frontend` | Login modal (no login wall — globe always visible), registration flow, confirmation page, auth Zustand store, authFetch utility, feature gating (watchlist/lookback/export require login), HUD user menu |

**Implementation notes:**
- Backend stories 1-3 (DB + SMTP + JWT) run in parallel first
- Backend stories 4-5 (register/login endpoints) next
- Frontend can start Story 1 (auth store) in parallel with backend Story 3 (JWT)
- Frontend Stories 2-5 depend on backend endpoints being available
- SMTP setup requires `alerts@heimdalwatch.cloud` email account created in Hostinger hPanel (manual, one-time)

### Wave 16 — User-Scoped Features & Notifications (2 specs, parallel)
Depends on: Wave 15 (auth backend + frontend)

| Spec | Slug | Scope |
|------|------|-------|
| 33 | `user-notifications` | Per-user watchlist migration, watch rules (vessel + geofence), notification engine (Redis event matching → email), digest modes (immediate/hourly/daily), rate limiting (50 emails/day/user), watch rules panel, notification bell, email templates via alerts@heimdalwatch.cloud |
| 34 | `bulk-track-export` | Async bulk track data export (DB + cold Parquet), background job queue (DB table, single-worker, CPU-conscious), gzip-compressed JSON/CSV, email with download link when ready, 5-day link expiry with auto-purge, max 3 pending per user |

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
Wave 8:  [17-event-scoring] [18-detection-rules] [19-logging-observability] ← COMPLETED
                       │              │                    │
                       └──────────────┴────────────────────┘
                                   │
Wave 9:       [20-yellow-enrichment] [21-performance-optimization]       ← COMPLETED
                       │                    │
                       └────────────────────┘
                                   │
Wave 10:                  [22-equasis-upload]                             ← COMPLETED
                                   │
Wave 11: [23-infra-backend] [24-spoofing-backend] [25-network-backend]   ← COMPLETED
                       │              │                    │
                       └──────────────┴────────────────────┘
                                   │
Wave 12:            [29-operations-centre-theme]                         ← COMPLETED
                                   │
Wave 13:       [26-infra-frontend] [27-spoofing-frontend]                ← COMPLETED
                       │                    │
                       └────────────────────┘
                                   │
Wave 14:               [28-network-frontend]                             ← COMPLETED
                                   │
                                   │
              ═══════════════════════════════════════
              ║  USER AUTH & NOTIFICATIONS PIVOT    ║
              ║  (Reverses D4: no-auth → multi-user)║
              ═══════════════════════════════════════
                                   │
Wave 15:       [31-auth-backend] → [32-auth-frontend]
               │ DB + SMTP + JWT │   │ Login modal    │
               │ Register/login  │   │ Feature gating │
               │ Auth middleware  │   │ Auth store     │
               │ Inactivity life │   │ Session mgmt   │
                       │                    │
                       └────────────────────┘
                                   │
Wave 16:  [33-user-notifications]    [34-bulk-track-export]
          │ Per-user watchlist  │    │ Async job queue     │
          │ Geofence watch rules│    │ DB + Parquet reader │
          │ Email alerts engine │    │ Gzip streaming      │
          │ Notification bell   │    │ Email download link │
          │ Digest batching     │    │ 5-day expiry+purge  │
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
| `heimdal:cable_entry:{mmsi}` | scoring (Wave 11+) | HASH (route_id, entry_time, entry_lat, entry_lon) |
| `heimdal:cable_align:{mmsi}` | scoring (Wave 11+) | HASH (route_id, first_parallel_time, consecutive_count) |
| `heimdal:last_pos:{mmsi}` | scoring (Wave 11+) | HASH (lat, lon, timestamp) — duplicate MMSI detection |

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
| infrastructure_routes | seed data (Wave 11+) | scoring, api-server |
| infrastructure_events | scoring (Wave 11+) | api-server |
| land_mask | seed data (Wave 11+) | scoring |
| gnss_interference_zones | scoring (Wave 11+) | api-server |
| network_edges | scoring, api-server (Wave 11+) | api-server, scoring |
| users | api-server (Wave 15+) | api-server |
| refresh_tokens | api-server (Wave 15+) | api-server |
| watch_rules | api-server (Wave 16+) | api-server, notification engine |
| notification_log | notification engine (Wave 16+) | api-server |
| export_jobs | api-server (Wave 16+) | api-server, export runner |

### External API Dependencies
| API | Consumer | Auth | Rate Limits |
|-----|----------|------|-------------|
| aisstream.io WebSocket | ais-ingest | API key | None (streaming) |
| GFW 4Wings API | enrichment | GFW API token → JWT | 50K req/day, 1.55M/month |
| GFW Events API | enrichment | GFW API token → JWT | Same |
| GFW Vessel API | enrichment | GFW API token → JWT | Same |
| OpenSanctions bulk | enrichment | None (download) | N/A |
