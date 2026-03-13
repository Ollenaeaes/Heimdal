# Feature Spec: Equasis Ship Folder PDF Upload

**Slug:** `equasis-upload`
**Created:** 2026-03-13
**Status:** completed
**Priority:** high
**Wave:** 10 (Equasis Integration)

---

## Overview

Allow operators to upload Equasis Ship Folder PDFs through the frontend. The system parses the PDF server-side, validates IMO/MMSI against the target vessel, extracts all structured data (ship particulars, management chain, classification, PSC inspections, flag history, name history, company history, safety certificates), stores the extracted data in the database, displays it in an expandable vessel information section, and feeds it into anomaly detection scoring rules.

## Problem Statement

Equasis is the richest source of vessel registry data (ownership chains, flag history, PSC inspections, classification changes) but prohibits automated scraping. Operators manually research flagged vessels on Equasis and currently can only enter a handful of fields via the manual enrichment form. The full Equasis Ship Folder PDF contains 20+ years of structured history that is critical for investigation and anomaly detection — but there's no way to get it into the system efficiently. Operators need to upload the PDF and have the system extract everything automatically.

## Out of Scope

- NOT: Automated Equasis scraping or API integration (ToS prohibits it)
- NOT: Parsing PDFs from other sources (Paris MoU, Tokyo MoU, corporate registries) — future specs
- NOT: OCR or scanned document handling — Equasis PDFs are text-based
- NOT: Multi-vessel batch upload (one PDF = one vessel)
- NOT: PDF storage — only extracted structured data is persisted

---

## User Stories

### Story 1: Database Schema — Equasis Data Table

**As a** system
**I want to** store structured Equasis data linked to vessel profiles
**So that** scoring rules and the frontend can access rich vessel history

**Acceptance Criteria:**

- GIVEN a new migration WHEN applied THEN creates an `equasis_data` table with columns: `id` (SERIAL PK), `mmsi` (INTEGER FK to vessel_profiles), `imo` (INTEGER), `upload_timestamp` (TIMESTAMPTZ DEFAULT NOW()), `edition_date` (DATE — from the PDF footer), `ship_particulars` (JSONB), `management` (JSONB), `classification_status` (JSONB), `classification_surveys` (JSONB), `safety_certificates` (JSONB), `psc_inspections` (JSONB), `name_history` (JSONB), `flag_history` (JSONB), `company_history` (JSONB), `raw_extracted` (JSONB — full extraction for debugging)
- GIVEN a vessel with existing equasis_data WHEN a new PDF is uploaded THEN a new row is inserted (keeping history of uploads), and the latest row is used for display/scoring
- GIVEN a successful equasis upload WHEN scoring reads the vessel THEN `vessel_profiles` fields are updated: `registered_owner`, `technical_manager`, `operator`, `class_society`, `build_year`, `dwt`, `gross_tonnage`, `flag_country`, `ship_name`, `call_sign`, `ship_type_text`, `length`, `width`

**Test Requirements:**

- [ ] Test: Migration creates equasis_data table with all columns and correct types
- [ ] Test: FK constraint to vessel_profiles.mmsi works (insert succeeds for existing vessel, fails for non-existent)
- [ ] Test: Multiple uploads for same vessel create separate rows ordered by upload_timestamp
- [ ] Test: vessel_profiles fields are updated from equasis data on upload

**Technical Notes:**

Migration file: `db/migrations/009_equasis_data.sql`. JSONB columns allow flexible storage while remaining queryable. The `raw_extracted` column stores the complete parser output for debugging without affecting the structured columns.

---

### Story 2: PDF Parser — Extract Structured Data from Equasis Ship Folder

**As a** system
**I want to** parse an Equasis Ship Folder PDF into structured data
**So that** all vessel information can be stored and used programmatically

**Acceptance Criteria:**

- GIVEN a valid Equasis Ship Folder PDF WHEN parsed THEN extracts Ship Particulars: IMO, name, call sign, MMSI, gross tonnage, DWT, type of ship, year of build, flag, status, last update date
- GIVEN a valid PDF WHEN parsed THEN extracts Management Detail: list of entries with company IMO, role (ISM Manager, Ship manager/Commercial manager, Registered owner), company name, address, date of effect
- GIVEN a valid PDF WHEN parsed THEN extracts Classification Status: list of entries with society name, date of status change, status (Delivered/Withdrawn), reason
- GIVEN a valid PDF WHEN parsed THEN extracts Classification Surveys: list of entries with society name, date of survey, date of next survey
- GIVEN a valid PDF WHEN parsed THEN extracts Safety Management Certificates: list of entries with society, date of survey, date of expiry, date of status, status, reason, type
- GIVEN a valid PDF WHEN parsed THEN extracts PSC Inspections: list of entries with authority (country), port, date, detention (Y/N), PSC organisation, type of inspection, duration (days), number of deficiencies
- GIVEN a valid PDF WHEN parsed THEN extracts Human Element Deficiencies: list of entries with PSC org, authority, port, date, count
- GIVEN a valid PDF WHEN parsed THEN extracts Ship History — Former Names: list of entries with name, date of effect, source
- GIVEN a valid PDF WHEN parsed THEN extracts Ship History — Former Flags: list of entries with flag, date of effect, source
- GIVEN a valid PDF WHEN parsed THEN extracts Company History: list of entries with company name, role, date of effect, sources
- GIVEN a valid PDF WHEN parsed THEN extracts the edition date from the PDF footer (e.g. "Edition date 13/03/2026")
- GIVEN an invalid or non-Equasis PDF WHEN parsed THEN returns a clear error message

**Test Requirements:**

- [ ] Test: Parse the sample ShipFop.pdf (BLUE, IMO 9236353) and verify all 8 sections extracted with correct field counts
- [ ] Test: Ship particulars — IMO=9236353, MMSI=613414602, name=BLUE, GT=84789, DWT=165293, type=Crude Oil Tanker, build=2003, flag=Cameroon
- [ ] Test: Management — 3 entries (ISM Manager UNKNOWN, Ship manager CRESTWAVE MARITIME LTD, Registered owner CRESTWAVE MARITIME LTD)
- [ ] Test: Classification status — 2 entries (Russian Maritime Register Delivered, RINA Withdrawn with reason)
- [ ] Test: PSC inspections — 30+ entries with correct fields, detention in Istanbul 28/12/2023 with 12 deficiencies
- [ ] Test: Flag history — 14+ entries spanning Cameroon to Greece
- [ ] Test: Name history — 7 entries (BLUE, Julia A, Azul, Icaria, Iskmati Spirit, Arlene, Aegean Eagle)
- [ ] Test: Company history — 15+ entries spanning CRESTWAVE to ARCADIA
- [ ] Test: Edition date extracted correctly
- [ ] Test: Non-Equasis PDF returns error
- [ ] Test: Corrupted/empty PDF returns error

**Technical Notes:**

Use `pdfplumber` (Python) for text extraction — it handles table detection well for structured PDFs. Parser lives in `services/api-server/equasis_parser.py`. The Equasis Ship Folder has a consistent structure: sections are marked by headers ("Ship informations", "Ship inspections", "Ship history"), data lives in tables with known column headers. Parse strategy: extract all text, identify section boundaries by headers, parse tables within each section. Copy `data/equasis-data/ShipFop.pdf` to `services/api-server/tests/fixtures/` for test use.

---

### Story 3: API Endpoint — Upload and Process Equasis PDF

**As an** operator
**I want to** upload an Equasis PDF via API and have it validated and stored
**So that** the vessel is enriched with the extracted data

**Acceptance Criteria:**

- GIVEN `POST /api/equasis/upload` with a PDF file and optional `mmsi` query param WHEN the PDF is valid Equasis format THEN extract data, validate IMO/MMSI, store in equasis_data table, update vessel_profiles, trigger re-scoring, return extracted data summary
- GIVEN upload with `mmsi` param WHEN the PDF's IMO or MMSI matches the vessel_profiles row for that MMSI THEN accept the upload
- GIVEN upload with `mmsi` param WHEN neither IMO nor MMSI from the PDF matches THEN reject with 422 and message "IMO/MMSI mismatch: PDF contains IMO {x} / MMSI {y} but vessel {mmsi} has IMO {a} / MMSI {b}"
- GIVEN upload WITHOUT `mmsi` param WHEN the PDF's MMSI exists in vessel_profiles THEN enrich that existing vessel
- GIVEN upload WITHOUT `mmsi` param WHEN the PDF's MMSI does NOT exist in vessel_profiles THEN create a new vessel_profiles row from the PDF data, insert equasis_data, return the new vessel with `created: true`
- GIVEN upload WHEN vessel_profiles is updated THEN fields are set: registered_owner (from Management → Registered owner), technical_manager (from Management → ISM Manager), operator (from Management → Ship manager), class_society (from current Classification Status entry), build_year, dwt, gross_tonnage, flag_country, ship_name, call_sign, ship_type_text, length, width (from Ship Particulars where Equasis has the data)
- GIVEN upload WHEN vessel_profiles is updated THEN publish re-scoring event to Redis `heimdal:positions` channel
- GIVEN a non-PDF file or corrupt file WHEN uploaded THEN return 400 with "Invalid file: could not parse as PDF"
- GIVEN a PDF that is not an Equasis Ship Folder WHEN uploaded THEN return 422 with "Not an Equasis Ship Folder: missing expected sections"

**Test Requirements:**

- [ ] Test: Upload valid Equasis PDF with matching mmsi → 201, equasis_data row created, vessel_profiles updated, response contains extracted summary
- [ ] Test: Upload with mmsi mismatch → 422 with descriptive error
- [ ] Test: Upload without mmsi, existing vessel → enriches that vessel
- [ ] Test: Upload without mmsi, new vessel → creates vessel_profiles + equasis_data, response has `created: true`
- [ ] Test: Upload non-PDF → 400
- [ ] Test: Upload non-Equasis PDF → 422
- [ ] Test: vessel_profiles fields updated correctly (registered_owner, class_society, etc.)
- [ ] Test: Re-scoring event published to Redis after successful upload
- [ ] Test: Second upload for same vessel creates new equasis_data row (history preserved)

**Technical Notes:**

New route file: `services/api-server/routes/equasis.py`. Use FastAPI's `UploadFile` for multipart/form-data. Max file size: 5MB (Equasis PDFs are typically 30-50KB). Add `pdfplumber` to api-server requirements. The endpoint orchestrates: parse → validate → store equasis_data → update vessel_profiles → publish Redis → respond. Register router in `main.py`.

---

### Story 4: Frontend — Upload Button on Vessel Panel

**As an** operator viewing a vessel
**I want to** upload an Equasis PDF directly from the vessel panel
**So that** I can quickly enrich the vessel I'm investigating

**Acceptance Criteria:**

- GIVEN the vessel detail panel WHEN viewing any vessel THEN an "Upload Equasis PDF" button is visible in the enrichment section area
- GIVEN the button WHEN clicked THEN opens a native file picker filtered to `.pdf` files
- GIVEN a file selected WHEN uploading THEN shows a loading spinner on the button with "Parsing..."
- GIVEN a successful upload WHEN server responds THEN show success toast "Equasis data imported: {name} (IMO {imo}) — {n} PSC inspections, {n} flag changes, {n} companies extracted"
- GIVEN an IMO/MMSI mismatch WHEN server responds 422 THEN show error toast with the mismatch details from the API
- GIVEN any other error WHEN server responds THEN show error toast with the error message
- GIVEN a successful upload WHEN the panel refreshes THEN vessel profile data and the new Equasis section are visible
- GIVEN the upload WHEN complete THEN invalidate the vessel detail query to trigger a refetch

**Test Requirements:**

- [ ] Test: Upload button renders on vessel panel
- [ ] Test: File picker opens on click, accepts only .pdf
- [ ] Test: Loading state shows during upload
- [ ] Test: Successful upload shows success toast with extraction summary
- [ ] Test: Mismatch error shows descriptive toast
- [ ] Test: Query invalidation triggers after success

**Technical Notes:**

Add upload button to the existing enrichment section area in `VesselPanel.tsx` or `EnrichmentForm.tsx`. Use `fetch` with `FormData` (multipart/form-data). Pass `mmsi` as query param since the vessel is already selected. New file: `frontend/src/components/VesselPanel/EquasisUpload.tsx`.

---

### Story 5: Frontend — Standalone Upload Button for Any Vessel

**As an** operator
**I want to** upload an Equasis PDF for any vessel, including ones not yet tracked
**So that** I can add new vessels to the system from Equasis data

**Acceptance Criteria:**

- GIVEN the main toolbar/header WHEN looking at the controls THEN an "Import Equasis PDF" button is visible (distinct from the per-vessel upload)
- GIVEN the button WHEN clicked THEN opens a native file picker for `.pdf` files
- GIVEN a file selected WHEN uploading THEN calls `POST /api/equasis/upload` WITHOUT `mmsi` param
- GIVEN a successful upload for an existing vessel WHEN server responds THEN show success toast and auto-select the vessel on the globe (set selectedMmsi in Zustand store)
- GIVEN a successful upload for a NEW vessel WHEN server responds with `created: true` THEN show toast "New vessel added: {name} (IMO {imo})" and auto-select it
- GIVEN an error WHEN server responds THEN show error toast with message

**Test Requirements:**

- [ ] Test: Import button renders in header/toolbar area
- [ ] Test: Upload calls API without mmsi param
- [ ] Test: Success for existing vessel auto-selects it
- [ ] Test: Success for new vessel shows "New vessel added" and auto-selects
- [ ] Test: Error shows toast

**Technical Notes:**

Add button near the search bar in `frontend/src/components/Controls/`. New file: `frontend/src/components/Controls/EquasisImport.tsx`. On success, set `selectedMmsi` in the Zustand store to navigate to the vessel.

---

### Story 6: Frontend — Expanded Vessel Information Display

**As an** operator investigating a vessel
**I want to** see the full Equasis data in an expandable section
**So that** I have complete vessel history for my investigation

**Acceptance Criteria:**

- GIVEN a vessel with equasis_data WHEN viewing the vessel panel THEN show an "Equasis Data" section with a summary line: "Last uploaded: {date} — {edition_date} edition"
- GIVEN the Equasis Data section WHEN clicking "Expand vessel information" THEN reveal the full extracted data organized into collapsible subsections:
  - **Ship Particulars** — table with IMO, MMSI, name, GT, DWT, type, build year, flag, status
  - **Management** — table with role, company, address, date of effect (current entries highlighted)
  - **Classification** — status table + surveys table, withdrawn entries highlighted in amber/red
  - **Safety Certificates** — table with society, survey date, expiry, status, type
  - **PSC Inspections** — sortable table with all inspection fields, detentions highlighted in red, deficiency counts colored (0=green, 1-5=yellow, 6+=red)
  - **Name History** — chronological list with dates
  - **Flag History** — chronological list with dates, colored by flag-of-convenience status
  - **Company History** — chronological list with role, company, date
- GIVEN a vessel WITHOUT equasis_data WHEN viewing THEN show "No Equasis data — Upload a Ship Folder PDF to enrich this vessel" with upload prompt
- GIVEN multiple equasis uploads WHEN viewing THEN show the latest upload's data, with a "Previous uploads" dropdown to view older versions

**Test Requirements:**

- [ ] Test: Equasis section renders with summary when data exists
- [ ] Test: Expand button reveals all subsections
- [ ] Test: Each subsection renders correct data from API
- [ ] Test: PSC detention rows highlighted in red
- [ ] Test: Empty state renders upload prompt
- [ ] Test: Previous uploads dropdown works when multiple uploads exist

**Technical Notes:**

New component: `frontend/src/components/VesselPanel/EquasisSection.tsx` with sub-components for each data section. The API endpoint `GET /api/vessels/{mmsi}` needs to include the latest `equasis_data` in its response. Add `equasis_data` to the `VesselDetail` TypeScript interface. The expand/collapse state can be local React state. Flag-of-convenience list for color coding: use the existing list from the `flag_of_convenience` scoring rule constants.

---

### Story 7: API — Include Equasis Data in Vessel Detail Response

**As a** frontend consumer
**I want to** receive equasis data as part of the vessel detail API response
**So that** the vessel panel can display it without a separate API call

**Acceptance Criteria:**

- GIVEN `GET /api/vessels/{mmsi}` WHEN the vessel has equasis_data THEN the response includes an `equasis` object with: `latest` (the most recent upload's structured data), `upload_count` (total number of uploads), `uploads` (list of all uploads with id, upload_timestamp, edition_date for the previous uploads dropdown)
- GIVEN `GET /api/vessels/{mmsi}` WHEN the vessel has NO equasis_data THEN `equasis` is `null`
- GIVEN `GET /api/equasis/{mmsi}/history` WHEN called with a specific upload ID THEN return that upload's full structured data (for viewing previous uploads)

**Test Requirements:**

- [ ] Test: Vessel detail includes equasis.latest with all sections when data exists
- [ ] Test: Vessel detail has equasis=null when no data
- [ ] Test: equasis.upload_count matches actual upload count
- [ ] Test: History endpoint returns specific upload by ID

**Technical Notes:**

Extend the existing `GET /api/vessels/{mmsi}` handler in `routes/vessels.py` to join equasis_data. Add a lightweight history endpoint in `routes/equasis.py`. Only include the full structured data for the latest upload in the vessel detail response — previous uploads are fetched on demand via the history endpoint to keep the response size manageable.

---

### Story 8: Scoring Enhancement — PSC and Classification Risk from Equasis

**As a** scoring engine
**I want to** use Equasis PSC inspection and classification data for risk evaluation
**So that** vessels with poor inspection records or withdrawn classification are flagged

**Acceptance Criteria:**

- GIVEN a vessel with equasis PSC data WHEN scored by `insurance_class_risk` THEN add findings for:
  - Any detention in the last 3 years → high severity, 15 points per detention (capped at 2 detentions = 30 pts)
  - Total deficiencies > 10 in last 3 years → moderate severity, 8 points
  - Total deficiencies > 25 in last 3 years → high severity, 15 points
  - Classification withdrawn "by society" → critical severity, 25 points
  - Classification by Russian Maritime Register with IACS society withdrawn → high severity, 20 points
- GIVEN a vessel with equasis flag history WHEN scored by `flag_hopping` THEN use the Equasis flag history (with dates) instead of/in addition to MID-derived flags — Equasis data has actual dated flag changes which is more accurate
- GIVEN the equasis flag_history WHEN counting flags within the 12-month window THEN use the `date_of_effect` field for accurate windowing (not just "flag was seen")
- GIVEN a vessel with equasis data WHEN any scoring rule reads the profile THEN equasis-derived fields (class_society, registered_owner, etc.) are available on the vessel_profiles row

**Test Requirements:**

- [ ] Test: PSC detention in last 3 years triggers finding with correct severity/points
- [ ] Test: PSC detention older than 3 years does NOT trigger
- [ ] Test: Deficiency thresholds (>10 moderate, >25 high) work correctly
- [ ] Test: Classification withdrawn by society triggers critical finding
- [ ] Test: Russian Register + IACS withdrawn combo triggers high finding
- [ ] Test: Flag hopping rule uses equasis flag_history dates for windowing
- [ ] Test: Vessel with 14 flags in equasis history (like BLUE) triggers high severity flag_hopping
- [ ] Test: Points are capped per MAX_PER_RULE

**Technical Notes:**

Modify `services/scoring/rules/insurance_class_risk.py` to read equasis PSC and classification data from the vessel profile (loaded from equasis_data via a repository function). Modify `services/scoring/rules/flag_hopping.py` to prefer equasis flag_history when available. The scoring engine loads the vessel profile dict — add a repository function that merges equasis_data into the profile dict so rules can access it transparently. Add equasis data loading to `shared/db/repositories.py` (`get_latest_equasis_data`).

---

## Technical Design

### Data Model Changes

New table `equasis_data`:
```sql
CREATE TABLE IF NOT EXISTS equasis_data (
    id                      SERIAL PRIMARY KEY,
    mmsi                    INTEGER NOT NULL REFERENCES vessel_profiles(mmsi),
    imo                     INTEGER,
    upload_timestamp        TIMESTAMPTZ DEFAULT NOW(),
    edition_date            DATE,
    ship_particulars        JSONB DEFAULT '{}',
    management              JSONB DEFAULT '[]',
    classification_status   JSONB DEFAULT '[]',
    classification_surveys  JSONB DEFAULT '[]',
    safety_certificates     JSONB DEFAULT '[]',
    psc_inspections         JSONB DEFAULT '[]',
    name_history            JSONB DEFAULT '[]',
    flag_history            JSONB DEFAULT '[]',
    company_history         JSONB DEFAULT '[]',
    raw_extracted           JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_equasis_data_mmsi ON equasis_data(mmsi);
CREATE INDEX IF NOT EXISTS idx_equasis_data_mmsi_latest ON equasis_data(mmsi, upload_timestamp DESC);
```

### API Changes

New endpoints:
- `POST /api/equasis/upload` — multipart/form-data, accepts PDF file + optional `mmsi` query param
- `GET /api/equasis/{mmsi}/history` — list all uploads for a vessel
- `GET /api/equasis/{mmsi}/upload/{id}` — get a specific upload's data

Modified endpoints:
- `GET /api/vessels/{mmsi}` — now includes `equasis` object in response

### Dependencies

- `pdfplumber` — Python PDF parsing library (add to api-server requirements)
- Existing: FastAPI UploadFile, SQLAlchemy, Redis pub/sub

### Security Considerations

- File size limit: 5MB max (reject larger files before parsing)
- File type validation: check both Content-Type and magic bytes for PDF
- Input sanitization: parsed text values are stored as strings in JSONB, no SQL injection risk
- No PDF storage: the file is discarded after parsing, only structured data persists

---

## Implementation Order

### Group 1 (parallel — no dependencies)
- **Story 1** — DB migration `db/migrations/009_equasis_data.sql` + repository functions in `shared/db/repositories.py`
- **Story 2** — PDF parser `services/api-server/equasis_parser.py` + tests with sample PDF

### Group 2 (parallel — after Group 1)
- **Story 3** — API endpoint `services/api-server/routes/equasis.py` — depends on Story 1 (DB) and Story 2 (parser)
- **Story 7** — API vessel detail extension `services/api-server/routes/vessels.py` — depends on Story 1 (DB schema)

### Group 3 (parallel — after Group 2)
- **Story 4** — Frontend vessel panel upload `frontend/src/components/VesselPanel/EquasisUpload.tsx` — depends on Story 3 (API)
- **Story 5** — Frontend standalone import `frontend/src/components/Controls/EquasisImport.tsx` — depends on Story 3 (API)
- **Story 6** — Frontend expanded display `frontend/src/components/VesselPanel/EquasisSection.tsx` — depends on Story 7 (API response)

### Group 4 (sequential — after Group 3)
- **Story 8** — Scoring enhancements `services/scoring/rules/insurance_class_risk.py` + `flag_hopping.py` — depends on Story 1 (DB) and Story 3 (data flow)

---

## Development Approach

### Simplifications (what starts simple)

- PDF parsing assumes standard Equasis Ship Folder format only — no handling of older/different Equasis layouts
- Single-file upload (no drag-and-drop zone, no multi-file)
- Previous uploads viewed via simple dropdown, not a full diff/comparison view
- Scoring reads equasis data from the latest upload only (not historical trends across uploads)

### Upgrade Path (what changes for production)

- "Add drag-and-drop upload zone" — UI enhancement story
- "Add PDF parsing for Paris MoU / Tokyo MoU reports" — separate parser + spec
- "Add upload diff view showing what changed between Equasis editions" — separate story
- "Add PSC trend scoring (increasing deficiency rate over time)" — separate scoring rule
- "Add automatic Equasis data refresh reminders for stale uploads (>90 days)" — separate story

### Architecture Decisions

- **Server-side PDF parsing** — more reliable than browser-based, keeps frontend simple, Python ecosystem has better PDF libraries
- **JSONB columns per section** — flexible enough for Equasis's varied data while remaining queryable; avoids over-normalizing into 8+ tables for a single data source
- **Keep all upload history** — new rows per upload instead of upsert; allows operators to compare editions and provides an audit trail
- **Merge into vessel_profiles on upload** — scoring rules already read vessel_profiles; updating those fields means all existing rules benefit from Equasis data without modification
- **pdfplumber over PyPDF2/pdfminer** — better table detection, actively maintained, handles the structured table layout of Equasis PDFs well
- **5MB file limit** — Equasis PDFs are typically 30-50KB; 5MB provides generous headroom while preventing abuse

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Sample PDF (ShipFop.pdf / BLUE) parses correctly end-to-end
- [ ] Upload from vessel panel works (matching vessel)
- [ ] Upload from toolbar works (new vessel creation)
- [ ] IMO/MMSI mismatch is rejected with clear error
- [ ] Expanded vessel information displays all Equasis sections
- [ ] Scoring rules use Equasis data (PSC detentions, classification, flag history)
- [ ] Re-scoring triggers after upload
- [ ] Edge cases handled (corrupt PDF, non-Equasis PDF, empty sections)
- [ ] No regressions in existing tests
- [ ] Code committed with proper messages
- [ ] Ready for human review
