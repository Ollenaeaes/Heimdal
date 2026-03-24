-- 020_gnss_zones_update.sql
-- Extend gnss_interference_zones with tracking columns for the
-- area-based GNSS interference zone detector (Story 4).

-- Track which vessels are affected by each zone
ALTER TABLE gnss_interference_zones ADD COLUMN IF NOT EXISTS affected_mmsis INTEGER[] NOT NULL DEFAULT '{}';

-- Classify zone as spoofing vs jamming
ALTER TABLE gnss_interference_zones ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'spoofing';

-- Peak severity observed in the zone
ALTER TABLE gnss_interference_zones ADD COLUMN IF NOT EXISTS peak_severity TEXT DEFAULT 'high';

-- Explicit creation timestamp (detected_at serves as first-seen)
ALTER TABLE gnss_interference_zones ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Composite index for efficient time-window queries
CREATE INDEX IF NOT EXISTS idx_gnss_zones_time_range ON gnss_interference_zones(detected_at, expires_at);

-- Allow tagging vessels as GNSS-affected (set by the zone detector)
ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS gnss_affected JSONB DEFAULT NULL;
