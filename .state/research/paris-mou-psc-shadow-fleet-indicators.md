# Paris MoU PSC Data: Shadow Fleet Indicators Research

**Date:** 2026-03-25
**Purpose:** Identify which Paris MoU PSC deficiency codes, inspection patterns, and data fields are the strongest indicators of shadow fleet operations and insurance compliance failures. Directly informs the `psc_compliance` scoring rule in spec 39.

---

## 1. Deficiency Code Structure

### How Deficiency Codes Work

Each Paris MoU deficiency has two components recorded in THETIS:

1. **Defective Item Code** (e.g. `01133`) — identifies WHAT is deficient. This is a 5-digit code organized by area. The reference table has columns: Code, Description, Area, Area Code, Detainable (boolean), RO Related (boolean), Restricted, EU Legislation.

2. **Nature of Defect Code** — identifies HOW it is deficient. Standard values include:
   - Missing
   - Invalid
   - Expired
   - Withdrawn
   - Not as required
   - Not properly filled/maintained
   - Entries missing
   - Incomplete
   - Survey out of window

A single deficiency is the combination of both: e.g. `DefectiveItemCode=01133` + `NatureOfDefectCode=Expired` means "Civil Liability for Oil Pollution Damage Certificate — Expired."

### Additional Boolean Flags Per Deficiency

From our actual data, each deficiency also carries:
- `isGroundDetention` — boolean, if true, this specific deficiency was serious enough to be grounds for detention
- `isRORelated` — boolean, indicates the deficiency relates to the Recognized Organization (classification society) that issued the certificate
- `isAccidentalDamage` — boolean, indicates damage from an incident rather than neglect

### Area Code Categories

The defective item codes are grouped by area. The key areas for shadow fleet detection:

| Area Code | Area Name | Shadow Fleet Relevance |
|-----------|-----------|----------------------|
| 011 | Certificate & Documentation - Ship Certificates | **CRITICAL** — insurance certs, DOC/SMC, class certs |
| 012 | Certificate & Documentation - Crew Certificates | Moderate — crew certification gaps |
| 013 | Certificate & Documentation - Documents | Moderate — missing docs |
| 014 | Certificate & Documentation - Ship's Log | Low |
| 07 | Fire Safety | Moderate — maintenance neglect indicator |
| 09 | Safety of Navigation | Moderate |
| 10 | Life-Saving Appliances | Moderate |
| 15 | ISM | **HIGH** — safety management system failures |

---

## 2. Insurance-Related Deficiency Codes (Area 011)

These are the highest-value shadow fleet indicators in Paris MoU data. They serve as the "back door" into P&I coverage status.

### Key Certificate Defective Item Codes

| Code | Description | Detainable | Shadow Fleet Signal |
|------|-------------|-----------|-------------------|
| 01101 | Cargo Ship Safety Equipment Cert | Yes | Moderate — general cert gap |
| 01102 | Cargo Ship Safety Construction Cert | Yes | Moderate |
| 01103 | Passenger Ship Safety Cert | Yes | Low for tankers |
| 01104 | Cargo Ship Safety Radio Cert | Yes | Moderate |
| 01105 | Cargo Ship Safety Cert | Yes | Moderate |
| **01106** | **Document of Compliance (DOC/ISM)** | **Yes** | **HIGH — ISM company identity** |
| **01107** | **Safety Management Certificate (SMC/ISM)** | **Yes** | **HIGH — vessel ISM compliance** |
| 01108 | Load Lines Cert | Yes | Moderate |
| 01111 | Liquefied Gases in Bulk (CoF/GC Code) | Yes | Tanker-specific |
| 01112 | Liquefied Gases in Bulk (ICoF/IGC Code) | Yes | Tanker-specific |
| 01113 | Minimum Safe Manning Document | Yes | Moderate |
| 01114 | Dangerous Chemicals in Bulk (CoF/BCH Code) | Yes | Tanker-specific |
| 01115 | Dangerous Chemicals in Bulk (ICoF/IBC Code) | Yes | Tanker-specific |
| 01117 | International Oil Pollution Prevention (IOPP) | Yes | High for tankers |
| **01133** | **Civil Liability for Oil Pollution Damage Cert (CLC)** | **Yes** | **CRITICAL — P&I insurance proof** |
| **01137** | **Civil Liability for Bunker Oil Pollution Damage Cert** | **Yes** | **CRITICAL — bunker insurance proof** |
| 01131 | International Anti-fouling System Certificate | Yes | Low |
| 01136 | Ballast Water Management Certificate | Yes | Moderate |

### Insurance Certificate Codes — The Crown Jewels

The following codes directly reveal insurance/financial security status:

**01133 — CLC Certificate (Civil Liability for Oil Pollution Damage)**
- Required for tankers carrying >2,000 tonnes of persistent oil as cargo
- Issued by the P&I insurer (as a "Blue Card") to the flag state, which issues the certificate
- A deficiency here means: the vessel's CLC certificate is missing, expired, invalid, or from a non-recognized insurer
- Nature of Defect "Expired" or "Missing" = strong shadow fleet signal (insurer dropped coverage or vessel changed hands without proper reinsurance)
- Nature of Defect "Not as required" = possible non-IG insurer, unrecognized coverage
- **Always detainable** — a vessel without valid CLC cannot legally sail

**01137 — Bunkers Convention Certificate**
- Required for ALL vessels over 1,000 GT (not just tankers)
- Also issued via P&I insurer Blue Card pathway
- Shadow fleet vessels carrying Russian oil products (not crude) may have valid CLC but invalid bunkers coverage
- Same interpretation as 01133 for deficiency nature

**How PSC inspectors record insurance problems:**
- "Missing" nature of defect = no certificate on board at all (strongest signal — likely no insurance)
- "Expired" = certificate date has passed (insurer dropped coverage or didn't renew)
- "Not as required" / "Invalid" = certificate exists but doesn't meet requirements (could be non-recognized insurer, wrong vessel details, or forged)
- "Withdrawn" = certificate was actively revoked (insurer explicitly pulled coverage — very strong signal)

### Wreck Removal Convention Certificate

Code for wreck removal convention certificate (Nairobi Convention) — introduced more recently. Should be in the 011xx range in the latest code list. Same Blue Card/P&I pathway. Required for vessels >300 GT in states party to the convention.

### How to Identify Insurance Codes in Reference Data

The reference table's `data` JSONB or description field can be searched for:
- Descriptions containing "Civil Liability", "insurance", "financial security"
- Codes 01133, 01137, and any wreck removal certificate code
- Area code 011 with descriptions containing "liability" or "pollution damage"

---

## 3. ISM Deficiency Codes — Safety Management Deterioration

### ISM Code Structure in PSC

The ISM (International Safety Management) Code requires every vessel to have:
- A **Document of Compliance (DOC)** — issued to the COMPANY (the ISM management company)
- A **Safety Management Certificate (SMC)** — issued to the VESSEL

### Key ISM Defective Item Codes

| Code | Description | Significance |
|------|-------------|-------------|
| **01106** | Document of Compliance (DOC/ISM) | Company-level ISM — missing DOC means ISM company may have lost certification |
| **01107** | Safety Management Certificate (SMC/ISM) | Vessel-level ISM — missing SMC is detainable |
| **15150** | ISM (general deficiency marker) | Catch-all ISM code — used for operational ISM failures |
| 15111 | Company verification, review and evaluation | ISM company procedures inadequate |
| 15112 | Certification, verification and control | ISM certification process failures |
| 15199 | Other ISM | Miscellaneous ISM issues |

### ISM Deficiency Weighting

Paris MoU treats ISM deficiencies with **5x weight** compared to technical deficiencies when calculating company performance. This means:
- 1 ISM deficiency = 5 technical deficiency points in the company performance formula
- A vessel with many ISM deficiencies will push its management company toward "Very Low" performance rating

### ISM Company IMO — The Ownership Chain Signal

The `ism_company_imo` field in inspection records identifies the ISM management company by its unique IMO company number. This is extremely valuable:

- **Legitimate vessel sale:** ISM company IMO changes once (old manager → new manager), with clean handover and continued certification
- **Shadow fleet transition:** ISM company IMO may change to a newly created company (founded recently, small fleet, based in India/UAE/Turkey), or to a company with "Very Low" Paris MoU performance rating
- **DOC withdrawal cascade:** When a DOC is withdrawn from a company, ALL vessels under that company lose their SMCs simultaneously. This can appear as a sudden wave of ISM deficiencies across a fleet

### Shadow Fleet ISM Patterns

1. **ISM company change to a recently formed entity**: Companies like Maritas Fleet PVT LTD (founded December 2022 in Mumbai, quickly took on 29 tankers) are characteristic ISM managers for shadow fleet vessels
2. **ISM company country shift**: Manager moves from an EU/UK country to India, UAE, Turkey, or similar
3. **Multiple ISM deficiencies in short period**: After ISM company change, first inspections under new management reveal systemic gaps
4. **Defective item 15150 marked as ISM**: A deficiency on ANY technical item can be additionally flagged with ISM code 15150, indicating systemic safety management failure rather than isolated equipment issue
5. **Action code 19 or 21**: Action 19 = "Safety management audit by the Administration required before departure" (most severe ISM action). Action 21 = "Corrective action on ISM system within 3 months"

---

## 4. Paris MoU Flag State Performance Lists (Black/Grey/White)

### 2024 Performance Data (valid 1 July 2025 — 30 June 2026)

**69 flags total:** 40 White, 17 Grey, 12 Black

Based on 3-year rolling detention rates vs statistical limits.

### Black List Flags (shadow fleet relevant)

| Flag | Risk Level | Inspections (3yr) | Detentions (3yr) | Shadow Fleet Role |
|------|-----------|-------------------|-------------------|-------------------|
| **Cameroon** | Very High Risk | 144 | 43 (~30%) | **2nd largest shadow fleet registry**, 13% of sanctioned tankers, 120+ sanctioned vessels |
| **Tanzania** | Very High Risk | 149 | 41 (~28%) | Emerging shadow fleet flag |
| **Moldova** | Very High Risk | 32 | 10 (~31%) | Small but problematic |
| **Vietnam** | Very High Risk | 43 | 12 (~28%) | Primarily cargo, some shadow fleet |
| **Comoros** | High Risk | 258 | 48 (~19%) | Major shadow fleet flag, EU sanctioned its registry operator |
| **Sierra Leone** | On black list | — | — | Known shadow fleet flag |
| **Togo** | On black/grey | — | — | Used by shadow fleet |
| **Palau** | On black/grey | — | — | Registry contractor blacklisted by US for Iran tanker services |
| **Equatorial Guinea** | On black/grey | — | — | Minimal oversight |

**Contrast with white list top performers:**
- France: 297 inspections, 1 detention (~0.3%)
- Denmark: 1,246 inspections, 14 detentions (~1.1%)
- Norway: 1,824 inspections, 23 detentions (~1.3%)

### Flag Transition Patterns

The shadow fleet flag progression typically follows:
1. Major registry (Liberia, Marshall Islands, Panama) — vessel sold to opaque new owner
2. Intermediate "stepping stone" flag (St Kitts & Nevis, Gabon, Cook Islands, Barbados) — Western pressure forces de-flagging
3. Final shadow fleet flag (Cameroon, Comoros, Palau, Sierra Leone, Tanzania, Gambia) — minimal oversight, no verification of beneficial ownership

Since 2022:
- Comoros and Gambia deleted 130+ tankers after pressure
- Palau dismissed its registry contractor
- Gabon registry operator sanctioned by EU
- Cameroon remains non-compliant despite pledges

### How Flag Performance Maps to Your Data

In your Paris MoU inspection data, the `flag` field on each inspection record contains the vessel's flag at time of inspection. Cross-reference with the flag performance list:
- **Black list flag + tanker + age >15 years = very strong shadow fleet indicator**
- **Flag change from white→grey→black in inspection history = classic transition pattern**
- The flag performance list itself is available as a Paris MoU background table

---

## 5. Recognized Organization (Classification Society) Performance

### How Class is Recorded in PSC

In Paris MoU inspection data:
- **IssuingAuthority** on `StatutoryCertificate` records = the entity that issued the certificate, identified by a numeric code
- **IssuingAuthorityType** = "RO" (Recognized Organization) or "Flag" (flag state administration)
- **ClassCertificate** records have their own `IssuingAuthority` = the classification society
- **ClassStatus** = "DELIVERED" (class certificate is in effect)

### IACS Members (legitimate class societies)

| Society | Country | Paris MoU Performance |
|---------|---------|----------------------|
| ABS | USA | Top performer (6,438 inspections, 2 detentions) |
| DNV | Norway/Germany | Top performer (23,476 inspections, 36 detentions) |
| Lloyd's Register | UK | Top performer (12,071 inspections, 30 detentions) |
| Bureau Veritas | France | High performer |
| RINA | Italy | High performer |
| ClassNK | Japan | High performer |
| CCS | China | Recently improved ranking |
| Korean Register | South Korea | Good performer |
| Indian Register (IRS) | India | Lower performer — acts as RO for some shadow fleet vessels |
| Russian Maritime Register (RS) | Russia | Sanctioned, acts as class for Russian shadow fleet |
| PRS | Poland | Small, good performer |
| CRS | Croatia | Small, good performer |

### Class Withdrawal Detection

**In PSC certificate records, class withdrawal manifests as:**
1. **Missing class certificate** on inspection — vessel appears with no ClassCertificate records or ClassStatus not "DELIVERED"
2. **Change of IssuingAuthority** between inspections — e.g., from DNV (high performer) to Indian Register or an unknown entity
3. **Statutory certificates issued by Flag rather than RO** — when a vessel loses its RO, the flag state may directly issue certificates, appearing as IssuingAuthorityType="Flag" where previously it was "RO"
4. **isRORelated deficiency flag = true** — deficiencies specifically attributed to the classification society's failure to maintain standards

### Shadow Fleet Class Patterns

1. **Drop from IACS member to non-IACS class**: Vessel moves from DNV/LR/BV to a smaller or non-IACS society. In PSC data, this appears as changed IssuingAuthority codes on certificates
2. **Class suspension visible via DNV tracker**: DNV publishes real-time class suspensions at classsuspensions.dnv.com. Other IACS members have similar
3. **P&I link**: P&I club rules require vessel to remain "in class" with an approved society. Changing to an unapproved class = P&I coverage ceases immediately without notice
4. **Timeline**: Class withdrawal typically follows flag change by weeks to months

---

## 6. Insurance Gaps — Quantitative Data

### KSE Institute Research (February 2025)

The Kyiv School of Economics published detailed analysis of shadow fleet insurance:

**Global tanker fleet insurance coverage:**
- 36.5% of the global tanker fleet lacks public insurance records
- 63.5% have identifiable coverage, of which 91% are with IG (International Group) P&I clubs

**Russian oil tanker fleet specifically:**
- Only 29.4% of tankers carrying Russian crude oil have IG P&I insurance
- 56.2% of tankers carrying Russian oil products have IG coverage
- Among 4,539 tankers with no ties to price cap coalition countries, only 6.3% have known P&I providers
- For shadow fleet vessels carrying Russian oil, only 16.9% have identifiable insurance

**Vessel characteristics of non-IG insured vessels:**
- Average age: 18.1 years (vs 14.4 years for IG-insured)
- 64.2% operate under grey-listed, black-listed, or unranked flags

**Russian insurers filling the gap:**
- Ingosstrakh — sanctioned by US and UK, major shadow fleet insurer, no transparency on coverage
- AlfaStrakhovanie — sanctioned by EU, US, and UK
- Russian P&I insurers disclose coverage for only 220 tankers total
- These insurers operate outside the IG framework and lack reinsurance backing for major claims

### What This Means for PSC Data

When a vessel's P&I insurer is Ingosstrakh or similar Russian entity:
- The CLC certificate (01133) may appear "valid" but issued by an insurer that wouldn't actually pay claims
- The Bunkers Convention certificate (01137) similarly may be formally present but substantively worthless
- PSC inspectors may record this as "not as required" rather than "missing" — the certificate exists but the insurer isn't recognized
- Some flag states (especially Cameroon, Comoros) may issue certificates based on Blue Cards from non-IG insurers without verification

---

## 7. Paris MoU Targeting System (NIR — New Inspection Regime)

### Ship Risk Profile (SRP)

Every vessel in THETIS gets a daily-recalculated risk profile: **High Risk**, **Standard Risk**, or **Low Risk**.

### Generic Parameters (vessel characteristics)

| Parameter | HRS Criteria | LRS Criteria |
|-----------|-------------|-------------|
| Ship Type | Oil tanker, chemical tanker, gas carrier, bulk carrier, passenger ship = "risk ship types" | Any type acceptable |
| Age | >12 years = higher risk | Newer vessels preferred |
| Flag | Black/Grey list = negative factor | White list required |
| Recognized Organization | Non-EU recognized or poor performing RO = negative | EU-recognized, high-performing RO |
| Company Performance | "Very Low" or "Low" = negative factor | "High" performance required |

### Historic Parameters (inspection history, 36-month rolling window)

| Parameter | HRS Criteria | LRS Criteria |
|-----------|-------------|-------------|
| Deficiencies | High deficiency count | <5 deficiencies in window |
| Detentions | Any detention = major negative | No detentions in window |
| ISM Deficiencies | ISM deficiencies weighted 5x | No ISM deficiencies |

### Inspection Intervals

- **High Risk Ship**: Must be inspected every 5-6 months
- **Standard Risk Ship**: Every 10-12 months
- **Low Risk Ship**: Every 24-36 months

### What This Means for Shadow Fleet

Shadow fleet vessels accumulate HRS factors rapidly:
- Old tanker (>12 years, often >20 years) = risk ship type + age
- Black/grey list flag = negative flag factor
- Non-IACS or poor-performing class society = negative RO factor
- New/unknown ISM company = likely "Very Low" or unrated performance
- Previous deficiencies/detentions = negative historic factors

**Result**: Shadow fleet vessels that enter Paris MoU ports get classified as HRS and inspected every 5-6 months. This creates a feedback loop — more inspections = more deficiencies found = more detentions = higher risk profile.

**Counter-tactic**: Shadow fleet vessels avoid Paris MoU ports entirely, trading instead in non-MoU jurisdictions (India, China, Turkey, UAE). This means: **absence of recent Paris MoU inspection for a vessel that previously had them is itself a signal**.

### Company Performance Calculation

Uses a matrix of two indices:

**Deficiency Index** = (Total deficiency points for company fleet / Total inspections) compared to Paris MoU average
- ISM deficiencies weighted at 5 points each
- Technical deficiencies weighted at 1 point each
- "Above Average" = company ratio 2+ points above MoU average
- "Below Average" = company ratio 2+ points below MoU average

**Detention Index** = (Total detentions for company fleet / Total inspections) compared to Paris MoU average
- "Above Average" = company ratio 2% above MoU average
- If a refusal of access has been issued = automatically "Above Average"

**Performance Matrix:**

| Detention Index | Deficiency Index | Performance |
|----------------|-----------------|-------------|
| Above Average | Above Average | **Very Low** |
| Above Average | Average | **Low** |
| Above Average | Below Average | Average |
| Average | Above Average | Average |
| Average | Average | **Medium** |
| Average | Below Average | Below Average |
| Below Average | Below Average | **High** |

Companies with no prior inspection records: assigned **Medium** by default.

---

## 8. Temporal Patterns — Shadow Fleet Transition Timeline

### The Classic Transition Sequence

Based on research across multiple sources, the typical shadow fleet transition follows this pattern over 6-18 months:

**Phase 1: Ownership Change (Month 0)**
- Vessel sold from established owner to shell company (typically registered in UAE, India, or secrecy jurisdiction)
- Name change common but not always
- IMO number stays the same (critical for tracking)

**Phase 2: Flag Change (Month 0-2)**
- Flag changes from mainstream registry (Liberia, Marshall Islands, Panama) to stepping-stone registry
- Then often to shadow fleet flag (Cameroon, Comoros, etc.)
- In PSC data: `flag` field changes between inspections

**Phase 3: Class Society Change (Month 1-3)**
- Class withdraws or is transferred from IACS member to non-IACS or Indian Register/Russian Register
- P&I coverage ceases automatically when class moves to unapproved society
- In PSC data: `IssuingAuthority` on ClassCertificate changes; `isRORelated` deficiencies may appear

**Phase 4: ISM Company Change (Month 1-4)**
- ISM management transfers to newly formed company (often Mumbai, Dubai, or Istanbul based)
- DOC issued by new flag state or RO
- In PSC data: `ism_company_imo` and `ism_company_name` change

**Phase 5: Insurance Gap (Month 2-6)**
- P&I coverage lapses or switches to Russian/non-IG insurer
- CLC and Bunkers Convention certificates may expire without renewal
- In PSC data: deficiencies on codes 01133 and 01137

**Phase 6: PSC Deficiency Accumulation (Month 6-18)**
- If vessel still calls at Paris MoU ports, deficiency count increases
- ISM deficiencies (15150) appear
- Safety equipment, navigation, fire safety deficiencies accumulate
- `deficiency_trend` = "increasing"

**Phase 7: Detention / Port Avoidance (Month 12+)**
- Vessel detained on PSC inspection, or
- Vessel stops calling at Paris MoU ports entirely (avoidance strategy)
- In PSC data: no new inspections despite vessel being active on AIS

### Distinguishing Legitimate Sale from Shadow Fleet Transition

| Signal | Legitimate Sale | Shadow Fleet Transition |
|--------|----------------|----------------------|
| Flag change | May change, stays on white list | Changes to grey/black list |
| Class society | Stays with IACS member | Moves to non-IACS or Indian/Russian register |
| ISM company | Established company, good track record | New company (<2 years old), unknown track record |
| P&I insurance | Continues with IG club | Drops to unknown/Russian insurer |
| PSC deficiencies after sale | Stable or improving | Increasing |
| AIS behavior | Normal routing | AIS gaps, STS transfers, sanctioned port calls |
| Vessel age at sale | Any age | Typically >15 years |
| Sale price indicators | Market rate | Below market (distressed sale to opaque buyer) |

### Key Temporal Signals in PSC Data

1. **No inspection for >12 months** for a vessel previously inspected every 6-12 months = possible port avoidance
2. **Flag change + class change within same 6-month window** = strong transition indicator
3. **ISM company IMO changes + insurance deficiency within 12 months** = very strong indicator
4. **Deficiency count doubling** between successive inspection periods = deteriorating management
5. **First-ever detention** after years of clean record = something changed fundamentally

---

## 9. Mapping to Your Data Fields

### From Your Actual Paris MoU Data Structure

**Inspection-level fields and their shadow fleet relevance:**

| Field | Shadow Fleet Use |
|-------|-----------------|
| `imo` | Primary key for tracking vessel across inspections |
| `flag` | Track flag changes over time; cross-reference with black/grey/white list |
| `ship_type` | Oil tanker, chemical tanker, gas carrier = risk ship types |
| `keel_date` | Calculate vessel age; >15 years + tanker = baseline risk |
| `ism_company_imo` | Track ISM company changes; new/recently created companies are suspicious |
| `ism_company_name` | Human-readable company identity |
| `ism_company_country` | Country shift (EU→India/UAE/Turkey) is a transition signal |
| `inspection_type` | EXPANDED_INSPECTION on a vessel = it's already flagged as high risk by Paris MoU |
| `detention` (JSONB) | Type + DurationOfDetention; >5 days = serious |
| `reporting_authority` | Which port inspected; useful for geographic pattern analysis |

**Deficiency-level fields:**

| Field | Shadow Fleet Use |
|-------|-----------------|
| `defective_item_code` | The WHAT — cross-reference with reference table for area and description |
| `nature_of_defect_code` | The HOW — "Missing", "Expired", "Withdrawn" on insurance certs = critical |
| `is_ground_detention` | This specific deficiency could have caused detention = severity marker |
| `is_ro_related` | Deficiency attributed to classification society = class standards failing |
| `is_accidental_damage` | Filter out — not a management/compliance failure |

**Certificate-level fields:**

| Field | Shadow Fleet Use |
|-------|-----------------|
| `certificate_type` | "statutory" vs "class" — both matter differently |
| `certificate_code` | Cross-reference with reference table |
| `issuing_authority` | Numeric code for the RO or flag state; track changes across inspections |
| `issuing_authority_type` | "RO" → "Flag" transition may indicate class loss |
| `date_of_issue` / `date_of_expiry` | Gap between expiry and next issue = coverage gap |
| `class_status` | "DELIVERED" = active; anything else = problem |

### Derived Signals for Scoring

Based on this research, the `psc_compliance` scoring rule should detect these patterns:

**Tier 1 — Direct Insurance/Certificate Evidence (20-30 points):**
- Deficiency on code 01133 (CLC) or 01137 (Bunkers) with nature "Missing", "Expired", or "Withdrawn"
- Deficiency on code 01106 (DOC) or 01107 (SMC) with nature "Missing" or "Withdrawn"
- Any wreck removal convention certificate deficiency

**Tier 2 — Detention and Serious Deficiencies (15-30 points):**
- Any detention, especially >5 days duration
- 3+ deficiencies with `isGroundDetention = true` in 3 years
- Detention on expanded inspection (vessel was already targeted as high risk)

**Tier 3 — Trajectory/Pattern Evidence (8-15 points):**
- Deficiency trend "increasing" (recent 18 months > prior 18 months)
- >25 deficiencies in 3 years
- ISM company IMO changed between inspections
- Flag changed between inspections (especially white→grey/black direction)
- IssuingAuthority changed on class certificates

**Tier 4 — Contextual Amplifiers (5-10 points):**
- Inspection type is EXPANDED_INSPECTION (Paris MoU already considers this vessel high risk)
- Flag on Paris MoU black list
- `isRORelated` deficiencies (class society not maintaining standards)
- Vessel age >15 years + tanker type

---

## 10. Specific Scoring Rule Recommendations

### Insurance Deficiency Code Detection

For the `psc_compliance` rule, identify insurance-related codes by querying `psc_reference_tables`:

```sql
-- Find insurance/certificate deficiency codes from reference data
SELECT code, description
FROM psc_reference_tables
WHERE table_name = 'defective_item'
AND (
    description ILIKE '%civil liability%'
    OR description ILIKE '%insurance%'
    OR description ILIKE '%financial security%'
    OR description ILIKE '%bunker%pollution%'
    OR description ILIKE '%wreck removal%'
    OR code IN ('01133', '01137')  -- known insurance codes as fallback
);
```

### ISM Company Change Detection

```sql
-- Detect ISM company changes for a vessel
SELECT DISTINCT ON (imo)
    i1.imo,
    i1.ism_company_imo AS current_company,
    i1.ism_company_name AS current_name,
    i2.ism_company_imo AS previous_company,
    i2.ism_company_name AS previous_name,
    i1.date_of_first_visit AS change_detected
FROM psc_inspections i1
JOIN psc_inspections i2 ON i1.imo = i2.imo
    AND i2.date_of_first_visit < i1.date_of_first_visit
WHERE i1.ism_company_imo != i2.ism_company_imo
ORDER BY i1.imo, i1.date_of_first_visit DESC;
```

### Flag Change Detection

```sql
-- Detect flag changes between inspections
SELECT
    i1.imo,
    i2.flag AS old_flag,
    i1.flag AS new_flag,
    i1.date_of_first_visit AS change_detected
FROM psc_inspections i1
JOIN psc_inspections i2 ON i1.imo = i2.imo
    AND i2.date_of_first_visit < i1.date_of_first_visit
WHERE i1.flag != i2.flag
ORDER BY i1.date_of_first_visit DESC;
```

---

## Sources

- [Paris MoU Deficiency Codes (official)](https://parismou.org/sites/default/files/List%20of%20Paris%20MoU%20deficiency%20codes%20on%20public%20website.pdf)
- [Paris MoU Deficiency Code Overview July 2024](https://maritime.public.lu/dam-assets/fsi/paris-mou-overview-of-deficiency-codes-01-july-2024.pdf)
- [Paris MoU Ship Risk Profile](https://parismou.org/PMoU-Procedures/Library/ship-risk-profile)
- [Paris MoU 2024 Flag Performance Lists](https://parismou.org/2025/07/2024-performance-lists-paris-mou)
- [Paris MoU Black List 2024](https://parismou.org/system/files/2025-06/Paris%20MoU%20Black%20List%202024.pdf)
- [Paris MoU Guidelines on ISM Code (2023)](https://safety4sea.com/wp-content/uploads/2023/07/Paris-MoU-Guidelines-on-the-ISM-Code_2023_07.pdf)
- [EMSA THETIS Company Performance](https://portal.emsa.europa.eu/web/thetis/company-performance-legal-information)
- [Paris MoU Company Performance Calculator](https://parismou.org/PMoU-Procedures/company-performance-calculator)
- [KSE Institute: Oil Spill Insurance and the Shadow Fleet (Feb 2025)](https://kse.ua/about-the-school/news/oil-spill-insurance-and-the-shadow-fleet-kse-institute-reveals-insurance-gaps-in-the-global-tanker-fleet-including-vessels-transporting-russian-oil/)
- [CHIRP Maritime: How to Identify the Shadow Fleet](https://safety4sea.com/chirp-maritime-how-to-identify-the-shadow-fleet/)
- [Windward: Cameroon Pledges Crackdown (13% of Dark Fleet)](https://windward.ai/blog/cameroon-pledges-crackdown-on-ship-registry-flagging-13-of-dark-fleet-tankers/)
- [RUSI: Countering Shadow Fleet via Flag State Reform](https://www.rusi.org/explore-our-research/publications/insights-papers/countering-shadow-fleet-activity-through-flag-state-reform)
- [Atlantic Council: Threats from the Global Shadow Fleet](https://www.atlanticcouncil.org/in-depth-research-reports/report/the-threats-posed-by-the-global-shadow-fleet-and-how-to-stop-it/)
- [SAFETY4SEA: PSC Deficiency Code Ranking and Spread](https://safety4sea.com/cm-psc-focus-deficiency-code-ranking-and-spread/)
- [West P&I: Paris MoU New Inspection Regime](https://www.westpandi.com/news-and-resources/news/port-state-control-paris-mou-new-inspection-regime/)
- [EU Sanctions Operator of Comoros and Gabon Flag Registries](https://maritime-executive.com/article/eu-sanctions-operator-of-the-comoros-and-gabon-flag-registries)
- [Comoros De-flags Shadow Fleet Vessels](https://safety4sea.com/comoros-de-flags-vessels-linked-to-shadow-fleet-activity/)
- [Who's Insuring Russia's Shadow Fleet](https://www.reinsurancene.ws/whos-insuring-russias-shadow-fleet/)
- [Paris MoU 2024 Annual Report Press Release](https://parismou.org/system/files/2025-06/Paris%20MoU%20-%20Press%20release%202024%20Annual%20Report%20(including%20performance%20lists)_1.pdf)
