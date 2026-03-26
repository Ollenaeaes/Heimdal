# Lessons Learned

This file is read at the start of every session. It captures mistakes, patterns, and decisions learned from code reviews, debugging sessions, and implementation experience. The agent uses these to avoid repeating mistakes.

**Rules for this file:**
- Keep each lesson to 1-3 lines
- Be specific: "Don't do X because Y" not "be careful with X"
- Include the date so stale lessons can be pruned
- Max 150 lines — when it gets long, archive old lessons and keep only what's still relevant

---

## Coding Patterns

- (2026-03-12) All paginated endpoints must use `page`/`per_page` params and return `{items, total, page, per_page}`. Don't use `limit`/`offset` in the API surface — convert internally. Don't use `count` — always `total`.
- (2026-03-12) Field naming must be consistent across list and detail endpoints. Use `ship_name` everywhere, not `name` in lists and `ship_name` in details. Same for `vessel_name` in joins — use `ship_name`.
- (2026-03-12) Never use f-strings for SQL table names, even with hardcoded values. Use pre-built `text()` objects instead. The `# noqa: S608` comment hides the problem, doesn't fix it.
- (2026-03-12) For bbox parameters, always validate and return HTTP 400 on invalid input. Never silently return unfiltered results — the client thinks filtering is applied when it isn't.

## Production Database

- (2026-03-16) **NEVER rebuild or recreate the prod postgres container.** All schema changes must be SQL migrations applied via `psql -f`. Rebuilding wipes all data — equasis imports, manual enrichment, watchlists, and scoring history are irreplaceable. Use `--no-deps` when deploying other services.
- (2026-03-16) **The timescaledb-ha image uses `/home/postgres/pgdata` as PGDATA**, not `/var/lib/postgresql/data`. The volume mount must point to `/home/postgres/pgdata` or data is stored in the container's ephemeral filesystem and lost on recreation.
- (2026-03-16) **Always dump before any infra change.** Disk space on Hostinger VPS is limited — pipe the backup directly to the local machine instead of storing on the server: `ssh root@76.13.248.226 "docker exec heimdal-postgres-1 pg_dump -U heimdal -Fc heimdal" > local_backup.dump`. Only use server-side dumps as a last resort.

## Infrastructure / VPS

- (2026-03-25) **Hostinger KVM 2 VPS has 2 CPUs / 8GB RAM — never over-provision Docker resource limits.** Adding adsb-ingest pushed always-on CPU limits to 2.5 (> 2 available). Hostinger auto-throttles via `ct_set_limits` actions when sustained CPU > ~70%. This risks OOM-killing postgres and losing data. Always sum all container CPU/RAM limits before deploying a new service and keep total ≤ 80% of VPS capacity (1.6 CPUs / 6.4GB for always-on).
- (2026-03-25) **Right-sized limits (post-fix):** postgres 0.75 CPU/3G, ais-ingest 0.3/384M, adsb-ingest 0.3/384M, api-server 0.4/768M = **1.75 CPU / 4.5G always-on**. Batch jobs (batch-pipeline 0.75/2G, cold-archiver 0.75/2G) run in `batch` profile so they don't stack on top permanently.
- (2026-03-25) **Postgres tuning must match container RAM limit.** `shared_buffers` should be ~15-25% of container RAM limit, `effective_cache_size` ~60-70%. With 3G container limit: shared_buffers=512MB, effective_cache_size=2GB, work_mem=8MB, maintenance_work_mem=128MB.
- (2026-03-25) **Never use `LEFT JOIN LATERAL` on `vessel_positions` for bulk queries.** The hypertable has no index on `mmsi` — only on `timestamp`. A lateral join per vessel does a full table scan per row, taking 4-6 minutes per query. Use denormalized columns in `vessel_profiles` (e.g. `last_cog`, `last_sog`, `last_heading`) instead. TODO: add `(mmsi, timestamp DESC)` index and `last_cog/sog/heading` columns to `vessel_profiles`.
- (2026-03-25) **Set `statement_timeout` on the database.** Currently set to 30s via `ALTER DATABASE`. Without it, slow queries pile up and spiral postgres to 265% CPU. The API server re-spawns queries faster than they complete, creating a death spiral.
- (2026-03-25) **TimescaleDB hypertables don't support `CREATE INDEX CONCURRENTLY`.** Use regular `CREATE INDEX` — TimescaleDB handles per-chunk indexing internally. Plan index creation during low-load periods since it briefly locks writes.
- (2026-03-25) **The batch-pipeline cron runs every 5 minutes** (`--load-only`) and every 2 hours (full). Each run spawns a new container. If runs don't finish before the next starts, containers pile up (found 5 simultaneous containers eating 5GB RAM). Cron backup at `/tmp/crontab.bak` on VPS. Re-enable with: `crontab /tmp/crontab.bak`.

## Mistakes to Avoid

- (2026-03-12) When parallel subagents all modify `main.py` (adding router imports), verify the final state after all complete — concurrent edits can conflict or duplicate lines.
- (2026-03-12) When changing pagination params in routes (e.g. `limit`→`page`), must also update ALL corresponding test assertions (`body["count"]`→`body["total"]`, query params in test URLs).
- (2026-03-12) Don't forget to expose service ports in docker-compose.yml. The Dockerfile `EXPOSE` is not enough — need `ports:` mapping for host access.
- (2026-03-12) When a service has a health endpoint, add a `healthcheck:` in docker-compose and use `condition: service_healthy` in dependents. The api-server was missing this, so the frontend could start before the API was ready.

## Project-Specific Gotchas

- (2026-03-12) The api-server Dockerfile installs shared deps inline (not from requirements-base.txt) because `shared/` is a runtime volume mount. If shared deps change, the Dockerfile must be updated separately.
- (2026-03-12) SAR bbox format is `sw_lat,sw_lon,ne_lat,ne_lon` (same as vessels/anomalies). Old code used `min_lon,min_lat,max_lon,max_lat` — watch for this when writing tests.
- (2026-03-12) The `DATABASE_URL` env var in docker-compose must use `postgresql+asyncpg://` prefix — shared config does NOT convert from sync format. Using `postgresql://` causes `ModuleNotFoundError: No module named 'psycopg2'`.

## Architecture Decisions

- (2026-03-12) CORS is `allow_origins=["*"]` because this is a single-user local workstation (D4). Acceptable for now but should be restricted if deployment changes.
- (2026-03-12) api-server healthcheck uses `CMD-SHELL` with `python3 -c '...'` instead of `curl` because the slim Python image doesn't include curl. Using `CMD` form with Python `-c` can cause syntax errors from Docker shell argument splitting.
- (2026-03-12) The `timescaledb-ha` Docker image runs as user `postgres`, not root. Must `USER root` before `apt-get install` and `USER postgres` after. Also, the `:pg16-latest` tag doesn't exist — use `:pg16`.
- (2026-03-12) Service Dockerfiles copy code to `/app/` root, but imports in `services/enrichment/` used full paths (`from services.enrichment.xxx`). In-container imports must use flat module names (`from xxx import`), not the host repo path structure.
- (2026-03-12) When adding new fields to a shared type like `FilterState`, update ALL test files that construct that type — not just the ones that fail first. Use `grep` to find all occurrences before fixing.
- (2026-03-12) Don't rebuild the frontend Docker image for every change — `npm ci` runs every time and takes minutes. Instead: `npx vite build` locally (6s), then `docker cp dist/... container:/usr/share/nginx/html/` and `nginx -s reload`.
- (2026-03-12) The frontend `npm run build` runs `tsc -b && vite build`. Skip `tsc` in Docker builds (`npx vite build` directly) — type checking with Cesium types is slow and OOMs in constrained Docker.
- (2026-03-12) Cesium requires `widgets.css` loaded in HTML (`<link rel="stylesheet" href="/cesium/Widgets/widgets.css" />`). Without it, the viewer renders tiny. Resium's `<Viewer full>` prop depends on these styles.
- (2026-03-12) `VITE_CESIUM_ION_TOKEN` must be available at build time (not runtime). Pass it via Docker `ARG`/`ENV` or set it in the shell before `vite build`. The `.env` key is `CESIUM_ION_TOKEN` — needs mapping to `VITE_` prefix.
- (2026-03-12) When using `replace_all` in Edit tool, `from services.enrichment.` → `from` eats the trailing space, producing `fromgfw_client`. Always include the space in the replacement: `from services.enrichment.` → `from `.
- (2026-03-12) **Never use React.StrictMode with CesiumJS/Resium.** StrictMode double-mounts components in dev; Cesium's `Viewer.destroy()` is irreversible, so the re-mount fails silently (blank page or "Page Unresponsive"). Remove StrictMode or wrap only non-Cesium parts.
- (2026-03-12) `CESIUM_BASE_URL` should be set via Vite `define` in vite.config.ts (compile-time replacement). Do NOT also set `window.CESIUM_BASE_URL` in main.tsx — it's redundant and the `define` already handles it inside Cesium's own source.
- (2026-03-12) When stuck on a rendering/integration bug, research online (docs, GitHub issues) after the first failed fix attempt. Don't keep guessing with code changes — one targeted research session beats ten blind attempts.

## CesiumJS / Globe Rendering

- (2026-03-15) **Never use `clampToGround: true` with large GeoJSON datasets in Cesium.** 7,570 polylines with terrain clamping causes `ArrayBuffer allocation failed` (OOM crash). Subsea cables/pipelines don't need clamping — use `clampToGround: false`.
- (2026-03-15) **Never render thousands of features as individual React `<Entity>` components.** Use `GeoJsonDataSource` loaded directly via Cesium API instead. 7,570 routes × 3 entities each = 30,000 React components = unusable performance. A single `GeoJsonDataSource` handles it natively.
- (2026-03-15) **Cesium `entity.id` is read-only** on entities created by `GeoJsonDataSource`. Use `entity.name` for custom identification/hover detection instead.
- (2026-03-15) **CesiumJS billboard `rotation` with `alignedAxis=Cartesian3.UNIT_Z` doesn't work for screen-space rotation.** Remove `alignedAxis` and `ConstantProperty` wrapper — just pass a plain numeric radian value to `rotation` for COG-based heading.
- (2026-03-15) **Vessel snapshot endpoint must include COG/SOG** for heading display. The `vessel_profiles` table only has `last_lat`/`last_lon` — COG lives in `vessel_positions`. Use a `LEFT JOIN LATERAL` to get the latest position's COG per vessel.
- (2026-03-15) **`vessel_profiles` uses `last_lat`/`last_lon` columns, not `last_position`.** Several queries incorrectly referenced `ST_Y(vp.last_position::geometry)` which doesn't exist.
- (2026-03-15) **When `podman compose up --build` rebuilds postgres, data is lost** because `init.sh` re-runs on container recreate. Use `--no-deps` flag to rebuild only the target service. Apply new migrations manually via `podman exec ... psql -f`.
- (2026-03-15) **After rebuilding a container, restart the frontend container** so nginx DNS resolves the new container IP. Otherwise the API proxy returns empty responses.
- (2026-03-15) **asyncpg requires JSON strings for JSONB columns**, not raw Python dicts. Always `json.dumps()` dict values before passing as SQL parameters. Symptom: `'dict' object has no attribute 'encode'`.
