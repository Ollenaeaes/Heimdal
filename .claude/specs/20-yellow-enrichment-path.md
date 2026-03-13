# Feature Spec: Yellow-Tier Enrichment Path

**Slug:** `yellow-enrichment-path`
**Created:** 2026-03-13
**Status:** completed
**Priority:** high

---

## Overview

When a vessel transitions to yellow tier (risk score 30-79), trigger an enhanced enrichment pipeline that goes beyond the standard 6-hour cycle. This "enrichment escalation" fetches ownership chain details, insurance/classification status, port state control history, and increases the enrichment frequency for elevated-risk vessels. The goal is to automatically gather the evidence an analyst needs to decide whether a yellow vessel is truly suspicious.

## Problem Statement

Currently, all vessels are enriched on the same 6-hour cycle regardless of risk level. When a vessel turns yellow:

1. **No ownership deep-dive** — enrichment fetches basic GFW vessel identity but doesn't investigate the corporate ownership chain, fleet size of the owning company, or incorporation dates.
2. **No insurance verification** — P&I club status and coverage gaps are the strongest shadow fleet indicators (82% of confirmed shadow fleet lacks IG coverage per S&P Global) but aren't checked.
3. **No classification check** — non-IACS classification correlates with 3.2x higher deficiency rates, but this isn't verified.
4. **Same enrichment frequency** — a vessel that just turned yellow waits up to 6 hours for its next enrichment cycle, same as a green vessel that's been stable for months.
5. **Analyst must manually research** — the manual enrichment form (spec 12) exists but requires the analyst to do their own research and input data.

## Out of Scope

- NOT: Automatic API integrations with P&I clubs or Equasis (start with GFW vessel identity deep-dive + manual enrichment prompts)
- NOT: Real-time enrichment on every position update (too expensive)
- NOT: Red-tier enrichment (red vessels are already flagged — focus on yellow where enrichment changes the decision)
- NOT: Frontend UI changes for enrichment status (the existing detail panel shows enrichment data)

---

## User Stories

### Story 1: Tier-Change Triggered Enrichment

**As a** system
**I want to** trigger immediate enrichment when a vessel's risk tier changes to yellow or red
**So that** elevated-risk vessels are enriched without waiting for the next 6-hour cycle

**Acceptance Criteria:**

- GIVEN a vessel transitions from green to yellow WHEN the scoring engine publishes a `risk_changes` event THEN the enrichment service receives it and queues immediate enrichment for that MMSI
- GIVEN a vessel transitions from yellow to red WHEN tier changes THEN enrichment is also triggered immediately
- GIVEN a vessel transitions from yellow to green WHEN tier changes THEN no special enrichment is triggered (standard cycle is sufficient)
- GIVEN the enrichment service receives a tier-change trigger WHEN it starts enriching THEN it runs the full enrichment pipeline (GFW events + SAR + identity + sanctions)
- GIVEN a vessel was enriched < 1 hour ago WHEN tier change triggers THEN enrichment is skipped (debounce to prevent rapid re-enrichment from score fluctuations)

**Test Requirements:**

- [ ] Test: Green → yellow transition triggers enrichment within 30 seconds
- [ ] Test: Yellow → red transition triggers enrichment
- [ ] Test: Yellow → green does NOT trigger enrichment
- [ ] Test: Debounce: vessel enriched 30 minutes ago → skipped
- [ ] Test: Debounce: vessel enriched 2 hours ago → enriched again
- [ ] Test: Multiple rapid tier changes → only one enrichment (debounce)

**Technical Notes:**

- Enrichment service already subscribes to Redis pub/sub — add subscription to `heimdal:risk_changes` channel
- Add a new Redis hash `heimdal:enrichment_triggered` tracking `{mmsi: last_triggered_timestamp}` with TTL
- Debounce window: 1 hour (configurable in config.yaml)
- The enrichment runner already handles single-vessel enrichment — just need to add the trigger path
- Config:
  ```yaml
  enrichment:
    tier_change_trigger:
      enabled: true
      debounce_hours: 1
      trigger_tiers: ["yellow", "red"]
  ```

---

### Story 2: Enhanced Ownership Enrichment

**As a** enrichment service
**I want to** fetch detailed ownership chain information for elevated-risk vessels
**So that** ownership obfuscation patterns can be detected by scoring rules

**Acceptance Criteria:**

- GIVEN a yellow/red vessel is being enriched WHEN GFW vessel identity is fetched THEN ownership data includes: registered owner, operator, beneficial owner (if available), flag state, and fleet size of owning company
- GIVEN ownership data is returned WHEN stored THEN `vessel_profiles.ownership_data` JSONB includes: `owners` array with `{name, country, role, fleet_size, incorporated_date}` for each entity
- GIVEN the owning company has fleet_size = 1 WHEN stored THEN a `single_vessel_company: true` flag is set in ownership_data
- GIVEN ownership data has changed since last enrichment WHEN stored THEN the change is recorded in `ownership_data.history` array with timestamps
- GIVEN GFW returns no ownership data WHEN enrichment completes THEN `ownership_data.ownership_status = "unknown"` is set (triggering the ownership_risk rule from spec 18)

**Test Requirements:**

- [ ] Test: GFW vessel identity returns owner + operator → stored correctly in ownership_data
- [ ] Test: Fleet size = 1 → single_vessel_company flag set
- [ ] Test: Ownership change detected → history entry added
- [ ] Test: No ownership data → ownership_status = "unknown"
- [ ] Test: Multiple enrichment cycles → ownership_data accumulates history, doesn't overwrite

**Technical Notes:**

- Update `services/enrichment/vessel_fetcher.py` to extract more detailed ownership from GFW response
- GFW Vessel API returns `registryOwners`, `registryOperators` — parse these into the structured format
- Fleet size: count vessels with the same owner name in GFW response (may need additional API call or maintain local cache)
- Ownership_data JSONB structure:
  ```json
  {
    "owners": [
      {"name": "...", "country": "AE", "role": "owner", "fleet_size": 1, "incorporated_date": null}
    ],
    "single_vessel_company": true,
    "ownership_status": "verified",
    "last_updated": "2026-03-13T...",
    "history": [
      {"date": "2026-03-01T...", "change": "owner_changed", "from": "...", "to": "..."}
    ]
  }
  ```
- Store incorporation_date as null if not available (many shell companies don't publish this)

---

### Story 3: Insurance and Classification Enrichment

**As a** enrichment service
**I want to** fetch P&I insurance and classification society status for elevated-risk vessels
**So that** the insurance_class_risk scoring rule (spec 18) has data to evaluate

**Acceptance Criteria:**

- GIVEN a yellow/red vessel is being enriched WHEN GFW vessel identity is fetched THEN classification society data is extracted and stored
- GIVEN the vessel has classification data WHEN stored THEN `vessel_profiles.classification_data` JSONB includes: `{society_name, society_code, is_iacs, class_status, last_survey_date}`
- GIVEN the vessel has P&I data available WHEN stored THEN `vessel_profiles.insurance_data` JSONB includes: `{provider, is_ig_member, coverage_status, expiry_date}`
- GIVEN classification data is not available from GFW WHEN manual enrichment has P&I or classification data THEN use manual enrichment data instead
- GIVEN classification changes WHEN detected THEN a `class_change_history` entry is added

**Test Requirements:**

- [ ] Test: GFW returns classification "DNV" → stored with is_iacs=true
- [ ] Test: GFW returns classification "Unknown Society" → stored with is_iacs=false
- [ ] Test: No classification data from GFW → classification_status = "unknown"
- [ ] Test: Manual enrichment has classification → used as fallback
- [ ] Test: Classification change from "DNV" to "Russian Register" → history entry added
- [ ] Test: P&I data stored when available

**Technical Notes:**

- GFW Vessel API may not have P&I data directly — check what fields are available
- If GFW doesn't provide P&I data, this story focuses on classification only
- P&I data primarily comes from manual enrichment (spec 12's form already has P&I fields)
- New database columns needed: add `classification_data JSONB` and `insurance_data JSONB` to vessel_profiles (new migration)
- IACS member codes: `{"ABS", "BV", "CCS", "CRS", "DNV", "IRS", "KR", "LR", "NK", "PRS", "RINA", "RS"}`
- Migration `008_enrichment_columns.sql`

---

### Story 4: Adaptive Enrichment Frequency

**As a** enrichment service
**I want to** enrich elevated-risk vessels more frequently than green vessels
**So that** changes in vessel behaviour are detected faster for suspicious vessels

**Acceptance Criteria:**

- GIVEN a green vessel WHEN the enrichment cycle runs THEN it is enriched on the standard 6-hour cycle
- GIVEN a yellow vessel WHEN the enrichment cycle runs THEN it is enriched every 2 hours
- GIVEN a red vessel WHEN the enrichment cycle runs THEN it is enriched every 1 hour
- GIVEN the enrichment runner queries vessels to enrich WHEN building the batch THEN it prioritises by risk tier: red first, then yellow, then green
- GIVEN the enrichment rate limit WHEN many vessels need enrichment THEN red/yellow vessels are guaranteed to be enriched even if green vessels are deferred

**Test Requirements:**

- [ ] Test: Green vessel enriched 4 hours ago → not in next batch (< 6h)
- [ ] Test: Yellow vessel enriched 3 hours ago → in next batch (> 2h threshold)
- [ ] Test: Red vessel enriched 90 minutes ago → in next batch (> 1h threshold)
- [ ] Test: Batch ordering: red vessels before yellow before green
- [ ] Test: Rate-limited scenario: 100 green, 5 yellow, 1 red → red + yellow enriched first
- [ ] Test: Frequency thresholds are configurable in config.yaml

**Technical Notes:**

- Update `services/enrichment/runner.py` to check vessel risk_tier when building batches
- Modify the Redis `heimdal:enriched` tracking to include risk_tier at enrichment time
- New config:
  ```yaml
  enrichment:
    frequency:
      green_hours: 6
      yellow_hours: 2
      red_hours: 1
    priority_order: ["red", "yellow", "green"]
  ```
- The runner currently enriches ALL vessels in batch. Change to: query vessels ordered by risk_tier DESC, then by last_enriched ASC
- Enrichment intervals: `SELECT mmsi, risk_tier FROM vessel_profiles WHERE risk_tier = 'red' AND (enriched_at IS NULL OR enriched_at < NOW() - INTERVAL '1 hour') ORDER BY enriched_at ASC LIMIT 50`
- May need to add `enriched_at` column to vessel_profiles or track in Redis with the enrichment timestamp + tier info

---

### Story 5: Enrichment Status in Vessel Profile

**As a** system
**I want to** track what enrichment data has been gathered for each vessel
**So that** scoring rules know what data is available and analysts can see enrichment coverage

**Acceptance Criteria:**

- GIVEN a vessel has been enriched WHEN the enrichment completes THEN `vessel_profiles.enrichment_status` JSONB is updated with: `{last_enriched, enrichment_sources, data_coverage}` where data_coverage lists which data types are available
- GIVEN enrichment_status WHEN the vessel detail panel requests data THEN data_coverage shows: `{gfw_events: true, sar_detections: true, sanctions: true, ownership: true, classification: false, insurance: false}`
- GIVEN a yellow vessel WHEN enrichment runs but ownership data is unavailable THEN data_coverage shows `ownership: false` and scoring rules treat this as "unknown" (itself a risk indicator)
- GIVEN the enrichment runner WHEN logging cycle completion THEN include enrichment coverage statistics: "85% of yellow vessels have ownership data, 12% have insurance data"

**Test Requirements:**

- [ ] Test: Enrichment completion updates enrichment_status with correct sources
- [ ] Test: Data coverage correctly reflects which data types are present
- [ ] Test: Missing data types show as false in coverage
- [ ] Test: Enrichment statistics logged correctly
- [ ] Test: API returns enrichment_status in vessel detail response

**Technical Notes:**

- Add `enrichment_status JSONB` column to vessel_profiles (migration `008_enrichment_columns.sql`)
- Enrichment status structure:
  ```json
  {
    "last_enriched": "2026-03-13T...",
    "enrichment_sources": ["gfw_events", "gfw_sar", "gfw_identity", "opensanctions"],
    "data_coverage": {
      "gfw_events": true,
      "sar_detections": true,
      "sanctions": true,
      "ownership": true,
      "classification": false,
      "insurance": false,
      "port_state_control": false
    },
    "tier_at_enrichment": "yellow"
  }
  ```
- Update enrichment runner to write this after each vessel's enrichment completes

---

## Technical Design

### Data Model Changes

**New migration `008_enrichment_columns.sql`:**
```sql
ALTER TABLE vessel_profiles ADD COLUMN classification_data JSONB;
ALTER TABLE vessel_profiles ADD COLUMN insurance_data JSONB;
ALTER TABLE vessel_profiles ADD COLUMN enrichment_status JSONB;
ALTER TABLE vessel_profiles ADD COLUMN enriched_at TIMESTAMPTZ;

CREATE INDEX idx_vessel_profiles_enrichment ON vessel_profiles (risk_tier, enriched_at);
```

### API Changes

- Vessel detail endpoint already returns all `vessel_profiles` columns — new JSONB columns will appear automatically
- Health endpoint enrichment service status will now include enrichment queue depth

### Dependencies

- Scoring engine (for tier change events via Redis pub/sub)
- GFW API (for enhanced vessel identity data)
- Existing enrichment pipeline (extended, not replaced)

### Security Considerations

- Ownership data may contain PII (company names, jurisdictions) — ensure logs don't include full ownership chains
- Insurance data should be treated as confidential

---

## Implementation Order

### Group 1 (parallel — no dependencies)
- Story 1 — Tier-change triggered enrichment (`services/enrichment/runner.py`, `services/enrichment/main.py`)
- Story 3 — Insurance/classification enrichment (`services/enrichment/vessel_fetcher.py`, migration `008`)

### Group 2 (parallel — after Group 1)
- Story 2 — Enhanced ownership enrichment (`services/enrichment/vessel_fetcher.py`)
- Story 4 — Adaptive enrichment frequency (`services/enrichment/runner.py`, `config.yaml`)

### Group 3 (sequential — after Group 2)
- Story 5 — Enrichment status tracking (`services/enrichment/runner.py`, `shared/models/`, API)

**Parallel safety rules:**
- Group 1: Story 1 touches runner.py/main.py, Story 3 touches vessel_fetcher.py + migration
- Group 2: Story 2 touches vessel_fetcher.py (different section than Story 3), Story 4 touches runner.py
- Group 3: Story 5 depends on all previous stories to know what data to track

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
- [ ] Ready for human review
