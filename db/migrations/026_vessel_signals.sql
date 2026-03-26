-- Migration 026: Vessel Signals
-- Stores geographic inference signals (D1-D7) produced by the geographic
-- inference engine. These are scoring inputs consumed by the signal-based
-- scoring engine (Story 6), NOT graph relationships.

BEGIN;

CREATE TABLE IF NOT EXISTS vessel_signals (
    id              BIGSERIAL PRIMARY KEY,
    mmsi            INTEGER NOT NULL,
    imo             INTEGER,
    signal_id       TEXT NOT NULL,
    weight          REAL NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    details         JSONB NOT NULL DEFAULT '{}',
    source_data     TEXT
);

-- Index for lookups by vessel
CREATE INDEX IF NOT EXISTS idx_vessel_signals_mmsi ON vessel_signals (mmsi);

-- Index for lookups by signal type
CREATE INDEX IF NOT EXISTS idx_vessel_signals_signal_id ON vessel_signals (signal_id);

-- Index for time-range queries
CREATE INDEX IF NOT EXISTS idx_vessel_signals_triggered_at ON vessel_signals (triggered_at DESC);

-- Composite index for dedup checks (same vessel + signal + day)
CREATE UNIQUE INDEX IF NOT EXISTS idx_vessel_signals_dedup
    ON vessel_signals (mmsi, signal_id, (triggered_at::date));

COMMIT;
