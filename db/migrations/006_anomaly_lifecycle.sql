-- 006_anomaly_lifecycle.sql
-- Add lifecycle columns to anomaly_events for tracking event start, end, and state.

ALTER TABLE anomaly_events ADD COLUMN IF NOT EXISTS event_start TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE anomaly_events ADD COLUMN IF NOT EXISTS event_end TIMESTAMPTZ;
ALTER TABLE anomaly_events ADD COLUMN IF NOT EXISTS event_state VARCHAR(20) DEFAULT 'active';

-- Backfill existing data
UPDATE anomaly_events SET event_start = created_at WHERE event_start IS NULL;
UPDATE anomaly_events SET event_state = CASE WHEN resolved THEN 'ended' ELSE 'active' END;

-- Index for lifecycle queries
CREATE INDEX IF NOT EXISTS idx_anomaly_events_lifecycle
    ON anomaly_events (mmsi, rule_id, event_state)
    WHERE event_state = 'active';
