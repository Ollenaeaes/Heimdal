-- 005_sar_matched_category.sql
-- Add matched_category column to sar_detections for GFW vessel type classification

ALTER TABLE sar_detections ADD COLUMN IF NOT EXISTS matched_category TEXT;
