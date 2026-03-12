-- 003_indexes.sql
-- Performance indexes for all tables

-- ============================================================
-- vessel_positions indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_positions_mmsi
    ON vessel_positions (mmsi, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_positions_geo
    ON vessel_positions USING GIST (position);

-- ============================================================
-- vessel_profiles indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_profiles_imo
    ON vessel_profiles (imo) WHERE imo IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_profiles_risk
    ON vessel_profiles (risk_tier, risk_score DESC);

CREATE INDEX IF NOT EXISTS idx_profiles_type
    ON vessel_profiles (ship_type);

CREATE INDEX IF NOT EXISTS idx_profiles_sanctions
    ON vessel_profiles USING GIN (sanctions_status);

-- ============================================================
-- anomaly_events indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_anomalies_vessel
    ON anomaly_events (mmsi, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_anomalies_severity
    ON anomaly_events (severity);

CREATE INDEX IF NOT EXISTS idx_anomalies_unresolved
    ON anomaly_events (mmsi) WHERE resolved = FALSE;

-- ============================================================
-- sar_detections indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_sar_geo
    ON sar_detections USING GIST (position);

CREATE INDEX IF NOT EXISTS idx_sar_dark
    ON sar_detections (detection_time DESC) WHERE is_dark = TRUE;

-- ============================================================
-- gfw_events indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_gfw_events_mmsi
    ON gfw_events (mmsi, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_gfw_events_type
    ON gfw_events (event_type);

-- ============================================================
-- zones indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_zones_geo
    ON zones USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_zones_type
    ON zones (zone_type);
