# Feature Spec: SAR & GFW Event Frontend

**Slug:** `sar-frontend`
**Created:** 2026-03-11
**Updated:** 2026-03-12 (GFW Integration — Update 001)
**Status:** completed
**Priority:** low
**Wave:** 7 (Polish)

---

## Overview

Add SAR and GFW event features to the frontend: dark ship detection markers on the globe (sourced from GFW 4Wings API), GFW behavioral event markers (encounters, loitering, AIS-disabling, port visits), and a dark ship filter toggle.

> **Update 001:** SAR detections are now sourced from GFW 4Wings API (not custom Copernicus pipeline). Added GFW event markers for behavioral events. Removed SAR coverage overlay (no longer applicable with GFW-sourced data).

## Problem Statement

SAR detections (especially dark ships) need to be visible on the globe as distinct markers. GFW behavioral events (encounters, loitering) should also be visualized. Operators need to filter for unmatched detections.

## Out of Scope

- NOT: SAR data fetching/storage (handled by enrichment service via GFW API — see `08-enrichment-service`)
- NOT: Globe rendering foundation (see `09-globe-rendering`)
- NOT: Vessel detail panel (see `10-vessel-detail-panel`)

---

## User Stories

### Story 1: SAR Detection Markers

**As a** user
**I want to** see GFW SAR vessel detections on the globe
**So that** I can spot dark ships that aren't transmitting AIS

**Acceptance Criteria:**

- GIVEN SAR detections exist WHEN fetched from `GET /api/sar/detections` THEN render as distinct markers on the globe
- GIVEN a dark ship detection (is_dark=true) WHEN rendered THEN show as white marker with red border and pulsing animation
- GIVEN a matched detection (is_dark=false) WHEN rendered THEN show as a smaller gray marker (lower visual priority)
- GIVEN a SAR marker WHEN clicked THEN show a popup with: detection time, estimated vessel length, matching_score, fishing_score, matched MMSI (if any)
- GIVEN the SAR layer WHEN toggled THEN it can be shown/hidden

**Test Requirements:**

- [ ] Test: SarMarker component renders correctly for dark vs matched detections
- [ ] Test: Click popup shows detection details
- [ ] Test: Layer toggle shows/hides all SAR markers

**Technical Notes:**

Use `sar-detection.svg` icon from public/icons/. Fetch detections via TanStack Query, polling every 5 minutes. Use Cesium BillboardGraphics with pulsing animation for dark ships.

---

### Story 2: GFW Event Markers

**As a** user
**I want to** see GFW behavioral events on the globe
**So that** I can visualize encounters, loitering, AIS-disabling, and port visits

**Acceptance Criteria:**

- GIVEN GFW events exist WHEN fetched from `GET /api/gfw/events` THEN render as distinct markers on the globe, color-coded by event type
- GIVEN an ENCOUNTER event WHEN rendered THEN show as orange diamond marker
- GIVEN a LOITERING event WHEN rendered THEN show as yellow circle marker
- GIVEN an AIS_DISABLING event WHEN rendered THEN show as red triangle marker
- GIVEN a PORT_VISIT event WHEN rendered THEN show as blue square marker
- GIVEN a GFW event marker WHEN clicked THEN show a popup with: event type, start/end time, duration, vessel MMSI/name, encounter partner (if encounter), port name (if port visit)
- GIVEN the GFW events layer WHEN toggled THEN it can be shown/hidden independently
- GIVEN the event type filter WHEN a specific type is selected THEN show only that event type

**Test Requirements:**

- [ ] Test: GfwEventMarker component renders correct icon per event type
- [ ] Test: Click popup shows event details
- [ ] Test: Layer toggle shows/hides all GFW event markers
- [ ] Test: Event type filter works

**Technical Notes:**

Create distinct SVG icons for each event type in public/icons/. Fetch events via TanStack Query, polling every 5 minutes. Use Cesium BillboardGraphics with different colors per event type.

---

### Story 3: Dark Ship Filter

**As a** user
**I want to** filter the globe to show only dark ship detections
**So that** I can focus on vessels not transmitting AIS

**Acceptance Criteria:**

- GIVEN a "Dark Ships" filter toggle WHEN enabled THEN show only SAR detections with is_dark=true
- GIVEN the filter WHEN combined with other filters THEN they work together (e.g., dark ships in a specific bbox)

**Test Requirements:**

- [ ] Test: Dark ship filter shows only is_dark=true detections
- [ ] Test: Filter integrates with existing filter state

---

## Implementation Order

### Group 1 (parallel)
- Story 1 — SAR detection markers
- Story 2 — GFW event markers
- Story 3 — Dark ship filter

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Dark ship markers are visually distinct from vessel markers
- [ ] GFW event markers are color-coded by type
- [ ] Dark ship filter works correctly
- [ ] Code committed with proper messages
- [ ] Ready for human review
