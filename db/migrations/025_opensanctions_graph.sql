-- Migration 025: OpenSanctions Entity Graph
-- Stores the full FTM entity graph from OpenSanctions: entities, relationships, and vessel links.
-- These tables feed the graph model (spec 42) with corporate ownership chains,
-- beneficial owners, and cross-vessel fleet groupings.

BEGIN;

-- =============================================================
-- os_entities: All FTM entities (Vessel, Company, Person, Organization, LegalEntity)
-- =============================================================
CREATE TABLE IF NOT EXISTS os_entities (
    entity_id   TEXT PRIMARY KEY,
    schema_type TEXT NOT NULL,        -- 'Vessel', 'Company', 'Person', 'Organization', 'LegalEntity'
    name        TEXT,
    properties  JSONB NOT NULL DEFAULT '{}',
    topics      TEXT[] NOT NULL DEFAULT '{}',
    target      BOOLEAN NOT NULL DEFAULT FALSE,  -- true if directly sanctioned/listed
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dataset     TEXT
);

CREATE INDEX IF NOT EXISTS idx_os_entities_schema_type ON os_entities (schema_type);
CREATE INDEX IF NOT EXISTS idx_os_entities_topics ON os_entities USING GIN (topics);
CREATE INDEX IF NOT EXISTS idx_os_entities_name ON os_entities (name);
CREATE INDEX IF NOT EXISTS idx_os_entities_target ON os_entities (target) WHERE target = TRUE;

-- =============================================================
-- os_relationships: Ownership, Directorship, Sanction, Family, Associate links
-- =============================================================
CREATE TABLE IF NOT EXISTS os_relationships (
    id                BIGSERIAL PRIMARY KEY,
    rel_type          TEXT NOT NULL,    -- 'ownership', 'directorship', 'sanction', 'family', 'associate'
    source_entity_id  TEXT NOT NULL REFERENCES os_entities(entity_id) ON DELETE CASCADE,
    target_entity_id  TEXT NOT NULL REFERENCES os_entities(entity_id) ON DELETE CASCADE,
    properties        JSONB NOT NULL DEFAULT '{}',
    first_seen        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_os_relationships_source ON os_relationships (source_entity_id);
CREATE INDEX IF NOT EXISTS idx_os_relationships_target ON os_relationships (target_entity_id);
CREATE INDEX IF NOT EXISTS idx_os_relationships_rel_type ON os_relationships (rel_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_os_relationships_unique
    ON os_relationships (rel_type, source_entity_id, target_entity_id);

-- =============================================================
-- os_vessel_links: Links OS Vessel entities to vessel_profiles via IMO/MMSI
-- =============================================================
CREATE TABLE IF NOT EXISTS os_vessel_links (
    entity_id    TEXT NOT NULL REFERENCES os_entities(entity_id) ON DELETE CASCADE,
    imo          INTEGER,
    mmsi         INTEGER,
    confidence   REAL NOT NULL DEFAULT 1.0,
    match_method TEXT NOT NULL,   -- 'imo_exact', 'mmsi_exact', 'name_exact'
    PRIMARY KEY (entity_id, match_method)
);

CREATE INDEX IF NOT EXISTS idx_os_vessel_links_imo ON os_vessel_links (imo);
CREATE INDEX IF NOT EXISTS idx_os_vessel_links_mmsi ON os_vessel_links (mmsi);
CREATE INDEX IF NOT EXISTS idx_os_vessel_links_entity ON os_vessel_links (entity_id);

COMMIT;
