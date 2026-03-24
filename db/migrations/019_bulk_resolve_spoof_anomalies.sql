-- 019: Bulk-resolve false positive spoofing/speed anomaly events
-- These rules produced false positives and are being rethought.
-- Idempotent: only updates rows that are still 'active'.

UPDATE anomaly_events
SET event_state = 'resolved',
    resolved    = TRUE,
    details     = details || '{"resolution": "bulk_resolved: false_positive_rethink_2026-03"}'::jsonb
WHERE event_state = 'active'
  AND rule_id IN (
      'ais_spoofing',
      'spoof_frozen_position',
      'spoof_impossible_speed',
      'speed_anomaly'
  );
