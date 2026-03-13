# Status
**Updated:** 2026-03-12T15:20:00
**Current branch:** main (uncommitted changes)
**Working on:** Getting the platform running — frontend Cesium globe not rendering

## What's Been Fixed (uncommitted)

1. **db/Dockerfile** — `timescaledb-ha:pg16-latest` → `:pg16`, added `USER root`/`USER postgres` for apt-get
2. **docker-compose.yml** — `DATABASE_URL` changed to `postgresql+asyncpg://`, healthcheck changed to `CMD-SHELL`, added `VITE_CESIUM_ION_TOKEN` build arg for frontend
3. **Frontend TS errors** — Added missing `darkShipsOnly`/`showGfwEventTypes` to FilterState in 7+ test files, fixed unused imports, fixed VesselCluster.tsx type issues
4. **services/enrichment/** — Fixed `from services.enrichment.xxx` → `from xxx` imports (container has flat `/app/` structure)
5. **Frontend Dockerfile** — Added `ARG/ENV VITE_CESIUM_ION_TOKEN`, changed `npm run build` → `npx vite build` (skip tsc in Docker)
6. **Frontend code splitting** — `App.tsx` uses `lazy()` + `Suspense` for GlobeView and VesselPanel
7. **Cesium CSS** — Added `<link rel="stylesheet" href="/cesium/Widgets/widgets.css" />` to `index.html`
8. **index.css** — Added `.cesium-viewer, .cesium-widget { width: 100% !important; height: 100% !important; }`
9. **App.tsx** — Added ErrorBoundary around GlobeView Suspense

## Current Service Status

All 7 Docker services are UP and running:
- postgres, redis, api-server, frontend (nginx), ais-ingest, scoring, enrichment
- API: http://localhost:8000 (healthy)
- Frontend: http://localhost:3000 (nginx serving, but globe not rendering)

## The Remaining Problem

**The Cesium globe does not render.** The app shell (header, controls, overlay toggles) loads fine. The "Loading globe..." spinner shows, meaning the lazy import is working. But the globe never appears — it either:
- Stays on the spinner forever (Suspense fallback never resolves)
- Or renders tiny in the upper-left corner (CSS issue with Cesium viewer sizing)

An ErrorBoundary was added but no error message is shown, suggesting the component may be mounting but the canvas isn't sizing correctly, OR there's a silent failure in Cesium initialization.

### What to investigate next:
1. **Open browser DevTools console** when loading localhost:3000 — look for JS errors
2. **Check if Cesium widget CSS is actually applied** — inspect the `.cesium-viewer` element's computed styles
3. **The `<Viewer full>` prop from Resium** — check if it sets `position: absolute; inset: 0` and if the parent `<main>` has actual pixel dimensions
4. **Consider using Playwright MCP** to automate browser debugging
5. **Consider reverting the lazy loading** temporarily to isolate whether it's the code splitting or the CSS causing the issue — the original non-lazy App.tsx did render a tiny globe in the corner

### Quick test — revert to eager loading:
In `App.tsx`, replace the lazy imports with direct imports (like the original) and rebuild. If the tiny globe reappears, the issue is Suspense/lazy interaction with Cesium. If still nothing, it's the CSS override or something else.

### Build workflow:
```bash
# Fast local build (6 seconds):
source .env && VITE_CESIUM_ION_TOKEN=$CESIUM_ION_TOKEN npx vite build

# Deploy to running container (skip Docker rebuild):
docker cp frontend/dist/index.html heimdal-frontend-1:/usr/share/nginx/html/
docker cp frontend/dist/assets/. heimdal-frontend-1:/usr/share/nginx/html/assets/
docker compose exec frontend nginx -s reload
```

## Decisions
- D1: Local vite build + docker cp is the dev workflow — Docker rebuild is too slow (npm ci every time)
- D2: Cesium stays bundled (not external) — ESM imports from resium don't work with IIFE global script
- D3: `tsc` skipped in Docker build — type checking done locally, vite build only in Docker

## Blockers
- Cesium globe rendering / sizing issue blocks all frontend work
