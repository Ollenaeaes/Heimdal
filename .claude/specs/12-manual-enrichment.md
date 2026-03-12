# Feature Spec: Manual Enrichment Form

**Slug:** `manual-enrichment`
**Created:** 2026-03-11
**Status:** draft
**Priority:** medium
**Wave:** 6 (Advanced Features)

---

## Overview

Build the manual enrichment form in the vessel detail panel that allows operators to enter data from Equasis and other restricted sources. The form submits to the API, stores enrichment data, and triggers re-scoring.

## Problem Statement

Automated enrichment cannot access Equasis (ToS prohibits scraping). Operators must manually research flagged vessels and enter ownership, insurance, classification, and inspection data. This form is how that manual intelligence enters the system.

## Out of Scope

- NOT: Automated enrichment (see `08-enrichment-service`)
- NOT: Vessel detail panel structure (see `10-vessel-detail-panel`)
- NOT: Scoring rules that consume enrichment (see `07-scoring-engine`)

---

## User Stories

### Story 1: Enrichment Form UI

**As an** operator
**I want to** enter manual enrichment data for a flagged vessel
**So that** ownership, insurance, and inspection data is recorded in the system

**Acceptance Criteria:**

- GIVEN the vessel detail panel WHEN scrolled to bottom THEN a collapsible "Manual Enrichment" section is visible
- GIVEN the form WHEN expanded THEN it shows fields: Source (dropdown: Equasis, Paris MoU, Tokyo MoU, Corporate Registry, Other), Registered Owner (text), Commercial Manager (text), Beneficial Owner (text), P&I Insurer (text + tier dropdown: IG Member, Non-IG Western, Russian State-Backed, Unknown, Fraudulent, None), Classification Society (text + IACS checkbox), PSC Detentions (number), PSC Deficiencies (number), Notes (textarea)
- GIVEN required field "Source" WHEN empty and submitting THEN show validation error
- GIVEN the form WHEN submitted THEN call `POST /api/vessels/{mmsi}/enrich` with form data

**Test Requirements:**

- [ ] Test: EnrichmentForm renders all fields
- [ ] Test: Source dropdown is required
- [ ] Test: P&I tier dropdown has correct options
- [ ] Test: Submit calls the correct API endpoint

**Technical Notes:**

Use controlled form with React state. Pi_insurer_tier options: 'ig_member', 'non_ig_western', 'russian_state', 'unknown', 'fraudulent', 'none'. Classification IACS checkbox is a boolean.

---

### Story 2: Form Submission and Feedback

**As an** operator
**I want to** see confirmation after submitting enrichment data
**So that** I know the data was saved and scoring was updated

**Acceptance Criteria:**

- GIVEN a successful submission WHEN response returns THEN show success toast "Enrichment data saved. Risk score recalculated."
- GIVEN a successful submission WHEN the panel refreshes THEN the vessel profile shows updated enrichment data
- GIVEN the submission WHEN it triggers re-scoring THEN the risk section updates with any score changes
- GIVEN a failed submission WHEN API returns error THEN show error toast with message
- GIVEN the form WHEN submitting THEN show loading state on submit button

**Test Requirements:**

- [ ] Test: Successful POST shows success message
- [ ] Test: Failed POST shows error message
- [ ] Test: Profile data refreshes after submission (TanStack Query invalidation)
- [ ] Test: Loading state shows during submission

**Technical Notes:**

Use TanStack Query `useMutation` for the POST. On success, invalidate the vessel query to trigger refetch. Toast notifications can be simple absolute-positioned divs with auto-dismiss.

---

### Story 3: Enrichment History Display

**As an** operator
**I want to** see previous enrichment entries for a vessel
**So that** I can review what data has already been entered and by whom

**Acceptance Criteria:**

- GIVEN a vessel with manual enrichment records WHEN viewing THEN show a list of past enrichment entries with: date, source, summary of data entered
- GIVEN each entry WHEN displayed THEN show collapsible detail with all fields
- GIVEN no enrichment history WHEN viewing THEN show "No manual enrichment data yet"

**Test Requirements:**

- [ ] Test: Enrichment history renders when data exists
- [ ] Test: Empty state renders correctly

**Technical Notes:**

Enrichment history comes from the vessel profile API response (includes manual_enrichment array). Render as a list of collapsible cards, newest first.

---

## Technical Design

### Data Model Changes

None — uses existing manual_enrichment table via API.

### API Changes

Consumes: `POST /api/vessels/{mmsi}/enrich` (from `06-api-server`)

### Dependencies

- Vessel detail panel (from `10-vessel-detail-panel`)
- API server enrichment endpoint (from `06-api-server`)

---

## Implementation Order

### Group 1 (sequential)
- Story 1 — Form UI
- Story 2 — Submission and feedback
- Story 3 — History display

---

## Verification Checklist

- [ ] All user stories implemented
- [ ] Form renders with all required fields
- [ ] Validation prevents submission without required fields
- [ ] Successful submission shows confirmation
- [ ] Profile refreshes with new enrichment data
- [ ] Enrichment history displays correctly
- [ ] Code committed with proper messages
- [ ] Ready for human review
