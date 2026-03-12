# Feature Spec: Vessel Detail Panel

**Slug:** `vessel-detail-panel`
**Created:** 2026-03-11
**Status:** completed
**Priority:** high
**Wave:** 5 (Frontend Features)

---

## Overview

Build the vessel detail side panel that slides in from the right when a vessel is selected. Contains all vessel information in sections: identity, current status, risk assessment with anomaly breakdown, voyage timeline, sanctions status, and ownership data.

## Problem Statement

Operators need a comprehensive view of each vessel to make risk assessments. The panel must show everything known about a vessel in an organized, scrollable layout with real-time updates.

## Out of Scope

- NOT: Enrichment form (see `12-manual-enrichment`)
- NOT: Globe rendering (see `09-globe-rendering`)
- NOT: Track replay controls (see `16-stats-and-replay`)
- NOT: Export functionality (see `16-stats-and-replay`)

---

## User Stories

### Story 1: Panel Container and Navigation

**As a** user
**I want to** see a detail panel slide in when I click a vessel
**So that** I can inspect vessel details without losing the globe view

**Acceptance Criteria:**

- GIVEN no vessel selected WHEN the panel area THEN it is hidden
- GIVEN a vessel marker clicked WHEN selectedMmsi is set THEN panel slides in from the right (420px wide)
- GIVEN the panel WHEN open THEN it shows a close button that sets selectedMmsi to null
- GIVEN the panel WHEN open THEN it is scrollable if content exceeds viewport height
- GIVEN the panel WHEN open THEN it fetches full vessel data from `GET /api/vessels/{mmsi}`
- GIVEN the panel WHEN data loading THEN it shows a loading skeleton

**Test Requirements:**

- [ ] Test: Panel renders when selectedMmsi is set
- [ ] Test: Panel hides when selectedMmsi is null
- [ ] Test: Close button clears selection
- [ ] Test: API fetch triggers on MMSI change

**Technical Notes:**

Use TanStack Query for data fetching (`useQuery` with key `['vessel', mmsi]`). Panel layout: fixed right-0, top below header bar, full height, z-index above globe. Animate with CSS transition (transform translateX).

---

### Story 2: Identity Section

**As a** user
**I want to** see vessel identity information
**So that** I know which vessel I'm looking at

**Acceptance Criteria:**

- GIVEN the panel header WHEN rendered THEN shows: vessel name (large text), IMO number, MMSI, flag emoji + flag name, risk tier badge (colored chip with score number)
- GIVEN `IdentitySection` WHEN rendered THEN shows: call sign, ship type (human-readable label, not just code number), dimensions (length x beam), year built
- GIVEN ship_type code WHEN displayed THEN it maps to human-readable labels (e.g., 80 = "Tanker", 70 = "Cargo")

**Test Requirements:**

- [ ] Test: IdentitySection renders all fields from vessel profile
- [ ] Test: Ship type code maps to human-readable label
- [ ] Test: Risk tier badge shows correct color and score

**Technical Notes:**

Ship type mapping: codes 80-89 = "Tanker" variants, 70-79 = "Cargo" variants, etc. Create a utility function for this mapping. Flag emoji: derive from ISO country code.

---

### Story 3: Status Section (Real-Time)

**As a** user
**I want to** see the vessel's current position and navigation status
**So that** I know where the vessel is right now and what it's doing

**Acceptance Criteria:**

- GIVEN `StatusSection` WHEN rendered THEN shows: current position (lat/lon in DMS format), speed (SOG in knots), course (COG in degrees), heading, draught (meters), destination, ETA, navigational status (human-readable)
- GIVEN WebSocket updates WHEN received for this vessel THEN position/speed/course update in real-time without re-fetching
- GIVEN nav_status code WHEN displayed THEN it maps to human-readable: 0=Under way using engine, 1=At anchor, 5=Moored, etc.

**Test Requirements:**

- [ ] Test: StatusSection renders all navigation fields
- [ ] Test: Position format is correct (e.g., "59°41.2'N, 28°24.0'E")
- [ ] Test: Nav status code maps to readable label
- [ ] Test: Real-time updates reflected without page reload

**Technical Notes:**

Subscribe to the vessel's position updates from the Zustand store. The store is already updated by the WebSocket hook. This section just reads from the store for the selected MMSI.

---

### Story 4: Risk Assessment Section

**As a** user
**I want to** see the full risk scoring breakdown
**So that** I can understand exactly why a vessel is flagged

**Acceptance Criteria:**

- GIVEN `RiskSection` WHEN rendered THEN shows: risk score bar (0-200+ scale with colored gradient green→yellow→red), current score as number
- GIVEN the anomaly list WHEN rendered THEN each active (unresolved) anomaly event is shown as a card with: rule name (human-readable), severity badge (colored), points, timestamp, and details text
- GIVEN rule_id WHEN displayed THEN it maps to human-readable names (e.g., "ais_gap" → "AIS Transmission Gap", "sts_proximity" → "STS Zone Loitering")
- GIVEN severity WHEN displayed THEN color coding: critical=dark red, high=red, moderate=amber, low=gray

**Test Requirements:**

- [ ] Test: RiskSection renders score bar with correct fill level
- [ ] Test: Anomaly cards show all required fields
- [ ] Test: Rule IDs map to human-readable names
- [ ] Test: Severity badges have correct colors

**Technical Notes:**

Score bar: div with gradient background, fill width proportional to score (cap visual at 200). Anomaly data comes from the full vessel profile API response. Rule name mapping: create a constant object in utils.

---

### Story 5: Voyage Timeline

**As a** user
**I want to** see an interactive timeline of the vessel's recent voyage
**So that** I can understand the vessel's recent behavior in context

**Acceptance Criteria:**

- GIVEN `VoyageTimeline` WHEN rendered THEN show a horizontal scrollable timeline for the past 7 days
- GIVEN the timeline WHEN showing track THEN display vessel's path as a line with markers for key events
- GIVEN an AIS gap WHEN shown on timeline THEN render as a red dashed segment
- GIVEN an STS zone entry WHEN shown on timeline THEN render as an amber marker
- GIVEN a port proximity event WHEN shown on timeline THEN render as a blue marker
- GIVEN a point on the timeline WHEN clicked THEN fly the globe camera to that position and time

**Test Requirements:**

- [ ] Test: VoyageTimeline renders a scrollable timeline
- [ ] Test: AIS gap events appear as distinct markers
- [ ] Test: Timeline click triggers camera fly-to

**Technical Notes:**

Fetch track data from `GET /api/vessels/{mmsi}/track?start=7d ago`. Merge with anomaly events from the vessel profile. Timeline can be a custom component or use a lightweight timeline library. Camera fly-to: use Cesium Viewer.flyTo() with the position from the clicked timeline point.

---

### Story 6: Sanctions and Ownership Sections

**As a** user
**I want to** see sanctions matches and ownership information
**So that** I can assess regulatory and corporate risk

**Acceptance Criteria:**

- GIVEN `SanctionsSection` WHEN vessel has sanctions matches THEN display each match with: source program, confidence score, matched field, and link to OpenSanctions entity page
- GIVEN `SanctionsSection` WHEN vessel has no matches THEN show "No sanctions matches found"
- GIVEN `OwnershipSection` WHEN ownership_data exists THEN display: registered owner, commercial manager, ISM manager, beneficial owner
- GIVEN `OwnershipSection` WHEN manual_enrichment exists THEN display ownership_chain from enrichment
- GIVEN `OwnershipSection` WHEN no data THEN show "No ownership data — enrich this vessel"

**Test Requirements:**

- [ ] Test: SanctionsSection renders matches with all fields
- [ ] Test: SanctionsSection shows empty state correctly
- [ ] Test: OwnershipSection renders ownership chain
- [ ] Test: OwnershipSection shows prompt when no data

---

## Technical Design

### Data Model Changes

None — reads from API only.

### API Changes

Consumes: `GET /api/vessels/{mmsi}`, `GET /api/vessels/{mmsi}/track`

### Dependencies

- API server endpoints (from `06-api-server`)
- Zustand store and WebSocket (from `09-globe-rendering`)
- TanStack Query (from `05-frontend-shell`)

---

## Implementation Order

### Group 1 (parallel)
- Story 1 — Panel container (layout and data fetching)
- Story 2 — Identity section (static data display)

### Group 2 (parallel — after Group 1)
- Story 3 — Status section (real-time updates)
- Story 4 — Risk assessment section
- Story 5 — Voyage timeline
- Story 6 — Sanctions and ownership sections

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Panel slides in/out smoothly
- [ ] All sections render with correct data
- [ ] Real-time position updates reflected in status section
- [ ] Risk score bar and anomaly cards display correctly
- [ ] Voyage timeline is interactive
- [ ] Code committed with proper messages
- [ ] Ready for human review
