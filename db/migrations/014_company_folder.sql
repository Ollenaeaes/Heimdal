-- 014_company_folder.sql
-- Support for Equasis Company Folder uploads and fleet network extraction.

-- Add imo_only flag to vessel_profiles for vessels known only from Equasis
-- (no AIS data yet). These use a synthetic negative MMSI derived from IMO.
ALTER TABLE vessel_profiles
    ADD COLUMN IF NOT EXISTS imo_only BOOLEAN NOT NULL DEFAULT FALSE;

-- Equasis company folder upload audit table
CREATE TABLE IF NOT EXISTS equasis_company_uploads (
    id                  SERIAL PRIMARY KEY,
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    company_imo         VARCHAR(16) NOT NULL,
    company_name        VARCHAR(256),
    company_address     TEXT,
    edition_date        DATE,
    fleet_size          INTEGER NOT NULL DEFAULT 0,
    vessels_created     INTEGER NOT NULL DEFAULT 0,
    vessels_updated     INTEGER NOT NULL DEFAULT 0,
    edges_created       INTEGER NOT NULL DEFAULT 0,
    inspection_synthesis JSONB DEFAULT '{}',
    parsed_data         JSONB NOT NULL DEFAULT '{}',
    raw_text            TEXT
);

CREATE INDEX IF NOT EXISTS idx_equasis_company_uploads_imo
    ON equasis_company_uploads (company_imo);
