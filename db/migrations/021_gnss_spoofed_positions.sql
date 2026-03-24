-- Migration: document gnss_spoofed_positions table
-- This table already exists in production (created by retrospective detector).
-- This migration ensures it exists and has proper indexes.

CREATE TABLE IF NOT EXISTS gnss_spoofed_positions (
    id              BIGSERIAL PRIMARY KEY,
    mmsi            INTEGER NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL,
    spoofed_lat     DOUBLE PRECISION NOT NULL,
    spoofed_lon     DOUBLE PRECISION NOT NULL,
    real_lat        DOUBLE PRECISION,
    real_lon        DOUBLE PRECISION,
    event_type      TEXT NOT NULL DEFAULT 'spoofing',
    deviation_km    DOUBLE PRECISION
);

-- Indexes for time-window queries and clustering
CREATE INDEX IF NOT EXISTS idx_gnss_spoofed_pos_detected
    ON gnss_spoofed_positions (detected_at);
CREATE INDEX IF NOT EXISTS idx_gnss_spoofed_pos_mmsi
    ON gnss_spoofed_positions (mmsi);
CREATE INDEX IF NOT EXISTS idx_gnss_spoofed_pos_event_type
    ON gnss_spoofed_positions (event_type);
