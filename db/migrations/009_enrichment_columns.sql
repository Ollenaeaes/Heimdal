-- Migration 009: Add enrichment columns to vessel_profiles
-- Adds classification_data, insurance_data, enrichment_status, and enriched_at
-- for the yellow-enrichment-path feature (spec 20, story 3).

ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS classification_data JSONB;
ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS insurance_data JSONB;
ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS enrichment_status JSONB;
ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_vessel_profiles_enrichment ON vessel_profiles (risk_tier, enriched_at);
