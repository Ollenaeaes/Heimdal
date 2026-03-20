# Feature Spec: Replace CesiumJS with MapLibre GL JS

**Slug:** `maplibre-migration`
**Created:** 2026-03-20
**Status:** approved
**Priority:** high

---

## Overview

Replace CesiumJS/Resium (3D globe) with MapLibre GL JS/react-map-gl (2D vector map) to eliminate the continuous 60fps GPU render loop that causes excessive CPU/GPU usage on client machines. All existing map features (vessel markers, tracks, overlays, lookback, infrastructure) are preserved with 1:1 functional equivalence.

## Problem Statement

CesiumJS renders a full 3D WebGL globe at ~60fps continuously, even when idle. On a 3440px-wide display this means 3.9 million pixels redrawn every frame. Measured impact: 104 MB JS heap, 185 tile requests on load, 1 FPS reported (GPU-bound). The 3D globe provides no value over a 2D map for maritime surveillance — all production maritime tracking platforms (MarineTraffic, VesselFinder) use 2D maps.

MapLibre GL JS only renders when the map state changes (pan, zoom, data update), reducing idle CPU to near zero. Bundle size drops from ~4 MB to ~800 KB. Vector tiles are smaller than satellite raster tiles.

## Out of Scope

- NOT: Changing any backend APIs or data models
- NOT: Changing the vessel store, lookback store, or any Zustand state shape
- NOT: Adding new map features not already present
- NOT: Changing the ops-centre dark theme for non-map UI (panels, HUD, controls)
- NOT: Aircraft tracking (future feature — this spec only replaces the map engine)
- NOT: Changing any scoring, enrichment, or detection logic

---

## User Stories

### Story 1: MapLibre Core Setup + Custom Style

**As a** maritime analyst
**I want to** see the vessel map on a clean, fast-loading 2D map
**So that** the application doesn't consume excessive CPU/GPU resources

**Acceptance Criteria:**

- GIVEN the app loads WHEN the map renders THEN it uses MapLibre GL JS (not CesiumJS)
- GIVEN the map is idle (no panning/zooming) WHEN 5 seconds pass THEN zero requestAnimationFrame calls are made by the map engine
- GIVEN the map loads WHEN I see the basemap THEN water is white/near-white, land is light gray, shorelines have a darker gray stroke
- GIVEN the map loads WHEN I zoom into a port area THEN I can distinguish port/industrial areas, oil terminals, and container facilities via landuse polygons
- GIVEN the map loads WHEN the initial view renders THEN it centers on (15°E, 68°N) at a zoom level showing the Norwegian coast (approximately zoom 4)
- GIVEN the map renders WHEN I check the page THEN no Cesium-related scripts, assets, or Ion requests are loaded

**Test Requirements:**

- [ ] Test: Map component renders without errors and produces a canvas element
- [ ] Test: MapLibre style has water color set to white/near-white (#F8FAFC or similar)
- [ ] Test: MapLibre style has land fill color set to light gray (#E2E8F0 or similar)
- [ ] Test: Initial center is [15, 68] and zoom is approximately 4
- [ ] Test: `getCesiumViewer` is replaced by `getMapInstance` returning a MapLibre Map
- [ ] Test: No imports from 'cesium' or 'resium' exist in the codebase

**Technical Notes:**

- Install `maplibre-gl` + `react-map-gl` (the maplibre-compatible version)
- Create `frontend/src/components/Map/MapView.tsx` as the new root map component
- Create `frontend/src/components/Map/mapInstance.ts` to replace `Globe/cesiumViewer.ts` (same pattern: `getMapInstance()` / `setMapInstance()`)
- Custom style JSON in `frontend/src/components/Map/style.ts`:
  - Water: `#F8FAFC` (very light blue-white)
  - Land fill: `#E2E8F0` (slate-200)
  - Land stroke/shoreline: `#94A3B8` (slate-400)
  - Country borders: `#CBD5E1` (slate-300, dashed)
  - City/port labels: `#475569` (slate-600)
  - Industrial/port landuse: `#D1D5DB` (slightly different gray to distinguish)
  - No terrain/hillshade layers
- Tile source: MapTiler vector tiles via `VITE_MAPTILER_KEY` env var
- Map container: `style={{ width: '100%', height: '100%' }}` to fill the viewport (same as Cesium `full` prop)
- Preserve all GlobeView props: `showGfwEvents`, `showSarDetections`, `showInfrastructure`, `showGnssZones`, `showNetwork`
- Keep the same component children pattern — each overlay is a child component that accesses the map via `useMap()` hook from react-map-gl

---

### Story 2: Vessel Markers with Clustering

**As a** maritime analyst
**I want to** see vessel positions as colored, rotated markers on the 2D map
**So that** I can monitor vessel movements and identify high-risk vessels at a glance

**Acceptance Criteria:**

- GIVEN vessels are loaded WHEN the map renders THEN each vessel appears as a marker colored by risk tier (green=#22C55E, amber=#F59E0B, red=#EF4444, blacklisted=#9333EA)
- GIVEN a vessel has a COG value WHEN it renders THEN the marker is rotated to match the course over ground
- GIVEN green vessels are on the map WHEN rendered THEN they appear at reduced opacity (0.3) and smaller size
- GIVEN red-tier vessels are on the map WHEN rendered THEN they pulse (scale oscillation ~1.0-1.15x at ~1Hz)
- GIVEN a vessel is on the watchlist WHEN rendered THEN it has a semi-transparent white halo ring
- GIVEN a vessel has active spoofing anomalies WHEN rendered THEN it has a dashed circle indicator
- GIVEN the map is zoomed out WHEN vessels are close together THEN they cluster into a single circle showing count and highest-severity color
- GIVEN a vessel marker WHEN I click it THEN it becomes the selected vessel and the map flies to it at ~zoom 10
- GIVEN a cluster marker WHEN I click it THEN the map zooms in to expand the cluster

**Test Requirements:**

- [ ] Test: Vessel GeoJSON source contains all vessels from store with correct coordinates
- [ ] Test: Symbol layer uses `icon-rotate` property mapped to vessel COG
- [ ] Test: Green vessels have opacity 0.3 in the paint property
- [ ] Test: Clustering is enabled with clusterRadius 50 and clusterMaxZoom 14
- [ ] Test: Cluster circles use the highest risk tier color from clustered points
- [ ] Test: Click on vessel feature calls `setSelectedMmsi` and triggers `map.flyTo`
- [ ] Test: Watchlisted vessels have a halo layer rendered beneath the main marker
- [ ] Test: Spoofed vessels have a dashed circle layer

**Technical Notes:**

- Create `frontend/src/components/Map/VesselLayer.tsx` (replaces both `VesselMarkers.tsx` and `VesselCluster.tsx`)
- Use a single GeoJSON source with clustering enabled — MapLibre handles cluster/uncluster automatically
- Vessel icons: generate small canvas icons per risk tier (colored chevron/arrow) and add to map via `map.addImage()`
- For pulsing red vessels: use `setInterval` to toggle between two icon variants (normal + slightly larger), updating the icon-image property. Only run the interval when red vessels exist.
- COG rotation: `layout: { 'icon-rotate': ['get', 'cog'] }`
- Cluster paint: `'circle-color': ['step', ['get', 'maxRiskScore'], '#22C55E', 30, '#F59E0B', 100, '#EF4444']`
- Use `useVesselStore` data, convert to GeoJSON FeatureCollection, update source data when store changes
- Selection ring: separate symbol layer filtered to `['==', ['get', 'mmsi'], selectedMmsi]`

---

### Story 3: Track Trails

**As a** maritime analyst
**I want to** see vessel movement trails on the map
**So that** I can track vessel movements over time and identify suspicious patterns

**Acceptance Criteria:**

- GIVEN vessels have position history WHEN the map renders THEN each non-green vessel shows a 1-hour fading trail
- GIVEN the 1h trail renders WHEN I look at it THEN it fades from transparent (oldest) to full opacity (newest), colored by risk tier
- GIVEN a vessel is selected WHEN I view the map THEN a 24-hour track trail appears for that vessel
- GIVEN the 24h trail has AIS gaps >10 minutes WHEN rendered THEN those segments appear as dashed lines
- GIVEN the 24h trail renders WHEN I look at it THEN older segments are thinner (0.5px) and newer segments are thicker (2px)
- GIVEN no vessel is selected WHEN I view the map THEN no 24h trail is shown

**Test Requirements:**

- [ ] Test: TrackTrails component creates a GeoJSON source with polyline features from position history
- [ ] Test: Trail opacity gradient is applied via line-opacity with a data-driven property
- [ ] Test: Selected vessel track fetches 24h data from `/api/vessels/{mmsi}/track?hours=24`
- [ ] Test: AIS gaps >10min produce separate line features with `dasharray` pattern
- [ ] Test: Line width varies by segment recency (0.5-2px range)
- [ ] Test: No 24h trail source exists when `selectedMmsi` is null

**Technical Notes:**

- Create `frontend/src/components/Map/TrackTrails.tsx` (replaces `TrackTrails.tsx` — 1h trails)
- Create `frontend/src/components/Map/TrackTrail.tsx` (replaces `TrackTrail.tsx` — 24h selected)
- 1h trails: one GeoJSON source with MultiLineString features per vessel, `line-color` from risk tier property
- 24h trail: separate GeoJSON source, split into segments by AIS gap detection, solid vs `line-dasharray: [4, 4]`
- Width tiers via multiple line layers filtered by recency property, or a single layer with `line-width: ['interpolate', ...]`
- Use `useVesselStore.positionHistory` for 1h trails
- Use TanStack Query (existing pattern, 30s refetch) for 24h track

---

### Story 4: Geographic Overlays (STS Zones, Terminals, EEZ)

**As a** maritime analyst
**I want to** see STS zones, Russian terminals, and the Norwegian EEZ boundary on the map
**So that** I have geographic context for vessel behavior analysis

**Acceptance Criteria:**

- GIVEN STS zones toggle is on WHEN the map renders THEN 12 STS zones appear as semi-transparent amber polygons with labeled names
- GIVEN Russian terminals toggle is on WHEN the map renders THEN 7 terminal markers appear as cyan points with labels
- GIVEN the EEZ toggle is on WHEN the map renders THEN the Norwegian EEZ boundary appears as a blue dashed polyline
- GIVEN toggles are off WHEN viewing the map THEN the corresponding overlays are hidden

**Test Requirements:**

- [ ] Test: STS zone GeoJSON source contains all zones from `stsZones.json`
- [ ] Test: STS zone fill layer uses amber color at ~20% opacity with outline
- [ ] Test: Terminal circle layer uses cyan (#06B6D4) fill color
- [ ] Test: EEZ line layer uses blue with dasharray pattern
- [ ] Test: Layer visibility toggles with `layout: { visibility: 'visible' | 'none' }`

**Technical Notes:**

- Create `frontend/src/components/Map/StaticOverlays.tsx` (replaces `Overlays.tsx`)
- Three GeoJSON sources, each with fill/line/symbol layers as appropriate
- Reuse existing GeoJSON files (`stsZones.json`, `terminals.json`, `eezBoundaries.json`)
- Toggle visibility via `map.setLayoutProperty(layerId, 'visibility', 'visible' | 'none')`
- Labels: `symbol` layer with `text-field: ['get', 'name']`, small font, positioned above features

---

### Story 5: Infrastructure Overlay (Cables & Pipelines)

**As a** maritime analyst
**I want to** see subsea cables and pipelines on the map with alert highlighting
**So that** I can monitor vessel proximity to critical infrastructure

**Acceptance Criteria:**

- GIVEN infrastructure toggle is on WHEN routes are loaded THEN cables appear as thin blue lines, power cables as yellow, pipelines as orange
- GIVEN a route has active alerts WHEN rendered THEN it appears as a thick red line (3px, 80% opacity) instead of the default thin style
- GIVEN I hover over a route WHEN the tooltip appears THEN it shows the route name and type
- GIVEN the viewport changes WHEN I pan/zoom THEN only routes within the visible area are fetched (viewport-aware)
- GIVEN infrastructure toggle is off WHEN viewing the map THEN no infrastructure routes are visible

**Test Requirements:**

- [ ] Test: Infrastructure GeoJSON source is populated from `/api/infrastructure/routes` response
- [ ] Test: Line color is data-driven based on route type property (telecom=blue, power=yellow, pipeline=orange)
- [ ] Test: Flagged routes have line-width 3 and color red (#EF4444)
- [ ] Test: Hover on route feature shows popup with name and type
- [ ] Test: API call includes bbox parameter from current map bounds
- [ ] Test: Layer visibility toggles correctly

**Technical Notes:**

- Create `frontend/src/components/Map/InfrastructureLayer.tsx` (replaces `InfrastructureOverlay.tsx`)
- Single GeoJSON source from API, line layer with data-driven styling
- Color expression: `['match', ['get', 'type'], 'telecom', '#3B82F6', 'power', '#EAB308', 'pipeline', '#F97316', '#6B7280']`
- Alert highlighting: add a `flagged` property to features, use `['case', ['get', 'flagged'], '#EF4444', <default-color>]`
- Viewport-aware fetching: listen to `map.on('moveend')`, compute bounds via `map.getBounds()`, fetch with bbox
- Hover: `map.on('mousemove', layerId, ...)` + `map.on('mouseleave', layerId, ...)`

---

### Story 6: Event Markers (GFW + SAR)

**As a** maritime analyst
**I want to** see GFW fishing events and SAR dark ship detections on the map
**So that** I can investigate suspicious maritime activity

**Acceptance Criteria:**

- GIVEN GFW events toggle is on WHEN events are loaded THEN markers appear color-coded by type (encounter=orange, loitering=yellow, AIS-disabling=red, port visit=blue)
- GIVEN SAR detections toggle is on WHEN detections are loaded THEN dark ship markers appear with a pulsing animation
- GIVEN SAR "dark ships only" filter is on WHEN rendered THEN only unmatched (dark) detections are shown
- GIVEN I click a GFW event marker WHEN the popup appears THEN it shows event type, time, duration, vessel info, coordinates
- GIVEN I click a SAR detection marker WHEN the popup appears THEN it shows detection metadata (length, fishing score, matching score)

**Test Requirements:**

- [ ] Test: GFW source contains features from `/api/gfw/events` with correct type property
- [ ] Test: GFW symbol layer uses type-specific icon images
- [ ] Test: SAR source contains features from `/api/sar/detections`
- [ ] Test: Dark ship filter expression: `['==', ['get', 'is_dark'], true]` when darkShipsOnly is active
- [ ] Test: Click handler opens popup with correct event/detection data
- [ ] Test: Both layers respect their visibility toggles independently

**Technical Notes:**

- Create `frontend/src/components/Map/GfwEventLayer.tsx` (replaces `GfwEventMarkers.tsx`)
- Create `frontend/src/components/Map/SarDetectionLayer.tsx` (replaces `SarMarkers.tsx`)
- GFW: use `['match', ['get', 'type'], ...]` for icon-image selection
- SAR pulsing: same setInterval approach as red vessel pulsing — toggle between two icon sizes
- Popups: use react-map-gl `<Popup>` component, positioned at click coordinates
- Reuse existing TanStack Query hooks (5min refetch interval)

---

### Story 7: Spoofing & Network Overlays

**As a** maritime analyst
**I want to** see GNSS spoofing zones, duplicate MMSI lines, and network connections on the map
**So that** I can identify spoofing hotspots and vessel relationship networks

**Acceptance Criteria:**

- GIVEN GNSS zones toggle is on WHEN spoofing data is loaded THEN a heatmap overlay shows spoofing density (yellow→orange→red gradient)
- GIVEN duplicate MMSI anomalies exist WHEN the overlay is active THEN dashed red lines connect the two conflicting positions with a "Duplicate MMSI" label at the midpoint
- GIVEN network toggle is on and a vessel is selected WHEN network data loads THEN connection lines appear between related vessels, styled by edge type (encounter=solid white, proximity=dashed gray, port visit=solid cyan, ownership=dashed purple)
- GIVEN network connections render WHEN I see connected vessels THEN they have highlighted point markers

**Test Requirements:**

- [ ] Test: Heatmap layer source contains points from `/api/gnss-spoofing-events` with severity weight property
- [ ] Test: Heatmap color ramp goes from transparent → yellow → orange → red
- [ ] Test: Duplicate MMSI line source creates LineString features between conflicting positions
- [ ] Test: Line layer uses dasharray and red color for duplicate MMSI
- [ ] Test: Network edge line styling matches edge type (4 types with distinct colors/dash patterns)
- [ ] Test: Network node circles use risk-tier colors

**Technical Notes:**

- Create `frontend/src/components/Map/GnssHeatmap.tsx` (replaces `GnssZoneOverlay.tsx`)
  - MapLibre has a native `heatmap` layer type — no more canvas→DataURL→imagery hack
  - `heatmap-weight`: from severity property, `heatmap-color`: gradient expression
  - Much more performant than the current canvas-based approach
- Create `frontend/src/components/Map/DuplicateMmsiLayer.tsx` (replaces `DuplicateMmsiLines.tsx`)
- Create `frontend/src/components/Map/NetworkLayer.tsx` (replaces `NetworkOverlay.tsx`)
  - Edge styling via `['match', ['get', 'edgeType'], ...]` expressions
- Spoofing time controls (`SpoofingTimeControls.tsx`) remain unchanged — they're pure UI

---

### Story 8: Interactions (Hover Tooltip + Camera)

**As a** maritime analyst
**I want to** see vessel information on hover and navigate the map by clicking
**So that** I can quickly identify vessels and navigate to areas of interest

**Acceptance Criteria:**

- GIVEN I hover over a vessel marker WHEN the tooltip appears THEN it shows vessel name, MMSI, flag, type, SOG, COG
- GIVEN I hover over an infrastructure route WHEN the tooltip appears THEN it shows route type and name
- GIVEN I hover over empty map space WHEN no feature is under cursor THEN no tooltip is shown
- GIVEN I click a vessel WHEN the click fires THEN the vessel is selected and the map smoothly flies to zoom ~10 centered on it
- GIVEN I click a GFW event or SAR detection WHEN the click fires THEN a popup opens and the map flies to zoom ~10
- GIVEN the cursor is over a clickable feature WHEN hovering THEN the cursor changes to pointer

**Test Requirements:**

- [ ] Test: Mouse move over vessel layer triggers tooltip display with correct data fields
- [ ] Test: Mouse leave from vessel layer hides tooltip
- [ ] Test: Click on vessel feature calls `flyTo` with correct coordinates and zoom
- [ ] Test: Cursor style changes to 'pointer' on interactive layers
- [ ] Test: Tooltip positioning doesn't overflow viewport edges

**Technical Notes:**

- Create `frontend/src/components/Map/HoverTooltip.tsx` (replaces `HoverDatablock.tsx`)
- Use `map.on('mousemove', layerId, ...)` for each interactive layer
- Use `map.on('click', layerId, ...)` for click handlers
- Set `map.getCanvas().style.cursor` on enter/leave
- `map.flyTo({ center: [lon, lat], zoom: 10, duration: 1500 })` replaces `viewer.camera.flyTo`
- Tooltip: absolute-positioned div, same styling as current HoverDatablock

---

### Story 9: Lookback Mode

**As a** maritime analyst
**I want to** replay historical vessel movements on the 2D map
**So that** I can investigate past behavior patterns

**Acceptance Criteria:**

- GIVEN lookback mode is active WHEN the timeline plays THEN vessel markers move along their historical tracks with interpolated positions
- GIVEN lookback is active WHEN real-time markers exist THEN they are hidden (only lookback vessels visible)
- GIVEN lookback is playing WHEN the scrubber moves THEN trails progressively draw behind each vessel up to the current time
- GIVEN network vessels are included in lookback WHEN rendered THEN they appear dimmed (25% opacity, 1px trails)
- GIVEN the area lookback tool is active WHEN I click on the map THEN vertices are placed to draw a polygon
- GIVEN a polygon is closed WHEN I complete the drawing THEN the area lookback panel shows vessels that transited the area
- GIVEN lookback controls render WHEN I see them THEN play/pause, speed (1x/5x/30x/100x), and scrubber work correctly

**Test Requirements:**

- [ ] Test: Lookback overlay creates a separate GeoJSON source for historical vessel positions
- [ ] Test: Position interpolation between track points uses binary search and linear interpolation
- [ ] Test: Real-time vessel layer visibility is set to 'none' when lookback is active
- [ ] Test: Network vessels have opacity 0.25 and line-width 1
- [ ] Test: Area drawing tool adds vertices on click and closes polygon on double-click
- [ ] Test: Timeline scrubber updates current time in lookback store
- [ ] Test: Speed multiplier affects animation step size correctly

**Technical Notes:**

- Create `frontend/src/components/Map/LookbackLayer.tsx` (replaces `LookbackOverlay.tsx`)
- Create `frontend/src/components/Map/AreaDrawingTool.tsx` (replaces `AreaLookbackTool.tsx`)
- Lookback animation: `requestAnimationFrame` loop that updates GeoJSON source data each frame (same as current approach, but updating a MapLibre source instead of Cesium CallbackProperty)
- Area drawing: use `map.on('click')` to place vertices, `map.on('dblclick')` to close. Render preview with a line + fill layer.
- `TimelineBar.tsx` and `AreaLookbackPanel.tsx` are pure UI — keep as-is, they read from `useLookbackStore`
- Binary search interpolation logic from current `LookbackOverlay.tsx` is reusable — extract to a utility

---

### Story 10: Minimap Replacement

**As a** maritime analyst
**I want to** see a minimap showing my current viewport on a world overview
**So that** I can orient myself and quickly navigate to different regions

**Acceptance Criteria:**

- GIVEN the map loads WHEN the minimap renders THEN it shows a small MapLibre map instance with world overview
- GIVEN the main map viewport changes WHEN I pan or zoom THEN the minimap shows a rectangle indicating the current view extent
- GIVEN I click on the minimap WHEN the click registers THEN the main map flies to that location
- GIVEN non-green vessels exist WHEN the minimap renders THEN they appear as colored dots by risk tier
- GIVEN the main map is idle WHEN the minimap is idle THEN neither triggers unnecessary re-renders

**Test Requirements:**

- [ ] Test: Minimap component renders a MapLibre map with world bounds
- [ ] Test: Viewport rectangle source updates on main map `moveend` event
- [ ] Test: Click on minimap calls main map `flyTo` with correct coordinates
- [ ] Test: Vessel dots source contains non-green vessels with risk tier colors
- [ ] Test: Minimap only re-renders on main map move events, not continuously

**Technical Notes:**

- Create `frontend/src/components/Map/Minimap.tsx` (replaces `Minimap.tsx`)
- Second `<Map>` instance from react-map-gl with `interactive={false}` (no pan/zoom on minimap itself)
- Same custom style but simplified (no labels, no landuse detail)
- Viewport rectangle: GeoJSON Polygon source, updated on main map `moveend` event — NOT a continuous RAF loop
- Vessel dots: GeoJSON Point source from `useVesselStore`, updated when vessels change
- Click handler: convert pixel to lngLat via `minimap.unproject()`, call `mainMap.flyTo()`
- Size: 200x150px, same positioning as current minimap

---

### Story 11: Cesium Removal & Cleanup

**As a** developer
**I want to** remove all CesiumJS/Resium dependencies and files
**So that** the bundle is smaller and there's no dead code

**Acceptance Criteria:**

- GIVEN the migration is complete WHEN I check package.json THEN `cesium`, `resium`, and `vite-plugin-cesium` are not listed
- GIVEN the migration is complete WHEN I search the codebase THEN no imports from 'cesium' or 'resium' exist
- GIVEN the old Globe directory exists WHEN cleanup runs THEN `frontend/src/components/Globe/` is deleted
- GIVEN the old Minimap.tsx exists WHEN cleanup runs THEN it is deleted
- GIVEN the build runs WHEN I check output THEN bundle size is significantly smaller (no 4MB cesium chunk)
- GIVEN the `.env.example` exists WHEN I check it THEN `VITE_CESIUM_ION_TOKEN` is removed and `VITE_MAPTILER_KEY` is added
- GIVEN vite.config.ts exists WHEN I check it THEN cesium-specific manual chunks are removed

**Test Requirements:**

- [ ] Test: `npm ls cesium` returns empty (not installed)
- [ ] Test: `grep -r "from 'cesium'" frontend/src/` returns no results
- [ ] Test: `grep -r "from 'resium'" frontend/src/` returns no results
- [ ] Test: `frontend/src/components/Globe/` directory does not exist
- [ ] Test: Build completes without errors
- [ ] Test: No references to `VITE_CESIUM_ION_TOKEN` in source code

**Technical Notes:**

- `npm uninstall cesium resium vite-plugin-cesium`
- Delete `frontend/src/components/Globe/` directory entirely
- Delete old `frontend/src/components/Minimap.tsx`
- Update `frontend/src/App.tsx` to import from `Map/MapView` instead of `Globe/GlobeView`
- Update `vite.config.ts` to remove cesium manual chunk config
- Update `.env.example` and any docker-compose env references
- Update any remaining imports (SearchBar, useOverlays, etc.) that reference `Globe/cesiumViewer`

---

## Technical Design

### Data Model Changes

None. This is a frontend-only migration.

### API Changes

None. All existing API endpoints are consumed identically.

### Dependencies

**Add:**
- `maplibre-gl` (~800 KB) — WebGL map renderer
- `react-map-gl` (maplibre-compatible) — React wrapper
- `@maplibre/maplibre-gl-geocoder` (optional, if search-to-location is desired later)

**Remove:**
- `cesium` (~4 MB)
- `resium`
- `vite-plugin-cesium` (if present)

**External:**
- MapTiler account (free tier) for vector tile hosting
- `VITE_MAPTILER_KEY` environment variable

### Security Considerations

- MapTiler API key is a public key (used in browser) — this is by design, restricted by HTTP referrer in MapTiler dashboard
- No sensitive data exposure changes — same data flows as before

---

## Implementation Order

### Group 1 (sequential — foundation)
- Story 1 — MapLibre core setup + style → `Map/MapView.tsx`, `Map/mapInstance.ts`, `Map/style.ts`

### Group 2 (parallel — independent layers, after Group 1)
- Story 2 — Vessel markers + clustering → `Map/VesselLayer.tsx`
- Story 4 — Geographic overlays → `Map/StaticOverlays.tsx`
- Story 5 — Infrastructure overlay → `Map/InfrastructureLayer.tsx`
- Story 7 — Spoofing & network overlays → `Map/GnssHeatmap.tsx`, `Map/DuplicateMmsiLayer.tsx`, `Map/NetworkLayer.tsx`
- Story 10 — Minimap → `Map/Minimap.tsx`

### Group 3 (parallel — depends on vessel layer from Group 2)
- Story 3 — Track trails → `Map/TrackTrails.tsx`, `Map/TrackTrail.tsx`
- Story 6 — Event markers → `Map/GfwEventLayer.tsx`, `Map/SarDetectionLayer.tsx`
- Story 8 — Interactions → `Map/HoverTooltip.tsx`

### Group 4 (sequential — depends on all layers)
- Story 9 — Lookback mode → `Map/LookbackLayer.tsx`, `Map/AreaDrawingTool.tsx`

### Group 5 (sequential — final cleanup after everything works)
- Story 11 — Cesium removal & cleanup

**Parallel safety rules:**
- Stories in the same group touch DIFFERENT files
- Story 1 creates the shared Map component that all others depend on
- Story 11 must be last — it deletes the old code that serves as reference during migration
- No database migrations in this spec

---

## Development Approach

### Simplifications (what starts simple)

- Map style starts as a programmatic style object in code; can move to a hosted style URL later
- Pulsing animations use setInterval icon swapping (simple); can upgrade to `addImage` with AnimationFrame later if needed
- Minimap uses same tile source as main map; could use a simpler/lighter tile source later

### Upgrade Path (what changes for production)

- "Host custom map style on MapTiler" — upload a custom style for easier iteration
- "Add satellite imagery toggle" — add a layer switcher for satellite view when needed
- "Add 3D terrain for specific views" — MapLibre supports terrain if ever needed for a specific feature
- "Add aircraft altitude color coding" — future story, altitude mapped to marker/trail color gradient

### Architecture Decisions

- **react-map-gl over raw MapLibre:** Provides React component model matching the existing Resium pattern. Each overlay is a child component, same as current architecture.
- **Single GeoJSON source with clustering for vessels:** MapLibre's built-in clustering is more performant than Cesium's EntityCluster. One source handles both individual markers and clusters automatically.
- **Data-driven styling over per-entity configuration:** MapLibre's expression system (`['match', ...]`, `['interpolate', ...]`) handles all the per-vessel color/size/rotation logic in the GPU, not in JavaScript. This is the biggest performance win.
- **Event-driven re-render over continuous loop:** MapLibre only renders on map state changes. The minimap updates on `moveend`, not 60fps RAF. Vessel source updates on store change, not every frame.
- **MapTiler over OpenFreeMap:** Better tile quality, port/industrial landuse detail, free tier sufficient for this use case. API key restricted by referrer.
- **Keep overlay components as separate files:** Matches existing architecture, allows parallel implementation, keeps each layer's logic isolated.

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled
- [ ] No regressions in existing tests
- [ ] Code committed with proper messages
- [ ] Idle CPU usage near zero (no continuous rendering)
- [ ] Bundle size reduced (no cesium chunk)
- [ ] All existing map features work identically to before
- [ ] Infrastructure cables/pipelines render correctly
- [ ] Port areas distinguishable on the map
- [ ] Lookback mode fully functional
- [ ] Ready for human review
