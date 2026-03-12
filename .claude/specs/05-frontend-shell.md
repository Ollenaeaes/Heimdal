# Feature Spec: Frontend Shell

**Slug:** `frontend-shell`
**Created:** 2026-03-11
**Status:** completed
**Priority:** critical
**Wave:** 2 (Data Pipeline)

---

## Overview

Set up the React + TypeScript + Vite frontend application with CesiumJS 3D globe integration. This creates the app skeleton: project scaffolding, globe component, basic app layout, TypeScript types, Zustand store skeleton, Dockerfile with nginx, and the initial camera view.

## Problem Statement

The frontend needs a working foundation: a CesiumJS globe rendering in the browser with the correct initial view and a layout that can host the vessel detail panel and controls. Without this shell, no frontend feature can be built.

## Out of Scope

- NOT: Vessel markers on the globe (see `09-globe-rendering`)
- NOT: Vessel detail panel content (see `10-vessel-detail-panel`)
- NOT: Search/filter controls (see `11-controls-and-filtering`)
- NOT: WebSocket data connections (see `09-globe-rendering`)
- NOT: Any backend API integration

---

## User Stories

### Story 1: Vite + React + TypeScript Project Setup

**As a** frontend developer
**I want to** have a properly configured Vite + React + TypeScript project
**So that** I can develop with hot reload and type safety

**Acceptance Criteria:**

- GIVEN `frontend/` WHEN `npm install && npm run dev` THEN the dev server starts on port 5173
- GIVEN the project WHEN built THEN `npm run build` produces optimized static files in `dist/`
- GIVEN `package.json` WHEN inspected THEN it includes React 18, TypeScript 5, Vite 5, CesiumJS 1.115+, Resium 1.18+, Zustand 4, TanStack Query 5, Tailwind CSS 3, date-fns 3
- GIVEN `tsconfig.json` WHEN inspected THEN strict mode is enabled

**Test Requirements:**

- [ ] Test: `npm run build` succeeds without errors
- [ ] Test: TypeScript compilation has no errors

**Technical Notes:**

Use `npm create vite@latest` with react-ts template as starting point. Add CesiumJS via `cesium` and `resium` packages. Vite config needs the `vite-plugin-cesium` or manual Cesium asset copying.

---

### Story 2: CesiumJS Globe Component

**As a** user
**I want to** see a 3D globe rendering in the browser
**So that** I have a geographic context for maritime data

**Acceptance Criteria:**

- GIVEN the app loads WHEN the globe renders THEN CesiumJS Viewer displays with Cesium Ion community imagery (or configurable imagery provider)
- GIVEN the globe WHEN initial view loads THEN camera is centered on Norwegian EEZ: lat 68, lon 15, altitude 5000km
- GIVEN the globe WHEN rendered THEN clock is in real-time mode (shouldAnimate=true)
- GIVEN the globe WHEN rendered THEN default Cesium widgets are configured (no info box, no selection indicator, no home button clutter — clean UI)
- GIVEN the globe WHEN rendered THEN it takes the full viewport height minus any header/toolbar

**Test Requirements:**

- [ ] Test: GlobeView component renders without errors
- [ ] Test: Cesium Viewer initializes with correct camera position

**Technical Notes:**

Use Resium's `<Viewer>` component. Configuration:
- `imageryProvider`: Cesium Ion (free tier) or Bing Maps (configurable via env)
- `terrainProvider`: Cesium World Terrain (free) or EllipsoidTerrainProvider
- `shouldAnimate={true}` for live tracking
- Initial camera: `Cesium.Cartesian3.fromDegrees(15, 68, 5000000)`
- Disable: infoBox, selectionIndicator, homeButton, baseLayerPicker (provide our own)

Component: `src/components/Globe/GlobeView.tsx`

---

### Story 3: TypeScript Types and Zustand Store Skeleton

**As a** frontend developer
**I want to** have TypeScript interfaces for all domain types and a Zustand store skeleton
**So that** future features have type-safe data structures to work with

**Acceptance Criteria:**

- GIVEN `src/types/vessel.ts` WHEN imported THEN VesselState interface exists with: mmsi, lat, lon, sog, cog, riskTier, riskScore, name?, timestamp
- GIVEN `src/types/anomaly.ts` WHEN imported THEN AnomalyEvent interface exists with: id, mmsi, timestamp, ruleId, severity, points, details, resolved
- GIVEN `src/types/api.ts` WHEN imported THEN API response types exist for paginated results, vessel detail, track points
- GIVEN `src/hooks/useVesselStore.ts` WHEN imported THEN Zustand store skeleton exists with: vessels Map, selectedMmsi, filters, updatePosition(), selectVessel(), setFilter()
- GIVEN the store WHEN updatePosition is called THEN the vessel map is updated without triggering full re-renders

**Test Requirements:**

- [ ] Test: TypeScript interfaces compile without errors
- [ ] Test: Zustand store initializes with empty state
- [ ] Test: updatePosition correctly adds/updates a vessel in the Map

**Technical Notes:**

VesselStore interface:
```typescript
interface VesselStore {
  vessels: Map<number, VesselState>;
  selectedMmsi: number | null;
  filters: FilterState;
  updatePosition: (update: VesselState) => void;
  selectVessel: (mmsi: number | null) => void;
  setFilter: (filter: Partial<FilterState>) => void;
}
```

FilterState: `{ riskTiers: Set<string>, shipTypes: number[], bbox: [number,number,number,number] | null, activeSince: string | null }`

---

### Story 4: App Layout and Routing

**As a** user
**I want to** see a clean app layout with the globe as the primary view
**So that** the interface is ready for vessel panels and controls

**Acceptance Criteria:**

- GIVEN the app WHEN loaded THEN it shows: a thin top bar area (for future stats/health), the globe taking remaining viewport height, and a right-side panel area (hidden by default, for vessel detail)
- GIVEN `src/App.tsx` WHEN rendered THEN it wraps the globe in a TanStack QueryClientProvider and Resium context
- GIVEN `src/main.tsx` WHEN the app bootstraps THEN it renders into the root element with proper providers

**Test Requirements:**

- [ ] Test: App component renders without errors
- [ ] Test: Layout has correct structure (header area, globe area, panel slot)

**Technical Notes:**

Use Tailwind CSS for layout. Full-height layout: `h-screen flex flex-col`. Top bar: `h-12`. Globe: `flex-1`. Panel: `fixed right-0 top-12 bottom-0 w-[420px]` (initially hidden). No routing needed — single page app.

---

### Story 5: Dockerfile and Nginx Configuration

**As a** developer
**I want to** build the frontend as a Docker image with nginx serving static files
**So that** it integrates with Docker Compose and proxies API/WS to the backend

**Acceptance Criteria:**

- GIVEN the Dockerfile WHEN built THEN stage 1 builds the Vite app with `npm run build`
- GIVEN the Dockerfile WHEN built THEN stage 2 copies dist/ into nginx:alpine and copies nginx.conf
- GIVEN nginx.conf WHEN serving THEN `/` serves static files with SPA fallback (`try_files $uri /index.html`)
- GIVEN nginx.conf WHEN proxying THEN `/api/*` proxies to `http://api-server:8000`
- GIVEN nginx.conf WHEN proxying THEN `/ws/*` proxies to `http://api-server:8000` with WebSocket upgrade headers

**Test Requirements:**

- [ ] Test: Dockerfile builds successfully (multi-stage)
- [ ] Test: nginx.conf has correct proxy_pass directives for /api/ and /ws/

**Technical Notes:**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

nginx.conf must include `proxy_http_version 1.1` and `proxy_set_header Upgrade/Connection` for WebSocket support.

---

### Story 6: Utility Functions and Data Files

**As a** frontend developer
**I want to** have utility functions for risk colors and display formatting
**So that** all components use consistent visual styling

**Acceptance Criteria:**

- GIVEN `src/utils/riskColors.ts` WHEN imported THEN it exports color mappings: green → subdued green, yellow → #D4820C, red → #C0392B
- GIVEN `src/utils/formatters.ts` WHEN imported THEN it exports formatting functions for: coordinates (lat/lon to DMS), speed (knots), course (degrees), timestamps (relative and absolute)
- GIVEN `src/data/stsZones.json` WHEN loaded THEN it contains GeoJSON-style coordinates for 6 STS zones
- GIVEN `src/data/terminals.json` WHEN loaded THEN it contains coordinates for 7 Russian export terminals
- GIVEN `public/icons/` WHEN checked THEN vessel SVG icons exist: vessel-green.svg, vessel-yellow.svg, vessel-red.svg, sar-detection.svg

**Test Requirements:**

- [ ] Test: riskColors returns correct hex colors for each tier
- [ ] Test: formatters produce correct output for sample values
- [ ] Test: JSON data files are valid and contain expected entries

**Technical Notes:**

Ship silhouette SVGs should be simple, directional icons (pointing up = heading 0). Three color variants. Approximately 24x24 viewbox. The sar-detection SVG is a radar-style icon.

---

## Technical Design

### Data Model Changes

None — frontend only.

### API Changes

None — this spec creates no API integration (that comes in later waves).

### Dependencies

- Node.js 20, npm
- React 18, TypeScript 5, Vite 5
- CesiumJS 1.115+, Resium 1.18+
- Zustand 4, TanStack Query 5
- Tailwind CSS 3, date-fns 3
- CESIUM_ION_TOKEN env variable (optional, for terrain/imagery)

### Security Considerations

- Cesium Ion token is the only sensitive value — loaded from env at build time
- No authentication in local deployment

---

## Implementation Order

### Group 1 (parallel)
- Story 1 — Vite project setup (scaffolding, package.json, configs)
- Story 3 — TypeScript types and Zustand store (pure type definitions)
- Story 6 — Utility functions and data files (pure functions, static data)

### Group 2 (after Group 1)
- Story 2 — CesiumJS globe component (needs Resium from Story 1)
- Story 4 — App layout (needs globe from Story 2)

### Group 3 (after Group 2)
- Story 5 — Dockerfile and nginx (needs buildable app)

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] `npm run dev` starts dev server with globe visible
- [ ] `npm run build` produces optimized static files
- [ ] Globe renders with correct initial camera position
- [ ] TypeScript compilation is clean (no errors)
- [ ] Dockerfile builds and nginx serves correctly
- [ ] Code committed with proper messages
- [ ] Ready for human review
