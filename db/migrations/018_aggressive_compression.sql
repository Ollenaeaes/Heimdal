-- 018_aggressive_compression.sql
-- Compress TimescaleDB chunks after 2 days instead of 30.
--
-- WHY: vessel_positions grows ~4.8 GB/day uncompressed. With 30-day
-- retention that's ~144 GB steady state — too much for 100 GB disk.
-- TimescaleDB compression typically achieves 90%+ reduction on
-- time-series AIS data. Compressed chunks remain fully queryable.
--
-- SAFETY: This does NOT delete data. Compression is transparent to
-- all queries — SELECT, JOIN, aggregation all work identically.

-- Remove old 30-day compression policy
SELECT remove_compression_policy('vessel_positions', if_exists => TRUE);

-- Add new 2-day compression policy
SELECT add_compression_policy('vessel_positions', INTERVAL '2 days', if_not_exists => TRUE);

-- Immediately compress all existing chunks older than 2 days
-- (otherwise we'd wait for the policy scheduler to catch up)
SELECT compress_chunk(c, if_not_compressed => true)
FROM show_chunks('vessel_positions', older_than => INTERVAL '2 days') c;
