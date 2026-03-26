# Feature Spec: Paris MoU Data Pipeline

**Slug:** `paris-mou-pipeline`
**Created:** 2026-03-26
**Status:** completed
**Priority:** high
**Depends on:** 39-local-dev-bootstrap (for testing locally)

---

## Overview

Build a complete pipeline for Paris MoU (THETIS) inspection data: XML parser, database schema, historical batch ingest (runs locally on MacBook), and incremental update service (runs on VPS weekly). Paris MoU data provides critical scoring signals: inspection recency, P&I provider identification, classification society at inspection time, ISM company fleet groupings, detention history, and deficiency patterns.

The Paris MoU DES (Data Exchange Service) API is already tested — `scripts/test_paris_mou.py` demonstrates authentication and file download. A sample XML file exists in `data/paris_mou/`. Research on deficiency codes and scoring indicators is complete in `.state/research/paris-mou-psc-shadow-fleet-indicators.md`.

## Problem Statement

The graph scoring spec (spec 42) requires Paris MoU signals (A1-A11) for vessel risk scoring. Currently no Paris MoU data is stored in the database. The XML data is available but unparsed. The scoring engine cannot evaluate inspection recency, P&I status, ISM fleet risk, or class transitions without this data.

## Out of Scope

- NOT: Scoring logic itself (spec 42 handles scoring rules that consume this data)
- NOT: OpenSanctions or IACS pipeline changes
- NOT: Frontend display of PSC inspection details (future spec)
- NOT: Real-time alerts on new inspections

---

## Data Source Verification

**Confirmed available in Paris MoU XML** (verified against downloaded `GetPublicFile_20260325_0345.xml`):

| Field | Present | XML Path |
|-------|---------|----------|
| IMO number | Yes | `<ImoNumber>` |
| Ship name | Yes | `<ShipName>` |
| Flag state | Yes | `<FlagStateCode>` |
| Ship type | Yes | `<ShipType>` or `<DetailedShipType>` |
| Gross tonnage | Yes | `<GrossTonnage>` |
| Keel-laid date | Yes | `<KeelLaidDate>` |
| Classification society (RO) | Yes | Within certificate records |
| ISM company (DOC holder) | Yes | `<IsmCompany>` with IMO number |
| P&I / insurance certificates | Yes | Certificate records (CLC 01133, Bunker 01137) |
| Inspection date | Yes | `<InspectionDate>` |
| Inspection port / country | Yes | `<PortOfInspection>`, `<PortCountryCode>` |
| Deficiency codes | Yes | `<DeficiencyCode>` per deficiency |
| Deficiency count | Derived | Count of deficiency elements |
| ISM deficiencies | Yes | Deficiency codes in 01100 range |
| Detention | Yes | `<Detained>` boolean |
| Action taken | Yes | `<ActionTakenCode>` per deficiency |

**Not in XML but needed:**
- Paris MoU black/grey/white flag list — this is a published classification, not per-inspection data. Hardcode as a reference table and update periodically.

---

## User Stories

### Story 1: Database Schema for PSC Inspections

**As a** system
**I want to** store Paris MoU inspection data in structured tables
**So that** the scoring engine can query inspection history by vessel

**Acceptance Criteria:**

- GIVEN a new migration WHEN applied THEN table `psc_inspections` exists with columns: id, imo (integer), ship_name, flag_state (varchar 2), ship_type, gross_tonnage (integer), keel_laid_date (date), inspection_date (date), inspection_port, port_country (varchar 2), detained (boolean), deficiency_count (integer), ism_deficiency (boolean), ro_at_inspection (text), pi_provider_at_inspection (text), pi_is_ig_member (boolean), ism_company_imo (varchar 16), ism_company_name (text), raw_data (jsonb), created_at (timestamptz)
- GIVEN the migration WHEN applied THEN table `psc_deficiencies` exists with columns: id, inspection_id (FK to psc_inspections), deficiency_code (varchar 16), nature_of_defect (varchar 16), action_taken (varchar 16), description (text)
- GIVEN the migration WHEN applied THEN table `psc_certificates` exists with columns: id, inspection_id (FK to psc_inspections), certificate_type (varchar 16), issuing_authority (text), expiry_date (date), certificate_number (text)
- GIVEN the migration WHEN applied THEN reference table `psc_flag_performance` exists with columns: iso_code (varchar 2, PK), list_status (varchar 8) — values: 'white', 'grey', 'black', year (integer)
- GIVEN the tables WHEN indexed THEN psc_inspections has indexes on: (imo, inspection_date DESC), (ism_company_imo), (flag_state), (detained) WHERE detained = TRUE
- GIVEN the tables WHEN seed data runs THEN psc_flag_performance is populated with current Paris MoU white/grey/black list assignments

**Test Requirements:**

- [ ] Test: Migration creates all four tables with correct columns and types
- [ ] Test: Foreign key from psc_deficiencies to psc_inspections works
- [ ] Test: Indexes exist on imo+inspection_date, ism_company_imo
- [ ] Test: psc_flag_performance is populated with data for at least 50 flag states

**Technical Notes:**

- Migration file: `db/migrations/024_psc_inspections.sql`
- The `ro_at_inspection` is the classification society name as recorded in certificates
- `pi_provider_at_inspection` is extracted from CLC (01133) or Bunker Convention (01137) certificates
- `pi_is_ig_member` is derived by matching pi_provider_at_inspection against a known list of IG P&I clubs
- Store raw_data JSONB for the full inspection record — useful for debugging and future field extraction

---

### Story 2: Paris MoU XML Parser

**As a** system
**I want to** parse Paris MoU THETIS XML files into structured Python objects
**So that** inspection records can be loaded into the database

**Acceptance Criteria:**

- GIVEN a Paris MoU XML file WHEN parsed THEN each `<Inspection>` element produces a structured dict with: imo, ship_name, flag_state, ship_type, gross_tonnage, keel_laid_date, inspection_date, inspection_port, port_country, detained, deficiencies (list), certificates (list), ism_company_imo, ism_company_name
- GIVEN an inspection with deficiency elements WHEN parsed THEN each deficiency includes: code, nature_of_defect, action_taken, description
- GIVEN an inspection with certificate elements WHEN parsed THEN each certificate includes: type, issuing_authority, expiry_date — and the parser identifies which certificate is P&I (CLC/Bunker convention) and which is the RO certificate
- GIVEN a CLC or Bunker Convention certificate WHEN the issuing authority is parsed THEN the parser derives `pi_is_ig_member` by checking against the IG P&I club list
- GIVEN a classification certificate WHEN parsed THEN `ro_at_inspection` is extracted
- GIVEN the parser WHEN run on the sample file `data/paris_mou/GetPublicFile_20260325_0345.xml` THEN it parses without errors and produces valid records
- GIVEN malformed or incomplete inspection records WHEN parsed THEN the parser logs warnings and skips invalid records rather than crashing

**Test Requirements:**

- [ ] Test: Parser extracts correct IMO, ship name, flag from a known inspection record
- [ ] Test: Parser extracts deficiency codes and counts from an inspection with deficiencies
- [ ] Test: Parser identifies P&I provider from CLC certificate
- [ ] Test: Parser identifies RO from classification certificate
- [ ] Test: Parser derives pi_is_ig_member correctly for a known IG club (e.g., Gard, Skuld)
- [ ] Test: Parser handles inspection record missing optional fields without crashing
- [ ] Test: Parser processes the full sample XML file and produces >0 valid records

**Technical Notes:**

- Use `lxml.etree` for XML parsing — it handles large files efficiently with iterparse
- XML namespace: `urn:getPublicInspections.xmlData.business.thetis.emsa.europa.eu`
- IG P&I club list (13 members): Britannia, Gard, Japan P&I, London, NorthStandard (merger of North and Standard), Shipowners, Skuld, Steamship Mutual, Swedish Club, UK P&I, West P&I, American Club, MS Amlin (associate). Store as a constant.
- Location: `services/paris-mou/parser.py` or `shared/parsers/paris_mou.py`

---

### Story 3: Historical Batch Ingest (Local)

**As a** developer
**I want to** download and ingest all historical Paris MoU XML data (2016-present) on my local machine
**So that** the graph can be bootstrapped with full inspection history

**Acceptance Criteria:**

- GIVEN a batch ingest script WHEN run locally THEN it authenticates with the Paris MoU DES API using PARIS_MOU_KEY from .env
- GIVEN authentication WHEN successful THEN the script lists all available GetPublicFile archives and downloads them to `data/paris_mou/`
- GIVEN downloaded XML files WHEN the ingest runs THEN each file is parsed and all inspections are inserted into psc_inspections, psc_deficiencies, and psc_certificates tables
- GIVEN duplicate inspections (same IMO + same inspection_date + same port) WHEN ingested THEN the system upserts rather than duplicating
- GIVEN the full historical ingest WHEN complete THEN it logs: total files processed, total inspections inserted, total deficiencies, total certificates, elapsed time
- GIVEN the script WHEN run with `--dry-run` THEN it lists available files and estimated record counts without writing to the database

**Test Requirements:**

- [ ] Test: Script authenticates successfully with valid API key
- [ ] Test: Script downloads at least one XML file
- [ ] Test: Ingested records have valid IMO numbers and inspection dates
- [ ] Test: Running ingest twice does not create duplicate inspection records
- [ ] Test: --dry-run flag does not modify the database

**Technical Notes:**

- Script location: `scripts/ingest_paris_mou.py`
- Reuse authentication logic from `scripts/test_paris_mou.py`
- Batch insert for performance — use `executemany` or COPY
- The DES API returns daily files — there may be hundreds of files to download for 2016-present
- Store downloaded files in `data/paris_mou/` so they don't need to be re-downloaded
- This runs LOCALLY on the MacBook, not on the VPS

---

### Story 4: Incremental Update Service (VPS)

**As a** system operator
**I want to** automatically fetch new Paris MoU inspection data weekly
**So that** the graph stays current without manual intervention

**Acceptance Criteria:**

- GIVEN a weekly cron job WHEN it runs THEN it authenticates with Paris MoU DES and downloads any new GetPublicFile files since the last download
- GIVEN new XML files WHEN downloaded THEN they are parsed and new inspections are upserted into the database
- GIVEN the update service WHEN it completes THEN it logs: files checked, new files found, inspections added/updated
- GIVEN the service WHEN no new files are available THEN it completes silently without errors
- GIVEN the update service WHEN configured in docker-compose THEN it runs as a scheduled job (not an always-on service)

**Test Requirements:**

- [ ] Test: Service identifies which files have already been downloaded
- [ ] Test: Service only downloads and processes new files
- [ ] Test: Service handles API authentication failures gracefully (retry with backoff)

**Technical Notes:**

- Track downloaded files in a metadata table or a local state file
- Run as part of the batch-pipeline cron or as a separate weekly job
- Same parser as story 2 — reuse the module

---

## Implementation Order

1. Story 1 (DB schema) — foundation
2. Story 2 (XML parser) — independent of DB but needed for stories 3-4
3. Story 3 (historical batch ingest) — depends on 1+2, runs locally
4. Story 4 (incremental updates) — depends on 1+2, runs on VPS

Stories 1 and 2 can run in parallel. Stories 3 and 4 are sequential after 1+2.

## Architecture Decisions

- **No changes to AIS tables or ingest** — per project constraint
- **IMO is the join key** — Paris MoU data joins to vessel_profiles via IMO number
- **Raw JSONB preserved** — full XML inspection data stored for future field extraction
- **IG P&I club list as constant** — not a database table; changes rarely (once per decade)
- **Historical batch runs locally** — too compute-heavy for VPS; incremental updates are lightweight
