-- Add denormalized navigation columns to vessel_profiles
-- so snapshot/poll queries don't need to JOIN vessel_positions.
-- Populated by ais-ingest writer on each position flush.

ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS last_cog real;
ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS last_sog real;
ALTER TABLE vessel_profiles ADD COLUMN IF NOT EXISTS last_heading integer;

-- Backfill from latest position per vessel
UPDATE vessel_profiles vp
SET last_cog = sub.cog,
    last_sog = sub.sog,
    last_heading = sub.heading
FROM (
    SELECT DISTINCT ON (mmsi) mmsi, cog, sog, heading
    FROM vessel_positions
    ORDER BY mmsi, timestamp DESC
) sub
WHERE vp.mmsi = sub.mmsi;
