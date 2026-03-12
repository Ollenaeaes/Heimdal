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

## Mistakes to Avoid

- (2026-03-12) When parallel subagents all modify `main.py` (adding router imports), verify the final state after all complete — concurrent edits can conflict or duplicate lines.
- (2026-03-12) When changing pagination params in routes (e.g. `limit`→`page`), must also update ALL corresponding test assertions (`body["count"]`→`body["total"]`, query params in test URLs).
- (2026-03-12) Don't forget to expose service ports in docker-compose.yml. The Dockerfile `EXPOSE` is not enough — need `ports:` mapping for host access.
- (2026-03-12) When a service has a health endpoint, add a `healthcheck:` in docker-compose and use `condition: service_healthy` in dependents. The api-server was missing this, so the frontend could start before the API was ready.

## Project-Specific Gotchas

- (2026-03-12) The api-server Dockerfile installs shared deps inline (not from requirements-base.txt) because `shared/` is a runtime volume mount. If shared deps change, the Dockerfile must be updated separately.
- (2026-03-12) SAR bbox format is `sw_lat,sw_lon,ne_lat,ne_lon` (same as vessels/anomalies). Old code used `min_lon,min_lat,max_lon,max_lat` — watch for this when writing tests.
- (2026-03-12) The `DATABASE_URL` env var in docker-compose uses `postgresql://` prefix (sync driver format). The shared config handles converting to asyncpg format internally.

## Architecture Decisions

- (2026-03-12) CORS is `allow_origins=["*"]` because this is a single-user local workstation (D4). Acceptable for now but should be restricted if deployment changes.
- (2026-03-12) api-server healthcheck uses `python3 -c "import urllib.request; ..."` instead of `curl` because the slim Python image doesn't include curl.
