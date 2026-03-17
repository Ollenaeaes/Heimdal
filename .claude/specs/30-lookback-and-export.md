# Feature Spec: Vessel Lookback & Track Export

**Slug:** `lookback-and-export`
**Created:** 2026-03-16
**Status:** completed
**Priority:** high

---

## Overview

Replace the existing single-vessel track replay with a multi-vessel temporal lookback system. A full-width bottom timeline bar lets operators scrub through time or play back at 1x/5x/30x/100x, watching up to 5 selected vessels (plus their network connections) move simultaneously on the globe. For data older than the 30-day hot window, provide a track export as JSON or CSV.

## Problem Statement

The current replay only shows one vessel at a time, embedded in the VesselPanel. Operators investigating interactions (STS transfers, convoy behavior, encounter follow-ups) need to watch multiple vessels move together in the same timeframe. Additionally, historical data beyond the 30-day DB retention is only available in cold Parquet storage — there's no way to access it from the UI.

## Out of Scope

- NOT: Playback of cold storage data (beyond 30 days) — that's export-only
- NOT: Streaming real-time playback (this is historical lookback only)
- NOT: More than 5 user-selected vessels in playback (network vessels are additive but read-only)
- NOT: PDF/image export of tracks
- NOT: Saving/sharing lookback sessions
- NOT: Saving/reusing drawn polygons (predefined zones are a future feature)
- NOT: Polygon vertex editing after drawing (redraw to change the area)
- NOT: Modifying the cold archiver or retention settings

---

## User Stories

### Story 1: Collapsible Panel Sections

**As a** user
**I want** all VesselPanel sections (except the top identity card) to be collapsible to their header
**So that** I can focus on the sections I care about without scrolling

**Acceptance Criteria:**

- GIVEN any VesselPanel section below IdentitySection WHEN I click its header THEN it toggles between collapsed (header only) and expanded (full content)
- GIVEN sections that already have expand/collapse (Ownership, NetworkGraph) WHEN rendered THEN they use the same shared collapsible pattern as new sections
- GIVEN a collapsible section WHEN collapsed THEN only the section title header row is visible (matching the existing Ownership pattern: uppercase label + ▲/▼ indicator)

**Test Requirements:**

- [ ] Test: Each section below IdentitySection renders with a clickable header that toggles content visibility
- [ ] Test: Collapsed sections show only the header row, expanded sections show full content
- [ ] Test: Sections that were already collapsible (Ownership) still work identically

**Technical Notes:**

Extract a shared `CollapsibleSection` wrapper component from the existing OwnershipSection pattern. Apply it to: StatusSection, RiskSection, VoyageTimeline, SanctionsSection, NetworkGraph, VesselChain, EnrichmentForm, EquasisSection, EquasisUpload, EnrichmentHistory, and the new Lookback/Export section. IdentitySection stays fixed (always visible).

---

### Story 2: Lookback Section in VesselPanel (Setup UI)

**As a** user
**I want** a "Lookback" collapsible section in the VesselPanel where I can configure multi-vessel playback
**So that** I can set up which vessels to watch and over what time range

**Acceptance Criteria:**

- GIVEN a selected vessel WHEN the VesselPanel renders THEN a "Lookback" collapsible section appears (replacing the old Track Replay section)
- GIVEN the Lookback section expanded WHEN I see it THEN it shows: a date range picker (start/end, defaulting to last 7 days, max 30 days), a vessel search input to add companion vessels (up to 5 total including the selected vessel), a list of currently added vessels with remove buttons, a "Show network" toggle checkbox, and a "Start Playback" button
- GIVEN the vessel search WHEN I type a name/MMSI/IMO THEN it shows matching results from the vessel store (same as the existing top search bar logic)
- GIVEN 5 vessels already added WHEN I try to add another THEN the search input is disabled with a "Max 5 vessels" hint
- GIVEN "Show network" is checked WHEN playback starts THEN vessels from the network graph of all selected vessels are also included (displayed but not counted toward the 5 limit)
- GIVEN the Lookback section WHEN "Start Playback" is clicked THEN the bottom timeline bar appears and playback mode activates

**Test Requirements:**

- [ ] Test: Lookback section renders in VesselPanel with date range picker, vessel search, vessel list, network toggle, and start button
- [ ] Test: Adding vessels via search works — vessels appear in the list, duplicates rejected
- [ ] Test: Cannot add more than 5 vessels (including primary selected vessel)
- [ ] Test: Removing a vessel from the list works
- [ ] Test: Date range is clamped to max 30 days ago
- [ ] Test: "Start Playback" dispatches to the lookback store and activates the timeline bar

**Technical Notes:**

Create `LookbackSection.tsx` in VesselPanel/. Use the existing `useVesselStore` search/filter logic for the vessel search. Store lookback configuration in a new `useLookbackStore` (Zustand). The old `TrackReplay.tsx` component and `useTrackReplay` hook will be removed after this feature is complete. The old `useReplayStore` is replaced by `useLookbackStore`.

---

### Story 3: Multi-Vessel Track Fetching

**As a** system
**I want** to fetch track data for multiple vessels in a given time range
**So that** the lookback timeline can animate all vessels simultaneously

**Acceptance Criteria:**

- GIVEN lookback is activated with vessels [A, B, C] and date range [start, end] WHEN tracks load THEN fetch `GET /api/vessels/{mmsi}/track?start=...&end=...` for each vessel in parallel
- GIVEN "Show network" is enabled WHEN tracks load THEN also fetch network data for each selected vessel via `GET /api/network/vessel/{mmsi}?depth=1`, collect unique network vessel MMSIs, and fetch their tracks too
- GIVEN network vessels WHEN displayed THEN they use a dimmed/ghost style (lower opacity, no selection interaction) to distinguish from the user-selected vessels
- GIVEN a track fetch fails for one vessel WHEN others succeed THEN show the available tracks and display a warning badge on the failed vessel

**Test Requirements:**

- [ ] Test: Activating lookback fetches tracks for all configured vessels in parallel
- [ ] Test: With "Show network" enabled, network vessel MMSIs are resolved and their tracks fetched
- [ ] Test: Failed track fetches don't block other vessels — partial results shown
- [ ] Test: Track data is correctly keyed by MMSI in the lookback store

**Technical Notes:**

Create `useLookbackTracks` hook that takes the lookback config (vessel list, date range, showNetwork flag) and uses `useQueries` from TanStack React Query to fetch all tracks in parallel. Network vessel resolution is a two-step process: first fetch network graphs, then fetch tracks for discovered MMSIs. Use `simplify=0.001` for tracks longer than 10,000 points to keep rendering performant.

---

### Story 4: Bottom Timeline Bar

**As a** user
**I want** a full-width timeline bar at the bottom of the screen
**So that** I can scrub through time and control playback for all vessels

**Acceptance Criteria:**

- GIVEN lookback is active WHEN the timeline bar renders THEN it spans the full width of the screen at the bottom (above any existing bottom UI), height ~60px, dark semi-transparent background
- GIVEN the timeline bar WHEN rendered THEN it shows: a play/pause button, speed buttons (1x, 5x, 30x, 100x), a full-width scrubber/slider representing the selected date range, the current timestamp displayed prominently, and a close/exit button
- GIVEN the scrubber WHEN I click or drag on it THEN the playback position jumps to that point in time — all vessels update their positions accordingly
- GIVEN playback is playing at Nx speed WHEN time advances THEN the scrubber playhead moves proportionally and all vessel markers on the globe move to their interpolated positions at that timestamp
- GIVEN the timeline bar WHEN "close" is clicked THEN lookback mode deactivates, the timeline bar disappears, and vessel markers return to their current real-time positions
- GIVEN AIS gaps for any vessel WHEN the timeline renders THEN gap periods are shown as red-tinted regions on the scrubber (matching existing pattern)
- GIVEN the current time position WHEN a vessel has no data at that exact timestamp THEN interpolate between the nearest before/after track points for smooth animation

**Test Requirements:**

- [ ] Test: Timeline bar renders at screen bottom with play/pause, speed buttons, scrubber, timestamp, and close button
- [ ] Test: Clicking the scrubber updates the current time and all vessel positions
- [ ] Test: Speed buttons change playback rate — 1x = real-time proportional, 100x = 100x faster
- [ ] Test: Play/pause toggles animation
- [ ] Test: Close button deactivates lookback and hides the timeline bar
- [ ] Test: AIS gap regions appear as red overlays on the scrubber
- [ ] Test: Timestamp label updates as playback progresses

**Technical Notes:**

Create `TimelineBar.tsx` in `components/Globe/` (it's a globe-level overlay, not a panel component). The animation loop should be time-based, not index-based like the old replay. Instead of stepping through track array indices, advance a `currentTime: Date` by `deltaMs * playbackSpeed` each frame. For each vessel, binary-search or linearly scan their track array to find the surrounding points and interpolate lat/lon. Use `requestAnimationFrame` for smooth animation. The timeline bar sits at `position: fixed; bottom: 0; left: 0; right: 0; z-index: 40`.

---

### Story 5: Globe Multi-Vessel Rendering During Lookback

**As a** user
**I want** to see all lookback vessels moving on the globe simultaneously
**So that** I can observe interactions and movement patterns between vessels

**Acceptance Criteria:**

- GIVEN lookback is active WHEN the globe renders THEN each user-selected vessel shows as a colored marker (risk-tier colored) with its track trail drawn behind it up to the current playback time
- GIVEN network vessels in lookback WHEN the globe renders THEN they appear as smaller, semi-transparent markers (40% opacity) with thin track trails
- GIVEN a vessel marker during lookback WHEN I hover it THEN show a tooltip with vessel name/MMSI, current interpolated speed, and risk tier
- GIVEN lookback is active WHEN the VesselPanel is still open THEN the selected vessel's panel data remains visible (identity, risk, etc.) — only the old replay section is replaced by the new Lookback section
- GIVEN lookback is active WHEN I click a vessel marker on the globe THEN it does NOT change the VesselPanel selection (lookback mode locks selection)

**Test Requirements:**

- [ ] Test: All selected vessels render as markers on the globe during lookback
- [ ] Test: Network vessels render with reduced opacity
- [ ] Test: Track trails draw progressively as playback advances
- [ ] Test: Vessel markers rotate based on interpolated COG
- [ ] Test: Clicking globe markers during lookback does not change vessel selection

**Technical Notes:**

Create `LookbackOverlay.tsx` in `components/Globe/` replacing `ReplayOverlay.tsx`. This component reads from `useLookbackStore` and renders Cesium Entities for each vessel. For each vessel: a Billboard (reusing the existing icon generation from VesselMarkers), a PolylineGraphics for the trail (from track start to current time), and optionally course-based rotation. Keep the existing VesselMarkers component but hide the real-time markers for vessels that are in the lookback set (to avoid double-rendering).

---

### Story 6: Track Export (JSON/CSV)

**As a** user
**I want** to export a vessel's track data as JSON or CSV
**So that** I can analyze historical tracks offline, including data from cold storage beyond 30 days

**Acceptance Criteria:**

- GIVEN the VesselPanel WHEN I see the "Track Export" collapsible section THEN it shows: a date range picker (no 30-day limit — can request any historical range), format selector (JSON or CSV), and an "Export" button
- GIVEN a date range within the last 30 days WHEN I click Export THEN the track is fetched from `GET /api/vessels/{mmsi}/track?start=...&end=...` and downloaded as the selected format
- GIVEN a date range older than 30 days WHEN I click Export THEN it calls a new backend endpoint `GET /api/vessels/{mmsi}/track/export?start=...&end=...&format=json|csv` which reads from cold Parquet storage
- GIVEN JSON export WHEN downloaded THEN the file is `track-{mmsi}-{start}-{end}.json` containing an array of `{timestamp, lat, lon, sog, cog, heading}` objects
- GIVEN CSV export WHEN downloaded THEN the file is `track-{mmsi}-{start}-{end}.csv` with headers `timestamp,lat,lon,sog,cog,heading` and one row per position
- GIVEN the export is processing WHEN waiting THEN show a loading spinner on the Export button
- GIVEN cold storage has no data for the requested range WHEN export completes THEN show "No data available for this date range"

**Test Requirements:**

- [ ] Test: Track Export section renders with date range picker, format selector, and export button
- [ ] Test: Export within 30 days fetches from the existing track endpoint and triggers download
- [ ] Test: Export beyond 30 days calls the cold storage export endpoint
- [ ] Test: JSON file contains correct structure and filename
- [ ] Test: CSV file contains correct headers, rows, and filename
- [ ] Test: Loading state shown during export
- [ ] Test: Empty result shows "No data available" message

**Technical Notes:**

**Frontend:** Create `TrackExportSection.tsx` in VesselPanel/. Use `URL.createObjectURL` + `Blob` for client-side download trigger. For CSV, convert JSON array to CSV string client-side.

**Backend:** Create `GET /api/vessels/{mmsi}/track/export` in `routes/vessels.py`. For dates within retention (30 days), query the DB as usual. For dates beyond retention, scan the Parquet files in `{base_path}/cold/ais/YYYY/MM/positions_YYYY-MM.parquet`, filter by MMSI and timestamp range, and return the results. Use `pyarrow` to read Parquet. Return JSON by default; for CSV, set `Content-Type: text/csv` and stream rows. Add `format` query param (`json`|`csv`).

---

### Story 8: Area Lookback (Draw-to-Investigate)

**As a** user investigating an incident in a specific sea area (e.g., subsea cable break, pollution event)
**I want** to draw a polygon on the globe, select a time range, and play back all vessel traffic that passed through that area
**So that** I can identify which vessels were present without knowing their identity in advance

**Acceptance Criteria:**

- GIVEN the globe view WHEN I click an "Area Lookback" button in the toolbar THEN the cursor changes to crosshair mode and I can click to place polygon vertices on the globe; double-click or click the first vertex to close the polygon
- GIVEN I've closed a polygon WHEN the shape completes THEN a configuration popup appears anchored near the polygon showing: the drawn area highlighted in semi-transparent blue, a date range picker (max 30 days), vessel count estimate (fetched on date change), a "Search" button, and a "Cancel" button to clear the polygon
- GIVEN I click "Search" WHEN the query runs THEN the backend returns all distinct vessels that had at least one position report inside the polygon during the time range
- GIVEN search results WHEN displayed THEN the popup shows a vessel list (name, MMSI, flag, risk tier, position count in area) sorted by position count descending, with checkboxes to include/exclude vessels from playback
- GIVEN the vessel list WHEN I click "Start Playback" THEN area lookback activates — all other vessel markers on the globe are hidden, only the discovered vessels are shown, reusing the existing TimelineBar and LookbackOverlay
- GIVEN area lookback is active WHEN the globe renders THEN the drawn polygon remains visible as a semi-transparent overlay, and only the area-discovered vessels (and their tracks) are rendered — no other vessels are shown to save compute
- GIVEN area lookback is active WHEN I close the timeline bar THEN the polygon, area lookback, and vessel hiding all deactivate — normal vessel rendering resumes
- GIVEN the search returns more than 50 vessels WHEN results display THEN show a warning "N vessels found — showing top 50 by activity. Narrow the area or time range for better results." and only the top 50 are available for playback

**Test Requirements:**

- [ ] Test: "Area Lookback" button enters drawing mode with crosshair cursor
- [ ] Test: Clicking on the globe places vertices; a preview polygon line follows the cursor
- [ ] Test: Double-click or clicking the first vertex closes the polygon
- [ ] Test: Configuration popup appears with date range picker and search button
- [ ] Test: Search calls the area-history API endpoint with correct polygon coordinates + time range
- [ ] Test: Results show discovered vessels sorted by position count with checkboxes
- [ ] Test: Unchecking a vessel excludes it from playback
- [ ] Test: "Start Playback" activates lookback with selected vessels and hides all other markers
- [ ] Test: Polygon overlay persists during playback
- [ ] Test: Closing timeline bar clears the polygon and restores normal vessel rendering
- [ ] Test: More than 50 vessels shows warning and truncates to top 50
- [ ] Test: Backend endpoint correctly filters positions within polygon geometry

**Technical Notes:**

**Frontend — Drawing Tool:** Create `AreaLookbackTool.tsx` in `components/Globe/`. Use Cesium `ScreenSpaceEventHandler` with `LEFT_CLICK` to place vertices and `MOUSE_MOVE` to show a preview line from the last vertex to the cursor. Double-click or clicking within 10px of the first vertex closes the polygon. Render the in-progress polygon as a `PolylineGraphics` and the completed polygon as a `PolygonGraphics` with semi-transparent blue fill. Store polygon coordinates in `useLookbackStore`.

**Frontend — Vessel Hiding:** When area lookback is active, `useLookbackStore.isAreaMode = true`. The existing `VesselMarkers` component checks this flag and renders nothing when true. Only `LookbackOverlay` renders vessels during area lookback. This is the simplest way to hide all non-relevant vessels without modifying the marker rendering logic.

**Frontend — Config Popup:** Create `AreaLookbackPanel.tsx` as a floating panel (absolute positioned near the polygon centroid). Shows search config before playback, vessel results after search. Feeds discovered MMSIs into `useLookbackStore.configure()` then `activate()` — reusing TimelineBar and LookbackOverlay without modification.

**Backend:** New endpoint `GET /api/vessels/area-history` in `routes/vessels.py`. Accepts `polygon` (JSON array of `[lon, lat]` coordinate pairs), `start`, `end` query params. Query:
```sql
SELECT vp.mmsi, vp2.ship_name, vp2.flag_state, vp2.risk_tier, COUNT(*) as position_count
FROM vessel_positions vp
JOIN vessel_profiles vp2 ON vp.mmsi = vp2.mmsi
WHERE vp.timestamp BETWEEN :start AND :end
  AND ST_Within(vp.position::geometry, ST_GeomFromGeoJSON(:polygon_geojson))
GROUP BY vp.mmsi, vp2.ship_name, vp2.flag_state, vp2.risk_tier
ORDER BY position_count DESC
LIMIT 50
```
Uses PostGIS `ST_Within` + `ST_GeomFromGeoJSON` against the `vessel_positions.position` geography column. Consider adding a spatial index (`CREATE INDEX idx_positions_geom ON vessel_positions USING GIST (position)`) if query performance is slow on large time ranges.

---

### Story 7: Remove Old Replay System

**As a** developer
**I want** the old single-vessel replay code removed
**So that** there's no dead code or confusion between old and new systems

**Acceptance Criteria:**

- GIVEN the new lookback system is working WHEN reviewing the codebase THEN `TrackReplay.tsx`, `useTrackReplay.ts`, `useReplayStore.ts`, and `ReplayOverlay.tsx` are deleted
- GIVEN VesselPanel.tsx WHEN rendered THEN it no longer imports or references the old replay components
- GIVEN the old replay tests WHEN checked THEN `trackReplay.test.ts` is removed or replaced with lookback tests

**Test Requirements:**

- [ ] Test: No imports of removed modules remain in the codebase
- [ ] Test: VesselPanel renders correctly without old replay components
- [ ] Test: Existing features (vessel selection, track trails, etc.) still work

**Technical Notes:**

This is a cleanup story. Run after all other stories are verified working. Grep for any remaining references to `useTrackReplay`, `useReplayStore`, `TrackReplay`, `ReplayOverlay` and remove them.

---

## Technical Design

### Data Model Changes

No database schema changes. A new Zustand store (`useLookbackStore`) replaces `useReplayStore`:

```typescript
interface LookbackState {
  // Configuration (set before playback starts)
  isActive: boolean;
  selectedVessels: number[];       // MMSIs (max 5 for vessel mode, up to 50 for area mode)
  networkVessels: number[];        // MMSIs from network graph (unbounded but typically <20)
  showNetwork: boolean;
  dateRange: { start: Date; end: Date };

  // Area lookback mode
  isAreaMode: boolean;             // true = area lookback, false = vessel lookback
  areaPolygon: [number, number][] | null;  // [lon, lat] pairs defining the polygon (null when not in area mode)
  isDrawing: boolean;              // true while user is placing polygon vertices

  // Playback state
  isPlaying: boolean;
  playbackSpeed: number;           // 1, 5, 30, 100
  currentTime: Date;               // current playback timestamp

  // Track data (keyed by MMSI)
  tracks: Map<number, TrackPoint[]>;
  trackErrors: Map<number, string>;

  // Actions
  configure: (config: LookbackConfig) => void;
  configureArea: (polygon: [number, number][], vessels: number[], dateRange: DateRange) => void;
  activate: () => void;
  deactivate: () => void;
  play: () => void;
  pause: () => void;
  setSpeed: (speed: number) => void;
  seekToTime: (time: Date) => void;
  seekToProgress: (percent: number) => void;
  setTracks: (mmsi: number, track: TrackPoint[]) => void;
  setTrackError: (mmsi: number, error: string) => void;
  startDrawing: () => void;
  finishDrawing: (polygon: [number, number][]) => void;
  cancelDrawing: () => void;
}
```

### API Changes

**New endpoints:**

```
GET /api/vessels/{mmsi}/track/export?start=<ISO>&end=<ISO>&format=json|csv
```

- Returns track data from either hot DB or cold Parquet storage depending on the date range
- Response: JSON array or CSV stream
- No auth changes (same as existing track endpoint)

```
GET /api/vessels/area-history?polygon=<GeoJSON>&start=<ISO>&end=<ISO>
```

- `polygon`: URL-encoded GeoJSON Polygon geometry (array of `[lon, lat]` coordinate rings)
- Returns distinct vessels with position counts inside the polygon during the time range
- Response: JSON array of `{mmsi, ship_name, flag_state, risk_tier, position_count}`
- Limited to 50 results, ordered by position_count descending
- Uses PostGIS `ST_Within` + `ST_GeomFromGeoJSON` for spatial filtering

### Dependencies

- `pyarrow` — already installed (used by cold-archiver)
- No new frontend dependencies

### Security Considerations

- The export endpoint reads Parquet files from disk — ensure path traversal is impossible (construct paths from validated MMSI + date components only, never from user input strings)
- Rate limiting on the export endpoint since Parquet reads can be expensive (consider adding a simple in-memory semaphore, max 2 concurrent exports)

---

## Implementation Order

### Group 1 (parallel — no dependencies)

- **Story 1** — Collapsible panel sections → `frontend/src/components/VesselPanel/CollapsibleSection.tsx` + refactor all section components
- **Story 6 (backend only)** — Track export API endpoint → `services/api-server/routes/vessels.py`
- **Story 8 (backend only)** — Area-history API endpoint → `services/api-server/routes/vessels.py` (different endpoint, same file — coordinate with Story 6)

### Group 2 (parallel — after Group 1)

- **Story 2** — Lookback section UI → `frontend/src/components/VesselPanel/LookbackSection.tsx` + `frontend/src/hooks/useLookbackStore.ts` (includes area mode fields in store)
- **Story 6 (frontend only)** — Track export UI → `frontend/src/components/VesselPanel/TrackExportSection.tsx`

### Group 3 (parallel — after Group 2)

- **Story 3** — Multi-vessel track fetching → `frontend/src/hooks/useLookbackTracks.ts`
- **Story 4** — Bottom timeline bar → `frontend/src/components/Globe/TimelineBar.tsx`
- **Story 8 (frontend)** — Area drawing tool + config panel → `frontend/src/components/Globe/AreaLookbackTool.tsx` + `AreaLookbackPanel.tsx`

### Group 4 (after Group 3)

- **Story 5** — Globe multi-vessel rendering → `frontend/src/components/Globe/LookbackOverlay.tsx` + modifications to `GlobeView.tsx` (includes area mode: hide other markers when `isAreaMode`, render polygon overlay)

### Group 5 (after Group 4 verified)

- **Story 7** — Remove old replay system → delete old files, update imports

**Parallel safety rules:**
- Stories in the same group touch DIFFERENT files/folders
- Story 5 depends on both the store (Story 2), tracks (Story 3), timeline (Story 4), and area tool (Story 8 frontend)
- Story 8 backend and Story 6 backend both touch `vessels.py` — if in same group, coordinate to avoid conflicts (different functions, append to file)
- Story 7 only runs after everything else is verified working

---

## Development Approach

### Simplifications (what starts simple)

- Vessel position interpolation: linear interpolation between track points (no geodesic interpolation)
- Network vessel resolution: depth=1 only (immediate connections, not full graph)
- Timeline scrubber: simple click-to-seek, no drag support initially
- Cold storage export: read full Parquet file and filter in memory (fine for monthly files)
- Area lookback polygon: simple click-to-place vertices, no vertex editing/dragging after placement
- Area-history query: no spatial index initially — add if query time exceeds 5s on typical ranges

### Upgrade Path (what changes for production)

- "Add drag-to-scrub on the timeline" — UX improvement story
- "Add geodesic interpolation for long gaps" — accuracy improvement
- "Partition Parquet by MMSI for faster cold exports" — performance story if export gets slow
- "Add shared lookback sessions via URL params" — collaboration feature
- "Add polygon vertex editing" — let users drag vertices to adjust the area after drawing
- "Add spatial index on vessel_positions" — `CREATE INDEX idx_positions_geom ON vessel_positions USING GIST (position)` if area queries are slow
- "Add predefined zones for area lookback" — let users pick from saved cable routes, shipping lanes, or port areas instead of drawing

### Architecture Decisions

- **Time-based animation instead of index-based**: The old replay stepped through array indices, which doesn't work for multi-vessel sync since vessels have different position reporting frequencies. The new system advances a global `currentTime` and each vessel independently finds its position at that time.
- **Zustand store over React state**: Lookback state needs to be shared between VesselPanel (config), TimelineBar (controls), LookbackOverlay (rendering), and AreaLookbackTool (drawing) — a global store is the right fit.
- **Separate TimelineBar from VesselPanel**: The timeline is a globe-level UI element, not a panel section. It needs full-width layout and sits outside the panel's DOM hierarchy.
- **Area lookback reuses the same playback infrastructure**: Once vessels are discovered via the area-history query, they're fed into the same `useLookbackStore` → `useLookbackTracks` → `LookbackOverlay` pipeline as vessel-selection lookback. The only difference is the entry point and the `isAreaMode` flag that hides unrelated vessels.
- **Hide all other vessels in area mode**: When `isAreaMode` is true, `VesselMarkers` renders nothing. This avoids computing positions, icons, and interactions for thousands of irrelevant vessels. The globe only renders the discovered area vessels via `LookbackOverlay`.

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled (empty tracks, failed fetches, max vessels, empty area results)
- [ ] No regressions in existing tests
- [ ] Old replay system fully removed with no dead references
- [ ] Code committed with proper messages
- [ ] Ready for human review
