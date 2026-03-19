# Spec 33: User-Scoped Watchlist & Email Notifications

**Slug:** `user-notifications`
**Wave:** 16
**Depends on:** Spec 31 (auth-backend), Spec 32 (auth-frontend)
**Status:** approved

---

## Overview

Migrate the global watchlist to per-user ownership, add geofence watch rules ("alert me when a sanctioned vessel enters this bounding box"), and build an email notification system that sends alerts from `alerts@heimdalwatch.cloud` when watch conditions are triggered.

---

## Business Rules

1. Each user has their own watchlist — adding a vessel to your watchlist doesn't affect other users.
2. Users can create **watch rules** with conditions:
   - **Vessel watch**: alert on risk tier change, new anomaly, or position update for specific vessels
   - **Area watch**: alert when any vessel matching filters (risk tier, sanctions status, ship type) enters a geographic bounding box
3. Notifications are sent via **email** and **browser push** (existing WebSocket alerts, now user-scoped).
4. Users can configure notification preferences: email on/off, browser on/off, digest frequency (immediate, hourly, daily).
5. Email notifications include: vessel name, MMSI, event type, timestamp, link to Heimdal focused on that vessel.
6. **Rate limiting**: max 50 emails per user per day to prevent spam from noisy rules.
7. **Digest mode**: hourly/daily digests batch multiple alerts into a single email.

---

## Database

### Migration 015_user_watchlist.sql

```sql
-- Add user_id to watchlist (migrate existing rows to NULL = legacy)
ALTER TABLE watchlist ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
CREATE INDEX idx_watchlist_user ON watchlist(user_id);
-- Allow same vessel on multiple users' watchlists
ALTER TABLE watchlist DROP CONSTRAINT watchlist_pkey;
ALTER TABLE watchlist ADD PRIMARY KEY (mmsi, user_id);

-- Watch rules (geofence alerts)
CREATE TABLE IF NOT EXISTS watch_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    rule_type       TEXT NOT NULL CHECK (rule_type IN ('vessel', 'area')),
    -- For vessel rules: which MMSIs to watch
    mmsis           INTEGER[],
    -- For area rules: bounding box or polygon
    geofence        GEOGRAPHY(POLYGON, 4326),
    -- Filter conditions (for area rules)
    risk_tiers      TEXT[],            -- e.g. {'red', 'yellow'}
    sanctions_only  BOOLEAN DEFAULT FALSE,
    ship_types      INTEGER[],
    -- Trigger conditions
    triggers        TEXT[] NOT NULL,    -- e.g. {'risk_change', 'anomaly', 'enter_area', 'position'}
    -- Notification preferences
    notify_email    BOOLEAN DEFAULT TRUE,
    notify_browser  BOOLEAN DEFAULT TRUE,
    digest_mode     TEXT DEFAULT 'immediate' CHECK (digest_mode IN ('immediate', 'hourly', 'daily')),
    -- State
    is_active       BOOLEAN DEFAULT TRUE,
    last_triggered  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_watch_rules_user ON watch_rules(user_id) WHERE is_active = TRUE;
CREATE INDEX idx_watch_rules_geofence ON watch_rules USING GIST(geofence) WHERE rule_type = 'area';

-- Notification log (prevents duplicates, enables digest batching)
CREATE TABLE IF NOT EXISTS notification_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rule_id         UUID REFERENCES watch_rules(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,
    mmsi            INTEGER,
    details         JSONB,
    emailed         BOOLEAN DEFAULT FALSE,
    emailed_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notification_log_user_pending ON notification_log(user_id, created_at)
    WHERE emailed = FALSE;
CREATE INDEX idx_notification_log_created ON notification_log(created_at);
```

---

## Notification Engine (Backend)

### Architecture

The notification engine runs as a **background task inside the API server** (or as a separate lightweight service). It listens to Redis channels and evaluates watch rules.

```
Redis channels (heimdal:risk_changes, heimdal:anomalies, heimdal:positions)
    │
    ▼
Notification Engine
    │
    ├── Match event against active watch_rules
    ├── Check rate limits (50/day/user)
    ├── Insert into notification_log
    │
    ├── Immediate mode → send email now
    └── Digest mode → batch in notification_log, send on schedule
```

### Event Matching

1. **risk_change event** → check all `vessel` rules with `risk_change` trigger that include the MMSI, plus all `area` rules with `risk_change` trigger where the vessel's position is within the geofence
2. **anomaly event** → same pattern with `anomaly` trigger
3. **position event** → check `area` rules with `enter_area` trigger, using ST_Intersects against the geofence. Only trigger on **first entry** (track "inside" state per rule+vessel in Redis to avoid repeated alerts).

### Digest Scheduler

- Runs on a timer (every 5 minutes)
- For hourly digest users: if pending notifications exist and last digest was >1h ago, send batch email
- For daily digest users: if pending notifications exist and last digest was >24h ago, send batch email

---

## API Endpoints

### Watch Rules CRUD

- `GET /api/watch-rules` — list user's rules (requires auth)
- `POST /api/watch-rules` — create rule (requires auth)
- `PUT /api/watch-rules/{id}` — update rule
- `DELETE /api/watch-rules/{id}` — delete rule
- `GET /api/notifications` — list user's notification log (paginated, requires auth)
- `POST /api/notifications/mark-read` — mark notifications as read

### Updated Watchlist Endpoints

- `GET /api/watchlist` — now filtered by `user_id` (from JWT)
- `POST /api/watchlist/{mmsi}` — creates with `user_id`
- `DELETE /api/watchlist/{mmsi}` — deletes only user's entry

### Notification Preferences

Stored on the watch_rule itself (notify_email, notify_browser, digest_mode).

---

## Email Templates

### Immediate Alert Email

```
Subject: [Heimdal] Alert: {vessel_name} — {event_type}

{vessel_name} (MMSI: {mmsi}) triggered your watch rule "{rule_name}":

  Event: {event_description}
  Time:  {timestamp}
  Position: {lat}, {lon}

View in Heimdal: {app_url}/?vessel={mmsi}

---
Heimdal Maritime Intelligence
You're receiving this because of your watch rule "{rule_name}".
Manage notifications: {app_url}/settings
```

### Digest Email

```
Subject: [Heimdal] {count} alerts in the last {period}

You have {count} new alerts:

1. {vessel_name} — {event_type} at {time}
2. {vessel_name} — {event_type} at {time}
...

View all in Heimdal: {app_url}

---
Heimdal Maritime Intelligence
```

---

## Frontend Components

### WatchRulesPanel.tsx

- Accessible from the HUD bar (new "Alerts" button next to watchlist)
- Lists active watch rules with name, type, trigger count
- "Create Rule" button opens a form:
  - **Name** (text)
  - **Type** toggle: Vessel / Area
  - **Vessel mode**: MMSI search (reuse existing vessel search)
  - **Area mode**: "Draw on map" button (reuse area lookback polygon tool), or manual bbox input
  - **Filters** (area mode): risk tier checkboxes, sanctions-only toggle, ship type dropdown
  - **Triggers**: checkboxes for risk_change, anomaly, enter_area, position
  - **Notification**: email on/off, browser on/off, digest mode dropdown
- Each rule card has edit/delete/toggle-active controls

### NotificationBell.tsx

- In HUD bar, shows unread notification count badge
- Dropdown shows recent notifications
- Click notification → select vessel on globe

### Updated WatchlistPanel.tsx

- Now shows only the current user's watchlist (or empty state with "Sign in" if anonymous)

---

## Stories

### Story 1: Database migration + watchlist migration
- Migration 015_user_watchlist.sql
- Migrate existing watchlist rows (set user_id=NULL for legacy, or assign to a default admin user)
- Update watchlist repository to filter by user_id
- Tests: migration, repository with user_id filtering

### Story 2: Watch rules CRUD + repository
- `shared/db/watch_rule_repository.py`: create, list, update, delete, get_active_for_event
- API endpoints: GET/POST/PUT/DELETE /api/watch-rules
- Tests: CRUD operations, auth enforcement

### Story 3: Notification engine + event matching
- `services/api-server/notifications/engine.py`: event listener, rule matching, rate limiting
- Redis subscription to risk_changes, anomalies channels
- Area rule matching via ST_Intersects
- Insert into notification_log
- Tests: event matching, rate limiting, area geofence matching

### Story 4: Email notification sending
- Immediate email sending for `digest_mode='immediate'` rules
- Digest scheduler for hourly/daily batching
- Email templates (immediate + digest)
- Tests: email sending, digest batching, template rendering

### Story 5: Frontend — watch rules panel
- WatchRulesPanel.tsx: rule list + create/edit form
- Polygon drawing integration for area rules
- HUD bar "Alerts" button
- Tests: form rendering, rule creation, edit/delete

### Story 6: Frontend — notification bell + updated watchlist
- NotificationBell.tsx: unread count, dropdown, click-to-select
- Update WatchlistPanel.tsx to be user-scoped
- GET /api/notifications endpoint integration
- Tests: notification display, watchlist user-scoping

### Implementation Order

```
Group 1 (sequential): Story 1                    — DB first
Group 2 (parallel): Story 2, Story 3             — depends on Story 1
Group 3 (sequential): Story 4                    — depends on Story 3
Group 4 (parallel): Story 5, Story 6             — depends on Story 2
```

---

## Acceptance Criteria

- [ ] Each user has their own independent watchlist
- [ ] Users can create vessel watch rules (alert on risk change / anomaly for specific MMSIs)
- [ ] Users can create area watch rules (alert when matching vessels enter a geofence)
- [ ] Immediate email alerts sent via `alerts@heimdalwatch.cloud`
- [ ] Digest mode batches alerts into hourly/daily summary emails
- [ ] Rate limiting prevents >50 emails/user/day
- [ ] Notification bell shows unread count with dropdown
- [ ] Watch rules panel allows CRUD with map-based geofence drawing
- [ ] Existing WebSocket alerts are now user-scoped
- [ ] Anonymous users see "Sign in" prompt on watchlist/rules features
