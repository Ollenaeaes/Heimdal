# Feature Spec: Watchlist and Notifications

**Slug:** `watchlist-notifications`
**Created:** 2026-03-11
**Status:** completed
**Priority:** medium
**Wave:** 6 (Advanced Features)

---

## Overview

Build the watchlist feature allowing operators to track specific vessels, with browser desktop notifications when watchlisted vessels have risk tier changes or new anomaly events.

## Problem Statement

Operators need to monitor specific vessels of interest over time. When a watchlisted vessel's risk changes or new anomalies are detected, the operator should be alerted immediately, even if they're not actively looking at that vessel.

## Out of Scope

- NOT: Email notifications (future scope)
- NOT: Sound alerts
- NOT: Watchlist sharing between users

---

## User Stories

### Story 1: Add/Remove from Watchlist

**As an** operator
**I want to** add and remove vessels from my watchlist
**So that** I can track specific vessels of interest

**Acceptance Criteria:**

- GIVEN the vessel detail panel WHEN viewing THEN show a "Watch" / "Unwatch" toggle button
- GIVEN clicking "Watch" WHEN the vessel is not watchlisted THEN call `POST /api/watchlist/{mmsi}` and update UI
- GIVEN clicking "Unwatch" WHEN the vessel is watchlisted THEN call `DELETE /api/watchlist/{mmsi}` and update UI
- GIVEN a watchlisted vessel WHEN shown on the globe THEN it has a distinct visual indicator (e.g., border ring or star icon)
- GIVEN the watchlist WHEN persisted THEN it survives browser refresh (stored server-side)

**Test Requirements:**

- [ ] Test: Watch button calls POST endpoint
- [ ] Test: Unwatch button calls DELETE endpoint
- [ ] Test: UI updates immediately (optimistic update)
- [ ] Test: Watchlisted vessels have distinct marker

**Technical Notes:**

Use `useWatchlist.ts` hook that manages watchlist state. Fetch initial watchlist from `GET /api/watchlist` on app load. Use TanStack Query for CRUD operations with optimistic updates.

---

### Story 2: Watchlist Panel/View

**As an** operator
**I want to** see all my watchlisted vessels in one place
**So that** I can quickly review their status

**Acceptance Criteria:**

- GIVEN a watchlist button in the controls area WHEN clicked THEN show a list of all watchlisted vessels
- GIVEN each watchlisted vessel WHEN shown THEN display: name, MMSI, risk tier badge, last position time
- GIVEN a vessel in the list WHEN clicked THEN select it on the globe and open the detail panel
- GIVEN the list WHEN empty THEN show "No vessels watched. Click a vessel and press Watch to start."

**Test Requirements:**

- [ ] Test: Watchlist panel renders with all watchlisted vessels
- [ ] Test: Clicking a vessel selects it
- [ ] Test: Empty state shows correctly

**Technical Notes:**

Can be a dropdown panel or a sidebar section. Fetch from `GET /api/watchlist`, join with vessel data from the Zustand store for real-time position/tier.

---

### Story 3: Browser Desktop Notifications

**As an** operator
**I want to** receive desktop notifications when a watchlisted vessel's risk changes
**So that** I'm alerted even when the app is in the background

**Acceptance Criteria:**

- GIVEN the app loads WHEN the user hasn't granted notification permission THEN prompt for permission on first watchlist event
- GIVEN a risk_change event from `ws://*/ws/alerts` WHEN the vessel is on my watchlist THEN trigger a browser Notification with: vessel name, old tier → new tier, and triggering rule
- GIVEN a notification WHEN clicked THEN focus the app window and select the vessel on the globe
- GIVEN a new anomaly event WHEN the vessel is watchlisted THEN trigger a notification with: vessel name, rule name, severity

**Test Requirements:**

- [ ] Test: useWatchlist hook subscribes to alert WebSocket
- [ ] Test: Notification fires for watchlisted vessel risk change
- [ ] Test: Notification does NOT fire for non-watchlisted vessels
- [ ] Test: Clicking notification selects the vessel

**Technical Notes:**

Use the Web Notifications API (`new Notification()`). Check `Notification.permission` and request if needed. The alert WebSocket from `09-globe-rendering` already streams events — this hook filters for watchlisted MMSIs.

---

## Technical Design

### Data Model Changes

None — uses existing watchlist table via API.

### API Changes

Consumes: `GET /api/watchlist`, `POST /api/watchlist/{mmsi}`, `DELETE /api/watchlist/{mmsi}`, `ws://*/ws/alerts`

### Dependencies

- API server watchlist endpoints (from `06-api-server`)
- Alert WebSocket (from `09-globe-rendering`)
- Globe rendering for marker styling (from `09-globe-rendering`)

---

## Implementation Order

### Group 1 (parallel)
- Story 1 — Add/remove from watchlist
- Story 2 — Watchlist panel

### Group 2 (after Group 1)
- Story 3 — Desktop notifications (needs watchlist state)

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Watchlist persists across browser refresh
- [ ] Watchlisted vessels have distinct visual indicators
- [ ] Desktop notifications fire for watchlisted vessel events
- [ ] Notifications do not fire for non-watchlisted vessels
- [ ] Clicking notification focuses app and selects vessel
- [ ] Code committed with proper messages
- [ ] Ready for human review
