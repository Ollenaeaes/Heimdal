"""Tests for OpenSanctions FTM entity graph extractor.

Uses synthetic NDJSON fixtures to test parsing of all entity types,
relationships, vessel links, streaming behavior, and edge cases.
"""

import json
import tempfile
from pathlib import Path

import pytest

from shared.parsers.opensanctions_ftm import (
    EntityRecord,
    ExtractionBatch,
    ExtractorStats,
    RelationshipRecord,
    VesselLinkRecord,
    _extract_vessel_links,
    _first_prop,
    _parse_entity,
    _parse_int,
    _parse_relationship,
    stream_extract,
)


# ---------------------------------------------------------------------------
# Fixtures: synthetic FTM entities
# ---------------------------------------------------------------------------

def _vessel_entity(
    entity_id: str = "os-vessel-001",
    name: str = "ATLANTIC STAR",
    imo: str = "9321172",
    mmsi: str = "636092441",
    flag: str = "LR",
    target: bool = True,
) -> dict:
    return {
        "id": entity_id,
        "schema": "Vessel",
        "properties": {
            "name": [name],
            "imoNumber": [imo] if imo else [],
            "mmsiNumber": [mmsi] if mmsi else [],
            "flag": [flag] if flag else [],
            "topics": ["sanction"] if target else [],
        },
        "target": target,
        "datasets": ["opensanctions"],
    }


def _company_entity(
    entity_id: str = "os-company-001",
    name: str = "Black Sea Shipping Ltd",
    country: str = "PA",
    incorporation_date: str = "2019-03-15",
    target: bool = False,
) -> dict:
    return {
        "id": entity_id,
        "schema": "Company",
        "properties": {
            "name": [name],
            "country": [country],
            "incorporationDate": [incorporation_date],
            "topics": [],
        },
        "target": target,
        "datasets": ["opensanctions"],
    }


def _person_entity(
    entity_id: str = "os-person-001",
    name: str = "Nikolai Petrov",
    nationality: str = "RU",
    target: bool = True,
) -> dict:
    return {
        "id": entity_id,
        "schema": "Person",
        "properties": {
            "name": [name],
            "nationality": [nationality],
            "topics": ["sanction"] if target else [],
        },
        "target": target,
        "datasets": ["eu_sanctions"],
    }


def _organization_entity(
    entity_id: str = "os-org-001",
    name: str = "Sovcomflot",
    country: str = "RU",
) -> dict:
    return {
        "id": entity_id,
        "schema": "Organization",
        "properties": {
            "name": [name],
            "country": [country],
            "topics": [],
        },
        "target": False,
        "datasets": ["opensanctions"],
    }


def _ownership_entity(
    entity_id: str = "os-own-001",
    owner_id: str = "os-company-001",
    asset_id: str = "os-vessel-001",
    role: str = "Beneficial Owner",
    start_date: str = "2020-01-01",
) -> dict:
    return {
        "id": entity_id,
        "schema": "Ownership",
        "properties": {
            "owner": [owner_id],
            "asset": [asset_id],
            "role": [role],
            "startDate": [start_date],
        },
        "target": False,
        "datasets": ["opensanctions"],
    }


def _directorship_entity(
    entity_id: str = "os-dir-001",
    director_id: str = "os-person-001",
    org_id: str = "os-company-001",
    role: str = "Director",
) -> dict:
    return {
        "id": entity_id,
        "schema": "Directorship",
        "properties": {
            "director": [director_id],
            "organization": [org_id],
            "role": [role],
        },
        "target": False,
        "datasets": ["opensanctions"],
    }


def _sanction_entity(
    entity_id: str = "os-sanction-001",
    sanctioned_id: str = "os-vessel-001",
    program: str = "EU Regulation 833/2014",
) -> dict:
    """Sanction entity — links to one entity only, no second endpoint."""
    return {
        "id": entity_id,
        "schema": "Sanction",
        "properties": {
            "entity": [sanctioned_id],
            "program": [program],
            "authority": ["European Union"],
            "listingDate": ["2022-04-08"],
        },
        "target": False,
        "datasets": ["eu_sanctions"],
    }


def _write_ndjson(entities: list[dict], path: Path) -> None:
    """Write a list of entity dicts as NDJSON."""
    with open(path, "w") as f:
        for e in entities:
            f.write(json.dumps(e) + "\n")


@pytest.fixture
def sample_ndjson(tmp_path: Path) -> Path:
    """Create a small NDJSON fixture with all entity types."""
    entities = [
        _vessel_entity(),
        _company_entity(),
        _person_entity(),
        _organization_entity(),
        _ownership_entity(),
        _directorship_entity(),
        _sanction_entity(),
        # A second vessel with MMSI only (no IMO)
        _vessel_entity(
            entity_id="os-vessel-002",
            name="DARK SHADOW",
            imo="",
            mmsi="123456789",
            target=False,
        ),
    ]
    filepath = tmp_path / "default.json"
    _write_ndjson(entities, filepath)
    return filepath


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------

class TestFirstProp:
    def test_returns_first_value(self):
        assert _first_prop({"name": ["Foo", "Bar"]}, "name") == "Foo"

    def test_returns_none_for_missing_key(self):
        assert _first_prop({}, "name") is None

    def test_returns_none_for_empty_list(self):
        assert _first_prop({"name": []}, "name") is None


class TestParseInt:
    def test_numeric_string(self):
        assert _parse_int("9321172") == 9321172

    def test_imo_prefixed(self):
        assert _parse_int("IMO9321172") == 9321172

    def test_none(self):
        assert _parse_int(None) is None

    def test_empty(self):
        assert _parse_int("") is None

    def test_non_numeric(self):
        assert _parse_int("unknown") is None


# ---------------------------------------------------------------------------
# Unit tests: entity parsing
# ---------------------------------------------------------------------------

class TestParseEntity:
    def test_vessel_entity(self):
        raw = _vessel_entity()
        record = _parse_entity(raw)
        assert record.entity_id == "os-vessel-001"
        assert record.schema_type == "Vessel"
        assert record.name == "ATLANTIC STAR"
        assert record.target is True
        assert "sanction" in record.topics
        assert record.dataset == "opensanctions"

    def test_company_entity_with_incorporation_date(self):
        raw = _company_entity()
        record = _parse_entity(raw)
        assert record.entity_id == "os-company-001"
        assert record.schema_type == "Company"
        assert record.name == "Black Sea Shipping Ltd"
        assert record.properties.get("incorporationDate") == ["2019-03-15"]
        assert record.target is False

    def test_person_entity(self):
        raw = _person_entity()
        record = _parse_entity(raw)
        assert record.schema_type == "Person"
        assert record.name == "Nikolai Petrov"
        assert record.target is True

    def test_entity_with_missing_optional_fields(self):
        raw = {
            "id": "os-minimal",
            "schema": "Company",
            "properties": {},
            "target": False,
        }
        record = _parse_entity(raw)
        assert record.entity_id == "os-minimal"
        assert record.name is None
        assert record.topics == []
        assert record.dataset is None


# ---------------------------------------------------------------------------
# Unit tests: relationship parsing
# ---------------------------------------------------------------------------

class TestParseRelationship:
    def test_ownership_relationship(self):
        raw = _ownership_entity()
        rel = _parse_relationship(raw)
        assert rel is not None
        assert rel.rel_type == "ownership"
        assert rel.source_entity_id == "os-company-001"
        assert rel.target_entity_id == "os-vessel-001"
        assert rel.properties.get("role") == "Beneficial Owner"
        assert rel.properties.get("startDate") == "2020-01-01"

    def test_directorship_relationship(self):
        raw = _directorship_entity()
        rel = _parse_relationship(raw)
        assert rel is not None
        assert rel.rel_type == "directorship"
        assert rel.source_entity_id == "os-person-001"
        assert rel.target_entity_id == "os-company-001"
        assert rel.properties.get("role") == "Director"

    def test_sanction_skipped_no_target(self):
        """Sanction entities only have one endpoint — skipped as relationship."""
        raw = _sanction_entity()
        rel = _parse_relationship(raw)
        assert rel is None  # Sanction has entity but no second endpoint

    def test_unknown_schema_returns_none(self):
        raw = {"id": "x", "schema": "Address", "properties": {}}
        rel = _parse_relationship(raw)
        assert rel is None

    def test_missing_source_returns_none(self):
        raw = {
            "id": "x",
            "schema": "Ownership",
            "properties": {"asset": ["os-vessel-001"]},
        }
        rel = _parse_relationship(raw)
        assert rel is None


# ---------------------------------------------------------------------------
# Unit tests: vessel link extraction
# ---------------------------------------------------------------------------

class TestExtractVesselLinks:
    def test_vessel_with_imo(self):
        raw = _vessel_entity(imo="9321172")
        links = _extract_vessel_links(raw)
        imo_links = [l for l in links if l.match_method == "imo_exact"]
        assert len(imo_links) == 1
        assert imo_links[0].imo == 9321172
        assert imo_links[0].confidence == 1.0

    def test_vessel_with_mmsi(self):
        raw = _vessel_entity(mmsi="636092441")
        links = _extract_vessel_links(raw)
        mmsi_links = [l for l in links if l.match_method == "mmsi_exact"]
        assert len(mmsi_links) == 1
        assert mmsi_links[0].mmsi == 636092441
        assert mmsi_links[0].confidence == 0.9

    def test_vessel_with_imo_prefix(self):
        raw = _vessel_entity(imo="IMO9321172")
        links = _extract_vessel_links(raw)
        imo_links = [l for l in links if l.match_method == "imo_exact"]
        assert len(imo_links) == 1
        assert imo_links[0].imo == 9321172

    def test_vessel_with_empty_imo(self):
        raw = _vessel_entity(imo="")
        links = _extract_vessel_links(raw)
        imo_links = [l for l in links if l.match_method == "imo_exact"]
        assert len(imo_links) == 0

    def test_vessel_with_both_imo_and_mmsi(self):
        raw = _vessel_entity(imo="9321172", mmsi="636092441")
        links = _extract_vessel_links(raw)
        assert len(links) == 2


# ---------------------------------------------------------------------------
# Integration: stream_extract
# ---------------------------------------------------------------------------

class TestStreamExtract:
    def test_extracts_all_entity_types(self, sample_ndjson: Path):
        all_batches = list(stream_extract(sample_ndjson, batch_size=100))
        assert len(all_batches) >= 1

        # Collect all records across batches
        all_entities = []
        all_rels = []
        all_links = []
        for batch, stats in all_batches:
            all_entities.extend(batch.entities)
            all_rels.extend(batch.relationships)
            all_links.extend(batch.vessel_links)

        # Should have 6 entities: 2 vessels + 1 company + 1 person + 1 org + (ownership/directorship are relationships, not entities)
        # Actually: Vessel, Company, Person, Organization = 4 ENTITY_SCHEMAS + second vessel = 5
        entity_types = {e.schema_type for e in all_entities}
        assert "Vessel" in entity_types
        assert "Company" in entity_types
        assert "Person" in entity_types
        assert "Organization" in entity_types
        assert len(all_entities) == 5  # 2 vessels + company + person + org

    def test_extracts_relationships(self, sample_ndjson: Path):
        all_rels = []
        for batch, _ in stream_extract(sample_ndjson, batch_size=100):
            all_rels.extend(batch.relationships)

        # ownership + directorship (sanction has no target, skipped)
        assert len(all_rels) == 2
        rel_types = {r.rel_type for r in all_rels}
        assert "ownership" in rel_types
        assert "directorship" in rel_types

    def test_extracts_vessel_links(self, sample_ndjson: Path):
        all_links = []
        for batch, _ in stream_extract(sample_ndjson, batch_size=100):
            all_links.extend(batch.vessel_links)

        # Vessel 1: IMO + MMSI = 2 links; Vessel 2: MMSI only = 1 link
        assert len(all_links) == 3
        imo_links = [l for l in all_links if l.match_method == "imo_exact"]
        mmsi_links = [l for l in all_links if l.match_method == "mmsi_exact"]
        assert len(imo_links) == 1
        assert len(mmsi_links) == 2

    def test_stats_are_accurate(self, sample_ndjson: Path):
        final_stats = None
        for _, stats in stream_extract(sample_ndjson, batch_size=100):
            final_stats = stats

        assert final_stats is not None
        assert final_stats.total_entities == 5
        assert final_stats.entities_by_type["Vessel"] == 2
        assert final_stats.entities_by_type["Company"] == 1
        assert final_stats.entities_by_type["Person"] == 1
        assert final_stats.total_relationships == 2
        assert final_stats.vessel_links == 3
        assert final_stats.lines_processed == 8
        assert final_stats.elapsed_seconds > 0

    def test_batching(self, sample_ndjson: Path):
        """With batch_size=2, should yield multiple batches."""
        batches = list(stream_extract(sample_ndjson, batch_size=2))
        # 5 entities + 2 rels + 3 links = 10 records, batch_size 2 → at least 3 batches
        assert len(batches) >= 2

    def test_handles_empty_lines(self, tmp_path: Path):
        filepath = tmp_path / "empty_lines.json"
        entities = [_vessel_entity()]
        with open(filepath, "w") as f:
            f.write("\n")
            f.write(json.dumps(entities[0]) + "\n")
            f.write("\n")
            f.write("\n")
        all_entities = []
        for batch, _ in stream_extract(filepath, batch_size=100):
            all_entities.extend(batch.entities)
        assert len(all_entities) == 1

    def test_handles_malformed_json(self, tmp_path: Path):
        filepath = tmp_path / "malformed.json"
        with open(filepath, "w") as f:
            f.write("{bad json\n")
            f.write(json.dumps(_vessel_entity()) + "\n")
        all_entities = []
        final_stats = None
        for batch, stats in stream_extract(filepath, batch_size=100):
            all_entities.extend(batch.entities)
            final_stats = stats
        assert len(all_entities) == 1
        assert final_stats.lines_skipped == 1

    def test_handles_entities_with_missing_id(self, tmp_path: Path):
        filepath = tmp_path / "no_id.json"
        with open(filepath, "w") as f:
            f.write(json.dumps({"schema": "Vessel", "properties": {"name": ["Test"]}}) + "\n")
            f.write(json.dumps(_vessel_entity()) + "\n")
        all_entities = []
        for batch, _ in stream_extract(filepath, batch_size=100):
            all_entities.extend(batch.entities)
        assert len(all_entities) == 1

    def test_file_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            list(stream_extract(tmp_path / "nonexistent.json"))

    def test_memory_bounded_streaming(self, tmp_path: Path):
        """Verify streaming processes line by line, not loading all into memory."""
        filepath = tmp_path / "large.json"
        # Write 100 entities — not truly large but verifies streaming behavior
        with open(filepath, "w") as f:
            for i in range(100):
                f.write(json.dumps(_vessel_entity(entity_id=f"v-{i}", imo=str(9000000 + i))) + "\n")

        batch_count = 0
        total_entities = 0
        for batch, _ in stream_extract(filepath, batch_size=10):
            batch_count += 1
            total_entities += len(batch.entities)
            # Each batch should have at most ~10 entities (might have links too)
            assert len(batch.entities) <= 20  # generous bound accounting for vessel links

        assert batch_count >= 5  # 100 entities with batch_size=10, but links push batches
        assert total_entities == 100
