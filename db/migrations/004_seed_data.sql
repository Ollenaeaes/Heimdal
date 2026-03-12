-- 004_seed_data.sql
-- Seed data: STS zones and Russian terminal zones

-- ============================================================
-- STS Zones (rectangular polygons from SW/NE corners)
-- WKT POLYGON format: (lon lat) pairs, counter-clockwise, closed ring
-- ============================================================

-- Malta OPL: SW(35.5, 13.8) NE(36.1, 14.8)
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Malta OPL', 'sts_zone',
 ST_GeogFromText('POLYGON((13.8 35.5, 14.8 35.5, 14.8 36.1, 13.8 36.1, 13.8 35.5))'),
 '{"description": "Malta offshore petroleum loading STS zone"}')
ON CONFLICT DO NOTHING;

-- Augusta: SW(36.9, 14.8) NE(37.5, 15.6)
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Augusta', 'sts_zone',
 ST_GeogFromText('POLYGON((14.8 36.9, 15.6 36.9, 15.6 37.5, 14.8 37.5, 14.8 36.9))'),
 '{"description": "Augusta STS zone off Sicily"}')
ON CONFLICT DO NOTHING;

-- Lomé: SW(5.7, 0.8) NE(6.5, 1.8)
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Lomé', 'sts_zone',
 ST_GeogFromText('POLYGON((0.8 5.7, 1.8 5.7, 1.8 6.5, 0.8 6.5, 0.8 5.7))'),
 '{"description": "Lomé anchorage STS zone, Gulf of Guinea"}')
ON CONFLICT DO NOTHING;

-- Kalamata: SW(36.3, 22.0) NE(37.1, 22.8)
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Kalamata', 'sts_zone',
 ST_GeogFromText('POLYGON((22.0 36.3, 22.8 36.3, 22.8 37.1, 22.0 37.1, 22.0 36.3))'),
 '{"description": "Kalamata STS zone off Peloponnese"}')
ON CONFLICT DO NOTHING;

-- Ceuta: SW(35.6, -5.8) NE(36.2, -4.8)
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Ceuta', 'sts_zone',
 ST_GeogFromText('POLYGON((-5.8 35.6, -4.8 35.6, -4.8 36.2, -5.8 36.2, -5.8 35.6))'),
 '{"description": "Ceuta STS zone, Strait of Gibraltar"}')
ON CONFLICT DO NOTHING;

-- Yeosu: SW(34.1, 127.2) NE(34.9, 128.2)
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Yeosu', 'sts_zone',
 ST_GeogFromText('POLYGON((127.2 34.1, 128.2 34.1, 128.2 34.9, 127.2 34.9, 127.2 34.1))'),
 '{"description": "Yeosu STS zone, South Korea"}')
ON CONFLICT DO NOTHING;

-- ============================================================
-- Russian Terminals (~5nm radius, 8-point circle approximation)
-- 5nm ≈ 0.083 degrees
-- 8 points at 0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°
-- For point (lat, lon) with radius r:
--   (lon + r*cos(angle), lat + r*sin(angle))
-- ============================================================

-- Ust-Luga: 59.680, 28.400
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Ust-Luga', 'terminal',
 ST_GeogFromText('POLYGON((28.483 59.680, 28.459 59.739, 28.400 59.763, 28.341 59.739, 28.317 59.680, 28.341 59.621, 28.400 59.597, 28.459 59.621, 28.483 59.680))'),
 '{"country": "Russia", "type": "oil_terminal", "port": "Ust-Luga"}')
ON CONFLICT DO NOTHING;

-- Primorsk: 60.350, 28.680
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Primorsk', 'terminal',
 ST_GeogFromText('POLYGON((28.763 60.350, 28.739 60.409, 28.680 60.433, 28.621 60.409, 28.597 60.350, 28.621 60.291, 28.680 60.267, 28.739 60.291, 28.763 60.350))'),
 '{"country": "Russia", "type": "oil_terminal", "port": "Primorsk"}')
ON CONFLICT DO NOTHING;

-- Novorossiysk: 44.660, 37.810
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Novorossiysk', 'terminal',
 ST_GeogFromText('POLYGON((37.893 44.660, 37.869 44.719, 37.810 44.743, 37.751 44.719, 37.727 44.660, 37.751 44.601, 37.810 44.577, 37.869 44.601, 37.893 44.660))'),
 '{"country": "Russia", "type": "oil_terminal", "port": "Novorossiysk"}')
ON CONFLICT DO NOTHING;

-- Kozmino: 42.730, 132.910
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Kozmino', 'terminal',
 ST_GeogFromText('POLYGON((132.993 42.730, 132.969 42.789, 132.910 42.813, 132.851 42.789, 132.827 42.730, 132.851 42.671, 132.910 42.647, 132.969 42.671, 132.993 42.730))'),
 '{"country": "Russia", "type": "oil_terminal", "port": "Kozmino"}')
ON CONFLICT DO NOTHING;

-- Murmansk: 68.970, 33.080
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Murmansk', 'terminal',
 ST_GeogFromText('POLYGON((33.163 68.970, 33.139 69.029, 33.080 69.053, 33.021 69.029, 32.997 68.970, 33.021 68.911, 33.080 68.887, 33.139 68.911, 33.163 68.970))'),
 '{"country": "Russia", "type": "oil_terminal", "port": "Murmansk"}')
ON CONFLICT DO NOTHING;

-- Taman: 45.220, 36.620
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Taman', 'terminal',
 ST_GeogFromText('POLYGON((36.703 45.220, 36.679 45.279, 36.620 45.303, 36.561 45.279, 36.537 45.220, 36.561 45.161, 36.620 45.137, 36.679 45.161, 36.703 45.220))'),
 '{"country": "Russia", "type": "oil_terminal", "port": "Taman"}')
ON CONFLICT DO NOTHING;

-- Vysotsk: 60.630, 28.570
INSERT INTO zones (zone_name, zone_type, geometry, properties) VALUES
('Vysotsk', 'terminal',
 ST_GeogFromText('POLYGON((28.653 60.630, 28.629 60.689, 28.570 60.713, 28.511 60.689, 28.487 60.630, 28.511 60.571, 28.570 60.547, 28.629 60.571, 28.653 60.630))'),
 '{"country": "Russia", "type": "oil_terminal", "port": "Vysotsk"}')
ON CONFLICT DO NOTHING;
