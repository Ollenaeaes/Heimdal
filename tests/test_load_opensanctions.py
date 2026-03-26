"""Tests for scripts/load_opensanctions.py batch load script.

Tests the persist_batch function with mock DB connections and verifies
the script's argument parsing and flow.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Add project root so we can import the script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.parsers.opensanctions_ftm import (
    EntityRecord,
    ExtractionBatch,
    RelationshipRecord,
    VesselLinkRecord,
)
from scripts.load_opensanctions import persist_batch, get_db_connection, print_db_stats


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_conn():
    """Mock psycopg2 connection with cursor."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    return conn


@pytest.fixture
def sample_batch():
    """A batch with one entity, one relationship, one vessel link."""
    return ExtractionBatch(
        entities=[
            EntityRecord(
                entity_id="e-001",
                schema_type="Vessel",
                name="ATLANTIC STAR",
                properties={"imoNumber": ["9321172"]},
                topics=["sanction"],
                target=True,
                dataset="opensanctions",
            ),
            EntityRecord(
                entity_id="e-002",
                schema_type="Company",
                name="Dark Shipping LLC",
                properties={"country": ["PA"]},
                topics=[],
                target=False,
                dataset="opensanctions",
            ),
        ],
        relationships=[
            RelationshipRecord(
                rel_type="ownership",
                source_entity_id="e-002",
                target_entity_id="e-001",
                properties={"role": "Beneficial Owner"},
            ),
        ],
        vessel_links=[
            VesselLinkRecord(
                entity_id="e-001",
                imo=9321172,
                mmsi=None,
                confidence=1.0,
                match_method="imo_exact",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Tests: persist_batch
# ---------------------------------------------------------------------------

class TestPersistBatch:
    def test_inserts_entities(self, mock_conn, sample_batch):
        counts = persist_batch(mock_conn, sample_batch)
        assert counts["entities"] == 2
        cursor = mock_conn.cursor.return_value
        # Should have called execute for each entity
        entity_calls = [
            c for c in cursor.execute.call_args_list
            if "os_entities" in str(c)
        ]
        assert len(entity_calls) == 2

    def test_inserts_relationships(self, mock_conn, sample_batch):
        counts = persist_batch(mock_conn, sample_batch)
        assert counts["relationships"] == 1
        cursor = mock_conn.cursor.return_value
        rel_calls = [
            c for c in cursor.execute.call_args_list
            if "os_relationships" in str(c)
        ]
        assert len(rel_calls) == 1

    def test_inserts_vessel_links(self, mock_conn, sample_batch):
        counts = persist_batch(mock_conn, sample_batch)
        assert counts["vessel_links"] == 1
        cursor = mock_conn.cursor.return_value
        link_calls = [
            c for c in cursor.execute.call_args_list
            if "os_vessel_links" in str(c)
        ]
        assert len(link_calls) == 1

    def test_commits_after_batch(self, mock_conn, sample_batch):
        persist_batch(mock_conn, sample_batch)
        mock_conn.commit.assert_called_once()

    def test_entity_upsert_sql_has_on_conflict(self, mock_conn, sample_batch):
        persist_batch(mock_conn, sample_batch)
        cursor = mock_conn.cursor.return_value
        entity_calls = [
            c for c in cursor.execute.call_args_list
            if "os_entities" in str(c)
        ]
        sql = entity_calls[0][0][0]  # First positional arg of execute
        assert "ON CONFLICT" in sql
        assert "entity_id" in sql

    def test_relationship_upsert_sql_has_on_conflict(self, mock_conn, sample_batch):
        persist_batch(mock_conn, sample_batch)
        cursor = mock_conn.cursor.return_value
        rel_calls = [
            c for c in cursor.execute.call_args_list
            if "os_relationships" in str(c)
        ]
        sql = rel_calls[0][0][0]
        assert "ON CONFLICT" in sql

    def test_empty_batch_commits_without_error(self, mock_conn):
        empty_batch = ExtractionBatch()
        counts = persist_batch(mock_conn, empty_batch)
        assert counts["entities"] == 0
        assert counts["relationships"] == 0
        assert counts["vessel_links"] == 0
        mock_conn.commit.assert_called_once()

    def test_entity_properties_serialized_as_json(self, mock_conn, sample_batch):
        persist_batch(mock_conn, sample_batch)
        cursor = mock_conn.cursor.return_value
        entity_calls = [
            c for c in cursor.execute.call_args_list
            if "os_entities" in str(c)
        ]
        # The 4th param (index 3) should be JSON-serialized properties
        params = entity_calls[0][0][1]
        props_param = params[3]  # properties is 4th after entity_id, schema_type, name
        assert isinstance(props_param, str)
        parsed = json.loads(props_param)
        assert "imoNumber" in parsed


# ---------------------------------------------------------------------------
# Tests: integration with stream_extract
# ---------------------------------------------------------------------------

class TestBatchLoadIntegration:
    def test_full_pipeline_with_mock_db(self, tmp_path, mock_conn):
        """End-to-end: NDJSON file → stream_extract → persist_batch."""
        from shared.parsers.opensanctions_ftm import stream_extract

        # Write a small NDJSON fixture
        entities = [
            {
                "id": "v1", "schema": "Vessel",
                "properties": {"name": ["TEST VESSEL"], "imoNumber": ["1234567"]},
                "target": True, "datasets": ["os"],
            },
            {
                "id": "c1", "schema": "Company",
                "properties": {"name": ["Test Corp"]},
                "target": False, "datasets": ["os"],
            },
            {
                "id": "o1", "schema": "Ownership",
                "properties": {"owner": ["c1"], "asset": ["v1"]},
                "target": False, "datasets": ["os"],
            },
        ]
        filepath = tmp_path / "test.json"
        with open(filepath, "w") as f:
            for e in entities:
                f.write(json.dumps(e) + "\n")

        totals = {"entities": 0, "relationships": 0, "vessel_links": 0}
        for batch, stats in stream_extract(filepath, batch_size=100):
            counts = persist_batch(mock_conn, batch)
            for key in totals:
                totals[key] += counts[key]

        assert totals["entities"] == 2   # Vessel + Company
        assert totals["relationships"] == 1  # Ownership
        assert totals["vessel_links"] == 1   # IMO link

    def test_rerun_does_not_duplicate(self, tmp_path, mock_conn):
        """Running twice should call ON CONFLICT upsert, not fail."""
        from shared.parsers.opensanctions_ftm import stream_extract

        entities = [
            {
                "id": "v1", "schema": "Vessel",
                "properties": {"name": ["TEST"]},
                "target": False, "datasets": ["os"],
            },
        ]
        filepath = tmp_path / "test.json"
        with open(filepath, "w") as f:
            for e in entities:
                f.write(json.dumps(e) + "\n")

        # Run twice
        for _ in range(2):
            for batch, _ in stream_extract(filepath, batch_size=100):
                persist_batch(mock_conn, batch)

        # Should have committed twice (once per run)
        assert mock_conn.commit.call_count == 2


# ---------------------------------------------------------------------------
# Tests: print_db_stats
# ---------------------------------------------------------------------------

class TestPrintDbStats:
    def test_prints_all_sections(self, mock_conn, capsys):
        cursor = mock_conn.cursor.return_value
        # Mock the various SELECT queries in order
        cursor.fetchone.side_effect = [
            (100,),   # total entities
            (50,),    # total relationships
            (30,),    # total vessel links
            (20,),    # target entities
        ]
        cursor.fetchall.side_effect = [
            [("Vessel", 40), ("Company", 35), ("Person", 25)],  # entities by type
            [("ownership", 30), ("directorship", 20)],          # rels by type
            [("imo_exact", 20), ("mmsi_exact", 10)],            # links by method
        ]

        print_db_stats(mock_conn)
        output = capsys.readouterr().out
        assert "Total entities: 100" in output
        assert "Vessel: 40" in output
        assert "Total relationships: 50" in output
        assert "ownership: 30" in output
        assert "Total vessel links: 30" in output
        assert "imo_exact: 20" in output
        assert "sanctioned/listed entities: 20" in output


# ---------------------------------------------------------------------------
# Tests: get_db_connection
# ---------------------------------------------------------------------------

class TestGetDbConnection:
    @patch("scripts.load_opensanctions.psycopg2", create=True)
    def test_converts_asyncpg_url(self, mock_psycopg2):
        """Async URL prefix is converted to sync."""
        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            # Re-import to use patched module
            import importlib
            import scripts.load_opensanctions as module
            importlib.reload(module)
            module.get_db_connection("postgresql+asyncpg://user:pass@host/db")
            mock_psycopg2.connect.assert_called_once_with("postgresql://user:pass@host/db")
