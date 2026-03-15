-- Enrichment tracking table — replaces Redis hash heimdal:enriched.
-- Tracks when each vessel was last enriched, used by the batch pipeline
-- to determine which vessels need enrichment based on tier-adaptive intervals.
CREATE TABLE IF NOT EXISTS enrichment_log (
    mmsi        INTEGER NOT NULL PRIMARY KEY,
    enriched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tier_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_enrichment_log_enriched_at
    ON enrichment_log (enriched_at);
