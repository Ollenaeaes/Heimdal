# Feature Spec: Globe Vessel Rendering

**Slug:** `globe-rendering`
**Created:** 2026-03-11
**Status:** draft
**Priority:** high
**Wave:** 5 (Frontend Features)

---

## Overview

Render vessel markers on the CesiumJS globe with risk-tier coloring, directional orientation, clustering at low zoom, geographic overlays (STS zones, Russian terminals, Norwegian EEZ), track trails, and real-time WebSocket position updates.

## Problem Statement

The globe needs to display thousands of moving vessels in real-time with visual differentiation by risk level. Geographic context (STS zones, terminals) must be visible as overlays. Performance must be maintained with up to 25K concurrent markers.

## Out of Scope

- NOT: Vessel detail panel (see `10-vessel-detail-panel`)
- NOT: Search bar and filter controls (see `11-controls-and-filtering`)
- NOT: SAR detection markers (see `15-sar-frontend`)
- NOT: Track replay animation (see `16-stats-and-replay`)

---

## User Stories

### Story 1: WebSocket Connection and Real-Time Updates

**As a** user
**I want to** see vessel positions update in real-time on the globe
**So that** I'm seeing current maritime activity

**Acceptance Criteria:**

- GIVEN the app loads WHEN WebSocket connects to `ws://*/ws/positions` THEN subscription message is sent with current filter state
- GIVEN a position update WHEN received THEN the Zustand vessel store is updated via `updatePosition()`
- GIVEN the WebSocket WHEN disconnected THEN auto-reconnect with exponential backoff
- GIVEN filter changes WHEN applied THEN WebSocket re-subscribes with updated filters

**Test Requirements:**

- [ ] Test: useWebSocket hook connects and receives messages
- [ ] Test: Store updates correctly on position message
- [ ] Test: Reconnection logic works on disconnect

**Technical Notes:**

Create `src/hooks/useWebSocket.ts`. Use native WebSocket API. Parse JSON messages and call `useVesselStore.updatePosition()`. Send subscription filter on connect and on filter change.

---

### Story 2: Vessel Markers with Risk-Tier Coloring

**As a** user
**I want to** see ship markers on the globe colored by risk level
**So that** I can immediately identify suspicious vessels

**Acceptance Criteria:**

- GIVEN a green vessel WHEN rendered THEN marker uses vessel-green.svg, opacity 0.4, scale 0.6
- GIVEN a yellow vessel WHEN rendered THEN marker uses vessel-yellow.svg, opacity 0.9, scale 0.8, amber color (#D4820C)
- GIVEN a red vessel WHEN rendered THEN marker uses vessel-red.svg, opacity 1.0, scale 1.0, with pulsing glow animation
- GIVEN any vessel WHEN rendered THEN marker is rotated to match COG (course over ground)
- GIVEN a vessel marker WHEN clicked THEN set `selectedMmsi` in Zustand store and fly camera to vessel position

**Test Requirements:**

- [ ] Test: VesselMarker component renders with correct SVG for each tier
- [ ] Test: Marker rotation matches COG value
- [ ] Test: Click handler sets selectedMmsi in store

**Technical Notes:**

Use Cesium BillboardGraphics entities. Create `VesselMarker.tsx` component. Rotation: set `billboard.rotation` to `-cog * (Math.PI / 180)` (Cesium uses radians, clockwise). Pulsing glow for red: use Cesium NearFarScalar for scale by distance or CSS animation.

---

### Story 3: Entity Clustering

**As a** user
**I want to** see vessels clustered at low zoom levels
**So that** the globe doesn't become an unreadable sea of markers

**Acceptance Criteria:**

- GIVEN many vessels close together at low zoom WHEN rendered THEN they cluster into a single marker
- GIVEN a cluster WHEN rendered THEN it shows the count and inherits the highest risk tier color
- GIVEN cluster threshold WHEN configured THEN it uses 50 pixels (from config)
- GIVEN zoom in WHEN expanding THEN clusters smoothly break apart into individual markers
- GIVEN the globe WHEN rendering 25K vessels THEN maintain >30fps

**Test Requirements:**

- [ ] Test: VesselCluster component renders with correct count
- [ ] Test: Cluster color reflects highest risk tier of contained vessels
- [ ] Test: Performance stays above 30fps with 10K+ markers

**Technical Notes:**

Use Cesium's `EntityCluster` or implement custom clustering. Cluster pixel range from `config.yaml: frontend.cluster_pixel_range`. For performance with 25K+ markers, consider using `Cesium.PointPrimitiveCollection` instead of Entity per vessel.

---

### Story 4: Geographic Overlays

**As a** user
**I want to** see STS zones, Russian terminals, and the Norwegian EEZ on the globe
**So that** I have geographic context for vessel behavior

**Acceptance Criteria:**

- GIVEN STS zones WHEN rendered THEN show as semi-transparent amber polygons (rgba(212, 130, 12, 0.15)) with amber outline and zone name labels
- GIVEN Russian terminals WHEN rendered THEN show as red point markers (16px) with terminal name labels
- GIVEN Norwegian EEZ WHEN rendered THEN show as blue dashed polyline (outline only, no fill)
- GIVEN overlays WHEN loaded THEN data comes from `src/data/stsZones.json`, `terminals.json`, `eezBoundaries.json`
- GIVEN overlays WHEN toggled THEN each layer can be shown/hidden independently

**Test Requirements:**

- [ ] Test: Overlays component renders without errors
- [ ] Test: 6 STS zone polygons appear at correct locations
- [ ] Test: 7 terminal markers appear at correct coordinates

**Technical Notes:**

Use Cesium PolygonGraphics for STS zones, PointGraphics for terminals, PolylineGraphics for EEZ. Load coordinates from JSON data files (created in `05-frontend-shell`). Create `Overlays.tsx` component.

---

### Story 5: Track Trails

**As a** user
**I want to** see a fading trail behind each vessel showing recent movement
**So that** I can see vessel direction and recent path at a glance

**Acceptance Criteria:**

- GIVEN track trails enabled WHEN rendering THEN show a polyline behind each vessel for the last 1 hour (configurable)
- GIVEN the trail WHEN rendered THEN it fades from full opacity at the vessel to transparent at the trail end
- GIVEN the trail WHEN colored THEN it matches the vessel's risk tier color
- GIVEN track trails WHEN toggled THEN they can be turned on/off (default: on)

**Test Requirements:**

- [ ] Test: TrackTrail component renders a polyline
- [ ] Test: Trail uses correct risk tier color

**Technical Notes:**

Use Cesium PolylineGraphics with material that supports alpha gradient. Trail duration from `config.yaml: frontend.track_trail_hours`. Store recent positions per vessel in the Zustand store (ring buffer of last N positions). Component: `TrackTrail.tsx`.

---

## Technical Design

### Data Model Changes

None — frontend only. Extends Zustand store with WebSocket data.

### API Changes

Consumes: `ws://*/ws/positions` WebSocket endpoint.

### Dependencies

- CesiumJS, Resium (from `05-frontend-shell`)
- API server WebSocket endpoint (from `06-api-server`)
- Zustand store (from `05-frontend-shell`)

---

## Implementation Order

### Group 1 (parallel)
- Story 1 — WebSocket connection (data layer)
- Story 4 — Geographic overlays (static, no data dependency)

### Group 2 (after Group 1)
- Story 2 — Vessel markers (needs WebSocket data in store)
- Story 3 — Entity clustering (needs vessel markers)
- Story 5 — Track trails (needs position history from WebSocket)

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Vessel markers render with correct tier colors
- [ ] Clustering works at low zoom levels
- [ ] All 6 STS zones and 7 terminals visible
- [ ] EEZ boundary renders as dashed blue line
- [ ] Track trails show recent vessel movement
- [ ] Performance >30fps with 25K markers
- [ ] Code committed with proper messages
- [ ] Ready for human review
