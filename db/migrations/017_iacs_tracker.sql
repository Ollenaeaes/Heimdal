-- IACS Vessels-in-Class tracker tables
-- Tracks weekly IACS CSV snapshots, current vessel state, and change history.

-- Snapshot metadata (one row per imported file)
CREATE TABLE IF NOT EXISTS iacs_snapshots (
    id              SERIAL PRIMARY KEY,
    filename        TEXT NOT NULL UNIQUE,
    snapshot_date   DATE NOT NULL,
    file_hash       TEXT NOT NULL UNIQUE,
    row_count       INTEGER NOT NULL DEFAULT 0,
    vessels_added   INTEGER NOT NULL DEFAULT 0,
    vessels_changed INTEGER NOT NULL DEFAULT 0,
    vessels_removed INTEGER NOT NULL DEFAULT 0,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Current state: one row per IMO, reflecting the latest known IACS status
CREATE TABLE IF NOT EXISTS iacs_vessels_current (
    imo                 INTEGER PRIMARY KEY,
    ship_name           TEXT,
    class_society       TEXT,
    date_of_survey      DATE,
    date_of_next_survey DATE,
    date_of_latest_status DATE,
    status              TEXT,           -- Delivered, Withdrawn, Suspended, Reinstated, Reassigned
    reason              TEXT,
    row_hash            TEXT NOT NULL,   -- hash of all mutable fields for fast diff
    all_entries         JSONB,           -- all rows for this IMO from latest snapshot
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    snapshot_date       DATE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_iacs_current_status ON iacs_vessels_current (status);
CREATE INDEX IF NOT EXISTS idx_iacs_current_class ON iacs_vessels_current (class_society);
CREATE INDEX IF NOT EXISTS idx_iacs_current_snapshot ON iacs_vessels_current (snapshot_date);

-- Change history: append-only log of all detected changes
CREATE TABLE IF NOT EXISTS iacs_vessels_changes (
    id              BIGSERIAL PRIMARY KEY,
    imo             INTEGER NOT NULL,
    ship_name       TEXT,
    change_type     TEXT NOT NULL,       -- status_change, class_change, name_change, vessel_added, vessel_removed, survey_update
    field_changed   TEXT,                -- which field changed (status, class_society, ship_name, etc.)
    old_value       TEXT,
    new_value       TEXT,
    is_high_risk    BOOLEAN NOT NULL DEFAULT FALSE,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    snapshot_date   DATE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_iacs_changes_imo ON iacs_vessels_changes (imo);
CREATE INDEX IF NOT EXISTS idx_iacs_changes_type ON iacs_vessels_changes (change_type);
CREATE INDEX IF NOT EXISTS idx_iacs_changes_risk ON iacs_vessels_changes (is_high_risk) WHERE is_high_risk = TRUE;
CREATE INDEX IF NOT EXISTS idx_iacs_changes_detected ON iacs_vessels_changes (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_iacs_changes_snapshot ON iacs_vessels_changes (snapshot_date);

-- Add iacs_data JSONB column to vessel_profiles for scoring rule access
ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS iacs_data JSONB;
