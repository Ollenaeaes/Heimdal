-- Add 'blacklisted' to risk_tier enum for vessels with confirmed sanctions matches
ALTER TYPE risk_tier ADD VALUE IF NOT EXISTS 'blacklisted';

-- Retroactively set existing vessels with IMO/MMSI-matched sanctions to blacklisted
UPDATE vessel_profiles SET risk_tier = 'blacklisted'
WHERE mmsi IN (
  SELECT mmsi FROM anomaly_events
  WHERE rule_id = 'sanctions_match' AND resolved = false
  AND (details->>'matched_field') IN ('imo', 'mmsi')
  AND (details->>'confidence')::float >= 0.9
);
