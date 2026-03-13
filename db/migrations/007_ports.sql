-- 007_ports.sql
-- Create ports table and seed with major global tanker ports for port-awareness scoring.

CREATE TABLE IF NOT EXISTS ports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(2) NOT NULL,
    position GEOGRAPHY(POINT, 4326) NOT NULL,
    port_type VARCHAR(50) DEFAULT 'tanker',
    radius_nm FLOAT DEFAULT 5.0
);

CREATE INDEX IF NOT EXISTS idx_ports_position ON ports USING GIST (position);

-- Seed with major tanker ports (50+)
INSERT INTO ports (name, country, position, port_type) VALUES
-- Western Europe
('Rotterdam', 'NL', ST_SetSRID(ST_MakePoint(4.0, 51.9), 4326)::geography, 'tanker'),
('Algeciras', 'ES', ST_SetSRID(ST_MakePoint(-5.44, 36.13), 4326)::geography, 'tanker'),
('Trieste', 'IT', ST_SetSRID(ST_MakePoint(13.75, 45.65), 4326)::geography, 'tanker'),
('Marsaxlokk', 'MT', ST_SetSRID(ST_MakePoint(14.54, 35.84), 4326)::geography, 'tanker'),
('Immingham', 'GB', ST_SetSRID(ST_MakePoint(-0.19, 53.63), 4326)::geography, 'tanker'),
('Milford Haven', 'GB', ST_SetSRID(ST_MakePoint(-5.05, 51.70), 4326)::geography, 'tanker'),
-- Scandinavia & Baltic
('Gothenburg', 'SE', ST_SetSRID(ST_MakePoint(11.97, 57.71), 4326)::geography, 'tanker'),
('Brofjorden', 'SE', ST_SetSRID(ST_MakePoint(11.45, 58.35), 4326)::geography, 'tanker'),
('Mongstad', 'NO', ST_SetSRID(ST_MakePoint(5.03, 60.81), 4326)::geography, 'tanker'),
('Slagen', 'NO', ST_SetSRID(ST_MakePoint(10.49, 59.30), 4326)::geography, 'tanker'),
('Gdansk', 'PL', ST_SetSRID(ST_MakePoint(18.66, 54.35), 4326)::geography, 'tanker'),
('Skoldvik', 'FI', ST_SetSRID(ST_MakePoint(25.55, 60.31), 4326)::geography, 'tanker'),
-- Mediterranean & Black Sea
('Piraeus', 'GR', ST_SetSRID(ST_MakePoint(23.63, 37.94), 4326)::geography, 'tanker'),
('Kalamata', 'GR', ST_SetSRID(ST_MakePoint(22.11, 37.04), 4326)::geography, 'tanker'),
('Ceuta', 'ES', ST_SetSRID(ST_MakePoint(-5.31, 35.89), 4326)::geography, 'tanker'),
('Sidi Kerir', 'EG', ST_SetSRID(ST_MakePoint(29.68, 31.17), 4326)::geography, 'tanker'),
-- West Africa
('Lome', 'TG', ST_SetSRID(ST_MakePoint(1.28, 6.13), 4326)::geography, 'tanker'),
('Lagos (Apapa)', 'NG', ST_SetSRID(ST_MakePoint(3.39, 6.44), 4326)::geography, 'tanker'),
('Durban', 'ZA', ST_SetSRID(ST_MakePoint(31.02, -29.87), 4326)::geography, 'tanker'),
-- Russian terminals
('Novorossiysk', 'RU', ST_SetSRID(ST_MakePoint(37.77, 44.72), 4326)::geography, 'tanker'),
('Primorsk', 'RU', ST_SetSRID(ST_MakePoint(29.22, 60.35), 4326)::geography, 'tanker'),
('Ust-Luga', 'RU', ST_SetSRID(ST_MakePoint(28.42, 59.68), 4326)::geography, 'tanker'),
('Kozmino', 'RU', ST_SetSRID(ST_MakePoint(132.76, 42.73), 4326)::geography, 'tanker'),
('Murmansk', 'RU', ST_SetSRID(ST_MakePoint(33.09, 68.97), 4326)::geography, 'tanker'),
('Taman', 'RU', ST_SetSRID(ST_MakePoint(36.72, 45.22), 4326)::geography, 'tanker'),
('Vysotsk', 'RU', ST_SetSRID(ST_MakePoint(28.57, 60.63), 4326)::geography, 'tanker'),
-- Major Indian refinery ports
('Sikka (Jamnagar)', 'IN', ST_SetSRID(ST_MakePoint(69.69, 22.42), 4326)::geography, 'tanker'),
('Paradip', 'IN', ST_SetSRID(ST_MakePoint(86.71, 20.26), 4326)::geography, 'tanker'),
('Vadinar', 'IN', ST_SetSRID(ST_MakePoint(69.72, 22.39), 4326)::geography, 'tanker'),
('Mumbai (JNPT)', 'IN', ST_SetSRID(ST_MakePoint(72.95, 18.95), 4326)::geography, 'tanker'),
('Chennai', 'IN', ST_SetSRID(ST_MakePoint(80.29, 13.1), 4326)::geography, 'tanker'),
-- Major Chinese refinery ports
('Qingdao', 'CN', ST_SetSRID(ST_MakePoint(120.38, 36.07), 4326)::geography, 'tanker'),
('Rizhao', 'CN', ST_SetSRID(ST_MakePoint(119.53, 35.39), 4326)::geography, 'tanker'),
('Dongying', 'CN', ST_SetSRID(ST_MakePoint(118.68, 37.45), 4326)::geography, 'tanker'),
('Zhoushan', 'CN', ST_SetSRID(ST_MakePoint(122.1, 30.0), 4326)::geography, 'tanker'),
('Ningbo', 'CN', ST_SetSRID(ST_MakePoint(121.55, 29.87), 4326)::geography, 'tanker'),
('Dalian', 'CN', ST_SetSRID(ST_MakePoint(121.65, 38.91), 4326)::geography, 'tanker'),
-- Turkish refinery ports
('Iskenderun', 'TR', ST_SetSRID(ST_MakePoint(36.17, 36.59), 4326)::geography, 'tanker'),
('Mersin', 'TR', ST_SetSRID(ST_MakePoint(34.63, 36.80), 4326)::geography, 'tanker'),
('Aliaga', 'TR', ST_SetSRID(ST_MakePoint(26.97, 38.80), 4326)::geography, 'tanker'),
('Dortyol', 'TR', ST_SetSRID(ST_MakePoint(36.22, 36.87), 4326)::geography, 'tanker'),
('Ceyhan', 'TR', ST_SetSRID(ST_MakePoint(35.87, 36.88), 4326)::geography, 'tanker'),
-- Caucasus
('Batumi', 'GE', ST_SetSRID(ST_MakePoint(41.64, 41.65), 4326)::geography, 'tanker'),
-- Middle East / Persian Gulf
('Fujairah', 'AE', ST_SetSRID(ST_MakePoint(56.35, 25.12), 4326)::geography, 'tanker'),
('Ras Tanura', 'SA', ST_SetSRID(ST_MakePoint(50.15, 26.64), 4326)::geography, 'tanker'),
('Yanbu', 'SA', ST_SetSRID(ST_MakePoint(38.06, 24.09), 4326)::geography, 'tanker'),
('Kharg Island', 'IR', ST_SetSRID(ST_MakePoint(50.32, 29.24), 4326)::geography, 'tanker'),
('Basra', 'IQ', ST_SetSRID(ST_MakePoint(47.83, 30.50), 4326)::geography, 'tanker'),
('Mina Al Ahmadi', 'KW', ST_SetSRID(ST_MakePoint(48.16, 29.07), 4326)::geography, 'tanker'),
-- Southeast Asia
('Singapore', 'SG', ST_SetSRID(ST_MakePoint(103.85, 1.26), 4326)::geography, 'tanker'),
-- Americas
('Houston', 'US', ST_SetSRID(ST_MakePoint(-95.01, 29.73), 4326)::geography, 'tanker');
