# Feature Spec: Controls and Filtering

**Slug:** `controls-and-filtering`
**Created:** 2026-03-11
**Status:** completed
**Priority:** high
**Wave:** 5 (Frontend Features)

---

## Overview

Build the search bar, risk tier filter toggles, vessel type filter, time range filter, top stats bar, and health indicator. These controls allow operators to find specific vessels and filter the globe view.

## Problem Statement

With thousands of vessels on the globe, operators need tools to find specific vessels and focus on relevant subsets. The stats bar provides at-a-glance system status.

## Out of Scope

- NOT: Globe rendering or markers (see `09-globe-rendering`)
- NOT: Vessel detail panel (see `10-vessel-detail-panel`)
- NOT: Advanced geographic filtering (draw-on-map bbox — future)
- NOT: Dark ship filter (see `15-sar-frontend`)

---

## User Stories

### Story 1: Search Bar

**As a** user
**I want to** search for vessels by name, IMO, or MMSI
**So that** I can quickly find a specific vessel

**Acceptance Criteria:**

- GIVEN the search bar WHEN typing a vessel name THEN show autocomplete results matching the name (case-insensitive)
- GIVEN the search bar WHEN typing a 9-digit number THEN search by MMSI
- GIVEN the search bar WHEN typing a 7-digit number THEN search by IMO
- GIVEN a search result WHEN clicked THEN select the vessel (set selectedMmsi) and fly camera to its position
- GIVEN the search bar WHEN debouncing THEN wait 300ms after last keystroke before querying
- GIVEN the search WHEN querying THEN call `GET /api/vessels?search={term}&per_page=10` (or similar)

**Test Requirements:**

- [ ] Test: SearchBar renders input with placeholder
- [ ] Test: Typing triggers debounced search
- [ ] Test: Clicking result sets selectedMmsi and triggers camera fly-to
- [ ] Test: MMSI and IMO number patterns are detected

**Technical Notes:**

Use TanStack Query for the search endpoint. Debounce with `useDeferredValue` or a custom debounce hook. Position the search bar in the top-left overlay area of the globe. Style with Tailwind: semi-transparent dark background, rounded.

---

### Story 2: Risk Tier Filter

**As a** user
**I want to** toggle visibility of green, yellow, and red vessels on the globe
**So that** I can focus on suspicious or high-risk vessels

**Acceptance Criteria:**

- GIVEN three tier toggle buttons (green, yellow, red) WHEN all are on THEN all vessels visible
- GIVEN green toggled off WHEN filtering THEN green vessels are hidden from the globe
- GIVEN the filter WHEN changed THEN Zustand store filter state updates and WebSocket re-subscribes
- GIVEN the toggles WHEN rendered THEN each shows the count of vessels in that tier

**Test Requirements:**

- [ ] Test: RiskFilter renders three toggle buttons with correct colors
- [ ] Test: Toggling a tier updates the store filter
- [ ] Test: Vessel counts display next to each toggle

**Technical Notes:**

The filter state lives in the Zustand store (`filters.riskTiers`). The globe rendering reads this to show/hide markers. The WebSocket subscription also uses it to reduce data volume.

---

### Story 3: Vessel Type Filter

**As a** user
**I want to** filter by vessel type (tankers, cargo, all)
**So that** I can focus on the vessel categories relevant to shadow fleet monitoring

**Acceptance Criteria:**

- GIVEN a type filter dropdown WHEN "Tankers only" selected THEN only ship_type 80-89 shown
- GIVEN "All types" selected WHEN filtering THEN all vessels shown
- GIVEN a custom selection WHEN choosing THEN arbitrary ship type codes can be toggled

**Test Requirements:**

- [ ] Test: TypeFilter renders dropdown with options
- [ ] Test: Selecting "Tankers" updates store with codes 80-89
- [ ] Test: Selecting "All" clears type filter

**Technical Notes:**

Simple dropdown or multi-select component. Updates `filters.shipTypes` in Zustand store.

---

### Story 4: Time Range Filter

**As a** user
**I want to** filter vessels by when they were last seen
**So that** I can focus on currently active vessels or review a historical period

**Acceptance Criteria:**

- GIVEN preset buttons WHEN clicking "Last 1h", "Last 6h", "Last 24h", "Last 7d" THEN only vessels with positions after that time shown
- GIVEN the filter WHEN applied THEN it updates `filters.activeSince` in Zustand store

**Test Requirements:**

- [ ] Test: TimeRange renders preset buttons
- [ ] Test: Clicking a preset updates activeSince filter

**Technical Notes:**

Simple button group. Use date-fns for time calculations (`subHours`, `subDays`).

---

### Story 5: Stats Bar

**As a** user
**I want to** see key platform metrics at a glance
**So that** I can verify the system is working and understand the current situation

**Acceptance Criteria:**

- GIVEN the stats bar WHEN rendered THEN show in the top bar area: total vessels tracked, count by tier (green/yellow/red), active anomaly count, ingestion rate (positions/sec)
- GIVEN the stats WHEN fetching THEN poll `GET /api/stats` every 30 seconds
- GIVEN ingestion rate WHEN shown THEN display as "X pos/sec" with the value from API

**Test Requirements:**

- [ ] Test: StatsBar renders all metric values
- [ ] Test: Stats refresh on interval

**Technical Notes:**

Use TanStack Query with `refetchInterval: 30000`. Display in a compact horizontal bar with Tailwind styling. Each metric is a small card/chip.

---

### Story 6: Health Indicator

**As a** user
**I want to** see if all system components are healthy
**So that** I know if data might be stale or missing

**Acceptance Criteria:**

- GIVEN the health indicator WHEN all services healthy THEN show a green dot with "All systems operational"
- GIVEN any service unhealthy WHEN displaying THEN show a yellow/red dot with the issue description
- GIVEN health WHEN checking THEN poll `GET /api/health` every 60 seconds
- GIVEN the AIS WebSocket WHEN stale (last_message_at > 2 min ago) THEN show warning

**Test Requirements:**

- [ ] Test: HealthIndicator shows green when all healthy
- [ ] Test: HealthIndicator shows warning when service is down

**Technical Notes:**

Small indicator in the top-right of the stats bar. Use TanStack Query for polling. Parse the health response to determine overall status.

---

## Technical Design

### Data Model Changes

None — frontend only. Extends Zustand store filter state.

### API Changes

Consumes: `GET /api/vessels` (search), `GET /api/stats`, `GET /api/health`

### Dependencies

- API server endpoints (from `06-api-server`)
- Zustand store (from `05-frontend-shell`)
- TanStack Query (from `05-frontend-shell`)

---

## Implementation Order

### Group 1 (parallel — all independent)
- Story 1 — Search bar
- Story 2 — Risk tier filter
- Story 3 — Vessel type filter
- Story 4 — Time range filter
- Story 5 — Stats bar
- Story 6 — Health indicator

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Search finds vessels by name, IMO, and MMSI
- [ ] Risk tier toggles show/hide vessels correctly
- [ ] Type filter limits to selected ship types
- [ ] Time range filter works with presets
- [ ] Stats bar shows live metrics
- [ ] Health indicator reflects actual service status
- [ ] Code committed with proper messages
- [ ] Ready for human review
