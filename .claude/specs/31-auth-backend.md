# Spec 31: User Authentication Backend

**Slug:** `auth-backend`
**Wave:** 15
**Depends on:** Wave 3 (api-server), Wave 6 (watchlist)
**Status:** approved

---

## Overview

Add user accounts, JWT-based sessions, and email-based registration to Heimdal. The app currently has zero authentication — all endpoints are public. This spec adds a `users` table, registration-via-email flow (signup → confirmation email → set password), login/logout, middleware to protect expensive endpoints, and an inactivity lifecycle (disable after 6 months, warn 2 weeks before).

Email sending uses SMTP via Hostinger (`alerts@heimdalwatch.cloud`).

---

## Business Rules

1. Users register with **email only**. They receive a confirmation email with a link to set their password.
2. Passwords are hashed with **bcrypt** (cost factor 12).
3. Sessions use **JWT access tokens** (short-lived, 1h) + **refresh tokens** (long-lived, 30d, stored in DB).
4. Unconfirmed accounts are purged after 48 hours.
5. Accounts inactive for **6 months** are **permanently deleted** — user record, watchlist, watch rules, notification log, and refresh tokens are all purged (CASCADE). A warning email is sent **2 weeks** before with a re-activation link.
6. If the user clicks the re-activation link within the 2-week grace period, `last_active_at` is reset and the countdown starts over. If they don't act, the account and all associated data are deleted on day 0.
7. The app remains **fully usable without login** for read-only/lightweight operations (globe, vessel list, vessel detail, basic filtering). Login gates only:
   - Watchlist add/remove
   - Lookback playback
   - Area lookback
   - Track export
   - Dossier export
   - Enrichment form submission
   - Future: email notifications (spec 33)

---

## Database

### Migration 014_users.sql

```sql
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT,                          -- NULL until confirmed
    display_name    TEXT,
    is_confirmed    BOOLEAN DEFAULT FALSE,
    confirm_token   TEXT,
    confirm_expires TIMESTAMPTZ,
    reset_token     TEXT,
    reset_expires   TIMESTAMPTZ,
    last_login_at   TIMESTAMPTZ,
    last_active_at  TIMESTAMPTZ DEFAULT NOW(),
    deletion_warning_sent_at TIMESTAMPTZ,       -- set when 2-week warning email sent
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_confirm_token ON users(confirm_token) WHERE confirm_token IS NOT NULL;
CREATE INDEX idx_users_reset_token ON users(reset_token) WHERE reset_token IS NOT NULL;
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_users_inactive ON users(last_active_at) WHERE is_confirmed = TRUE;
```

---

## SMTP Email Utility

### shared/email.py

- Uses `aiosmtplib` for async SMTP sending
- Configuration via environment variables:
  - `SMTP_HOST` (default: `smtp.hostinger.com`)
  - `SMTP_PORT` (default: `465`)
  - `SMTP_USER` (default: `alerts@heimdalwatch.cloud`)
  - `SMTP_PASS` (required, from env/secrets)
  - `SMTP_FROM_NAME` (default: `Heimdal`)
- Provides `send_email(to, subject, html_body)` async function
- Graceful failure: logs error but doesn't crash the caller
- Template rendering: simple f-string HTML templates (no Jinja needed)

### Email Templates

1. **Confirmation email** — "Confirm your Heimdal account" with link to `/confirm?token={token}`
2. **Password reset email** — "Reset your Heimdal password" with link to `/reset-password?token={token}`. Link expires in 1 hour.
3. **Inactivity warning** — "Your Heimdal account will be permanently deleted in 2 weeks" with re-activation link. Must clearly state: all watchlists, watch rules, notification preferences, and account data will be permanently removed if no action is taken.

---

## API Endpoints

### POST /api/auth/register
- Body: `{ email: string }`
- Creates user with `is_confirmed=false`, generates `confirm_token` (URL-safe random, 64 chars), sets `confirm_expires` to 48h from now
- Sends confirmation email
- Returns 201 `{ message: "Check your email to confirm your account" }`
- If email already exists and confirmed: returns 409
- If email exists but unconfirmed: regenerate token, resend email, return 201

### POST /api/auth/confirm
- Body: `{ token: string, password: string }`
- Validates token exists, not expired
- Hashes password, sets `is_confirmed=true`, clears `confirm_token`
- Creates a session (returns JWT + refresh token)
- Returns 200 `{ access_token, refresh_token, user: { id, email, display_name } }`

### POST /api/auth/login
- Body: `{ email: string, password: string }`
- Validates credentials, checks `is_confirmed`
- Updates `last_login_at` and `last_active_at`
- Returns 200 `{ access_token, refresh_token, user }`
- Returns 401 on bad credentials, 403 if not confirmed

### POST /api/auth/refresh
- Body: `{ refresh_token: string }`
- Validates refresh token hash in DB, not expired
- Issues new access + refresh token pair (rotate refresh token)
- Returns 200 `{ access_token, refresh_token }`

### POST /api/auth/logout
- Header: `Authorization: Bearer {access_token}`
- Deletes all refresh tokens for the user
- Returns 200

### GET /api/auth/me
- Header: `Authorization: Bearer {access_token}`
- Returns current user profile
- Updates `last_active_at`

### POST /api/auth/forgot-password
- Body: `{ email: string }`
- If email exists and is confirmed: generates a `reset_token` (URL-safe random, 64 chars), sets `reset_expires` to 1 hour from now, sends password reset email with link to `/reset-password?token={token}`
- Always returns 200 `{ message: "If that email exists, we sent a reset link" }` (no email enumeration)

### POST /api/auth/reset-password
- Body: `{ token: string, password: string }`
- Validates token exists and not expired
- Hashes new password, clears `reset_token`
- Invalidates all existing refresh tokens for the user (force re-login everywhere)
- Returns 200 `{ message: "Password updated. Please sign in." }`
- Returns 400 if token invalid/expired

### POST /api/auth/reactivate
- Body: `{ token: string }`
- Resets `last_active_at` to NOW() and clears `deletion_warning_sent_at`, preventing the upcoming deletion
- Only valid during the 2-week grace period (after warning, before deletion)
- Returns 200 `{ message: "Account reactivated. Your data has been preserved." }`
- Returns 404 if account already deleted

---

## Auth Middleware

### `get_current_user` dependency (FastAPI)

- Reads `Authorization: Bearer <token>` header
- Decodes JWT, validates signature and expiry
- Returns `User` object or `None` (not 401 — see below)

### `require_auth` dependency

- Wraps `get_current_user`, raises 401 if no valid user
- Used on protected endpoints

### Endpoint protection strategy

- **Public endpoints** (no change): vessels, stats, health, anomalies, SAR, GFW, network, positions WS
- **Protected endpoints** (add `require_auth`): watchlist mutations, enrichment POST, track export, lookback track fetch, area-history

The `get_current_user` dependency is also added to ALL endpoints (optional) so `last_active_at` can be updated on any authenticated request.

---

## Inactivity Lifecycle

### Background task (runs daily via APScheduler or asyncio loop)

1. **Warning phase**: Query users where `is_active=TRUE AND last_active_at < NOW() - INTERVAL '5 months 2 weeks'` and no warning sent yet
   - Send inactivity warning email with re-activation link
   - Email must state: "Your account and all associated data (watchlists, watch rules, notifications) will be **permanently deleted** on {deletion_date} unless you sign in or click the link below."
   - Store warning state (add `deletion_warning_sent_at` column to users table)
2. **Deletion phase**: Query users where `is_active=TRUE AND last_active_at < NOW() - INTERVAL '6 months'`
   - `DELETE FROM users WHERE id = :id` — CASCADE deletes all associated data (watchlist, watch_rules, notification_log, refresh_tokens)
   - Log the deletion (user email + deletion timestamp) for audit purposes
3. Purge unconfirmed users where `created_at < NOW() - INTERVAL '48 hours' AND is_confirmed=FALSE`
4. Purge expired refresh tokens

---

## JWT Configuration

- Algorithm: HS256
- Secret: `JWT_SECRET` env var (required)
- Access token TTL: 1 hour
- Refresh token TTL: 30 days
- Payload: `{ sub: user_id, email: email, exp: timestamp, iat: timestamp }`

---

## Stories

### Story 1: Database migration + user repository
- Migration 014_users.sql
- `shared/db/user_repository.py`: create_user, get_by_email, get_by_id, get_by_confirm_token, confirm_user, update_last_active, reactivate_user (reset last_active_at + clear warning), delete_user, purge_unconfirmed, get_users_needing_warning (5.5mo inactive, no warning sent), get_users_for_deletion (6mo inactive)
- Tests: repository functions with mock DB

### Story 2: SMTP email utility
- `shared/email.py`: send_email, email templates (confirm, warning, disabled, reactivate)
- SMTP config in `shared/config.py`
- Tests: mock SMTP, template rendering

### Story 3: JWT utility + auth middleware
- `shared/auth.py`: create_access_token, create_refresh_token, decode_token, hash_password, verify_password
- `services/api-server/middleware/auth.py`: get_current_user, require_auth FastAPI dependencies
- Tests: token creation/validation, password hashing, middleware behavior

### Story 4: Registration + confirmation endpoints
- POST /api/auth/register, POST /api/auth/confirm
- Token generation, email sending, account creation flow
- Tests: happy path, duplicate email, expired token, invalid token

### Story 5: Login + refresh + logout + me + password reset endpoints
- POST /api/auth/login, POST /api/auth/refresh, POST /api/auth/logout, GET /api/auth/me
- POST /api/auth/forgot-password, POST /api/auth/reset-password
- Refresh token rotation, last_active tracking
- Password reset invalidates all refresh tokens
- Tests: login success/failure, token refresh, logout, forgot-password (no email enumeration), reset-password (valid/expired/invalid token)

### Story 6: Protect existing endpoints
- Add `require_auth` to: watchlist POST/DELETE, enrichment POST, track export, area-history
- Add optional `get_current_user` to all routes for activity tracking
- Tests: verify 401 on protected endpoints without token, 200 with valid token

### Story 7: Inactivity lifecycle
- Background task: warning emails at 5.5 months, **permanent account deletion** at 6 months (CASCADE), purge unconfirmed at 48h
- POST /api/auth/reactivate endpoint (grace period only)
- Audit logging of deleted accounts
- Tests: lifecycle state transitions, email sending, CASCADE deletion, reactivation during grace period, reactivation after deletion returns 404

### Implementation Order

```
Group 1 (parallel): Story 1, Story 2, Story 3
Group 2 (parallel): Story 4, Story 5     — depends on Group 1
Group 3 (sequential): Story 6            — depends on Group 2
Group 4 (sequential): Story 7            — depends on Group 2
```

---

## Acceptance Criteria

- [ ] Users can register with email, receive confirmation, set password, and log in
- [ ] JWT access/refresh tokens work correctly with rotation
- [ ] Protected endpoints return 401 without valid token
- [ ] Public endpoints still work without authentication
- [ ] Inactivity lifecycle sends warning at 5.5 months and **permanently deletes** account + all data at 6 months
- [ ] Warning email clearly states data will be permanently deleted with the exact date
- [ ] Re-activation link works during the 2-week grace period (resets last_active_at)
- [ ] After deletion, all user data is gone (watchlist, watch rules, notifications, tokens) via CASCADE
- [ ] Deleted accounts are logged for audit
- [ ] SMTP sends real emails via Hostinger (testable with env vars set)
- [ ] Unconfirmed accounts are purged after 48 hours
