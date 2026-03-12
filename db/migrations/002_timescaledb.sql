-- 002_timescaledb.sql
-- TimescaleDB hypertable, compression, retention, and continuous aggregates

-- ============================================================
-- Convert vessel_positions to a hypertable (7-day chunks)
-- ============================================================
SELECT create_hypertable(
    'vessel_positions',
    by_range('timestamp', INTERVAL '7 days'),
    if_not_exists => TRUE
);

-- ============================================================
-- Compression policy
-- ============================================================
ALTER TABLE vessel_positions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'mmsi',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Compress chunks older than 30 days
SELECT add_compression_policy('vessel_positions', INTERVAL '30 days', if_not_exists => TRUE);

-- ============================================================
-- Retention policy: drop chunks older than 365 days
-- ============================================================
SELECT add_retention_policy('vessel_positions', INTERVAL '365 days', if_not_exists => TRUE);

-- ============================================================
-- Continuous aggregate: hourly vessel summaries
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS vessel_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp)    AS bucket,
    mmsi,
    AVG(sog)                            AS avg_sog,
    MAX(sog)                            AS max_sog,
    AVG(draught)                        AS avg_draught,
    COUNT(*)                            AS position_count,
    ST_Collect(position::geometry)      AS track
FROM vessel_positions
GROUP BY bucket, mmsi
WITH NO DATA;

-- Refresh policy: look back 2 hours, up to 1 hour ago, run every hour
SELECT add_continuous_aggregate_policy('vessel_hourly',
    start_offset    => INTERVAL '2 hours',
    end_offset      => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists   => TRUE
);
