# Feature Spec: Enhanced Detection Rules

**Slug:** `enhanced-detection-rules`
**Created:** 2026-03-13
**Status:** draft
**Priority:** high

---

## Overview

Add new scoring rules based on real-world shadow fleet intelligence from CREA, Windward, Kpler, S&P Global, and Lloyd's List. These rules target the specific patterns that distinguish shadow fleet tankers from legitimate vessels: AIS spoofing patterns, ownership obfuscation, insurance/classification gaps, and voyage pattern analysis. Also adds new STS hotspots and rebalances existing rule weights based on industry data.

## Problem Statement

The current 14 rules cover basic behavioural patterns but miss several high-confidence indicators used by professional maritime intelligence platforms:

1. **AIS spoofing goes undetected** — the system catches AIS gaps but not position spoofing (circle spoofing, anchor spoofing, slow-roll spoofing), which is the fastest-growing evasion tactic (52% increase in 2024, 212 incidents in May 2025 alone per Kpler).
2. **Ownership risk is unchecked** — enrichment fetches ownership data but no rule scores it. Single-vessel shell companies, recently incorporated entities, and high-risk jurisdictions (UAE, Turkey) are strong indicators (OFAC 2024 guidance).
3. **Insurance/classification gaps are invisible** — 82% of confirmed shadow fleet vessels lack IG P&I coverage (S&P Global). Non-IACS classification has DPI of 5.66 vs 1.78 for IACS.
4. **STS hotspots are incomplete** — only 6 AOIs monitored. Missing the South China Sea (largest dark fleet gathering point, 350M barrels in 9 months), Gulf of Oman, Singapore Strait approaches, and Baltic bunkering hubs.
5. **Voyage pattern analysis is absent** — Russian port → STS hotspot → India/China/Turkey is the canonical shadow fleet route, but no rule tracks multi-leg voyage patterns.
6. **Rule weights don't reflect evidence** — `speed_anomaly` cap of 15 points is too high for what's often legitimate behaviour, while `vessel_age` cap of 40 doesn't reflect that 93% of shadow fleet is >15 years old.

## Out of Scope

- NOT: Satellite imagery verification (SAR is handled by GFW integration)
- NOT: Real-time AIS spoofing detection via ML models (start with heuristic detection)
- NOT: Scraping external ownership databases (use enrichment data already collected)
- NOT: Changing the rule framework architecture (that's spec 17)
- NOT: Payment/financial flow analysis

---

## User Stories

### Story 1: AIS Position Spoofing Detection Rule

**As a** maritime analyst
**I want to** detect vessels broadcasting false positions
**So that** I can identify vessels trying to hide their true location during illicit activities

**Acceptance Criteria:**

- GIVEN consecutive positions with a distance > 500 nm in < 1 hour WHEN evaluating THEN fire `ais_spoofing` with severity=critical (impossible speed indicates position jump)
- GIVEN a vessel reporting positions forming a near-perfect circle (variance < 0.01 degrees) for > 24 hours WHEN evaluating THEN fire `ais_spoofing` with reason=circle_spoofing
- GIVEN a vessel reporting positions that haven't changed by > 0.001 degrees for > 48 hours BUT nav_status is "underway" WHEN evaluating THEN fire `ais_spoofing` with reason=anchor_spoofing
- GIVEN a vessel reporting unrealistically slow movement (< 0.5 knots sustained but not anchored/moored) with no position variance for > 12 hours WHEN evaluating THEN fire `ais_spoofing` with reason=slow_roll_spoofing
- GIVEN a spoofing detection WHEN scored THEN severity=critical, points=30

**Test Requirements:**

- [ ] Test: Position jump of 1000 nm in 30 minutes → critical spoofing alert
- [ ] Test: Circle pattern with 8 positions over 24h forming a circle → circle spoofing detected
- [ ] Test: Stationary "underway" vessel for 48h → anchor spoofing detected
- [ ] Test: Vessel genuinely at anchor with nav_status "at anchor" → NOT flagged
- [ ] Test: Vessel with GPS drift (< 0.01 nm variation) → NOT flagged (normal noise)
- [ ] Test: Slow-roll with 0.3 knots and zero heading change for 12h → flagged

**Technical Notes:**

- New file: `services/scoring/rules/ais_spoofing.py`
- Position jump detection: calculate great-circle distance between consecutive positions, flag if implied speed > 50 knots
- Circle detection: compute centroid of recent positions, check if all positions within 0.01 degrees of centroid while vessel claims to be underway
- Anchor spoofing: stationary positions + "underway" nav_status
- `MAX_PER_RULE['ais_spoofing'] = 100` (critical indicator)
- Add to `constants.py` ALL_RULE_IDS

---

### Story 2: Ownership Risk Scoring Rule

**As a** maritime analyst
**I want to** score vessels based on their ownership structure
**So that** shell company patterns and opaque ownership trigger appropriate risk levels

**Acceptance Criteria:**

- GIVEN a vessel owned by a single-vessel company WHEN evaluating THEN fire `ownership_risk` with reason=single_vessel_company, severity=moderate
- GIVEN ownership company incorporated < 2 years ago WHEN evaluating THEN fire with reason=recently_incorporated, severity=moderate
- GIVEN ownership in high-risk jurisdiction (Cameroon, Comoros, Gabon, Palau, Tanzania, Togo) AND vessel is a tanker WHEN evaluating THEN fire with reason=high_risk_jurisdiction, severity=high
- GIVEN > 1 ownership change in 12 months WHEN evaluating THEN fire with reason=frequent_ownership_changes, severity=high
- GIVEN no beneficial ownership information available WHEN evaluating THEN fire with reason=opaque_ownership, severity=moderate
- GIVEN combined ownership risk factors (2+) WHEN evaluating THEN severity escalates to critical

**Test Requirements:**

- [ ] Test: Single-vessel company owner → moderate ownership_risk
- [ ] Test: Company incorporated 6 months ago → moderate ownership_risk
- [ ] Test: Cameroon-registered owner for a tanker → high ownership_risk
- [ ] Test: 2 ownership changes in 8 months → high ownership_risk
- [ ] Test: No ownership data available → moderate ownership_risk
- [ ] Test: Single-vessel + recently incorporated + high-risk jurisdiction → critical
- [ ] Test: Normal vessel with established owner in Netherlands → no firing

**Technical Notes:**

- New file: `services/scoring/rules/ownership_risk.py`
- Reads from `vessel_profiles.ownership_data` JSONB (populated by enrichment)
- Ownership data structure: `{"ownership": [{"role": "owner", "name": "...", "country": "...", "incorporated": "..."}]}`
- High-risk ownership jurisdictions (from OFAC + Atlantic Council): `{"CM", "KM", "GA", "PW", "TZ", "TG", "GM", "SL"}`
- `MAX_PER_RULE['ownership_risk'] = 60`
- Need to add `fleet_size` and `incorporation_date` to enrichment data if not already present (check vessel_fetcher.py)

---

### Story 3: Insurance and Classification Risk Rule

**As a** maritime analyst
**I want to** score vessels based on their P&I insurance and classification society status
**So that** uninsured or improperly classified vessels (82% of shadow fleet) are flagged

**Acceptance Criteria:**

- GIVEN a vessel with no IG P&I coverage AND ship_type is tanker WHEN evaluating THEN fire `insurance_class_risk` with reason=no_ig_insurance, severity=high
- GIVEN a vessel classed by a non-IACS society WHEN evaluating THEN fire with reason=non_iacs_class, severity=moderate
- GIVEN a vessel with no classification at all WHEN evaluating THEN fire with reason=unclassed, severity=critical
- GIVEN a vessel that changed classification society in the last 12 months WHEN evaluating THEN fire with reason=recent_class_change, severity=moderate
- GIVEN a vessel classed by Russian Maritime Register WHEN evaluating THEN fire with reason=russian_register, severity=high
- GIVEN combined insurance + classification risk (2+) WHEN scoring THEN severity escalates

**Test Requirements:**

- [ ] Test: Tanker without IG P&I → high insurance_class_risk
- [ ] Test: Vessel classed by unknown non-IACS society → moderate
- [ ] Test: Unclassed vessel → critical
- [ ] Test: Class changed from DNV to Russian Register 3 months ago → high
- [ ] Test: Properly insured vessel with Lloyd's Register classification → no firing
- [ ] Test: Non-tanker without IG P&I → moderate (not high — P&I gap less significant for non-tankers)

**Technical Notes:**

- New file: `services/scoring/rules/insurance_class_risk.py`
- Reads from `vessel_profiles` — need to check if enrichment populates P&I and classification data
- If not populated by enrichment yet, this rule will only fire when manual enrichment provides the data (via spec 12's enrichment form which already has classification + P&I fields)
- IACS members list: `{"ABS", "BV", "CCS", "CRS", "DNV", "IRS", "KR", "LR", "NK", "PRS", "RINA", "RS"}`
- `MAX_PER_RULE['insurance_class_risk'] = 60`
- Russian Maritime Register code: `"RS"` (note: RS is in IACS, so flag specifically for Russian Register, not non-IACS)

---

### Story 4: Voyage Pattern Analysis Rule

**As a** maritime analyst
**I want to** detect canonical shadow fleet voyage patterns
**So that** vessels following known sanctions-evasion routes are flagged

**Acceptance Criteria:**

- GIVEN a vessel visited a Russian port AND then visited an STS hotspot within 30 days WHEN evaluating THEN fire `voyage_pattern` with reason=russian_port_to_sts, severity=high
- GIVEN a vessel visited an STS hotspot AND then has a destination of India/China/Turkey WHEN evaluating THEN fire with reason=sts_to_destination, severity=moderate
- GIVEN a vessel completed the full chain (Russian port → STS → India/China/Turkey) WHEN evaluating THEN fire with reason=full_evasion_route, severity=critical
- GIVEN a vessel is on a ballast voyage to an STS hotspot with no documented commercial reason WHEN evaluating THEN fire with reason=suspicious_ballast, severity=moderate

**Test Requirements:**

- [ ] Test: Vessel with gfw_port_visit to Novorossiysk + position in Kalamata STS zone → high
- [ ] Test: Vessel in Laconian Gulf STS zone + destination "SIKKA" (India) → moderate
- [ ] Test: Full chain: Primorsk → Ceuta STS → Jamnagar → critical
- [ ] Test: Vessel transiting through STS zone at high speed (not loitering) → NOT flagged
- [ ] Test: Vessel with legitimate Mediterranean trade (Rotterdam → Piraeus) → NOT flagged
- [ ] Test: Ballast vessel headed to STS hotspot from open ocean → moderate

**Technical Notes:**

- New file: `services/scoring/rules/voyage_pattern.py`
- Uses GFW port_visit events from `gfw_events` table + current position + destination field
- Russian ports list already exists in seed data (7 terminals)
- India/China/Turkey destination keywords: `{"SIKKA", "JAMNAGAR", "PARADIP", "VADINAR", "MUMBAI", "CHENNAI", "QINGDAO", "RIZHAO", "DONGYING", "ZHOUSHAN", "NINGBO", "ISKENDERUN", "MERSIN", "ALIAGA", "DORTYOL"}`
- Ballast detection: low draught + heading toward STS zone + no cargo manifest
- `MAX_PER_RULE['voyage_pattern'] = 80`

---

### Story 5: Extended STS Hotspot Coverage

**As a** system
**I want to** monitor additional STS transfer hotspots
**So that** dark fleet activity in the South China Sea, Gulf of Oman, and other known hotspots is detected

**Acceptance Criteria:**

- GIVEN new STS hotspot AOIs added to config WHEN enrichment fetches SAR detections THEN the new AOIs are included in GFW queries
- GIVEN new STS zone polygons added to seed data WHEN sts_proximity evaluates THEN the new zones are checked
- GIVEN a vessel loitering in the South China Sea STS area WHEN evaluated THEN `sts_proximity` fires correctly
- New hotspots include at minimum:
  - South China Sea (east of Malaysian peninsula, ~104.5°E 2.5°N)
  - Gulf of Oman (~57°E 25°N)
  - Singapore Strait approaches (~104°E 1.2°N)
  - Alboran Sea (~-3.5°W 36°N)
  - Baltic/Primorsk approaches (~28°E 60°N)
  - South of Crete (~25°E 34.5°N)

**Test Requirements:**

- [ ] Test: config.yaml contains all new AOIs with valid coordinates
- [ ] Test: STS zone seed data includes all new zones
- [ ] Test: sts_proximity correctly evaluates vessel in South China Sea hotspot
- [ ] Test: enrichment SAR fetcher queries all AOIs including new ones
- [ ] Test: zone_helpers.is_in_sts_zone works for new zones

**Technical Notes:**

- Update `config.yaml` gfw.aois section with new AOIs
- Update `db/migrations/004_seed_data.sql` or add new migration `007_new_sts_zones.sql` with additional zones
- Coordinates sourced from Kpler, Bloomberg, and Marine Insight reporting on shadow fleet gathering points
- The South China Sea zone should be larger than the Mediterranean ones (activity area spans ~100km)

---

### Story 6: Rule Weight Rebalancing

**As a** scoring engine
**I want to** rebalance rule weights and caps based on real-world evidence
**So that** the risk score accurately reflects the likelihood of illicit activity

**Acceptance Criteria:**

- GIVEN the existing rules WHEN caps are rebalanced THEN `speed_anomaly` MAX_PER_RULE drops from 15 to 10 (high false-positive rate near ports)
- GIVEN the existing rules WHEN caps are rebalanced THEN `vessel_age` gets progressive scoring: 15-19 years = 5 points (low), 20-24 years = 15 points (moderate), 25+ years = 25 points (high)
- GIVEN the existing rules WHEN caps are rebalanced THEN `flag_of_convenience` gets two tiers: standard FoC flags = 5 points (low), known fraudulent registries (Cameroon, Comoros, Palau, Gabon, Tanzania, Gambia, Malawi, Sierra Leone) = 20 points (high)
- GIVEN new rules added (ais_spoofing, ownership_risk, insurance_class_risk, voyage_pattern) WHEN MAX_PER_RULE is updated THEN new rules have appropriate caps
- GIVEN all rule changes WHEN existing tests run THEN test expected values are updated to match

**Test Requirements:**

- [ ] Test: speed_anomaly cap is 10 (changed from 15)
- [ ] Test: vessel_age progressive scoring: 18-year tanker = 5, 22-year tanker = 15, 27-year tanker = 25
- [ ] Test: Cameroon flag = 20 points, Panama flag = 5 points, Norway flag = 0 points
- [ ] Test: New rules have correct MAX_PER_RULE entries
- [ ] Test: Aggregate score correctly uses updated caps
- [ ] Test: Tier thresholds still produce reasonable distribution (most vessels green, suspicious ones yellow, bad ones red)

**Technical Notes:**

- Update `shared/constants.py` MAX_PER_RULE dict
- Update `services/scoring/rules/vessel_age.py` for progressive scoring
- Update `services/scoring/rules/flag_of_convenience.py` for two-tier system
- New MAX_PER_RULE entries:
  ```python
  "ais_spoofing": 100,
  "ownership_risk": 60,
  "insurance_class_risk": 60,
  "voyage_pattern": 80,
  ```
- Known fraudulent registries (separate from SHADOW_FLEET_FLAGS):
  ```python
  FRAUDULENT_REGISTRY_FLAGS = {"CM", "KM", "PW", "GA", "TZ", "GM", "MW", "SL"}
  ```
- Add `SHADOW_FLEET_DESTINATIONS` constant for Indian/Chinese/Turkish refinery port names

---

## Technical Design

### Data Model Changes

- No new tables required (all rules read existing data)
- New migration `007_new_sts_zones.sql` for additional STS zones
- Update `constants.py` with new rule IDs, MAX_PER_RULE entries, and new constants

### API Changes

- No API changes — new rules automatically appear in anomaly responses
- `/api/anomalies` will include new rule_ids in results

### Dependencies

- Spec 17 (event-scoring-model) for event lifecycle support — but new rules can work without it initially
- Enrichment data for ownership and insurance rules (existing enrichment pipeline)
- GFW API for extended STS hotspot SAR data

### Security Considerations

None — all data is already in the system from existing enrichment.

---

## Implementation Order

### Group 1 (parallel — no dependencies)
- Story 1 — AIS spoofing rule (`services/scoring/rules/ais_spoofing.py`)
- Story 2 — Ownership risk rule (`services/scoring/rules/ownership_risk.py`)
- Story 3 — Insurance/classification rule (`services/scoring/rules/insurance_class_risk.py`)

### Group 2 (parallel — no dependencies between them)
- Story 4 — Voyage pattern rule (`services/scoring/rules/voyage_pattern.py`)
- Story 5 — Extended STS hotspots (`config.yaml`, `db/migrations/`, `zone_helpers.py`)

### Group 3 (sequential — after all new rules exist)
- Story 6 — Rule weight rebalancing (`shared/constants.py`, update existing rule files, update tests)

**Parallel safety rules:**
- Group 1: Each rule is a separate file
- Group 2: Voyage pattern is a new rule file; STS hotspots touch config/migrations
- Group 3: Must come last as it touches constants.py and existing rule files

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
