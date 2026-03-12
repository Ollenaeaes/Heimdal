-- 001_schema.sql
-- Core schema: extensions, types, and tables for Heimdal

-- ============================================================
-- Extensions
-- ============================================================
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- Custom Types
-- ============================================================
DO $$ BEGIN
    CREATE TYPE risk_tier AS ENUM ('green', 'yellow', 'red');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE anomaly_severity AS ENUM ('critical', 'high', 'moderate', 'low');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pi_tier AS ENUM ('ig_member', 'non_ig_western', 'russian_state', 'unknown', 'fraudulent', 'none');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- Tables
-- ============================================================

-- AIS position reports (will become a TimescaleDB hypertable)
CREATE TABLE IF NOT EXISTS vessel_positions (
    timestamp   TIMESTAMPTZ NOT NULL,
    mmsi        INTEGER NOT NULL,
    position    GEOGRAPHY(POINT, 4326) NOT NULL,
    sog         REAL,
    cog         REAL,
    heading     REAL,
    nav_status  SMALLINT,
    rot         REAL,
    draught     REAL
);

-- Vessel profile / registry data
CREATE TABLE IF NOT EXISTS vessel_profiles (
    mmsi                INTEGER PRIMARY KEY,
    imo                 INTEGER,
    ship_name           TEXT,
    ship_type           INTEGER,
    ship_type_text      TEXT,
    flag_country        TEXT,
    call_sign           TEXT,
    length              REAL,
    width               REAL,
    draught             REAL,
    destination         TEXT,
    eta                 TIMESTAMPTZ,
    last_position_time  TIMESTAMPTZ,
    last_lat            DOUBLE PRECISION,
    last_lon            DOUBLE PRECISION,
    risk_score          REAL DEFAULT 0,
    risk_tier           risk_tier DEFAULT 'green',
    sanctions_status    JSONB DEFAULT '{}',
    pi_tier             pi_tier DEFAULT 'none',
    pi_details          JSONB DEFAULT '{}',
    owner               TEXT,
    operator            TEXT,
    insurer             TEXT,
    class_society       TEXT,
    build_year          INTEGER,
    dwt                 INTEGER,
    gross_tonnage       INTEGER,
    group_owner         TEXT,
    registered_owner    TEXT,
    technical_manager   TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Anomaly events detected by rules engine
CREATE TABLE IF NOT EXISTS anomaly_events (
    id          SERIAL PRIMARY KEY,
    mmsi        INTEGER NOT NULL REFERENCES vessel_profiles(mmsi),
    rule_id     TEXT NOT NULL,
    severity    anomaly_severity NOT NULL,
    points      REAL NOT NULL,
    details     JSONB DEFAULT '{}',
    resolved    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- SAR (Synthetic Aperture Radar) dark vessel detections
CREATE TABLE IF NOT EXISTS sar_detections (
    id                SERIAL PRIMARY KEY,
    detection_time    TIMESTAMPTZ NOT NULL,
    position          GEOGRAPHY(POINT, 4326) NOT NULL,
    length_m          REAL,
    width_m           REAL,
    heading_deg       REAL,
    confidence        REAL,
    is_dark           BOOLEAN DEFAULT FALSE,
    matched_mmsi      INTEGER REFERENCES vessel_profiles(mmsi),
    match_distance_m  REAL,
    source            TEXT DEFAULT 'gfw',
    gfw_detection_id  TEXT UNIQUE,
    matching_score    REAL,
    fishing_score     REAL,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Global Fishing Watch event data
CREATE TABLE IF NOT EXISTS gfw_events (
    id              SERIAL PRIMARY KEY,
    gfw_event_id    TEXT UNIQUE NOT NULL,
    event_type      TEXT NOT NULL,
    mmsi            INTEGER REFERENCES vessel_profiles(mmsi),
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    details         JSONB DEFAULT '{}',
    encounter_mmsi  INTEGER,
    port_name       TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Analyst-provided enrichment data
CREATE TABLE IF NOT EXISTS manual_enrichment (
    id              SERIAL PRIMARY KEY,
    mmsi            INTEGER NOT NULL REFERENCES vessel_profiles(mmsi),
    analyst_notes   TEXT,
    source          TEXT,
    pi_tier         pi_tier,
    confidence      REAL,
    attachments     JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Vessel watchlist
CREATE TABLE IF NOT EXISTS watchlist (
    mmsi        INTEGER PRIMARY KEY REFERENCES vessel_profiles(mmsi),
    reason      TEXT,
    added_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Geographic zones (STS zones, terminals, exclusion zones, etc.)
CREATE TABLE IF NOT EXISTS zones (
    id          SERIAL PRIMARY KEY,
    zone_name   TEXT NOT NULL,
    zone_type   TEXT NOT NULL,
    geometry    GEOGRAPHY(POLYGON, 4326) NOT NULL,
    properties  JSONB DEFAULT '{}'
);
