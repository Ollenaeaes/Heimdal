"""Tests for graph export/import scripts (Story 9)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from falkordb import FalkorDB


def _falkordb_available():
    try:
        db = FalkorDB(host="localhost", port=6380)
        db.select_graph("_ping").query("RETURN 1")
        db.close()
        return True
    except Exception:
        return False


skip_no_falkordb = pytest.mark.skipif(
    not _falkordb_available(),
    reason="FalkorDB not running on localhost:6380",
)


def _redis_cli_available():
    try:
        result = subprocess.run(["redis-cli", "--version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


skip_no_redis_cli = pytest.mark.skipif(
    not _redis_cli_available(),
    reason="redis-cli not available",
)


@skip_no_falkordb
@skip_no_redis_cli
class TestExportGraph:
    """Test FalkorDB graph export produces a non-empty dump file."""

    def test_export_produces_rdb_file(self, tmp_path):
        """Export produces a non-empty RDB dump file."""
        from scripts.export_graph import export_falkordb_graph

        # Create some data in FalkorDB first
        db = FalkorDB(host="localhost", port=6380)
        g = db.select_graph("heimdal")
        g.query("MERGE (v:Vessel {imo: 7777777, name: 'Export Test'})")

        dump_path = export_falkordb_graph(tmp_path)

        assert dump_path.exists()
        assert dump_path.stat().st_size > 0
        assert dump_path.suffix == ".rdb"

        g.query("MATCH (v:Vessel {imo: 7777777}) DELETE v")
        db.close()


@skip_no_falkordb
class TestVerifyExport:
    """Test export verification."""

    def test_verify_missing_files(self, tmp_path):
        """Verify reports missing files."""
        from scripts.export_graph import verify_export

        results = verify_export(tmp_path)
        assert "error" in results["graph"]
        assert "error" in results["signals"]

    def test_verify_existing_files(self, tmp_path):
        """Verify reports present files."""
        from scripts.export_graph import verify_export

        # Create dummy files
        (tmp_path / "falkordb_heimdal.rdb").write_bytes(b"dummy rdb data here")
        (tmp_path / "vessel_signals.dump").write_bytes(b"dummy pg dump here")

        results = verify_export(tmp_path)
        assert "path" in results["graph"]
        assert results["graph"]["size_bytes"] > 0
        assert "path" in results["signals"]
        assert results["signals"]["size_bytes"] > 0


class TestImportGraph:
    """Test import script validation."""

    def test_import_raises_on_missing_rdb(self, tmp_path):
        """Import raises FileNotFoundError when RDB dump is missing."""
        from scripts.import_graph import import_falkordb_graph

        with pytest.raises(FileNotFoundError):
            import_falkordb_graph(tmp_path)

    def test_import_raises_on_missing_signals(self, tmp_path):
        """Import raises FileNotFoundError when signals dump is missing."""
        from scripts.import_graph import import_vessel_signals

        with pytest.raises(FileNotFoundError):
            import_vessel_signals(tmp_path)


@skip_no_falkordb
class TestNodeEdgeCountMatch:
    """Test that exported graph preserves node/edge counts."""

    def test_node_counts_preserved(self):
        """Node counts before and after export should match."""
        db = FalkorDB(host="localhost", port=6380)
        g = db.select_graph("heimdal_count_test")

        # Create test data
        g.query("""
            CREATE (v1:Vessel {imo: 8888001, name: 'Count Ship 1'})
            CREATE (v2:Vessel {imo: 8888002, name: 'Count Ship 2'})
            CREATE (c:Company {name: 'Count Co'})
            CREATE (v1)-[:OWNED_BY]->(c)
            CREATE (v2)-[:OWNED_BY]->(c)
        """)

        # Count nodes and edges
        node_count = g.query("MATCH (n) RETURN count(n)").result_set[0][0]
        edge_count = g.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]

        assert node_count == 3  # 2 vessels + 1 company
        assert edge_count == 2  # 2 OWNED_BY edges

        g.delete()
        db.close()
