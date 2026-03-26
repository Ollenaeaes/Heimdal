# Feature Spec: OpenSanctions Ownership Graph Extraction

**Slug:** `opensanctions-ownership-graph`
**Created:** 2026-03-26
**Status:** approved
**Priority:** high
**Depends on:** 39-local-dev-bootstrap (for testing locally)

---

## Overview

Extract the full FollowTheMoney (FTM) entity graph from OpenSanctions — not just Vessel entities (which the current `sanctions_matcher.py` handles) but also Company, Person, Ownership, and Directorship relationships. This data feeds the graph model (spec 42) with corporate ownership chains, beneficial owners, and cross-vessel fleet groupings that are critical for shadow fleet detection.

The OpenSanctions default dataset (2.4GB NDJSON at `/data/opensanctions/default.json`) already contains all entity types. The current pipeline filters to Vessel entities only and discards everything else. This spec extracts the rest.

## Problem Statement

The graph scoring spec requires signals B1-B7 (ownership depth, company creation date, cross-vessel ownership, jurisdiction risk). Currently OpenSanctions data only provides: "is this vessel sanctioned?" It cannot answer: "who owns this vessel? do they own other sanctioned vessels? when was the owning company created? how many layers of shell companies exist?"

## Out of Scope

- NOT: Changing the existing vessel sanctions matching (sanctions_matcher.py stays as-is for backward compatibility)
- NOT: Graph database setup (spec 42)
- NOT: Scoring logic (spec 42)
- NOT: Fuzzy company name matching across data sources (future enhancement)
- NOT: Real-time OpenSanctions API integration (we use bulk data)

---

## Data Source Verification

**Confirmed available in OpenSanctions FTM data** (verified against `/data/opensanctions/default.json`):

| Entity Type | Present | Key Properties |
|------------|---------|----------------|
| Vessel | Yes | name, imoNumber, mmsiNumber, flag, tonnage, type, buildDate, previousName, topics |
| Company | Yes | name, country, registrationNumber, incorporationDate, sector, topics |
| Person | Yes | name, nationality, birthDate, topics |
| Organization | Yes | name, country, topics |
| Ownership | Yes | owner (entity ref), asset (entity ref), role, startDate, endDate |
| Directorship | Yes | director (entity ref), organization (entity ref), role, startDate, endDate |
| Sanction | Yes | entity (ref), program, authority, startDate, listingDate |

**What's NOT directly available:**
- `jurisdiction` as a standalone field on Company — derived from `country` property
- `ism_company_number` — this comes from Paris MoU data, not OpenSanctions. Ownership graph and ISM fleet grouping are separate concepts that get merged in the graph (spec 42).
- Some vessels have minimal data (name only, no IMO) — these can only be matched fuzzily

---

## User Stories

### Story 1: Database Schema for Entity Graph

**As a** system
**I want to** store OpenSanctions entities and their relationships in structured tables
**So that** the graph builder can construct ownership chains

**Acceptance Criteria:**

- GIVEN a new migration WHEN applied THEN table `os_entities` exists with columns: entity_id (text PK), schema_type (text — 'Vessel', 'Company', 'Person', 'Organization'), name (text), properties (jsonb), topics (text[]), target (boolean — true if directly sanctioned/listed), first_seen (timestamptz), last_seen (timestamptz), dataset (text)
- GIVEN the migration WHEN applied THEN table `os_relationships` exists with columns: id (bigserial PK), rel_type (text — 'ownership', 'directorship', 'sanction', 'family', 'associate'), source_entity_id (text FK), target_entity_id (text FK), properties (jsonb — role, startDate, endDate, program, etc.), first_seen (timestamptz), last_seen (timestamptz)
- GIVEN the migration WHEN applied THEN table `os_vessel_links` exists with columns: entity_id (text FK to os_entities), imo (integer), mmsi (integer), confidence (real), match_method (text — 'imo_exact', 'mmsi_exact', 'name_exact') — this links OS Vessel entities to vessel_profiles
- GIVEN the tables WHEN indexed THEN os_entities has indexes on: (schema_type), GIN on (topics), (name) for text search
- GIVEN the tables WHEN indexed THEN os_relationships has indexes on: (source_entity_id), (target_entity_id), (rel_type)
- GIVEN the tables WHEN indexed THEN os_vessel_links has indexes on: (imo), (mmsi), (entity_id)

**Test Requirements:**

- [ ] Test: Migration creates all three tables with correct column types
- [ ] Test: Foreign keys from os_relationships to os_entities work
- [ ] Test: GIN index on topics array enables efficient topic filtering
- [ ] Test: os_vessel_links links an entity_id to an imo number

**Technical Notes:**

- Migration file: `db/migrations/025_opensanctions_graph.sql`
- `target` boolean distinguishes entities that are directly on a sanctions list from entities that are merely connected to one
- topics array stores: 'sanction', 'debarment', 'poi', 'crime.fraud', 'shadow_fleet', etc.
- properties JSONB stores all FTM properties verbatim for future use

---

### Story 2: FTM Entity Extractor

**As a** system
**I want to** parse the full OpenSanctions FTM dump and extract all relevant entity types
**So that** Company, Person, and relationship data is available for graph construction

**Acceptance Criteria:**

- GIVEN the OpenSanctions NDJSON file WHEN processed THEN all entities with schema in ('Vessel', 'Company', 'Person', 'Organization', 'LegalEntity') are extracted and stored in os_entities
- GIVEN Ownership schema entities WHEN processed THEN they produce os_relationships rows with rel_type='ownership', source_entity_id=owner, target_entity_id=asset
- GIVEN Directorship schema entities WHEN processed THEN they produce os_relationships rows with rel_type='directorship', source_entity_id=director, target_entity_id=organization
- GIVEN Sanction schema entities WHEN processed THEN they produce os_relationships rows with rel_type='sanction', linking the sanctioned entity to a program record
- GIVEN Vessel entities with IMO numbers WHEN processed THEN os_vessel_links rows are created linking entity_id to imo with confidence=1.0 and match_method='imo_exact'
- GIVEN Vessel entities with MMSI numbers WHEN processed THEN os_vessel_links rows are created with confidence=0.9 and match_method='mmsi_exact'
- GIVEN the extractor WHEN run on the full dataset THEN it processes the 2.4GB file in streaming mode (line-by-line) without loading the entire file into memory
- GIVEN the extractor WHEN complete THEN it logs: entity counts by schema_type, relationship counts by rel_type, vessel link counts, elapsed time

**Test Requirements:**

- [ ] Test: Extractor parses a Vessel entity and stores correct name, properties, topics
- [ ] Test: Extractor parses a Company entity with incorporationDate and stores it in properties
- [ ] Test: Extractor creates ownership relationship linking Company → Person
- [ ] Test: Extractor creates vessel_link for a Vessel with IMO number
- [ ] Test: Extractor handles entities with missing optional fields
- [ ] Test: Memory usage stays bounded during full file processing (streaming, not bulk load)

**Technical Notes:**

- Location: `services/opensanctions/extractor.py` or `shared/parsers/opensanctions_ftm.py`
- FTM entity format: `{"id": "...", "schema": "Vessel", "properties": {"name": ["..."], "imoNumber": ["..."]}, "target": true}`
- Properties are arrays (FTM convention) — take first value for scalar fields
- Ownership entities have `asset` and `owner` properties pointing to entity IDs
- The file is 2.4GB — must use streaming (readline), not json.load()

---

### Story 3: Historical Batch Load (Local)

**As a** developer
**I want to** load the full OpenSanctions entity graph into my local database
**So that** the graph builder has complete ownership chain data

**Acceptance Criteria:**

- GIVEN a batch script WHEN run locally THEN it calls the FTM extractor on `/data/opensanctions/default.json`
- GIVEN the extraction WHEN complete THEN all entities and relationships are in the local database
- GIVEN the script WHEN run with `--stats` THEN it prints: total entities, entities by type, total relationships, relationships by type, total vessel links
- GIVEN the script WHEN run again (re-run) THEN it upserts entities (updates last_seen, merges properties) rather than duplicating

**Test Requirements:**

- [ ] Test: Batch load populates os_entities with Vessel, Company, Person entities
- [ ] Test: Batch load populates os_relationships with ownership and directorship links
- [ ] Test: Running batch load twice does not create duplicate entities
- [ ] Test: Stats output shows non-zero counts for all entity types

**Technical Notes:**

- Script location: `scripts/load_opensanctions.py`
- Use COPY or batch INSERT for performance
- Consider creating a smaller test fixture (first 10k lines of the NDJSON) for fast test iteration

---

### Story 4: Daily Incremental Sync (VPS)

**As a** system operator
**I want to** automatically update OpenSanctions data daily
**So that** new sanctions designations and ownership changes are captured

**Acceptance Criteria:**

- GIVEN a daily cron job WHEN it runs THEN it downloads the latest OpenSanctions default dataset
- GIVEN a new dataset WHEN downloaded THEN the extractor runs and upserts all entities/relationships
- GIVEN entities that existed in the previous dataset but not the new one WHEN detected THEN they are NOT deleted (OpenSanctions occasionally removes and re-adds entities)
- GIVEN the sync WHEN complete THEN it logs: entities added, entities updated, relationships added/updated
- GIVEN the existing `scripts/download-opensanctions.sh` WHEN used THEN the sync reuses it for the download step

**Test Requirements:**

- [ ] Test: Sync downloads the file successfully
- [ ] Test: Sync processes the file and updates entity counts
- [ ] Test: Entities not in the new dataset retain their last_seen timestamp (not deleted)

**Technical Notes:**

- Reuse `scripts/download-opensanctions.sh` for download
- The full file is re-processed each time (OpenSanctions doesn't provide deltas for the default dataset)
- This is acceptable — the extractor is streaming and the dataset, while 2.4GB, processes in minutes
- Run as part of the batch-pipeline or as a separate daily cron

---

## Implementation Order

1. Story 1 (DB schema) — foundation
2. Story 2 (FTM extractor) — independent of DB but needed for stories 3-4
3. Story 3 (historical batch) — depends on 1+2, runs locally
4. Story 4 (daily sync) — depends on 1+2, runs on VPS

Stories 1 and 2 can run in parallel. Stories 3 and 4 are sequential after 1+2.

## Architecture Decisions

- **Separate tables from existing sanctions_status** — the existing `vessel_profiles.sanctions_status` JSONB and `sanctions_matcher.py` continue to work for backward compatibility. The new os_entities/os_relationships tables are the source of truth for the graph builder.
- **Entity IDs are OpenSanctions IDs** — stable across updates, used as graph node identifiers
- **No graph database yet** — this spec stores relational data. Spec 42 builds the graph from these tables.
- **FTM properties stored as JSONB** — future-proof; new fields from OpenSanctions are automatically preserved
- **No deletion on sync** — entities may temporarily disappear from OpenSanctions during data quality updates; we preserve them with last_seen timestamps
