# Spec 32: User Authentication Frontend

**Slug:** `auth-frontend`
**Wave:** 15
**Depends on:** Spec 31 (auth-backend) — API contract needed, can start UI shell in parallel
**Status:** approved

---

## Overview

Add login, registration, and email confirmation pages to the Heimdal frontend. Implement an auth store, token management, and a feature-gating system that hides/disables protected features for anonymous users while keeping the app fully usable for read-only browsing.

---

## Design Philosophy

- **The globe is always visible.** There is no full-page login wall. Anonymous users see the globe, vessels, filters, and can browse vessel details.
- **Login is a sidebar/modal flow**, not a separate page. It slides in from the right (like the vessel panel) or appears as a centered modal.
- **Protected features show a "Sign in to use" prompt** rather than disappearing entirely. Users should know what they're missing.
- **Session persists in localStorage** (access + refresh tokens). Auto-refresh happens transparently.

---

## Auth Store (Zustand)

### `useAuthStore`

```typescript
interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  register: (email: string) => Promise<{ message: string }>;
  confirm: (token: string, password: string) => Promise<void>;
  forgotPassword: (email: string) => Promise<{ message: string }>;
  resetPassword: (token: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<boolean>;
  loadSession: () => void;  // from localStorage on app start
}
```

- On app startup, `loadSession()` reads tokens from localStorage and validates with `GET /api/auth/me`
- If access token expired, auto-refresh using refresh token
- If refresh fails, clear session (user must log in again)
- All API calls use an `authFetch` wrapper that attaches the Bearer header and handles 401 with auto-refresh

### `authFetch` utility

- Wraps `fetch` with Authorization header
- On 401: attempt refresh, retry original request once
- On refresh failure: clear session, optionally show "Session expired" toast

---

## Pages / Components

### LoginModal.tsx

- Triggered by "Sign In" button in the HUD top bar (replaces a section of the header, or appears as a slide-over)
- Two modes: **Login** and **Register**
- **Login mode:**
  - Email + password fields
  - "Sign In" button
  - "Forgot password?" link → switches to forgot-password mode
  - "Don't have an account? Register" link
  - Error display (invalid credentials, not confirmed)
- **Forgot password mode:**
  - Email field only
  - "Send Reset Link" button
  - Success state: "If that email exists, we sent a reset link"
  - "Back to Sign In" link
- **Register mode:**
  - Email field only
  - "Send Confirmation" button
  - Success state: "Check your email — we sent a confirmation link to {email}"
  - "Already have an account? Sign In" link
- Styled consistently with the operations centre theme (dark panels, sharp corners)

### ConfirmPage.tsx

- Accessed via `/confirm?token=xxx` (or handled as a route within the SPA)
- Shows a "Set your password" form when token is valid
- Password field + confirm password field
- On success: auto-logs in and redirects to globe
- On invalid/expired token: error message with "Request new confirmation" link

### ResetPasswordPage.tsx

- Accessed via `/reset-password?token=xxx`
- Shows "Set new password" form (new password + confirm password)
- On success: "Password updated. Please sign in." → redirects to login modal
- On invalid/expired token: error message with "Request a new reset link" link

### UserMenu (in HUD bar)

- When logged in: shows user email/avatar, dropdown with "Sign Out"
- When logged out: shows "Sign In" button
- Compact — fits in the existing HUD top bar

---

## Feature Gating

### `useRequireAuth` hook

```typescript
function useRequireAuth(): {
  isAuthenticated: boolean;
  requireAuth: (action: string) => boolean;  // shows login modal if not auth'd, returns false
}
```

### Protected features (show "Sign in" prompt when clicked by anonymous user)

| Feature | Component | Gating behavior |
|---------|-----------|-----------------|
| Add to watchlist | WatchButton.tsx | Click → opens login modal with message "Sign in to use watchlists" |
| Lookback playback | LookbackSection.tsx | "Start Playback" button disabled + tooltip "Sign in to use lookback" |
| Area lookback | AreaLookbackPanel.tsx | "Search" button disabled + tooltip |
| Track export | TrackExportSection.tsx | Export button disabled + tooltip |
| Dossier export | DossierExport.tsx | Export button disabled + tooltip |
| Enrichment form | EnrichmentForm.tsx | Form disabled + message |

### Gating pattern

Each protected component checks `isAuthenticated` from the auth store:
- If authenticated: normal behavior
- If not: show a subtle lock icon / "Sign in" overlay, and clicking opens the login modal

---

## Token Management

- **Access token**: stored in Zustand state (memory) + localStorage
- **Refresh token**: stored in localStorage only
- On page load: `loadSession()` reads from localStorage, validates with `/api/auth/me`
- On login/confirm: store both tokens
- On logout: clear both tokens from state + localStorage, call `/api/auth/logout`
- Auto-refresh: when `authFetch` gets 401, use refresh token to get new pair

---

## Routing

The app currently has no router — it's a single-page globe app. We need minimal routing for the confirmation flow:

- Add `react-router-dom` (or handle with URL params — simpler)
- `/confirm?token=xxx` → shows ConfirmPage overlay on top of the globe
- `/reset-password?token=xxx` → shows ResetPasswordPage overlay on top of the globe
- All other URLs → normal app

Alternatively, use simple URL param checks in App.tsx:
```typescript
const params = new URLSearchParams(window.location.search);
const confirmToken = params.get('confirm');
const resetToken = params.get('reset-password');
if (confirmToken) return <ConfirmPage token={confirmToken} />;
if (resetToken) return <ResetPasswordPage token={resetToken} />;
```

---

## Stories

### Story 1: Auth store + token management + authFetch utility
- `useAuthStore.ts`: Zustand store with all state and actions
- `authFetch.ts`: fetch wrapper with auto-refresh
- localStorage persistence
- Tests: store actions, token refresh logic, authFetch 401 handling

### Story 2: LoginModal component
- Login + Register + Forgot Password modes
- Form validation, error handling, loading states
- Styled with ops-centre theme
- Tests: renders all three modes, form submission, error display, mode switching

### Story 3: ConfirmPage + ResetPasswordPage + URL handling
- ConfirmPage: password set form, token validation, auto-login on success
- ResetPasswordPage: new password form, token validation, redirect to login on success
- URL param detection in App.tsx for both `/confirm` and `/reset-password`
- Tests: valid token flow, expired token, password mismatch, both pages

### Story 4: HUD bar auth integration + UserMenu
- "Sign In" button when logged out
- User dropdown when logged in (email + sign out)
- Session initialization on app startup
- Tests: renders correct state, logout flow

### Story 5: Feature gating
- `useRequireAuth` hook
- Update WatchButton, LookbackSection, AreaLookbackPanel, TrackExportSection, DossierExport, EnrichmentForm
- Lock icon / "Sign in" overlays
- Tests: features disabled when not auth'd, enabled when auth'd

### Implementation Order

```
Group 1 (parallel): Story 1, Story 2, Story 3
Group 2 (sequential): Story 4            — depends on Story 1
Group 3 (sequential): Story 5            — depends on Story 1
```

Story 4 and 5 can run in parallel with each other (both depend on Story 1 only).

---

## Acceptance Criteria

- [ ] Anonymous users can browse the globe, view vessels, use filters — no login wall
- [ ] Users can register with email, receive confirmation, set password
- [ ] Login/logout works with JWT + refresh tokens
- [ ] Session persists across page reloads via localStorage
- [ ] Protected features show "Sign in" prompt for anonymous users
- [ ] Confirmation page works via URL parameter
- [ ] Auto-refresh handles token expiry transparently
- [ ] UI matches the operations centre visual theme
