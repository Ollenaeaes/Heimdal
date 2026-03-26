-- 022_adsb_tables.sql
-- ADS-B integration: aircraft of interest catalog, position tracking,
-- and interference detection (replaces AIS-derived GNSS zones).

-- ============================================================
-- 1. Aircraft of interest catalog (static reference table)
-- ============================================================
CREATE TABLE IF NOT EXISTS aircraft_of_interest (
    icao_hex      TEXT PRIMARY KEY,
    registration  TEXT,
    type_code     TEXT,
    description   TEXT,
    country       TEXT,
    category      TEXT,       -- military / police / coast_guard / government
    role          TEXT,       -- e.g. "Danish Defence", "US Navy maritime patrol"
    source        TEXT,       -- tar1090-db flag=10 / manual_override
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aoi_category ON aircraft_of_interest(category);
CREATE INDEX IF NOT EXISTS idx_aoi_country ON aircraft_of_interest(country);

-- ============================================================
-- 2. ADS-B positions for aircraft of interest (hypertable)
-- ============================================================
CREATE TABLE IF NOT EXISTS adsb_positions (
    time          TIMESTAMPTZ NOT NULL,
    icao_hex      TEXT NOT NULL,
    callsign      TEXT,
    lat           DOUBLE PRECISION NOT NULL,
    lon           DOUBLE PRECISION NOT NULL,
    alt_baro      INTEGER,
    alt_geom      INTEGER,
    ground_speed  REAL,
    track         REAL,
    vertical_rate REAL,
    squawk        TEXT,
    nac_p         SMALLINT,
    nic           SMALLINT,
    on_ground     BOOLEAN DEFAULT FALSE,
    category      TEXT,       -- from aircraft_of_interest join
    country       TEXT,       -- from aircraft_of_interest join
    role          TEXT        -- from aircraft_of_interest join
);

SELECT create_hypertable('adsb_positions', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_adsb_pos_hex_time ON adsb_positions(icao_hex, time DESC);
CREATE INDEX IF NOT EXISTS idx_adsb_pos_spatial ON adsb_positions(lat, lon, time DESC);

-- Compression policy: compress chunks older than 2 days
ALTER TABLE adsb_positions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'icao_hex',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('adsb_positions', INTERVAL '2 days', if_not_exists => TRUE);

-- Retention: keep 1 year of position data
SELECT add_retention_policy('adsb_positions', INTERVAL '365 days', if_not_exists => TRUE);

-- ============================================================
-- 3. Interference observations (H3 grid, short retention)
-- ============================================================
CREATE TABLE IF NOT EXISTS adsb_interference_observations (
    time            TIMESTAMPTZ NOT NULL,
    h3_index        BIGINT NOT NULL,
    h3_resolution   SMALLINT NOT NULL DEFAULT 5,
    center_lat      DOUBLE PRECISION NOT NULL,
    center_lon      DOUBLE PRECISION NOT NULL,
    aircraft_count  INTEGER NOT NULL DEFAULT 0,
    degraded_count  INTEGER NOT NULL DEFAULT 0,
    min_nac_p       SMALLINT,
    gps_lost_count  INTEGER NOT NULL DEFAULT 0,
    avg_alt_baro    INTEGER
);

SELECT create_hypertable('adsb_interference_observations', 'time',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_adsb_obs_h3_time ON adsb_interference_observations(h3_index, time DESC);

-- Compression after 6 hours
ALTER TABLE adsb_interference_observations SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'h3_index',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('adsb_interference_observations', INTERVAL '6 hours', if_not_exists => TRUE);

-- Short retention: 48 hours
SELECT add_retention_policy('adsb_interference_observations', INTERVAL '48 hours', if_not_exists => TRUE);

-- ============================================================
-- 4. Interference events (long retention, queryable by frontend)
-- ============================================================
CREATE TABLE IF NOT EXISTS adsb_interference_events (
    id            BIGINT GENERATED ALWAYS AS IDENTITY,
    time_start    TIMESTAMPTZ NOT NULL,
    time_end      TIMESTAMPTZ NOT NULL,
    h3_index      BIGINT NOT NULL,
    center_lat    DOUBLE PRECISION NOT NULL,
    center_lon    DOUBLE PRECISION NOT NULL,
    radius_km     REAL NOT NULL DEFAULT 20.0,
    severity      TEXT NOT NULL DEFAULT 'moderate',  -- moderate / severe
    event_type    TEXT NOT NULL DEFAULT 'jamming',    -- jamming / spoofing
    confidence    REAL NOT NULL DEFAULT 0.5,
    peak_aircraft_affected  INTEGER NOT NULL DEFAULT 0,
    min_nac_p_observed      SMALLINT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('adsb_interference_events', 'time_start',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_adsb_events_active ON adsb_interference_events(is_active, time_start DESC);
CREATE INDEX IF NOT EXISTS idx_adsb_events_h3 ON adsb_interference_events(h3_index, time_start DESC);
CREATE INDEX IF NOT EXISTS idx_adsb_events_time_range ON adsb_interference_events(time_start, time_end);
CREATE INDEX IF NOT EXISTS idx_adsb_events_spatial ON adsb_interference_events(center_lat, center_lon);
