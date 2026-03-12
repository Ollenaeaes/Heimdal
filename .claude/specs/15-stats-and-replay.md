# Feature Spec: Stats Dashboard and Track Replay

**Slug:** `stats-and-replay`
**Created:** 2026-03-11
**Status:** draft
**Priority:** low
**Wave:** 7 (Polish)

---

## Overview

Build the statistics dashboard with real-time metrics, the track replay feature for animated historical playback, and the vessel dossier export functionality.

## Problem Statement

Operators need at-a-glance metrics about the platform's activity and the ability to replay vessel movements to understand historical behavior. Export functionality allows sharing vessel intelligence.

## Out of Scope

- NOT: PDF export (future scope)
- NOT: Geographic heatmaps (future scope)
- NOT: Machine learning insights

---

## User Stories

### Story 1: Enhanced Stats Dashboard

**As a** user
**I want to** see comprehensive platform statistics
**So that** I can understand the scope of monitored activity

**Acceptance Criteria:**

- GIVEN the stats dashboard WHEN rendered THEN show: total vessels tracked, breakdown by risk tier (green/yellow/red with counts and percentages), active anomalies by severity, dark ship candidate count, GFW events count by type, ingestion rate (positions/sec), storage usage estimate
- GIVEN the stats WHEN updating THEN poll every 30 seconds
- GIVEN the dashboard WHEN clicked THEN expand into a more detailed view with charts/graphs

**Test Requirements:**

- [ ] Test: Dashboard renders all metric categories
- [ ] Test: Tier breakdown shows correct percentages

**Technical Notes:**

Expand the basic stats bar from `11-controls-and-filtering` into a richer view. Can use a simple expandable panel. Charts can be done with lightweight libraries or pure CSS bars.

---

### Story 2: Track Replay

**As a** user
**I want to** replay a vessel's historical track as an animation on the globe
**So that** I can understand the vessel's voyage behavior over time

**Acceptance Criteria:**

- GIVEN the vessel detail panel WHEN a "Replay Track" button is clicked THEN load the full track from `GET /api/vessels/{mmsi}/track`
- GIVEN the replay WHEN started THEN animate the vessel marker along the historical track with play/pause controls
- GIVEN the replay WHEN playing THEN show a timeline scrubber with current position in time
- GIVEN the replay WHEN showing THEN highlight AIS gap periods as red segments in the track
- GIVEN the replay WHEN showing THEN overlay GFW events (encounters, loitering, AIS-disabling) as markers along the track timeline
- GIVEN the replay WHEN at a point THEN show the vessel's data at that timestamp (speed, course, etc.)
- GIVEN the replay WHEN paused THEN allow clicking on the track to jump to a position

**Test Requirements:**

- [ ] Test: Replay loads track data from API
- [ ] Test: Play/pause controls work
- [ ] Test: Timeline scrubber reflects current position
- [ ] Test: AIS gap segments are visually distinct
- [ ] Test: GFW events appear on the track timeline

**Technical Notes:**

Use CesiumJS clock and timeline for animation. Set the Cesium clock to the track's time range. Use `SampledPositionProperty` for smooth interpolation between track points. Create a replay control bar component. Fetch GFW events for the vessel from `GET /api/gfw/events?mmsi={mmsi}` and overlay them on the timeline.

---

### Story 3: Vessel Dossier Export

**As a** user
**I want to** export a vessel's complete dossier as JSON
**So that** I can share vessel intelligence with colleagues or archives

**Acceptance Criteria:**

- GIVEN the vessel detail panel WHEN "Export" is clicked THEN generate a JSON file containing: vessel profile, all anomaly events, GFW events, enrichment data, sanctions matches, recent track, risk breakdown
- GIVEN the export WHEN downloaded THEN filename is `heimdal-dossier-{mmsi}-{date}.json`
- GIVEN the JSON WHEN opened THEN it is human-readable with clear field names

**Test Requirements:**

- [ ] Test: Export button generates valid JSON
- [ ] Test: JSON contains all expected sections (including GFW events)
- [ ] Test: File downloads with correct filename

**Technical Notes:**

Fetch full vessel profile from API, combine with track data and GFW events, create a Blob and trigger download via `URL.createObjectURL`. No backend changes needed — this is a frontend-only aggregation.

---

## Implementation Order

### Group 1 (parallel)
- Story 1 — Enhanced stats dashboard
- Story 2 — Track replay
- Story 3 — Vessel dossier export

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Stats dashboard shows comprehensive metrics (including GFW event counts)
- [ ] Track replay animates smoothly
- [ ] Play/pause/scrub controls work
- [ ] GFW events visible on track replay timeline
- [ ] Export produces valid, complete JSON
- [ ] Code committed with proper messages
- [ ] Ready for human review
