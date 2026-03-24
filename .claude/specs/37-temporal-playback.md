# Feature Spec: Temporal Playback with GNSS Overlay

**Slug:** `temporal-playback`
**Created:** 2026-03-24
**Status:** completed
**Priority:** high

---

## Overview

Add a unified playback speed slider and optional GNSS spoofing/jamming overlay to the existing vessel lookback and area lookback playback modes. Also make the standalone GNSS time bar playable. The same speed slider component is used in all three contexts so the user has one consistent control.

## Problem Statement

Analysts need to correlate vessel movements with GNSS interference timing. Currently, vessel tracks and GNSS zones are viewed separately — the track as an animated replay, the zones as a static time-window overlay. There's no way to see "was the spoofing zone already active when this vessel arrived, or did it appear because of her?" The existing speed buttons (1x, 10x, 100x, 500x) are too coarse for intelligence work.

## Out of Scope

- NOT: New playback entry points. Vessel lookback and area lookback are triggered exactly as they are today.
- NOT: Drawing tools or area selection changes.
- NOT: Changes to how tracks are fetched, stored, or rendered (the trail-behind-marker behavior stays).
- NOT: GNSS zone detection algorithm changes.
- NOT: Changes to the GNSS zones API response format.
- NOT: Recording or exporting playback as video.

---

## User Stories

### Story 1: Unified Speed Slider

**As an** analyst
**I want to** control playback speed with a continuous slider
**So that** I can smoothly adjust between slow and fast replay without fixed presets

**Acceptance Criteria:**

- GIVEN playback is active (vessel lookback, area lookback, or standalone GNSS) WHEN I drag the speed slider THEN playback speed changes smoothly between 1 min/sec and 5 hr/sec
- GIVEN the speed slider is visible WHEN I look at it THEN I see the current speed labeled in human-readable format (e.g. "10 min/sec", "1 hr/sec", "3 hr/sec")
- GIVEN playback is active WHEN I change speed mid-playback THEN the speed change takes effect immediately without resetting the playhead position

**Test Requirements:**

- [ ] Test: Speed slider renders with correct min/max bounds
- [ ] Test: Moving slider updates `playbackSpeed` in the lookback store
- [ ] Test: Speed label formats correctly at key values (1 min, 30 min, 1 hr, 5 hr)
- [ ] Test: Changing speed during playback does not reset currentTime

**Technical Notes:**

Replace the discrete speed buttons `[1, 10, 100, 500]` in `TimelineBar.tsx` with a continuous range input. The slider value maps to simulation-minutes-per-real-second on a logarithmic scale:
- Min: 1 min/sec (= 60x real-time)
- Mid: ~30 min/sec (= 1800x)
- Max: 5 hr/sec (= 18000x)

The `playbackSpeed` in `useLookbackStore` currently represents a real-time multiplier. The animation loop in `TimelineBar` uses `deltaMs * speed` — this stays the same, just the speed values change.

The same `SpeedSlider` component is also used in the standalone GNSS time bar (Story 3).

---

### Story 2: GNSS Overlay in Lookback Playback

**As an** analyst
**I want to** optionally see GNSS spoofing/jamming zones during vessel or area playback
**So that** I can see whether interference was active before, during, or after a vessel transited an area

**Acceptance Criteria:**

- GIVEN lookback playback is active WHEN I check "Show GNSS zones" THEN GNSS interference zones appear on the map, filtered to the current playhead time
- GIVEN GNSS overlay is enabled WHEN the playhead advances THEN zones appear and disappear at their correct `detected_at`/`expires_at` timestamps
- GIVEN GNSS overlay checkbox is checked WHEN I select a time window (1h, 3h, or 6h) THEN zones within that window around the playhead are shown
- GIVEN lookback playback starts WHEN GNSS overlay is enabled THEN all GNSS zones for the full playback date range are pre-fetched in one API call
- GIVEN the GNSS zones have been pre-fetched WHEN playback advances THEN zone filtering happens client-side with no additional API calls

**Test Requirements:**

- [ ] Test: Checkbox toggles GNSS overlay visibility during lookback
- [ ] Test: Pre-fetch queries the full date range (dateRange.start to dateRange.end) from `/api/gnss-zones`
- [ ] Test: Client-side filtering correctly shows only zones where `detected_at <= playhead + window/2` AND `expires_at >= playhead - window/2`
- [ ] Test: Zone appears exactly when playhead reaches `detected_at - window/2` and disappears when playhead passes `expires_at + window/2`
- [ ] Test: Window size selector (1h, 3h, 6h) changes the visible range around the playhead

**Technical Notes:**

Add to the `TimelineBar` UI:
- A checkbox "GNSS zones"
- A small window-size picker (1h | 3h | 6h) that appears when the checkbox is checked

Add to `useLookbackStore`:
- `showGnssOverlay: boolean`
- `gnssOverlayWindow: '1h' | '3h' | '6h'`
- `gnssZonesCache: GeoJSON.FeatureCollection | null`

Pre-fetch: When lookback activates with GNSS overlay enabled, call `/api/gnss-zones?center=<midpoint>&window=<full-range>`. The API already supports arbitrary window sizes. Store the full response in `gnssZonesCache`.

Client-side filtering: In `GnssHeatmap` (or a new wrapper), accept `playbackTime` prop. Filter `gnssZonesCache.features` where `detected_at <= playbackTime + windowHalf` AND `expires_at >= playbackTime - windowHalf`. This is cheap — just filtering a pre-fetched array every frame.

Render the filtered features using the existing `GnssHeatmap` fill/line paint styles. The temporal fade (`opacity_factor`) should be recalculated relative to the playhead time, not wall-clock time.

---

### Story 3: Playable Standalone GNSS Time Bar

**As an** analyst
**I want to** press play on the GNSS time bar and watch zones evolve over time
**So that** I can see spoofing patterns without setting up a vessel or area playback

**Acceptance Criteria:**

- GIVEN the GNSS layer is enabled (no lookback active) WHEN I see the GNSS time bar THEN there is a play/pause button and the same speed slider as in lookback mode
- GIVEN I press play on the GNSS time bar WHEN time is not at "Now" THEN the center time advances at the selected speed, and zones update accordingly
- GIVEN GNSS playback is running WHEN the center time reaches "Now" THEN playback stops automatically
- GIVEN GNSS playback is running WHEN I press pause THEN playback stops and the time bar stays at the current position
- GIVEN GNSS playback is running WHEN I drag the time slider THEN playback pauses and the time jumps to where I dragged

**Test Requirements:**

- [ ] Test: Play button appears on GNSS time bar
- [ ] Test: Pressing play advances `centerTime` by `speed * deltaTime` each frame
- [ ] Test: Playback stops when centerTime reaches now
- [ ] Test: Dragging the slider pauses playback
- [ ] Test: Speed slider in GNSS time bar uses the same component as lookback TimelineBar

**Technical Notes:**

Add play/pause state and animation loop to `SpoofingTimeControls.tsx`. This can use a local `useState` + `useRef` + `requestAnimationFrame` pattern (same as `TimelineBar`), or extract the animation loop into a shared `usePlaybackLoop` hook used by both.

The speed slider component (`SpeedSlider`) is shared — import it from the new shared component.

The existing GNSS time bar already has `centerTime`, `onCenterTimeChange`, and the slider. Playing just means auto-advancing `centerTime` at the selected rate. The `GnssHeatmap` already re-fetches when `centerTime` changes, but at high playback speeds this would be too many API calls. During GNSS playback, switch to pre-fetching the full 30-day range and filtering client-side (same pattern as Story 2).

---

## Technical Design

### New Shared Component: `SpeedSlider`

```
frontend/src/components/Map/SpeedSlider.tsx
```

A logarithmic range slider mapping to simulation-minutes-per-real-second:
- Input range: 0–100 (slider position)
- Output: 60–18000 (real-time multiplier, i.e. 1 min/sec to 5 hr/sec)
- Logarithmic mapping: `speed = 60 * Math.pow(300, sliderValue / 100)`
- Label: dynamically computed ("1 min/sec", "15 min/sec", "1 hr/sec", "5 hr/sec")
- Props: `value: number`, `onChange: (speed: number) => void`, `className?: string`

### State Changes: `useLookbackStore`

New fields:
```typescript
showGnssOverlay: boolean;
gnssOverlayWindow: '1h' | '3h' | '6h';
gnssZonesCache: GeoJSON.FeatureCollection | null;
toggleGnssOverlay: () => void;
setGnssOverlayWindow: (w: '1h' | '3h' | '6h') => void;
setGnssZonesCache: (data: GeoJSON.FeatureCollection | null) => void;
```

### Data Flow During Lookback + GNSS

1. User activates lookback (vessel or area) and checks "GNSS zones"
2. Frontend pre-fetches `/api/gnss-zones?center=<midpoint>&window=<total-range>`
3. Response stored in `gnssZonesCache`
4. Each animation frame: filter `gnssZonesCache.features` by `currentTime ± gnssOverlayWindow/2`
5. Pass filtered GeoJSON to `GnssHeatmap` (or new `PlaybackGnssOverlay` component)

### API Changes

None. The existing `/api/gnss-zones` endpoint already accepts arbitrary `center` and `window` parameters and returns GeoJSON. For a 7-day lookback, the request would be `?center=<midpoint>&window=7d`. For 30-day GNSS playback, `?window=30d`.

If 30 days of zones is too much data, we can add a `limit` or accept it will be a larger payload (~50-200 zones). This is a reasonable trade-off for smooth playback.

### Dependencies

- Existing `useLookbackStore` (play/pause/speed/currentTime)
- Existing `TimelineBar` (scrubber, play/pause button, animation loop)
- Existing `GnssHeatmap` (zone rendering with fill/line paint)
- Existing `SpoofingTimeControls` / `GnssTimeBar` (time slider)
- Existing `/api/gnss-zones` endpoint

### Security Considerations

None — this is purely a frontend visualization change with no new data exposure.

---

## Implementation Order

### Group 1 (parallel — no dependencies)

- **Story 1: SpeedSlider component** — creates new `frontend/src/components/Map/SpeedSlider.tsx`
- **Store changes** — adds GNSS overlay fields to `frontend/src/hooks/useLookbackStore.ts`

### Group 2 (parallel — after Group 1)

- **Story 2: GNSS overlay in lookback** — modifies `TimelineBar.tsx` (adds checkbox + window picker), creates `PlaybackGnssOverlay.tsx`, modifies `MapView.tsx`
- **Story 3: Playable GNSS time bar** — modifies `SpoofingTimeControls.tsx` (adds play/pause + SpeedSlider)

### Group 3 (after Group 2)

- **Integration: Replace speed buttons** — swap discrete speed buttons in `TimelineBar.tsx` for the new `SpeedSlider` component

**Parallel safety rules:**
- Group 1 stories touch different files (new component vs store)
- Group 2 stories touch different files (TimelineBar vs SpoofingTimeControls)
- Group 3 is a small integration pass after everything works

---

## Development Approach

### Simplifications (what starts simple)

- GNSS zone pre-fetch: single API call for the full range. If the payload is too large for 30-day standalone GNSS playback, cap at 7 days of pre-fetch and re-fetch in chunks as the playhead moves.
- Speed slider: logarithmic scale with snap-to-nice-values is a stretch goal. Start with raw logarithmic mapping.
- Client-side zone filtering: simple array filter per frame. If there are >500 zones this could be slow — optimize with binary search on sorted `detected_at` if needed.

### Upgrade Path

- "Add zone click interaction during playback" — separate story, not part of this spec
- "Export playback as GIF/video" — separate feature entirely
- "Playback SAR detections alongside GNSS zones" — natural extension using the same pre-fetch + filter pattern
- "Share a playback timestamp via URL" — add `?playback=<iso>&speed=<n>` query params

### Architecture Decisions

- **Shared SpeedSlider** over duplicating speed controls: Both TimelineBar and GnssTimeBar need the same slider. A shared component prevents drift.
- **Pre-fetch + client-side filter** over per-frame API calls: At 5 hr/sec playback, per-frame fetching would fire 60+ requests/second. Pre-fetching the full range is the only viable approach.
- **Extend useLookbackStore** over creating a new store: The playback state (play/pause/speed/currentTime) already lives here. Adding GNSS overlay state keeps it co-located.
- **Reuse GnssHeatmap paint styles** over creating new rendering: The fill/line styles for spoofing (red/orange) and jamming (purple/blue) are already correct. Just need to swap the data source from API-fetched to client-filtered.

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled
- [ ] No regressions in existing tests
- [ ] Speed slider works in both TimelineBar and GnssTimeBar
- [ ] GNSS zones appear/disappear at correct timestamps during playback
- [ ] Playback stops at end of range (not loop)
- [ ] Pre-fetch does not cause excessive API calls during playback
- [ ] Code committed with proper messages
- [ ] Ready for human review
