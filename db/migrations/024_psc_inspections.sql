-- Migration: 024_psc_inspections
-- Paris MoU PSC inspection data tables and flag performance seed data

BEGIN;

-- ============================================================
-- Table: psc_inspections
-- ============================================================
CREATE TABLE IF NOT EXISTS psc_inspections (
    id SERIAL PRIMARY KEY,
    inspection_id VARCHAR(20) UNIQUE NOT NULL,  -- Paris MoU InspectionID
    imo INTEGER NOT NULL,
    ship_name TEXT,
    flag_state VARCHAR(2),
    ship_type VARCHAR(10),
    gross_tonnage INTEGER,
    keel_laid_date DATE,
    inspection_date DATE NOT NULL,
    inspection_end_date DATE,
    inspection_type VARCHAR(30),  -- INITIAL_INSPECTION, DETAILED_INSPECTION, EXPANDED_INSPECTION
    inspection_port VARCHAR(10),
    port_country VARCHAR(2),
    reporting_authority VARCHAR(2),
    detained BOOLEAN NOT NULL DEFAULT FALSE,  -- derived from any deficiency having isGroundDetention=true
    deficiency_count INTEGER NOT NULL DEFAULT 0,
    ism_deficiency BOOLEAN NOT NULL DEFAULT FALSE,
    ro_at_inspection TEXT,  -- classification society code from ClassCertificate
    pi_provider_at_inspection TEXT,  -- from CLC/Bunker cert issuing authority
    pi_is_ig_member BOOLEAN,
    ism_company_imo VARCHAR(16),
    ism_company_name TEXT,
    raw_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Table: psc_deficiencies
-- ============================================================
CREATE TABLE IF NOT EXISTS psc_deficiencies (
    id SERIAL PRIMARY KEY,
    inspection_id INTEGER NOT NULL REFERENCES psc_inspections(id) ON DELETE CASCADE,
    deficiency_code VARCHAR(16),  -- DefectiveItemCode
    nature_of_defect VARCHAR(16),  -- NatureOfDefectCode
    is_ground_detention BOOLEAN NOT NULL DEFAULT FALSE,
    is_ro_related BOOLEAN NOT NULL DEFAULT FALSE,
    is_accidental_damage BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT  -- may be empty, kept for future use
);

-- ============================================================
-- Table: psc_certificates
-- ============================================================
CREATE TABLE IF NOT EXISTS psc_certificates (
    id SERIAL PRIMARY KEY,
    inspection_id INTEGER NOT NULL REFERENCES psc_inspections(id) ON DELETE CASCADE,
    certificate_type VARCHAR(16),  -- CertificateCode (e.g. 511, 533)
    issuing_authority TEXT,
    issuing_authority_type VARCHAR(10),  -- RO or Flag
    expiry_date DATE,
    issue_date DATE,
    certificate_source VARCHAR(10) NOT NULL DEFAULT 'statutory'  -- 'class' or 'statutory'
);

-- ============================================================
-- Table: psc_flag_performance
-- ============================================================
CREATE TABLE IF NOT EXISTS psc_flag_performance (
    iso_code VARCHAR(2) PRIMARY KEY,
    list_status VARCHAR(8) NOT NULL CHECK (list_status IN ('white', 'grey', 'black')),
    year INTEGER NOT NULL DEFAULT 2024
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_psc_inspections_imo_date ON psc_inspections (imo, inspection_date DESC);
CREATE INDEX IF NOT EXISTS idx_psc_inspections_ism_company ON psc_inspections (ism_company_imo);
CREATE INDEX IF NOT EXISTS idx_psc_inspections_flag ON psc_inspections (flag_state);
CREATE INDEX IF NOT EXISTS idx_psc_inspections_detained ON psc_inspections (imo) WHERE detained = TRUE;
CREATE INDEX IF NOT EXISTS idx_psc_deficiencies_inspection ON psc_deficiencies (inspection_id);
CREATE INDEX IF NOT EXISTS idx_psc_certificates_inspection ON psc_certificates (inspection_id);

-- ============================================================
-- Seed data: Paris MoU 2023-2024 flag performance list
-- ============================================================

-- Grey list flags
INSERT INTO psc_flag_performance (iso_code, list_status, year) VALUES
    ('AL', 'grey', 2024),
    ('BS', 'grey', 2024),
    ('BB', 'grey', 2024),
    ('BZ', 'grey', 2024),
    ('CM', 'grey', 2024),
    ('KM', 'grey', 2024),
    ('CK', 'grey', 2024),
    ('CW', 'grey', 2024),
    ('EG', 'grey', 2024),
    ('GN', 'grey', 2024),
    ('HN', 'grey', 2024),
    ('JM', 'grey', 2024),
    ('LB', 'grey', 2024),
    ('LY', 'grey', 2024),
    ('MD', 'grey', 2024),
    ('MN', 'grey', 2024),
    ('PW', 'grey', 2024),
    ('SL', 'grey', 2024),
    ('KN', 'grey', 2024),
    ('VC', 'grey', 2024),
    ('TZ', 'grey', 2024),
    ('TG', 'grey', 2024),
    ('VU', 'grey', 2024)
ON CONFLICT (iso_code) DO NOTHING;

-- White list flags
INSERT INTO psc_flag_performance (iso_code, list_status, year) VALUES
    ('AG', 'white', 2024),
    ('AU', 'white', 2024),
    ('BE', 'white', 2024),
    ('BM', 'white', 2024),
    ('BG', 'white', 2024),
    ('CA', 'white', 2024),
    ('KY', 'white', 2024),
    ('CN', 'white', 2024),
    ('HR', 'white', 2024),
    ('CY', 'white', 2024),
    ('CZ', 'white', 2024),
    ('DK', 'white', 2024),
    ('EE', 'white', 2024),
    ('FO', 'white', 2024),
    ('FI', 'white', 2024),
    ('FR', 'white', 2024),
    ('DE', 'white', 2024),
    ('GI', 'white', 2024),
    ('GR', 'white', 2024),
    ('HK', 'white', 2024),
    ('IS', 'white', 2024),
    ('IN', 'white', 2024),
    ('ID', 'white', 2024),
    ('IR', 'white', 2024),
    ('IE', 'white', 2024),
    ('IM', 'white', 2024),
    ('IT', 'white', 2024),
    ('JP', 'white', 2024),
    ('LV', 'white', 2024),
    ('LR', 'white', 2024),
    ('LT', 'white', 2024),
    ('LU', 'white', 2024),
    ('MY', 'white', 2024),
    ('MT', 'white', 2024),
    ('MH', 'white', 2024),
    ('MX', 'white', 2024),
    ('MA', 'white', 2024),
    ('NL', 'white', 2024),
    ('NZ', 'white', 2024),
    ('NG', 'white', 2024),
    ('NO', 'white', 2024),
    ('PA', 'white', 2024),
    ('PH', 'white', 2024),
    ('PL', 'white', 2024),
    ('PT', 'white', 2024),
    ('QA', 'white', 2024),
    ('RO', 'white', 2024),
    ('RU', 'white', 2024),
    ('SA', 'white', 2024),
    ('SG', 'white', 2024),
    ('SK', 'white', 2024),
    ('KR', 'white', 2024),
    ('ES', 'white', 2024),
    ('LK', 'white', 2024),
    ('SE', 'white', 2024),
    ('CH', 'white', 2024),
    ('TH', 'white', 2024),
    ('TR', 'white', 2024),
    ('TV', 'white', 2024),
    ('UA', 'white', 2024),
    ('AE', 'white', 2024),
    ('GB', 'white', 2024),
    ('US', 'white', 2024),
    ('VN', 'white', 2024)
ON CONFLICT (iso_code) DO NOTHING;

COMMIT;
