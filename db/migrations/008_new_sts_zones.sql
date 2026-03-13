-- 008_new_sts_zones.sql
-- New STS hotspot zones (Wave 8 — extended coverage)

-- South China Sea STS
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('South China Sea STS', 'sts_zone',
 ST_GeogFromText('POLYGON((103.50 1.50, 105.50 1.50, 105.50 3.50, 103.50 3.50, 103.50 1.50))'),
 '{"description": "South China Sea STS hotspot"}')
ON CONFLICT DO NOTHING;

-- Gulf of Oman STS
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Gulf of Oman STS', 'sts_zone',
 ST_GeogFromText('POLYGON((56.00 24.00, 58.00 24.00, 58.00 26.00, 56.00 26.00, 56.00 24.00))'),
 '{"description": "Gulf of Oman STS hotspot"}')
ON CONFLICT DO NOTHING;

-- Singapore Strait STS
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Singapore Strait STS', 'sts_zone',
 ST_GeogFromText('POLYGON((103.50 1.00, 104.50 1.00, 104.50 1.50, 103.50 1.50, 103.50 1.00))'),
 '{"description": "Singapore Strait STS hotspot"}')
ON CONFLICT DO NOTHING;

-- Alboran Sea STS
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Alboran Sea STS', 'sts_zone',
 ST_GeogFromText('POLYGON((-4.50 35.50, -2.50 35.50, -2.50 36.50, -4.50 36.50, -4.50 35.50))'),
 '{"description": "Alboran Sea STS hotspot"}')
ON CONFLICT DO NOTHING;

-- Baltic/Primorsk STS
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Baltic/Primorsk STS', 'sts_zone',
 ST_GeogFromText('POLYGON((27.00 59.50, 29.50 59.50, 29.50 61.00, 27.00 61.00, 27.00 59.50))'),
 '{"description": "Baltic/Primorsk STS hotspot"}')
ON CONFLICT DO NOTHING;

-- South of Crete STS
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('South of Crete STS', 'sts_zone',
 ST_GeogFromText('POLYGON((24.00 34.00, 26.00 34.00, 26.00 35.00, 24.00 35.00, 24.00 34.00))'),
 '{"description": "South of Crete STS hotspot"}')
ON CONFLICT DO NOTHING;
