-- 012_spoofing_tables.sql
-- AIS spoofing detection: land mask and GNSS interference zone tables.

-- Land mask table for on-land position detection
CREATE TABLE IF NOT EXISTS land_mask (
    id          SERIAL PRIMARY KEY,
    geometry    GEOGRAPHY(MULTIPOLYGON, 4326) NOT NULL,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_land_mask_geometry
    ON land_mask USING GIST (geometry);

-- GNSS interference zone clustering
CREATE TABLE IF NOT EXISTS gnss_interference_zones (
    id              BIGSERIAL PRIMARY KEY,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    geometry        GEOGRAPHY(POLYGON, 4326) NOT NULL,
    affected_count  INTEGER NOT NULL DEFAULT 0,
    details         JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_gnss_zones_geometry
    ON gnss_interference_zones USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_gnss_zones_expires_at
    ON gnss_interference_zones (expires_at);
