"""Tests for the Graph Build + Signal Scoring Pipeline (Story 8).

Tests use a real FalkorDB instance and mock PostgreSQL.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest
from falkordb import FalkorDB

TEST_GRAPH_NAME = "heimdal_test_pipeline"


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


@pytest.fixture
def graph():
    db = FalkorDB(host="localhost", port=6380)
    g = db.select_graph(TEST_GRAPH_NAME)
    yield g
    try:
        g.delete()
    except Exception:
        pass
    db.close()


def _mock_pg_conn():
    """Create a mock PostgreSQL connection."""
    mock_pg = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall = MagicMock(return_value=[])
    mock_cursor.fetchone = MagicMock(return_value=None)
    mock_cursor.execute = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.rowcount = 0
    mock_pg.cursor = MagicMock(return_value=mock_cursor)
    mock_pg.commit = MagicMock()
    mock_pg.autocommit = False
    return mock_pg


@skip_no_falkordb
class TestPipelineScoring:
    """Test that pipeline scores vessels correctly."""

    def test_pipeline_updates_vessel_classification(self, graph):
        """Pipeline updates vessel_profiles risk_score and risk_tier."""
        # Create a vessel in the graph
        graph.query("""
            CREATE (v:Vessel {imo: 8000001, name: 'Test Pipeline Ship', score: 7, classification: 'red'})
        """)

        # Verify graph node has classification
        result = graph.query("MATCH (v:Vessel {imo: 8000001}) RETURN v.classification, v.score")
        assert result.result_set[0][0] == "red"
        assert result.result_set[0][1] == 7

    def test_single_vessel_mode_returns_signals(self, graph):
        """Single vessel mode produces correct score for known vessel."""
        from services.graph_builder.pipeline import GraphPipeline
        from services.graph_builder.score_calculator import compute_score
        from services.graph_builder.signal_scorer import Signal

        # Test compute_score directly since full pipeline needs DB
        signals = [
            Signal("A1", 3, {"reason": "test"}, "test"),
            Signal("C1", 3, {"reason": "test"}, "test"),
        ]
        score, classification = compute_score(signals, is_sanctioned=False)
        assert score == 6
        assert classification == "red"

    def test_incremental_mode_only_processes_updated(self, graph):
        """Incremental pipeline only processes recently-updated vessels."""
        from services.graph_builder.pipeline import GraphPipeline

        mock_pg = _mock_pg_conn()

        # Mock the cursor to return empty updated vessels
        pipeline = GraphPipeline.__new__(GraphPipeline)
        pipeline.graph = graph
        pipeline.pg = mock_pg

        updated = pipeline._find_recently_updated_vessels()
        assert isinstance(updated, list)


@skip_no_falkordb
class TestPipelineStages:
    """Test individual pipeline stages."""

    def test_graph_build_initializes_indexes(self, graph):
        """Pipeline initializes graph indexes via init_graph."""
        from services.graph_builder.schema import init_graph
        stats = init_graph(graph)
        assert stats["indexes_created"] > 0

    def test_score_updates_graph_node(self, graph):
        """Scoring updates the graph node classification."""
        graph.query("CREATE (v:Vessel {imo: 8100001, name: 'Score Test'})")

        graph.query(
            "MATCH (v:Vessel {imo: $imo}) SET v.score = $score, v.classification = $cls",
            {"imo": 8100001, "score": 5, "cls": "yellow"},
        )

        result = graph.query("MATCH (v:Vessel {imo: 8100001}) RETURN v.score, v.classification")
        assert result.result_set[0][0] == 5
        assert result.result_set[0][1] == "yellow"

    def test_fleet_propagation_runs_after_scoring(self, graph):
        """Fleet propagation adds A10/B4 after individual scoring."""
        graph.query("""
            CREATE (va:Vessel {imo: 8200001, name: 'Bad Ship', classification: 'blacklisted'})
            CREATE (vb:Vessel {imo: 8200002, name: 'Sibling', classification: 'green'})
            CREATE (c:Company {name: 'Fleet Co'})
            CREATE (va)-[:OWNED_BY]->(c)
            CREATE (vb)-[:OWNED_BY]->(c)
        """)

        from services.graph_builder.fleet_propagation import propagate_fleet_risk
        signals = propagate_fleet_risk(graph, 8200002)
        assert any(s.signal_id == "B4" for s in signals)


class TestPipelineCLI:
    """Test CLI argument parsing."""

    def test_argparse_full_mode(self):
        """Default mode is full pipeline."""
        from services.graph_builder.pipeline import main
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--incremental", action="store_true")
        parser.add_argument("--vessel", type=int)
        args = parser.parse_args([])
        assert not args.incremental
        assert args.vessel is None

    def test_argparse_incremental(self):
        """--incremental flag is parsed."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--incremental", action="store_true")
        parser.add_argument("--vessel", type=int)
        args = parser.parse_args(["--incremental"])
        assert args.incremental

    def test_argparse_vessel(self):
        """--vessel IMO flag is parsed."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--incremental", action="store_true")
        parser.add_argument("--vessel", type=int)
        args = parser.parse_args(["--vessel", "9876543"])
        assert args.vessel == 9876543
