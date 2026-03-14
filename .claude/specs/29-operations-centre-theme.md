# Feature Spec: Maritime Operations Centre Visual Theme

**Slug:** `operations-centre-theme`
**Created:** 2026-03-14
**Status:** approved
**Priority:** high

---

## Overview

Transform Heimdal's frontend from "functional dark web app" into "maritime operations centre display" — the visual credibility that determines whether government analysts take a screenshot to their supervisor and whether journalists cite the tool. This is a full restyling of every visual surface: globe, markers, panels, HUD, controls, typography, and color palette.

## Problem Statement

Heimdal has better data and sharper analytical purpose than tools like WorldView, but the current frontend looks like a standard dark-mode React app. The target aesthetic is a naval vessel traffic service (VTS) display — dark-adapted, information-dense, operationally serious. The first screenshot anyone sees should look like it belongs in an operations centre, not like a prototype.

## Out of Scope

- NOT: New features or functionality — this is purely visual
- NOT: A design system or component library — specific values for one tool
- NOT: A light mode or dark mode toggle — Heimdal is always dark
- NOT: Satellite pass indicator in HUD (future feature)
- NOT: Mobile-first redesign — desktop is the primary platform
- NOT: Branding, logo, marketing pages, or an "about" screen

---

## User Stories

### Story 1: Theme Foundation — Tailwind Config, Fonts, CSS Variables

**As a** developer
**I want to** establish the colour palette, typography, and CSS foundation
**So that** all subsequent stories build on a consistent visual system

**Acceptance Criteria:**

- GIVEN the frontend loads WHEN checking fonts THEN Inter (proportional) and JetBrains Mono (monospace) are loaded via Google Fonts or self-hosted
- GIVEN the Tailwind config WHEN checking custom colors THEN the following are defined: `heimdal-bg` (#0A0E17), `heimdal-panel` (#111827), `heimdal-border` (#1F2937), `heimdal-accent` (#3B82F6), `heimdal-infra` (#06B6D4), `heimdal-sar` (#A78BFA)
- GIVEN the risk color constants WHEN checked THEN green=#22C55E, amber=#F59E0B, red=#EF4444
- GIVEN the CSS variables WHEN the app loads THEN font sizes are set: xs=0.7rem, sm=0.8rem, base=0.875rem, lg=1rem, xl=1.25rem
- GIVEN the root element WHEN inspected THEN background is #0A0E17, font-family is Inter/system-ui, color is #E5E7EB

**Test Requirements:**

- [ ] Test: riskColors.ts exports updated hex values (green=#22C55E, yellow=#F59E0B, red=#EF4444)
- [ ] Test: Font families include 'Inter' and 'JetBrains Mono'
- [ ] Test: Custom Tailwind colors are accessible (bg-heimdal-bg, bg-heimdal-panel, etc.)
- [ ] Test: Body background is #0A0E17

**Technical Notes:**

- Files: `frontend/index.html` (font links), `frontend/src/index.css` (CSS variables, Tailwind theme), `frontend/src/utils/riskColors.ts`
- Tailwind v4 uses CSS-based config — extend in `index.css` with `@theme` block
- Load fonts via `<link>` in index.html to avoid FOUT (Inter 400/500/600, JetBrains Mono 400/500)
- Update severityColors.ts to match new palette

---

### Story 2: Globe Styling — Dark Ocean, Atmosphere, Fog

**As an** operator
**I want to** see a dark, atmospheric globe with deep navy ocean
**So that** the workspace feels like a maritime operations display, not a consumer map

**Acceptance Criteria:**

- GIVEN the globe loads WHEN checking the base color THEN ocean is deep navy (#0A1628), not bright blue
- GIVEN the scene WHEN inspected THEN fog is enabled (density 0.0003), atmosphere brightness is reduced (-0.4 shift), scene background matches app background (#0A0E17)
- GIVEN a Cesium Ion account with Earth at Night asset WHEN the globe loads THEN night lights imagery is used as base layer
- GIVEN a free Cesium Ion account without Earth at Night WHEN the globe loads THEN it falls back to the dark globe base color (#0A1628) with no visible artifact
- GIVEN the globe WHEN zoomed out THEN ground atmosphere effect is visible

**Test Requirements:**

- [ ] Test: GlobeView configures globe.baseColor to #0A1628
- [ ] Test: Scene fog enabled with density 0.0003
- [ ] Test: Sky atmosphere brightness shift is -0.4
- [ ] Test: Scene backgroundColor is #0A0E17
- [ ] Test: Earth at Night imagery is attempted; fallback to base color on failure

**Technical Notes:**

- File: `frontend/src/components/Globe/GlobeView.tsx`
- Configure in useEffect after viewer is ready:
  ```js
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0A1628');
  viewer.scene.globe.showGroundAtmosphere = true;
  viewer.scene.fog.enabled = true;
  viewer.scene.fog.density = 0.0003;
  viewer.scene.skyAtmosphere.brightnessShift = -0.4;
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0A0E17');
  ```
- Earth at Night: attempt `Cesium.IonImageryProvider.fromAssetId(3812)`, catch and fall back
- Remove or override the default Bing Maps imagery if no Ion asset available

---

### Story 3: Vessel Markers — Chevron Arrows with Tier-Differentiated Rendering

**As an** operator
**I want to** see directional chevron markers with risk tiers visually separated by salience
**So that** red vessels are impossible to miss, green vessels fade into background noise, and I can read direction at a glance

**Acceptance Criteria:**

- GIVEN a vessel marker WHEN rendered THEN it is a chevron/arrow shape oriented to COG, not a circle or basic triangle
- GIVEN a green vessel WHEN rendered THEN fill opacity is 0.3, no glow — barely visible background noise
- GIVEN a yellow vessel WHEN rendered THEN fill opacity is 0.8 with subtle amber glow (second slightly larger, blurred billboard behind the main one)
- GIVEN a red vessel WHEN rendered THEN fill opacity is 1.0 with pulsing red glow at 1Hz, scale oscillating between 1.0x and 1.15x
- GIVEN a selected vessel WHEN rendered THEN it has a bright white ring around the marker
- GIVEN a watchlisted vessel WHEN rendered THEN it has a small star/dot indicator persistent regardless of tier

**Test Requirements:**

- [ ] Test: Chevron icon generator creates valid data URL with arrow shape
- [ ] Test: Green marker style has opacity 0.3, scale 0.5
- [ ] Test: Yellow marker style has opacity 0.8, scale 1.0
- [ ] Test: Red marker style has opacity 1.0, scale 1.2
- [ ] Test: Red pulse oscillates between 1.0 and 1.15 scale factor
- [ ] Test: Selected vessel gets white ring billboard
- [ ] Test: Watchlist halo is still rendered for watched vessels
- [ ] Test: cogToRotation converts COG degrees to radians correctly

**Technical Notes:**

- Files: `frontend/src/utils/vesselIcons.ts`, `frontend/src/components/Globe/VesselMarkers.tsx`
- Redraw the canvas icon: sharper chevron shape with better bow point and stern notch
- Yellow glow: render a second Entity with a larger, semi-transparent billboard behind the main marker
- Red pulse: current implementation uses 0.8-1.2 range, narrow to 1.0-1.15 and set frequency to ~1Hz (adjust step per frame)
- Selected vessel ring: add a white circle billboard for the selectedMmsi vessel

---

### Story 4: Track Trails — Tapering Width and AIS Gap Dashes

**As an** operator
**I want to** see vessel track trails that taper from recent to old and show dashed segments for AIS gaps
**So that** I can visually read the track age and identify where the vessel went dark

**Acceptance Criteria:**

- GIVEN a selected vessel track WHEN rendered THEN the polyline color matches the vessel's risk tier at reduced opacity
- GIVEN a track trail WHEN rendered THEN line width tapers from 2px (most recent) to 0.5px (oldest)
- GIVEN positions with a gap > 10 minutes between consecutive points WHEN rendered THEN that segment is dashed (communicating "unknown position")
- GIVEN no AIS gaps WHEN rendered THEN the trail is a solid polyline

**Test Requirements:**

- [ ] Test: Track polyline uses risk tier color (not hardcoded blue)
- [ ] Test: Track segments are rendered with decreasing width
- [ ] Test: AIS gap detection identifies gaps > 10 minutes between consecutive positions
- [ ] Test: Gap segments render as dashed lines (separate Entity with dash pattern)

**Technical Notes:**

- File: `frontend/src/components/Globe/TrackTrail.tsx`
- Currently uses a single solid polyline in hardcoded blue (#38bdf8)
- Split into multiple segments: solid segments for continuous positions, dashed segments for gaps
- Use Cesium PolylineDashMaterialProperty for gap segments
- Tapering: Cesium polyline width is uniform per entity; split into 3-5 segment groups with decreasing width (2px, 1.5px, 1px, 0.5px based on position age)
- Color: look up selected vessel's risk tier from store, use tier color with 0.6 alpha

---

### Story 5: HUD Top Bar — Operations Centre Status Display

**As an** operator
**I want to** see a thin heads-up display showing real-time vessel counts, risk distribution, ingestion rate, and active alerts
**So that** I have situational awareness without opening any panels

**Acceptance Criteria:**

- GIVEN the app loads WHEN the HUD is visible THEN it is a 40px bar at the top with semi-transparent background (#0A0E17 at 90% opacity)
- GIVEN the HUD WHEN reading left to right THEN it shows: HEIMDAL label | vessel count | risk tier counts (green/yellow/red with colored dots) | ingestion rate | active alerts count
- GIVEN the HEIMDAL label WHEN styled THEN it uses small-caps, letter-spacing 0.05em, text-gray-400
- GIVEN the risk tier counts WHEN clicked THEN the globe filters to show only that tier
- GIVEN WebSocket data WHEN stats update THEN numbers update in real-time (no animation, just replace)
- GIVEN the HUD WHEN on mobile (<768px) THEN only risk counts are shown (simplified)

**Test Requirements:**

- [ ] Test: HUD renders vessel count, risk tier counts, ingestion rate, alerts count
- [ ] Test: HUD height is 40px (h-10)
- [ ] Test: HEIMDAL label has tracking-wide/small-caps styling
- [ ] Test: Clicking a risk count applies the risk tier filter to the store
- [ ] Test: Stats data is fetched and displayed from /api/stats
- [ ] Test: HUD background is semi-transparent

**Technical Notes:**

- Files: `frontend/src/App.tsx` (header section), `frontend/src/components/Controls/StatsBar.tsx` (merge into HUD)
- Replace current header (h-12, bg-gray-900) with new HUD (h-10, bg-heimdal-bg/90, backdrop-blur)
- Merge StatsBar metrics into the HUD bar directly (remove the expandable dropdown — put expanded stats in a separate view or keep as click-expand)
- Move WatchlistPanel and EquasisImport into the vessel panel or a separate toolbar
- HUD items separated by thin vertical dividers (border-l border-gray-700/50)
- Use monospace font for numbers (JetBrains Mono)
- HealthIndicator dot integrates into the right side of the HUD

---

### Story 6: Side Panel Restyle — Dense, Sharp, Monospace Data

**As an** operator
**I want to** see vessel detail in a dense, sharp-cornered panel with monospace data fields
**So that** information density is maximised and the panel feels like an operational instrument

**Acceptance Criteria:**

- GIVEN the vessel panel WHEN styled THEN background is #111827, left border is #1F2937, no rounded corners on the panel itself
- GIVEN content cards within the panel WHEN styled THEN they have 4px rounded corners and #1F2937 border
- GIVEN MMSI, IMO, coordinates, timestamps WHEN rendered THEN they use JetBrains Mono (monospace) font
- GIVEN vessel name WHEN rendered THEN it uses Inter font at 1.25rem (--font-size-xl)
- GIVEN the risk tier badge WHEN rendered THEN it is pill-shaped, filled with tier color, white text, format: "● RED — 140pts"
- GIVEN anomaly event cards WHEN rendered THEN they have a 4px left border colored by severity (red=critical, amber=high, etc.)
- GIVEN Ownership, Sanctions, Enrichment Form sections WHEN panel opens THEN they are collapsed by default, expandable on click
- GIVEN labels and values WHEN rendered THEN they are on the same line where possible: "Flag: Panama (PAN) | Type: Crude Oil Tanker | Built: 2001"
- GIVEN the loading state WHEN panel is loading THEN it shows "Loading vessel..." in muted grey text, not skeleton screens or pulse animations

**Test Requirements:**

- [ ] Test: Panel container has no rounded corners (rounded-none)
- [ ] Test: Panel background is heimdal-panel (#111827)
- [ ] Test: MMSI/IMO fields use font-mono class
- [ ] Test: Risk badge displays tier color, label, and score
- [ ] Test: Anomaly cards have severity-colored left border
- [ ] Test: Collapsible sections default to collapsed
- [ ] Test: Loading state shows text, not skeleton animation
- [ ] Test: Dense layout — labels and values on same line

**Technical Notes:**

- Files: `frontend/src/components/VesselPanel/VesselPanel.tsx` and ALL subsection components (IdentitySection, StatusSection, RiskSection, VoyageTimeline, SanctionsSection, OwnershipSection, EnrichmentForm, EquasisSection, EnrichmentHistory, etc.)
- This is the most file-touch-heavy story — every panel component needs restyling
- Remove animate-pulse skeleton and replace with text "Loading vessel..."
- Add collapsible wrapper component: header + chevron indicator + collapsed/expanded content
- Dense field layout: use flex with items-center and gap-x-3 for inline label-value pairs
- Scoring breakdown: compact table (grid-cols), not cards
- Reduce padding throughout: px-3 py-2 instead of px-4 py-3

---

### Story 7: Controls Restyle — Filters, Search, Overlay Toggles

**As an** operator
**I want to** see map controls styled consistently with the operations centre theme
**So that** every UI surface feels like part of the same operational tool

**Acceptance Criteria:**

- GIVEN the search bar WHEN styled THEN it has backdrop-blur, heimdal-panel background, heimdal-border border, Inter font
- GIVEN risk filter toggles WHEN styled THEN they use the new risk colors (green=#22C55E, amber=#F59E0B, red=#EF4444) and match the HUD count style
- GIVEN overlay toggles WHEN styled THEN they have sharp corners, thin borders, consistent with panel cards
- GIVEN filter controls WHEN arranged THEN they are positioned top-left on the globe with minimal visual weight
- GIVEN all controls WHEN rendered THEN font sizes match the typography scale (0.7-0.875rem)

**Test Requirements:**

- [ ] Test: SearchBar uses updated background and border colors
- [ ] Test: RiskFilter buttons use new risk tier colors
- [ ] Test: TypeFilter dropdown matches theme
- [ ] Test: TimeRangeFilter active state uses accent blue (#3B82F6)
- [ ] Test: OverlayToggles match card styling (4px border-radius, heimdal-border)
- [ ] Test: All control text uses the correct font size scale

**Technical Notes:**

- Files: ALL components in `frontend/src/components/Controls/` (SearchBar, RiskFilter, TypeFilter, TimeRangeFilter, OverlayToggles)
- Update Tailwind classes from gray-900/800/700 to heimdal-bg/panel/border where appropriate
- Risk filter colors: update from current hardcoded hex to new palette
- Ensure backdrop-blur-sm on overlay controls for glass effect over the globe
- Use `text-[0.8rem]` or the CSS variable for consistent small text

---

## Technical Design

### Colour Palette Change Summary

| Element | Old | New |
|---------|-----|-----|
| App background | bg-gray-900 | #0A0E17 (heimdal-bg) |
| Panel background | bg-gray-900 | #111827 (heimdal-panel) |
| Borders | border-gray-800 | #1F2937 (heimdal-border) |
| Risk green | #27AE60 | #22C55E |
| Risk yellow | #D4820C | #F59E0B |
| Risk red | #C0392B | #EF4444 |
| Accent | gray-600 focus | #3B82F6 (heimdal-accent) |

### Font Stack

- Proportional: Inter, system-ui, sans-serif
- Monospace: JetBrains Mono, Fira Code, monospace
- Base size: 0.875rem (14px) — deliberately smaller than typical web

### Dependencies

- Google Fonts: Inter (400, 500, 600), JetBrains Mono (400, 500)
- No new npm packages required
- CesiumJS Earth at Night asset (optional, graceful fallback)

### Files Changed

Every frontend visual component is touched. Major changes:
- `index.html` — font links
- `index.css` — CSS variables, Tailwind theme extension
- `App.tsx` — header/HUD restructure
- `GlobeView.tsx` — Cesium scene configuration
- `VesselMarkers.tsx` — selected vessel ring, glow billboards
- `vesselIcons.ts` — chevron redraw, updated marker styles
- `riskColors.ts` — new hex values
- `severityColors.ts` — updated severity palette
- `TrackTrail.tsx` — risk-colored, tapering, dashed gaps
- `StatsBar.tsx` — merge into HUD
- `VesselPanel.tsx` + all subsections — dense restyle
- All Controls components — theme alignment

### Security Considerations

- No security changes — purely visual
- Google Fonts loaded via standard `<link>` tags

---

## Implementation Order

### Group 1 (sequential — foundation first)
- Story 1 — Theme Foundation: CSS variables, fonts, Tailwind config, risk colors

### Group 2 (parallel — independent visual changes, after Group 1)
- Story 2 — Globe Styling: CesiumJS configuration
- Story 3 — Vessel Markers: chevron icons, glow, pulse, selection ring
- Story 4 — Track Trails: tapering, risk color, AIS gap dashes

### Group 3 (parallel — UI component restyling, after Group 1)
- Story 5 — HUD Top Bar: operations centre status display
- Story 6 — Side Panel Restyle: dense, sharp, monospace data
- Story 7 — Controls Restyle: filters, search, overlay toggles

**Parallel safety rules:**
- Group 2 stories touch different files (GlobeView vs VesselMarkers/vesselIcons vs TrackTrail)
- Group 3 stories touch different component directories (App+StatsBar vs VesselPanel/* vs Controls/*)
- Story 1 MUST complete first — it defines the colors/fonts everything else references
- Stories 5 and 6 both touch App.tsx layout — Story 5 handles the header, Story 6 handles the panel. If both need App.tsx, coordinate via the header section being Story 5's domain.

---

## Development Approach

### Simplifications (what starts simple)

- Earth at Night imagery: attempt once, fall back to dark base color — no retry logic
- Track trail tapering: 3-4 discrete width steps rather than continuous taper
- Mobile responsive: basic functional layout, not a polished mobile experience
- No new animation library — use CSS transitions and Cesium's built-in CallbackProperty

### Upgrade Path (what changes for production)

- "Add Mapbox Dark style as 2D map alternative" for lower-bandwidth environments
- "Responsive bottom sheet" for proper mobile vessel detail experience
- "Keyboard shortcuts overlay" styled as an ops-centre quick reference

### Architecture Decisions

- CSS variables over Tailwind theme extension for dynamic values (font sizes) — Tailwind v4 CSS-native config makes this natural
- Google Fonts over self-hosted — simpler, CDN-cached, no build impact
- Single pass restyle rather than incremental — every story produces a visually coherent result within its scope

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] No regressions in existing frontend tests
- [ ] Globe renders with dark ocean and atmosphere
- [ ] Vessel markers are chevrons with correct tier differentiation
- [ ] Red vessels pulse at ~1Hz
- [ ] HUD displays real-time stats with monospace numbers
- [ ] Vessel panel is dense, sharp-cornered, with monospace data fields
- [ ] Inter and JetBrains Mono fonts load correctly
- [ ] Risk colors updated across all components
- [ ] Track trails show risk-tier colors and dashed AIS gaps
- [ ] Screenshot looks like it belongs in an operations centre
- [ ] Ready for human review
