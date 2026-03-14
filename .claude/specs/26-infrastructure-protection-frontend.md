# Feature Spec: Infrastructure Protection Frontend

**Slug:** `infrastructure-protection-frontend`
**Created:** 2026-03-14
**Status:** draft
**Priority:** high

---

## Overview

Globe overlays for subsea cables, pipelines, wind farms, and platforms with infrastructure risk halos when flagged vessels enter corridors. Plus an infrastructure-at-risk dashboard panel showing monitored assets, real-time corridor alerts, and traffic density.

## Problem Statement

The infrastructure protection scoring rules (spec 23) detect suspicious behavior near critical infrastructure, but operators need to SEE the infrastructure on the globe to understand the context. A vessel moving slowly near an invisible cable corridor has no visual impact — but the same vessel crawling along a visible blue cable line with a pulsing red halo immediately communicates the threat.

## Out of Scope

- NOT: Backend scoring rules (spec 23)
- NOT: Data loading scripts (spec 23)
- NOT: Cable burial depth or condition visualization
- NOT: Real-time cable integrity status
- NOT: Traffic density heat map (deferred to refinement phase)

---

## User Stories

### Story 1: Infrastructure Globe Overlay — Cable and Pipeline Routes

**As an** operator
**I want to** see subsea cable and pipeline routes rendered on the globe
**So that** I can visually assess vessel proximity to critical infrastructure

**Acceptance Criteria:**

- GIVEN infrastructure routes exist in the database WHEN the infrastructure overlay is toggled on THEN cable and pipeline routes are rendered as polylines on the globe
- GIVEN a telecom cable WHEN rendered THEN it is colored blue
- GIVEN a power cable WHEN rendered THEN it is colored yellow
- GIVEN a gas or oil pipeline WHEN rendered THEN it is colored orange
- GIVEN the overlay toggle WHEN toggled off THEN all infrastructure lines are hidden
- GIVEN many routes WHEN the globe is zoomed out THEN routes are visible but not overwhelming (appropriate line width)

**Test Requirements:**

- [ ] Test: API call fetches infrastructure routes and returns GeoJSON-compatible data
- [ ] Test: Toggle on renders polylines, toggle off removes them
- [ ] Test: Color mapping: telecom_cable=blue, power_cable=yellow, gas_pipeline=orange, oil_pipeline=orange
- [ ] Test: Routes render with correct geographic positions on the globe

**Technical Notes:**

- New API endpoint needed: `GET /api/infrastructure/routes` returning route geometries as GeoJSON
- Component: `frontend/src/components/Globe/InfrastructureOverlay.tsx`
- Uses CesiumJS PolylineGraphics or GeoJsonDataSource for rendering
- Line width: 2px at current zoom, scales slightly with zoom level
- Add toggle to existing Overlays.tsx controls (alongside STS zones and terminals)
- Fetch data once on component mount, cache with TanStack Query (routes rarely change)

---

### Story 2: Infrastructure Globe Overlay — Point Features

**As an** operator
**I want to** see cable landing stations, offshore wind farms, and oil/gas platforms on the globe
**So that** I have a complete picture of all critical maritime infrastructure

**Acceptance Criteria:**

- GIVEN cable landing stations in the database WHEN the overlay is on THEN they are rendered as small markers at cable-to-shore transition points
- GIVEN offshore wind farm boundaries WHEN the overlay is on THEN they are rendered as polygon outlines
- GIVEN oil/gas platform locations WHEN the overlay is on THEN they are rendered as point markers
- GIVEN the infrastructure overlay toggle WHEN toggled THEN all infrastructure features (routes + points) toggle together

**Test Requirements:**

- [ ] Test: Landing station markers render at correct positions
- [ ] Test: Wind farm polygons render as outlines (not filled)
- [ ] Test: Platform markers render at correct positions
- [ ] Test: All features share the same toggle control

**Technical Notes:**

- Landing stations and platforms come from the same `infrastructure_routes` or `zones` table (point features)
- Wind farm polygons from zones table (zone_type='wind_farm')
- Use distinct marker icons/shapes: landing station = small square, platform = diamond
- Render in same InfrastructureOverlay component
- Extend the API endpoint to include point features and polygons

---

### Story 3: Infrastructure Risk Halos

**As an** operator
**I want to** see cable corridor segments glow when a yellow or red-flagged vessel is nearby
**So that** my attention is immediately drawn to vessels near infrastructure that already have risk indicators

**Acceptance Criteria:**

- GIVEN a yellow-tier vessel within a cable corridor WHEN the infrastructure overlay is on THEN the corridor segment near the vessel pulses with an amber glow
- GIVEN a red-tier vessel within a cable corridor WHEN the infrastructure overlay is on THEN the corridor segment pulses with a red glow
- GIVEN a green-tier vessel within a cable corridor WHEN rendered THEN no halo is shown (low-risk vessel, no visual alert)
- GIVEN the vessel exits the corridor WHEN the halo was active THEN the halo disappears

**Test Requirements:**

- [ ] Test: Yellow vessel in corridor → amber halo renders on nearby corridor segment
- [ ] Test: Red vessel in corridor → red halo renders
- [ ] Test: Green vessel in corridor → no halo
- [ ] Test: Halo disappears when vessel leaves corridor
- [ ] Test: Halo color matches vessel risk tier

**Technical Notes:**

- Halo implementation: render a wider, semi-transparent polyline segment overlaid on the route near the vessel position
- Use vessel positions from the Zustand store + infrastructure route geometry from cached API data
- Compute nearest point on route to vessel position (client-side approximation — check if lat/lon is within ~1nm of any route segment)
- Pulse animation: CSS/Cesium material opacity oscillation (0.3-0.7 over 2 seconds)
- Performance consideration: only check halos for vessels currently visible in the viewport

---

### Story 4: Infrastructure Dashboard Panel

**As an** operator
**I want to** see a dashboard panel listing all monitored infrastructure assets and current corridor alerts
**So that** I can quickly assess the infrastructure threat picture

**Acceptance Criteria:**

- GIVEN the dashboard panel WHEN opened THEN it shows a list of monitored infrastructure assets with name, type, and last vessel transit timestamp
- GIVEN vessels currently in infrastructure corridors WHEN the panel is open THEN an alert feed shows those vessels sorted by risk score (highest first)
- GIVEN an infrastructure alert item WHEN clicked THEN the globe centers on that vessel and selects it
- GIVEN no vessels in any corridor WHEN the panel is open THEN the alert feed shows "No active corridor alerts"

**Test Requirements:**

- [ ] Test: Panel lists infrastructure assets from API
- [ ] Test: Alert feed shows vessels in corridors sorted by risk
- [ ] Test: Clicking an alert centers globe and selects vessel
- [ ] Test: Empty state shows "No active corridor alerts"
- [ ] Test: Alert feed updates when new vessel enters a corridor

**Technical Notes:**

- New API endpoint needed: `GET /api/infrastructure/alerts` returning vessels currently in corridors (from infrastructure_events where exit_time IS NULL)
- Component: `frontend/src/components/Dashboard/InfrastructurePanel.tsx`
- Could be a tab within the existing expanded stats dashboard, or a dedicated panel
- Poll every 30 seconds for active corridor events
- Asset list: `GET /api/infrastructure/routes` with last_transit metadata

---

## Technical Design

### Data Model Changes

None — this spec consumes data from spec 23's tables.

### API Changes

- `GET /api/infrastructure/routes` — infrastructure route geometries + metadata as GeoJSON
- `GET /api/infrastructure/alerts` — vessels currently in infrastructure corridors
- Both endpoints added to api-server

### Dependencies

- Spec 23 (infrastructure-protection-backend) must be implemented first
- CesiumJS PolylineGraphics or GeoJsonDataSource for route rendering
- Existing Overlays.tsx toggle pattern
- Existing Zustand store for vessel positions

### Security Considerations

- Read-only endpoints
- Infrastructure route data is public

---

## Implementation Order

### Group 1 (parallel — no dependencies between them)
- Story 1 — Cable/pipeline overlay: `InfrastructureOverlay.tsx`, API endpoint
- Story 4 — Dashboard panel: `InfrastructurePanel.tsx`, alerts API endpoint

### Group 2 (after Group 1)
- Story 2 — Point features: extends InfrastructureOverlay.tsx
- Story 3 — Risk halos: depends on overlay and vessel store integration

**Parallel safety rules:**
- Story 1 and 4 touch different components and different API endpoints
- Story 2 extends Story 1's component file
- Story 3 depends on Story 1 for the rendered routes to apply halos to

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Infrastructure routes render correctly on globe
- [ ] Risk halos pulse at correct locations with correct colors
- [ ] Dashboard panel shows real-time corridor alerts
- [ ] Toggle controls work consistently
- [ ] No regressions in existing globe rendering or overlays
- [ ] Ready for human review
