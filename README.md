# Heimdal

Maritime intelligence platform for monitoring vessel behavior, detecting sanctions evasion, and identifying dark fleet activity. Heimdal ingests live AIS data, enriches it with Global Fishing Watch analytics and OpenSanctions data, then scores vessels across 14 behavioral rules to surface high-risk activity in real time.

## Architecture

```
                         aisstream.io WebSocket
                                |
                                v
+----------------------------------------------------------+
|                      Docker Compose                       |
|                                                           |
|  +--------------+    +--------------+    +-------------+  |
|  |  ais-ingest  |--->|   postgres   |<---|   scoring   |  |
|  |  (WebSocket  |    |  (TimescaleDB|    |  (14 rules  |  |
|  |   consumer)  |    |   + PostGIS) |    |   engine)   |  |
|  +------+-------+    +------^-------+    +------+------+  |
|         |                   |                   |         |
|         v                   |                   v         |
|  +--------------+    +------+-------+    +-------------+  |
|  |    redis     |<-->|  api-server  |<-->| enrichment  |  |
|  |  (pub/sub +  |    |  (FastAPI    |    | (GFW API +  |  |
|  |   caching)   |    |   REST + WS) |    | sanctions)  |  |
|  +--------------+    +------^-------+    +-------------+  |
|                             |                             |
|                      +------+-------+                     |
|                      |   frontend   |                     |
|                      |  (React +    |                     |
|                      |   CesiumJS)  |                     |
|                      +--------------+                     |
+----------------------------------------------------------+
                              |
         +--------------------+--------------------+
         v                    v                    v
   Global Fishing       OpenSanctions        aisstream.io
   Watch API            (bulk download)      (live AIS)
```

### Data Flow

1. **ais-ingest** connects to aisstream.io via WebSocket, parses AIS position reports and static data, deduplicates via Redis, and batch-writes positions to TimescaleDB.
2. **scoring** subscribes to Redis position events, evaluates 14 rules (5 GFW-sourced + 9 real-time), aggregates risk scores, and publishes tier changes.
3. **enrichment** runs on a 6-hour cycle, querying Global Fishing Watch for SAR detections, behavioral events, and vessel identity; then matches against OpenSanctions.
4. **api-server** exposes REST endpoints for vessels, anomalies, SAR detections, and GFW events, plus WebSocket streams for live position and alert updates.
5. **frontend** renders a 3D globe (CesiumJS) with risk-colored vessel markers, track trails, STS zone overlays, and a detail panel with scoring breakdown.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (V2)
- API keys (all free tier):
  - **aisstream.io** -- live AIS data feed ([register here](https://aisstream.io))
  - **Cesium Ion** -- 3D globe tile rendering ([get token](https://ion.cesium.com/tokens))
  - **Global Fishing Watch** -- vessel analytics and SAR detections ([register here](https://globalfishingwatch.org/our-apis/))

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/heimdal.git
cd heimdal

# Create environment file
cp .env.example .env

# Fill in your API keys (see Configuration section below)
# At minimum, set: AIS_API_KEY, CESIUM_ION_TOKEN, GFW_API_TOKEN

# Start all services
make up
```

## First-Run Walkthrough

1. **Start the platform:**
   ```bash
   make up
   ```
   This launches PostgreSQL (with TimescaleDB + PostGIS), Redis, and all 5 application services. The database migrations run automatically on first boot.

2. **Verify services are healthy:**
   ```bash
   make logs
   ```
   Look for `ais-ingest` connecting to aisstream.io and `api-server` listening on port 8000.

3. **Open the frontend:**
   Navigate to [http://localhost:3000](http://localhost:3000). You should see a 3D globe centered on the Norwegian EEZ. Vessel markers will begin appearing within seconds as AIS data flows in.

4. **Download OpenSanctions data** (optional, for sanctions matching):
   ```bash
   make fetch-sanctions
   ```

5. **Check platform health:**
   ```
   curl http://localhost:8000/api/health
   ```
   Returns service status, vessel counts, and ingestion metrics.

## Configuration

All configuration is via environment variables in `.env`. Copy `.env.example` and fill in:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AIS_API_KEY` | Yes | -- | aisstream.io WebSocket API key |
| `CESIUM_ION_TOKEN` | Yes | -- | Cesium Ion access token for globe rendering |
| `GFW_API_TOKEN` | Yes | -- | Global Fishing Watch API bearer token |
| `DB_PASSWORD` | No | `heimdal_dev` | PostgreSQL password |
| `DB_PORT` | No | `5432` | PostgreSQL host port |
| `API_PORT` | No | `8000` | API server host port |
| `FRONTEND_PORT` | No | `3000` | Frontend host port |
| `AIS_BOUNDING_BOXES` | No | `worldwide` | AIS position filter (lat_min,lon_min,lat_max,lon_max) |
| `AIS_SHIP_TYPES` | No | all | Comma-separated ship type codes to ingest |
| `ENRICHMENT_INTERVAL` | No | `6` | Hours between enrichment cycles |
| `GFW_EVENTS_LOOKBACK_DAYS` | No | `30` | Days to look back for GFW events |

### Obtaining API Keys

**aisstream.io (free):**
1. Register at [aisstream.io](https://aisstream.io)
2. Go to your dashboard and copy the API key
3. Set `AIS_API_KEY` in `.env`

**Cesium Ion (free):**
1. Create an account at [cesium.com/ion](https://cesium.com/ion/)
2. Go to Access Tokens and create a new token (default permissions are fine)
3. Set `CESIUM_ION_TOKEN` in `.env`

**Global Fishing Watch (free):**
1. Register at [globalfishingwatch.org/our-apis](https://globalfishingwatch.org/our-apis/)
2. Follow the instructions to obtain an API token
3. Set `GFW_API_TOKEN` in `.env`

## Makefile Targets

Run `make help` to see all targets:

| Target | Description |
|--------|-------------|
| `make up` | Start all services in the background |
| `make down` | Stop all services |
| `make reset` | Destroy volumes and rebuild all containers |
| `make logs` | Tail logs for all services |
| `make logs-ingest` | Tail AIS ingest service logs |
| `make logs-scoring` | Tail scoring engine logs |
| `make migrate` | Run SQL migrations |
| `make shell-db` | Open psql shell |
| `make shell-api` | Open bash shell in api-server |
| `make fetch-sanctions` | Download OpenSanctions data |
| `make test` | Run test suite |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Service health and metrics |
| GET | `/api/stats` | Risk tier breakdown, anomaly stats |
| GET | `/api/vessels` | List vessels (paginated, filterable) |
| GET | `/api/vessels/{mmsi}` | Vessel detail with risk profile |
| GET | `/api/vessels/{mmsi}/track` | Position history (time range) |
| GET | `/api/anomalies` | List anomaly events (filterable) |
| GET | `/api/sar/detections` | SAR dark vessel detections |
| GET | `/api/gfw/events` | Global Fishing Watch events |
| GET | `/api/watchlist` | List watched vessels |
| POST | `/api/watchlist` | Add vessel to watchlist |
| DELETE | `/api/watchlist/{mmsi}` | Remove vessel from watchlist |
| POST | `/api/vessels/{mmsi}/enrich` | Submit manual enrichment |
| WS | `/ws/positions` | Live vessel position stream |
| WS | `/ws/alerts` | Risk change and anomaly alerts |

## Scoring Rules

Heimdal evaluates vessels against 14 behavioral rules:

**GFW-sourced (higher confidence, 3-5 day delay):**
- `gfw_ais_disabling` -- AIS gaps detected by GFW ML models
- `gfw_encounter` -- Ship-to-ship transfers in STS zones
- `gfw_loitering` -- Suspicious loitering in STS zones
- `gfw_port_visit` -- Visits to sanctioned Russian ports
- `gfw_dark_sar` -- SAR detections correlated with AIS gaps

**Real-time (lower confidence, instant):**
- `ais_gap` -- AIS signal gaps (24h cooldown)
- `sts_proximity` -- Slow-speed proximity in STS zones
- `destination_spoof` -- Placeholder/sea area destinations
- `draft_change` -- At-sea draught increases
- `flag_hopping` -- MID-based flag changes
- `sanctions_match` -- Direct/fuzzy sanctions matches
- `vessel_age` -- Aged tankers (higher risk profile)
- `speed_anomaly` -- Slow steaming or abrupt speed changes
- `identity_mismatch` -- Dimension/flag inconsistencies

Risk tiers: **green** (0-29), **yellow** (30-99), **red** (100+)

## Project Structure

```
heimdal/
├── services/
│   ├── ais-ingest/      # WebSocket AIS consumer + batch writer
│   ├── api-server/      # FastAPI REST + WebSocket server
│   ├── enrichment/      # GFW + OpenSanctions enrichment
│   └── scoring/         # 14-rule scoring engine
├── frontend/            # React + CesiumJS + Tailwind
├── shared/              # Shared models, DB layer, config
├── db/                  # PostgreSQL Dockerfile + migrations
├── tests/               # Test suite (pytest)
│   ├── fixtures/        # Test data fixtures
│   ├── api-server/      # API endpoint tests
│   └── integration/     # Integration tests
├── scripts/             # Utility scripts
├── docker-compose.yml   # Service orchestration
├── Makefile             # Developer interface
└── config.yaml          # Application configuration
```

## Troubleshooting

**Services won't start:**
- Ensure Docker is running: `docker info`
- Check if ports are in use: `lsof -i :5432` / `lsof -i :8000` / `lsof -i :3000`
- Reset everything: `make reset`

**No vessels appearing on the globe:**
- Verify `AIS_API_KEY` is set correctly in `.env`
- Check ingest logs: `make logs-ingest`
- Ensure aisstream.io is reachable from your network

**Globe not rendering:**
- Verify `CESIUM_ION_TOKEN` is set in `.env`
- Check browser console for Cesium errors
- Ensure you have a valid Cesium Ion account

**Database connection errors:**
- Wait for PostgreSQL healthcheck to pass: `docker compose ps`
- Check database logs: `docker compose logs postgres`
- Reset database: `make reset`

**Enrichment not working:**
- Verify `GFW_API_TOKEN` is set in `.env`
- Check enrichment logs: `docker compose logs enrichment`
- Ensure GFW API token has the correct permissions

**Tests failing:**
- Run inside the container: `make test`
- For local development, ensure `DATABASE_URL` is set (tests mock DB access)
- Run specific test files: `docker compose exec api-server pytest tests/test_parser.py -v`

## License

Proprietary. All rights reserved.
