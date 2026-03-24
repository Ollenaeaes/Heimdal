# Feature Spec: Real Spoofing Footprint Detection

**Slug:** `spoofing-footprint`
**Created:** 2026-03-24
**Status:** approved
**Priority:** high

---

## Overview

Extend the GNSS zone detector to also create zones around the **pre-jump positions** — where vessels physically were when their GPS started reporting impossible speeds. Currently zones are only created around where spoofed positions cluster (e.g., Kaliningrad), missing the true geographic extent of interference. With this change, the area between Bornholm and Gotland where Astor Marine was actually sailing would also be painted as an affected zone.

## Problem Statement

Russia broadcasts GPS spoofing signals from Kaliningrad that affect vessels across the southern/central Baltic. Our zone detector currently clusters the **spoofed positions** (where the GPS says the vessel jumped to), not the **real positions** (where the vessel was when it got spoofed). This means the map shows a big red zone over Kaliningrad but nothing over the sea lanes between Bornholm and Gotland where vessels are actually being affected. Analysts can't see the true interference coverage area.

Data confirms: vessels from Bergen (Norway) to Gdansk (Poland) all get their positions dragged to the same Kaliningrad cluster. The real spoofing footprint is an area stretching hundreds of kilometers — far larger than what's currently shown.

## Out of Scope

- NOT: Changes to the GNSS zones API endpoint (the new zone type flows through the existing API)
- NOT: Changes to the playback/timeline system (interference_area zones just appear alongside existing zones)
- NOT: Per-vessel spoofing alerts or scoring (vessels are victims, not suspects)
- NOT: Historical backfill of pre-jump zones for already-detected events
- NOT: Changes to jamming detection logic

---

## User Stories

### Story 1: Detect Pre-Jump Positions in Zone Detector

**As a** system
**I want to** find the last known good position of each vessel before an impossible-speed jump
**So that** I know where vessels physically were when they entered the spoofing field

**Acceptance Criteria:**

- GIVEN the zone detector finds anomalous positions (implied speed > 45 kn) WHEN it processes them THEN for each anomalous position it also retrieves the previous position (the pre-jump location)
- GIVEN a vessel at 55.4°N 15.0°E that jumps to 54.9°N 20.0°E (Kaliningrad) WHEN the detector runs THEN the pre-jump position (55.4°N 15.0°E) is available for clustering alongside the post-jump position
- GIVEN the pre-jump position is further than 50km from the post-jump cluster WHEN clustering runs THEN the pre-jump positions form their own cluster (the interference area) separate from the spoofing target cluster

**Test Requirements:**

- [ ] Test: `_find_anomalous_positions` returns both the anomalous position AND the previous (pre-jump) position for each vessel
- [ ] Test: Pre-jump position has correct lat/lon from the LAG() window function
- [ ] Test: When pre-jump positions cluster separately from post-jump positions, two distinct clusters are produced
- [ ] Test: Pre-jump positions that are close together (same sea lane) form a single interference_area cluster

**Technical Notes:**

Modify `_find_anomalous_positions()` in `gnss_zone_detector.py`. The SQL already uses `LAG()` to get the previous position — extend it to also return `prev_lat`, `prev_lon`, `prev_timestamp` in the result. Then in the return value, yield TWO rows per anomalous pair:
1. The post-jump position (current behavior, lat/lon) — tagged `position_type='spoofed'`
2. The pre-jump position (prev_lat/prev_lon) — tagged `position_type='pre_jump'`

Both go into the same list and get clustered by DBSCAN. Since pre-jump positions are geographically far from post-jump positions (different sea area), they'll naturally form separate clusters.

---

### Story 2: Tag Zones by Origin Type

**As a** system
**I want to** label whether a zone was created from spoofed positions or pre-jump positions
**So that** the frontend can color them differently

**Acceptance Criteria:**

- GIVEN a cluster where most positions are tagged `position_type='spoofed'` WHEN a zone is created THEN its `event_type` is set to `'spoofing'` (existing behavior)
- GIVEN a cluster where most positions are tagged `position_type='pre_jump'` WHEN a zone is created THEN its `event_type` is set to `'interference_area'`
- GIVEN an existing `'spoofing'` zone that overlaps with new pre-jump positions WHEN the zone is updated THEN the `event_type` stays `'spoofing'` (post-jump positions are the defining characteristic of the target zone)

**Test Requirements:**

- [ ] Test: Cluster with >50% `pre_jump` positions produces a zone with `event_type='interference_area'`
- [ ] Test: Cluster with >50% `spoofed` positions produces a zone with `event_type='spoofing'`
- [ ] Test: Mixed cluster uses majority vote for event_type
- [ ] Test: Existing spoofing zone doesn't get its type overwritten by pre-jump positions

**Technical Notes:**

Modify `_classify_event_type()` to accept the position_type tags. If the majority of positions in the cluster have `position_type='pre_jump'`, return `'interference_area'`. Otherwise keep existing logic (`'spoofing'` or `'jamming'`).

The `event_type` column in `gnss_interference_zones` is already a text field — no migration needed for the new value.

---

### Story 3: Render Interference Area Zones in Cyan/Blue

**As an** analyst
**I want to** see interference area zones in a different color from spoofing target zones
**So that** I can distinguish where vessels actually were from where their GPS was dragged to

**Acceptance Criteria:**

- GIVEN the GNSS layer is visible WHEN interference_area zones exist THEN they render in cyan/blue (distinguishable from red/orange spoofing zones)
- GIVEN both spoofing and interference_area zones exist simultaneously WHEN viewing the map THEN the two zone types are visually distinct — red for spoofing target, cyan for interference area
- GIVEN the playback GNSS overlay is active WHEN interference_area zones exist in the time range THEN they appear/disappear at correct timestamps just like spoofing zones

**Test Requirements:**

- [ ] Test: GnssHeatmap fill paint has a third branch for `event_type='interference_area'` using cyan/blue colors
- [ ] Test: GnssHeatmap line paint has matching cyan/blue outline for interference_area zones
- [ ] Test: PlaybackGnssOverlay filters and renders interference_area zones correctly

**Technical Notes:**

Modify `GnssHeatmap.tsx` fill paint to add a third `case` branch:
```
['==', ['get', 'event_type'], 'interference_area'],
[
  'interpolate', ['linear'], ['get', 'affected_count'],
  1, 'rgba(6,182,212,0.3)',    // cyan-500 at 30% for 1 vessel
  15, 'rgba(14,116,144,0.8)',  // cyan-700 at 80% for 15+ vessels
],
```

Same for line paint: `'rgba(6,182,212,0.9)'` for interference_area outlines.

The `PlaybackGnssOverlay.tsx` doesn't need changes — it renders whatever features are in the GeoJSON, and the paint styles from GnssHeatmap handle coloring by event_type.

---

## Technical Design

### Algorithm Change

Current flow:
```
positions → find anomalous (post-jump only) → cluster → create zones
```

New flow:
```
positions → find anomalous (post-jump + pre-jump) → cluster both → create zones with type tag
```

The DBSCAN clustering naturally separates pre-jump positions (e.g., south of Sweden) from post-jump positions (e.g., Kaliningrad) because they're geographically far apart. No changes to clustering logic needed.

### Data Model Changes

None. The `gnss_interference_zones.event_type` column is already a text field. The new value `'interference_area'` is just a new string.

### API Changes

None. The `/api/gnss-zones` endpoint returns all zones as GeoJSON features with `event_type` in properties. The new type flows through automatically.

### Dependencies

- Existing `gnss_zone_detector.py` (all changes are here)
- Existing `GnssHeatmap.tsx` (add paint branch)
- Existing `PlaybackGnssOverlay.tsx` (no changes needed — already handles all event types)

### Security Considerations

None — backend-only detection logic change plus frontend coloring.

---

## Implementation Order

### Group 1 (sequential — detector changes)

- **Story 1: Pre-jump position detection** — modifies `services/scoring/gnss_zone_detector.py` `_find_anomalous_positions()`
- **Story 2: Zone type tagging** — modifies `services/scoring/gnss_zone_detector.py` `_classify_event_type()` and `_upsert_zone()`

Stories 1 and 2 modify the same file sequentially.

### Group 2 (after Group 1)

- **Story 3: Frontend coloring** — modifies `frontend/src/components/Map/GnssHeatmap.tsx` paint styles

---

## Development Approach

### Simplifications

- Pre-jump position is taken from the LAG() window function that already exists in the SQL query — no additional DB query needed
- DBSCAN clustering doesn't need parameter changes — the geographic separation between pre-jump and post-jump positions is large enough (hundreds of km) that they naturally form separate clusters at the current 0.25° (~15nm) radius
- No migration needed — event_type is already a text column

### Upgrade Path

- "Add interference area boundary estimation from multiple jump origins" — use the pre-jump positions over time to estimate the effective range of the spoofing transmitter (circular approximation from the broadcast site)
- "Correlate interference_area zones with known transmitter locations" — database of known Russian military GPS spoofing installations
- "Temporal analysis: when does the interference area expand/contract" — track zone size changes over time

### Architecture Decisions

- **Dual-position approach over separate detector**: Emitting both pre-jump and post-jump positions from the same query and letting DBSCAN separate them is simpler and more correct than running two separate detection passes.
- **Majority vote for event_type over always tagging**: In edge cases where pre-jump and post-jump positions land in the same cluster (vessel very close to the spoofing source), the majority vote keeps the classification sensible.
- **Cyan/blue for interference vs red for spoofing**: Cyan communicates "affected area" without alarm, while red communicates "active spoofing target." This matches maritime chart conventions where blue is informational and red is danger.

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Pre-jump positions correctly extracted from existing LAG() query
- [ ] DBSCAN naturally separates pre-jump from post-jump clusters
- [ ] interference_area zones render in cyan/blue
- [ ] spoofing zones still render in red/orange (no regression)
- [ ] Playback overlay handles interference_area zones correctly
- [ ] Zone detector still runs within acceptable time (< 30s per cycle)
- [ ] Code committed with proper messages
- [ ] Ready for human review
