-- 013_network_edges.sql
-- Network edges table for sanctions evasion network mapping.

-- ============================================================
-- Network edges (vessel-to-vessel relationships)
-- ============================================================
CREATE TABLE IF NOT EXISTS network_edges (
    id              BIGSERIAL PRIMARY KEY,
    vessel_a_mmsi   INTEGER NOT NULL REFERENCES vessel_profiles(mmsi),
    vessel_b_mmsi   INTEGER NOT NULL REFERENCES vessel_profiles(mmsi),
    edge_type       VARCHAR(32) NOT NULL,
    confidence      REAL DEFAULT 1.0,
    first_observed  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_observed   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    observation_count INTEGER DEFAULT 1,
    location        GEOGRAPHY(POINT, 4326),
    details         JSONB DEFAULT '{}',

    CONSTRAINT uq_network_edge UNIQUE (vessel_a_mmsi, vessel_b_mmsi, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_network_edges_vessel_a
    ON network_edges (vessel_a_mmsi);

CREATE INDEX IF NOT EXISTS idx_network_edges_vessel_b
    ON network_edges (vessel_b_mmsi);

CREATE INDEX IF NOT EXISTS idx_network_edges_edge_type
    ON network_edges (edge_type);

-- Add network_score column to vessel_profiles
ALTER TABLE vessel_profiles
    ADD COLUMN IF NOT EXISTS network_score INTEGER DEFAULT 0;
