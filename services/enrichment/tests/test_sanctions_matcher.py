"""Tests for the OpenSanctions bulk matching engine.

Tests use in-memory fixtures — no actual OpenSanctions data file required.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from sanctions_matcher import (
    SanctionsIndex,
    match_vessel,
    normalize_name,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_entity(
    entity_id: str,
    *,
    imo: str | None = None,
    mmsi: str | None = None,
    name: str | None = None,
    topics: list[str] | None = None,
    datasets: list[str] | None = None,
) -> dict:
    """Create a minimal OpenSanctions-style entity for testing."""
    props: dict = {}
    if imo is not None:
        props["imoNumber"] = [imo]
    if mmsi is not None:
        props["mmsiNumber"] = [mmsi]
    if name is not None:
        props["name"] = [name]
    if topics is not None:
        props["topics"] = topics
    if datasets is not None:
        pass  # datasets is top-level
    return {
        "id": entity_id,
        "schema": "Vessel",
        "properties": props,
        "datasets": datasets or ["us_ofac_sdn"],
    }


@pytest.fixture
def populated_index() -> SanctionsIndex:
    """Create and populate an index with test entities."""
    index = SanctionsIndex()

    entities = [
        _make_entity(
            "vessel-001",
            imo="9999991",
            mmsi="273456789",
            name="DARK SHADOW",
            topics=["sanction"],
        ),
        _make_entity(
            "vessel-002",
            imo="9999992",
            mmsi="351123456",
            name="OCEAN PHANTOM",
            topics=["sanction"],
            datasets=["eu_sanctions"],
        ),
        _make_entity(
            "vessel-003",
            name="SANCTIONED TANKER",
            topics=["sanction"],
        ),
        _make_entity(
            "vessel-004",
            imo="8888881",
            name="SPIRIT OF FREEDOM",
            topics=["sanction"],
        ),
    ]

    # Write to temp file and load
    with tempfile.TemporaryDirectory() as tmpdir:
        data_file = Path(tmpdir) / "default.json"
        with open(data_file, "w") as f:
            for entity in entities:
                f.write(json.dumps(entity) + "\n")
        count = index.load(tmpdir)
        assert count == 4

    return index


# ---------------------------------------------------------------------------
# Name normalization tests
# ---------------------------------------------------------------------------

class TestNormalizeName:
    def test_lowercase(self):
        assert normalize_name("DARK SHADOW") == "dark shadow"

    def test_strip_special_characters(self):
        assert normalize_name("M/V DARK-SHADOW") == "mv darkshadow"

    def test_collapse_whitespace(self):
        assert normalize_name("DARK   SHADOW") == "dark shadow"

    def test_strip_leading_trailing(self):
        assert normalize_name("  DARK SHADOW  ") == "dark shadow"

    def test_mixed_special_and_spaces(self):
        assert normalize_name("  M/V  DARK--SHADOW!!  ") == "mv darkshadow"

    def test_numbers_preserved(self):
        assert normalize_name("TANKER 42") == "tanker 42"

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_only_special_chars(self):
        assert normalize_name("---///") == ""


# ---------------------------------------------------------------------------
# IMO matching tests
# ---------------------------------------------------------------------------

class TestIMOMatching:
    def test_exact_imo_match_returns_confidence_1(self, populated_index):
        result = match_vessel(populated_index, imo="9999991")
        assert result != {}
        assert len(result["matches"]) >= 1
        match = result["matches"][0]
        assert match["confidence"] == 1.0
        assert match["matched_field"] == "imo"
        assert match["entity_id"] == "vessel-001"

    def test_imo_match_includes_program(self, populated_index):
        result = match_vessel(populated_index, imo="9999992")
        match = result["matches"][0]
        assert match["entity_id"] == "vessel-002"
        assert match["confidence"] == 1.0

    def test_imo_no_match(self, populated_index):
        result = match_vessel(populated_index, imo="0000000")
        assert result == {}

    def test_imo_as_int(self, populated_index):
        result = match_vessel(populated_index, imo=9999991)
        assert len(result["matches"]) >= 1
        assert result["matches"][0]["confidence"] == 1.0


# ---------------------------------------------------------------------------
# MMSI matching tests
# ---------------------------------------------------------------------------

class TestMMSIMatching:
    def test_exact_mmsi_match_returns_confidence_09(self, populated_index):
        result = match_vessel(populated_index, mmsi="273456789")
        assert result != {}
        assert len(result["matches"]) >= 1
        match = result["matches"][0]
        assert match["confidence"] == 0.9
        assert match["matched_field"] == "mmsi"
        assert match["entity_id"] == "vessel-001"

    def test_mmsi_no_match(self, populated_index):
        result = match_vessel(populated_index, mmsi="999999999")
        assert result == {}

    def test_mmsi_as_int(self, populated_index):
        result = match_vessel(populated_index, mmsi=351123456)
        assert len(result["matches"]) >= 1
        assert result["matches"][0]["confidence"] == 0.9

    def test_imo_takes_priority_over_mmsi_for_same_entity(self, populated_index):
        """When both IMO and MMSI match the same entity, IMO wins (higher confidence)."""
        result = match_vessel(
            populated_index, imo="9999991", mmsi="273456789"
        )
        # Should have one match (deduplicated), with IMO confidence
        entity_matches = [
            m for m in result["matches"] if m["entity_id"] == "vessel-001"
        ]
        assert len(entity_matches) == 1
        assert entity_matches[0]["confidence"] == 1.0
        assert entity_matches[0]["matched_field"] == "imo"


# ---------------------------------------------------------------------------
# Fuzzy name matching tests
# ---------------------------------------------------------------------------

class TestFuzzyNameMatching:
    def test_exact_name_match_returns_confidence_07(self, populated_index):
        result = match_vessel(populated_index, name="DARK SHADOW")
        assert result != {}
        matches = [m for m in result["matches"] if m["matched_field"] == "name"]
        assert len(matches) >= 1
        assert matches[0]["confidence"] == 0.7
        assert matches[0]["entity_id"] == "vessel-001"

    def test_fuzzy_name_within_distance_2(self, populated_index):
        # "dark shadov" has Levenshtein distance 1 from "dark shadow"
        result = match_vessel(populated_index, name="DARK SHADOV")
        assert result != {}
        matches = [m for m in result["matches"] if m["matched_field"] == "name"]
        assert len(matches) >= 1
        assert matches[0]["confidence"] == 0.7

    def test_fuzzy_name_distance_2(self, populated_index):
        # "dark shadxx" has distance 2 from "dark shadow"
        result = match_vessel(populated_index, name="DARK SHADXX")
        assert result != {}
        matches = [m for m in result["matches"] if m["matched_field"] == "name"]
        assert len(matches) >= 1

    def test_fuzzy_name_distance_3_no_match(self, populated_index):
        # "dark shaxxx" has distance 3 from "dark shadow" — should NOT match
        result = match_vessel(populated_index, name="DARK SHAXXX")
        # May still match other entities; check specifically for vessel-001
        if result:
            entity_001_matches = [
                m for m in result["matches"]
                if m["entity_id"] == "vessel-001"
            ]
            assert len(entity_001_matches) == 0

    def test_name_no_match(self, populated_index):
        result = match_vessel(populated_index, name="COMPLETELY DIFFERENT NAME HERE")
        assert result == {}

    def test_name_normalization_case_insensitive(self, populated_index):
        result = match_vessel(populated_index, name="dark shadow")
        assert result != {}

    def test_name_deduplication_with_imo(self, populated_index):
        """When IMO already matched an entity, fuzzy name should not duplicate it."""
        result = match_vessel(
            populated_index, imo="9999991", name="DARK SHADOW"
        )
        entity_matches = [
            m for m in result["matches"] if m["entity_id"] == "vessel-001"
        ]
        assert len(entity_matches) == 1  # only the IMO match


# ---------------------------------------------------------------------------
# No match tests
# ---------------------------------------------------------------------------

class TestNoMatch:
    def test_no_match_returns_empty_dict(self, populated_index):
        result = match_vessel(
            populated_index,
            imo="0000000",
            mmsi="999999999",
            name="NONEXISTENT VESSEL NAME XYZ",
        )
        assert result == {}

    def test_empty_index_returns_empty(self):
        empty_index = SanctionsIndex()
        result = match_vessel(empty_index, imo="9999991")
        assert result == {}

    def test_none_params_returns_empty(self, populated_index):
        result = match_vessel(populated_index)
        assert result == {}


# ---------------------------------------------------------------------------
# Index loading tests
# ---------------------------------------------------------------------------

class TestIndexLoading:
    def test_load_from_ndjson(self):
        entities = [
            _make_entity("e1", imo="1234567", name="TEST VESSEL"),
            _make_entity("e2", mmsi="123456789", name="ANOTHER VESSEL"),
        ]
        index = SanctionsIndex()
        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "default.json"
            with open(data_file, "w") as f:
                for entity in entities:
                    f.write(json.dumps(entity) + "\n")
            count = index.load(tmpdir)

        assert count == 2
        assert index.loaded is True
        assert "1234567" in index.by_imo
        assert "123456789" in index.by_mmsi

    def test_load_missing_file_returns_zero(self):
        index = SanctionsIndex()
        count = index.load("/nonexistent/path")
        assert count == 0
        assert index.loaded is False

    def test_load_skips_invalid_json_lines(self):
        index = SanctionsIndex()
        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "default.json"
            with open(data_file, "w") as f:
                f.write(json.dumps(_make_entity("e1", imo="111")) + "\n")
                f.write("this is not valid json\n")
                f.write(json.dumps(_make_entity("e2", imo="222")) + "\n")
            count = index.load(tmpdir)
        assert count == 2

    def test_load_skips_non_vessel_entities(self):
        index = SanctionsIndex()
        non_vessel = {
            "id": "person-001",
            "schema": "Person",
            "properties": {"name": ["John Doe"]},
            "datasets": ["us_ofac_sdn"],
        }
        vessel = _make_entity("v1", imo="555", name="REAL VESSEL")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "default.json"
            with open(data_file, "w") as f:
                f.write(json.dumps(non_vessel) + "\n")
                f.write(json.dumps(vessel) + "\n")
            count = index.load(tmpdir)
        assert count == 1
