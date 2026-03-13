-- Migration 010: Equasis Ship Folder data storage
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
