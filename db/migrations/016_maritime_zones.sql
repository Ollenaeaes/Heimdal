-- 016_maritime_zones.sql
-- Maritime boundary zones: EEZ (200nm) and Territorial Sea (12nm).
-- Loaded from Flanders Marine Institute (VLIZ) shapefiles.
--
-- Two tables:
--   maritime_zones      — polygon zones for spatial containment queries ("is vessel in Norwegian EEZ?")
--   maritime_boundaries — boundary lines for map display (lightweight, no coastline complexity)

-- ============================================================
-- Zone polygons (for spatial queries)
-- ============================================================
CREATE TABLE IF NOT EXISTS maritime_zones (
    id          SERIAL PRIMARY KEY,
    zone_type   VARCHAR(16) NOT NULL,          -- 'eez' or '12nm'
    mrgid       INTEGER,                        -- VLIZ Marine Region ID
    geoname     VARCHAR(256),                   -- e.g. "Norwegian Exclusive Economic Zone"
    sovereign   VARCHAR(128),                   -- sovereign state name
    iso_sov     VARCHAR(8),                     -- ISO 3166 code of sovereign
    territory   VARCHAR(128),                   -- territory name (may differ from sovereign)
    iso_ter     VARCHAR(8),                     -- ISO code of territory
    pol_type    VARCHAR(80),                    -- polygon type from source
    area_km2    BIGINT,                         -- area in square kilometers (12nm only)
    geometry    GEOGRAPHY(MULTIPOLYGON, 4326) NOT NULL,
    metadata    JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_maritime_zones_geometry
    ON maritime_zones USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_maritime_zones_type
    ON maritime_zones (zone_type);

CREATE INDEX IF NOT EXISTS idx_maritime_zones_iso_sov
    ON maritime_zones (iso_sov);

CREATE INDEX IF NOT EXISTS idx_maritime_zones_type_iso
    ON maritime_zones (zone_type, iso_sov);

-- ============================================================
-- Boundary lines (for map display — much lighter than polygons)
-- ============================================================
CREATE TABLE IF NOT EXISTS maritime_boundaries (
    id          SERIAL PRIMARY KEY,
    boundary_type VARCHAR(16) NOT NULL,        -- 'eez' or '12nm'
    line_id     INTEGER,                        -- original LINE_ID from VLIZ
    line_name   VARCHAR(256),                   -- e.g. "Norway - Russia"
    line_type   VARCHAR(256),                   -- e.g. "Agreed", "Median", "200 NM"
    sovereign1  VARCHAR(128),
    sovereign2  VARCHAR(128),
    eez1        VARCHAR(256),
    eez2        VARCHAR(256),
    length_km   REAL,
    geometry    GEOGRAPHY(LINESTRING, 4326) NOT NULL,
    metadata    JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_maritime_boundaries_geometry
    ON maritime_boundaries USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_maritime_boundaries_type
    ON maritime_boundaries (boundary_type);
