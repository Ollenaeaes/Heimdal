# Feature Spec: AIS Spoofing Detection Frontend

**Slug:** `spoofing-detection-frontend`
**Created:** 2026-03-14
**Status:** draft
**Priority:** high

---

## Overview

Visual indicators for spoofed vessels on the globe (dashed/hatched marker borders), duplicate MMSI connector lines between incompatible positions, and a GNSS interference zone overlay showing areas of probable GPS jamming. These visuals communicate "the position data itself may not be trustworthy" separately from risk tier coloring.

## Problem Statement

Spoofing detection rules (spec 24) identify vessels with suspect AIS data, but the anomaly appears the same as any other in the vessel panel. Operators need an immediate visual signal that a vessel's POSITION may be wrong — distinct from its RISK being high. A vessel could be green-tier but spoofed (its reported location is unreliable). The visual language needs to separate "this vessel is risky" (color) from "this vessel's data is suspect" (border treatment).

## Out of Scope

- NOT: Backend spoofing rules (spec 24)
- NOT: Land mask data loading (spec 24)
- NOT: RF direction-finding or SAR cross-referencing
- NOT: Manual MMSI whitelist management UI

---

## User Stories

### Story 1: Spoofed Vessel Marker Styling

**As an** operator
**I want to** see a distinct visual indicator on vessel markers that have active spoofing anomalies
**So that** I know the position data may not be trustworthy before I even click the vessel

**Acceptance Criteria:**

- GIVEN a vessel with one or more active spoof_* anomalies WHEN rendered on the globe THEN its marker has a dashed or hatched border overlaid on the existing green/yellow/red coloring
- GIVEN a vessel with no spoofing anomalies WHEN rendered THEN its marker has the standard solid appearance
- GIVEN a vessel transitions from spoofed to non-spoofed (anomaly resolved) WHEN rendered THEN the dashed border is removed
- GIVEN the spoof indicator WHEN overlaid THEN it does NOT change the risk tier color — both signals coexist

**Test Requirements:**

- [ ] Test: Vessel with spoof_land_position anomaly → marker has dashed border
- [ ] Test: Vessel with spoof_duplicate_mmsi anomaly → marker has dashed border
- [ ] Test: Vessel with no spoof anomalies → standard marker (no dash)
- [ ] Test: Vessel with spoof anomaly AND red tier → red marker with dashed border (both visible)
- [ ] Test: Spoofed state derives from anomaly data (rule_id starts with 'spoof_')

**Technical Notes:**

- Modify existing vessel marker rendering in `VesselMarkers.tsx`
- Spoof detection: check vessel's unresolved anomalies for any rule_id starting with `spoof_`
- Implementation options: (a) dashed circle overlay billboard, (b) second billboard with hatched texture, (c) CSS border on the marker element
- The spoofed state should be available in the Zustand vessel store — add a `hasSpoofAnomaly` derived flag
- Anomaly data comes from the existing anomaly WebSocket or polling — no new data source needed

---

### Story 2: Duplicate MMSI Connector Lines

**As an** operator
**I want to** see both reported positions of a duplicate MMSI connected by a dashed line on the globe
**So that** I can immediately see the spatial impossibility of the duplicate transmission

**Acceptance Criteria:**

- GIVEN a duplicate MMSI detection (spoof_duplicate_mmsi anomaly) WHEN both positions are known THEN a dashed line connects them on the globe
- GIVEN the dashed line WHEN rendered THEN it has a label "Duplicate MMSI" at the midpoint
- GIVEN the duplicate detection resolves WHEN the vessel's next position is normal THEN the connector line disappears
- GIVEN no duplicate MMSI detections WHEN the globe renders THEN no connector lines are shown

**Test Requirements:**

- [ ] Test: Duplicate MMSI anomaly with two positions → dashed line renders between them
- [ ] Test: Line has "Duplicate MMSI" label
- [ ] Test: Line disappears when anomaly resolves
- [ ] Test: No duplicate anomalies → no lines rendered

**Technical Notes:**

- The spoof_duplicate_mmsi anomaly details contain the conflicting position: `{lat, lon, conflicting_lat, conflicting_lon}`
- Component: `frontend/src/components/Globe/DuplicateMmsiLines.tsx`
- Use CesiumJS PolylineGraphics with dashed material (PolylineDashMaterialProperty)
- Label: CesiumJS LabelGraphics positioned at midpoint of the line
- Data source: poll anomaly API for active spoof_duplicate_mmsi events, or derive from WebSocket alerts
- Only show lines for currently active (unresolved) duplicate MMSI anomalies

---

### Story 3: GNSS Interference Zone Overlay

**As an** operator
**I want to** see GNSS interference zones displayed as semi-transparent overlays on the globe
**So that** I can identify areas where GPS jamming may affect vessel position accuracy

**Acceptance Criteria:**

- GIVEN GNSS interference zones exist in the database (not expired) WHEN the overlay is toggled on THEN zones are rendered as semi-transparent red/orange polygons on the globe
- GIVEN a zone's affected_count WHEN rendering THEN opacity scales with affected count (more vessels = more opaque, range 0.15-0.5)
- GIVEN a zone has expired (expires_at < now()) WHEN the overlay renders THEN the zone is NOT shown
- GIVEN the overlay toggle WHEN toggled off THEN all GNSS zones are hidden
- GIVEN a GNSS zone WHEN hovered or clicked THEN a tooltip shows: detection time, affected vessel count, and time until expiry

**Test Requirements:**

- [ ] Test: Active GNSS zone → semi-transparent polygon renders on globe
- [ ] Test: Expired zone → not rendered
- [ ] Test: Opacity scales with affected_count (3 vessels = 0.15, 10+ vessels = 0.5)
- [ ] Test: Toggle on/off works
- [ ] Test: Tooltip shows zone details on interaction

**Technical Notes:**

- New API endpoint: `GET /api/gnss-zones` returning active (non-expired) zones as GeoJSON
- Component: `frontend/src/components/Globe/GnssZoneOverlay.tsx`
- Use CesiumJS PolygonGraphics or GeoJsonDataSource with semi-transparent fill
- Color: red-orange gradient (#FF4444 to #FF8800) based on affected_count
- Poll every 60 seconds (zones change slowly — 24h expiry)
- Add toggle to Overlays.tsx controls

---

## Technical Design

### Data Model Changes

None — consumes data from spec 24 tables.

### API Changes

- `GET /api/gnss-zones` — active GNSS interference zones as GeoJSON

### Dependencies

- Spec 24 (spoofing-detection-backend) must be implemented first
- Existing anomaly data pipeline (WebSocket alerts or REST polling)
- CesiumJS PolylineGraphics, PolygonGraphics, LabelGraphics

### Security Considerations

- Read-only endpoints
- No sensitive data exposed

---

## Implementation Order

### Group 1 (parallel — independent components)
- Story 1 — Spoof marker styling: modifies `VesselMarkers.tsx`
- Story 3 — GNSS zone overlay: new `GnssZoneOverlay.tsx`

### Group 2 (after Group 1)
- Story 2 — Duplicate MMSI lines: new `DuplicateMmsiLines.tsx` (depends on spoof marker logic being in place for data flow consistency)

**Parallel safety rules:**
- Story 1 modifies existing VesselMarkers.tsx
- Stories 2 and 3 create new component files — no conflicts with each other or Story 1

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Dashed borders visible on spoofed vessel markers
- [ ] Duplicate MMSI lines render correctly with labels
- [ ] GNSS zones render and expire correctly
- [ ] All toggle controls work
- [ ] No regressions in existing vessel marker rendering
- [ ] Performance acceptable with multiple spoofed vessels and GNSS zones
- [ ] Ready for human review
