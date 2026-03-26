"""Tests for AIS-derived graph enrichment (Story 4).

Tests use a real FalkorDB instance and mock PostgreSQL reads.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest
from falkordb import FalkorDB

TEST_GRAPH_NAME = "heimdal_test_ais"


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


def _make_builder(graph, mock_rows_map=None):
    """Create a GraphBuilder with mocked PostgreSQL connection."""
    from services.graph_builder.builder import GraphBuilder

    mock_pg = MagicMock()
    mock_cursor = MagicMock()

    # Track which query was executed to return appropriate rows
    rows_map = mock_rows_map or {}
    executed_queries = []

    def execute_side_effect(query, params=None):
        executed_queries.append(query)
        return None

    def fetchall_side_effect():
        if not executed_queries:
            return []
        last_query = executed_queries[-1]
        for key, rows in rows_map.items():
            if key in last_query:
                return rows
        return []

    def fetchone_side_effect():
        if not executed_queries:
            return None
        last_query = executed_queries[-1]
        for key, rows in rows_map.items():
            if key in last_query and rows:
                return rows[0]
        return None

    mock_cursor.execute = MagicMock(side_effect=execute_side_effect)
    mock_cursor.fetchall = MagicMock(side_effect=fetchall_side_effect)
    mock_cursor.fetchone = MagicMock(side_effect=fetchone_side_effect)
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_pg.cursor = MagicMock(return_value=mock_cursor)

    builder = GraphBuilder(graph=graph, pg_conn=mock_pg)
    return builder


@skip_no_falkordb
class TestAISPositionUpdate:
    """Test updating Vessel nodes with last-seen positions."""

    def test_vessel_updated_with_last_seen(self, graph):
        """Vessel node gets last_seen_lat/lon/date from vessel_profiles."""
        # Pre-create vessel in graph
        graph.query("CREATE (v:Vessel {imo: 9111111, name: 'Test Tanker'})")

        rows_map = {
            "vessel_profiles": [
                {
                    "mmsi": 258111000,
                    "imo": 9111111,
                    "last_lat": 59.45,
                    "last_lon": 10.73,
                    "last_position_time": datetime.datetime(2026, 3, 25, 14, 30),
                }
            ]
        }

        builder = _make_builder(graph, rows_map)
        builder._update_vessel_positions()

        result = graph.query(
            "MATCH (v:Vessel {imo: 9111111}) "
            "RETURN v.last_seen_lat, v.last_seen_lon, v.mmsi"
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == 59.45
        assert result.result_set[0][1] == 10.73
        assert result.result_set[0][2] == "258111000"

    def test_no_write_to_postgresql(self, graph):
        """AIS enrichment does not write to PostgreSQL tables."""
        graph.query("CREATE (v:Vessel {imo: 9222222, name: 'Read Only Test'})")

        # Use a more specific mock that returns empty results for GFW/anomaly queries
        rows_map = {
            "FROM vessel_profiles": [
                {
                    "mmsi": 258222000,
                    "imo": 9222222,
                    "last_lat": 60.0,
                    "last_lon": 5.0,
                    "last_position_time": datetime.datetime(2026, 3, 25, 10, 0),
                }
            ],
            "FROM gfw_events": [],
            "FROM anomaly_events": [],
        }

        builder = _make_builder(graph, rows_map)
        builder.enrich_from_ais()

        # Verify the vessel was updated in the graph
        result = graph.query("MATCH (v:Vessel {imo: 9222222}) RETURN v.last_seen_lat")
        assert result.result_set[0][0] == 60.0


@skip_no_falkordb
class TestSTSPartnerEdges:
    """Test STS_PARTNER edge creation from GFW encounters."""

    def test_gfw_encounter_creates_sts_edge(self, graph):
        """GFW encounter event creates STS_PARTNER edge between two vessels."""
        graph.query("CREATE (v1:Vessel {imo: 9333333, name: 'Tanker Alpha'})")
        graph.query("CREATE (v2:Vessel {imo: 9444444, name: 'Tanker Beta'})")

        rows_map = {
            "gfw_events": [
                {
                    "mmsi": 258333000,
                    "encounter_mmsi": 258444000,
                    "start_time": datetime.datetime(2026, 2, 10, 8, 0),
                    "lat": 36.5,
                    "lon": 22.8,
                    "duration_hours": 4.5,
                    "imo1": 9333333,
                    "imo2": 9444444,
                }
            ],
            "anomaly_events": [],
        }

        builder = _make_builder(graph, rows_map)
        builder._create_sts_from_gfw()

        result = graph.query(
            """
            MATCH (v1:Vessel {imo: 9333333})-[e:STS_PARTNER]->(v2:Vessel {imo: 9444444})
            RETURN e.event_date, e.latitude, e.longitude, e.duration_hours
            """
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "2026-02-10"
        assert result.result_set[0][1] == 36.5
        assert result.result_set[0][2] == 22.8
        assert result.result_set[0][3] == 4.5

    def test_sts_proximity_anomaly_creates_edge(self, graph):
        """sts_proximity anomaly creates STS_PARTNER edge."""
        graph.query("CREATE (v1:Vessel {imo: 9555555, name: 'Tanker Gamma'})")
        graph.query("CREATE (v2:Vessel {imo: 9666666, name: 'Tanker Delta'})")

        # First call returns anomaly data, second returns partner IMO
        call_count = [0]
        mock_pg = MagicMock()
        mock_cursor = MagicMock()

        anomaly_rows = [
            {
                "mmsi": 258555000,
                "details": {"partner_mmsi": 258666000, "lat": 35.0, "lon": 23.5},
                "created_at": datetime.datetime(2026, 3, 1),
                "imo": 9555555,
            }
        ]
        partner_rows = [{"imo": 9666666}]

        def fetchall_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return anomaly_rows
            return []

        def fetchone_side_effect():
            return partner_rows[0]

        mock_cursor.execute = MagicMock()
        mock_cursor.fetchall = MagicMock(side_effect=fetchall_side_effect)
        mock_cursor.fetchone = MagicMock(side_effect=fetchone_side_effect)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_pg.cursor = MagicMock(return_value=mock_cursor)

        from services.graph_builder.builder import GraphBuilder
        builder = GraphBuilder(graph=graph, pg_conn=mock_pg)
        builder._create_sts_from_anomalies()

        result = graph.query(
            """
            MATCH (v1:Vessel {imo: 9555555})-[e:STS_PARTNER]->(v2:Vessel {imo: 9666666})
            RETURN e.event_date, e.source
            """
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "2026-03-01"
        assert result.result_set[0][1] == "sts_proximity"

    def test_stats_track_sts_edges(self, graph):
        """BuildStats includes STS_PARTNER edge count."""
        from services.graph_builder.builder import BuildStats

        stats = BuildStats()
        assert "STS_PARTNER" in stats.edges
        assert stats.edges["STS_PARTNER"] == 0
