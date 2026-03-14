-- 011_infrastructure_tables.sql
-- Infrastructure protection tables for cable/pipeline corridor monitoring.

-- ============================================================
-- Infrastructure routes (cables, pipelines)
-- ============================================================
CREATE TABLE IF NOT EXISTS infrastructure_routes (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(256) NOT NULL,
    route_type  VARCHAR(32) NOT NULL,
    operator    VARCHAR(256),
    geometry    GEOGRAPHY(LINESTRING, 4326) NOT NULL,
    buffer_nm   REAL DEFAULT 1.0,
    metadata    JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_infrastructure_routes_geometry
    ON infrastructure_routes USING GIST (geometry);

-- ============================================================
-- Infrastructure events (vessel entries into corridors)
-- ============================================================
CREATE TABLE IF NOT EXISTS infrastructure_events (
    id              BIGSERIAL PRIMARY KEY,
    mmsi            INTEGER NOT NULL REFERENCES vessel_profiles(mmsi),
    route_id        INTEGER NOT NULL REFERENCES infrastructure_routes(id),
    entry_time      TIMESTAMPTZ NOT NULL,
    exit_time       TIMESTAMPTZ,
    duration_minutes REAL,
    min_speed       REAL,
    max_alignment   REAL,
    risk_assessed   BOOLEAN DEFAULT FALSE,
    details         JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_infrastructure_events_mmsi_entry
    ON infrastructure_events (mmsi, entry_time DESC);
