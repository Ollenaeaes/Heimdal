"""Tests for FalkorDB infrastructure (Story 1) and graph schema (Story 2).

These tests require a running FalkorDB instance on localhost:6380.
They are skipped if FalkorDB is not available.
"""

import pytest
from falkordb import FalkorDB

# Use a dedicated test graph to avoid polluting the main graph
TEST_GRAPH_NAME = "heimdal_test"


def _falkordb_available():
    """Check if FalkorDB is running on localhost:6380."""
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
    """Provide a clean FalkorDB test graph, deleted after each test."""
    db = FalkorDB(host="localhost", port=6380)
    g = db.select_graph(TEST_GRAPH_NAME)
    yield g
    try:
        g.delete()
    except Exception:
        pass
    db.close()


# =========================================================================
# Story 1: FalkorDB Infrastructure
# =========================================================================


@skip_no_falkordb
class TestFalkorDBInfrastructure:
    """Test FalkorDB container connectivity and basic operations."""

    def test_connection_and_ping(self):
        """FalkorDB container accepts connections."""
        db = FalkorDB(host="localhost", port=6380)
        g = db.select_graph("_test_ping")
        result = g.query("RETURN 1 AS n")
        assert result.result_set == [[1]]
        g.delete()
        db.close()

    def test_create_and_query_node(self, graph):
        """Python client can create a node and query it back."""
        graph.query(
            "CREATE (v:Vessel {imo: $imo, name: $name})",
            {"imo": "1234567", "name": "Test Vessel"},
        )
        result = graph.query(
            "MATCH (v:Vessel {imo: $imo}) RETURN v.name",
            {"imo": "1234567"},
        )
        assert result.result_set == [["Test Vessel"]]

    def test_data_persists_within_session(self, graph):
        """Data is queryable after creation in the same session."""
        graph.query("CREATE (c:Company {name: 'Acme Shipping'})")
        result = graph.query("MATCH (c:Company) RETURN c.name")
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "Acme Shipping"

    def test_config_settings(self):
        """FalkorDB config is present in shared settings."""
        from shared.config import settings

        assert settings.falkordb.host == "localhost"
        assert settings.falkordb.port == 6380
        assert settings.falkordb.graph_name == "heimdal"

    def test_graph_client_module(self):
        """shared.db.graph module provides get_graph/close_graph."""
        from shared.db.graph import close_graph, get_client, get_graph

        assert callable(get_client)
        assert callable(get_graph)
        assert callable(close_graph)


# =========================================================================
# Story 2: Graph Node & Edge Schema
# =========================================================================


@skip_no_falkordb
class TestGraphSchema:
    """Test graph schema: node types, edge types, temporal edges, indexes."""

    def test_create_vessel_with_all_attributes(self, graph):
        """Create a Vessel node with all attributes and query it back."""
        graph.query(
            """
            CREATE (v:Vessel {
                imo: '9876543',
                name: 'Nordic Star',
                mmsi: '258123000',
                ship_type: 'Oil Tanker',
                gross_tonnage: 85000,
                build_year: 2008,
                score: 7,
                classification: 'red',
                last_psc_date: '2025-11-15',
                last_psc_port: 'Rotterdam',
                deficiency_count: 5,
                ism_deficiency: true,
                detained: false,
                last_seen_date: '2026-03-25',
                last_seen_lat: 59.45,
                last_seen_lon: 10.73
            })
            """
        )
        result = graph.query(
            "MATCH (v:Vessel {imo: '9876543'}) "
            "RETURN v.name, v.classification, v.gross_tonnage, v.detained"
        )
        row = result.result_set[0]
        assert row[0] == "Nordic Star"
        assert row[1] == "red"
        assert row[2] == 85000
        assert row[3] is False

    def test_temporal_classed_by_edge(self, graph):
        """Create temporal CLASSED_BY edges — active and historical."""
        graph.query(
            """
            CREATE (v:Vessel {imo: '1111111', name: 'Test Ship'})
            CREATE (cs1:ClassSociety {name: 'Lloyd Register', iacs_member: true})
            CREATE (cs2:ClassSociety {name: 'DNV', iacs_member: true})
            CREATE (v)-[:CLASSED_BY {from_date: '2020-01-01', to_date: '2024-06-15', status: 'withdrawn'}]->(cs1)
            CREATE (v)-[:CLASSED_BY {from_date: '2024-06-15', to_date: null, status: 'active'}]->(cs2)
            """
        )
        # Query active edges (to_date is null)
        result = graph.query(
            """
            MATCH (v:Vessel {imo: '1111111'})-[e:CLASSED_BY]->(cs:ClassSociety)
            WHERE e.to_date IS NULL
            RETURN cs.name, e.status
            """
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "DNV"
        assert result.result_set[0][1] == "active"

        # Query all edges (historical + active)
        all_edges = graph.query(
            """
            MATCH (v:Vessel {imo: '1111111'})-[e:CLASSED_BY]->(cs:ClassSociety)
            RETURN cs.name, e.status
            ORDER BY e.from_date
            """
        )
        assert len(all_edges.result_set) == 2

    def test_ownership_chain(self, graph):
        """Create OWNED_BY chain: Vessel→Company→Company→Person."""
        graph.query(
            """
            CREATE (v:Vessel {imo: '2222222', name: 'Shadow Runner'})
            CREATE (c1:Company {name: 'Shadow Maritime Ltd', jurisdiction: 'Marshall Islands'})
            CREATE (c2:Company {name: 'Dark Pool Holdings', jurisdiction: 'Seychelles'})
            CREATE (p:Person {name: 'Ivan Petrov', nationality: 'RU'})
            CREATE (v)-[:OWNED_BY {from_date: '2023-01-01', to_date: null}]->(c1)
            CREATE (c1)-[:OWNED_BY {from_date: '2022-06-01', to_date: null}]->(c2)
            CREATE (c2)-[:OWNED_BY {from_date: '2021-01-01', to_date: null}]->(p)
            """
        )
        # Query full ownership chain from vessel to ultimate beneficial owner
        result = graph.query(
            """
            MATCH (v:Vessel {imo: '2222222'})-[:OWNED_BY*1..3]->(owner)
            RETURN labels(owner)[0] AS type, owner.name
            """
        )
        names = [row[1] for row in result.result_set]
        assert "Shadow Maritime Ltd" in names
        assert "Dark Pool Holdings" in names
        assert "Ivan Petrov" in names

    def test_indexes_created(self, graph):
        """Graph initialization creates indexes on key properties."""
        from services.graph_builder.schema import init_graph

        stats = init_graph(graph)
        assert stats["indexes_created"] > 0

        # Verify index on Vessel.imo works — query by indexed property
        graph.query("CREATE (v:Vessel {imo: '9999999', name: 'Indexed Ship'})")
        result = graph.query("MATCH (v:Vessel {imo: '9999999'}) RETURN v.name")
        assert result.result_set == [["Indexed Ship"]]

    def test_sts_partner_edge(self, graph):
        """STS_PARTNER edges store event metadata."""
        graph.query(
            """
            CREATE (v1:Vessel {imo: '3333333', name: 'Tanker A'})
            CREATE (v2:Vessel {imo: '4444444', name: 'Tanker B'})
            CREATE (v1)-[:STS_PARTNER {
                event_date: '2026-02-10',
                latitude: 36.5,
                longitude: 22.8,
                duration_hours: 4.5
            }]->(v2)
            """
        )
        result = graph.query(
            """
            MATCH (v1:Vessel)-[e:STS_PARTNER]->(v2:Vessel)
            RETURN v1.imo, v2.imo, e.duration_hours, e.latitude
            """
        )
        assert len(result.result_set) == 1
        row = result.result_set[0]
        assert row[0] == "3333333"
        assert row[1] == "4444444"
        assert row[2] == 4.5

    def test_flag_state_and_insured_by(self, graph):
        """Create FlagState and PIClub nodes with edges."""
        graph.query(
            """
            CREATE (v:Vessel {imo: '5555555', name: 'Flag Test'})
            CREATE (f:FlagState {name: 'Gabon', iso_code: 'GA', paris_mou_list: 'black'})
            CREATE (p:PIClub {name: 'West of England', ig_member: true})
            CREATE (v)-[:FLAGGED_AS {from_date: '2024-01-01', to_date: null}]->(f)
            CREATE (v)-[:INSURED_BY {from_date: '2024-01-01', to_date: null}]->(p)
            """
        )
        result = graph.query(
            """
            MATCH (v:Vessel {imo: '5555555'})-[:FLAGGED_AS]->(f:FlagState)
            RETURN f.iso_code, f.paris_mou_list
            """
        )
        assert result.result_set[0] == ["GA", "black"]

    def test_managed_by_and_directed_by(self, graph):
        """MANAGED_BY and DIRECTED_BY edges."""
        graph.query(
            """
            CREATE (v:Vessel {imo: '6666666', name: 'Managed Ship'})
            CREATE (c:Company {name: 'ISM Managers Co', ism_company_number: '12345'})
            CREATE (p:Person {name: 'Dmitry Smirnov'})
            CREATE (v)-[:MANAGED_BY {from_date: '2023-06-01', to_date: null}]->(c)
            CREATE (c)-[:DIRECTED_BY {from_date: '2020-01-01', to_date: null}]->(p)
            """
        )
        # Query from vessel through company to director
        result = graph.query(
            """
            MATCH (v:Vessel {imo: '6666666'})-[:MANAGED_BY]->(c:Company)-[:DIRECTED_BY]->(p:Person)
            RETURN p.name
            """
        )
        assert result.result_set == [["Dmitry Smirnov"]]

    def test_pi_clubs_seeded(self, graph):
        """init_graph seeds IG P&I Club nodes."""
        from services.graph_builder.schema import init_graph

        stats = init_graph(graph)
        assert stats["pi_clubs_seeded"] == 13

        result = graph.query(
            "MATCH (p:PIClub {ig_member: true}) RETURN count(p)"
        )
        assert result.result_set[0][0] == 13

    def test_no_sanction_programme_node(self, graph):
        """Sanctions are attributes on Vessel, NOT a separate node type."""
        from services.graph_builder.schema import NODE_TYPES

        assert "SanctionProgramme" not in NODE_TYPES

    def test_schema_definitions_complete(self):
        """All expected node and edge types are defined."""
        from services.graph_builder.schema import EDGE_TYPES, NODE_TYPES

        assert set(NODE_TYPES.keys()) == {
            "Vessel", "Company", "Person", "ClassSociety", "FlagState", "PIClub",
        }
        assert set(EDGE_TYPES.keys()) == {
            "OWNED_BY", "MANAGED_BY", "CLASSED_BY", "FLAGGED_AS",
            "INSURED_BY", "DIRECTED_BY", "STS_PARTNER",
        }
        # All temporal edges have from_date/to_date
        for edge_name, edge_def in EDGE_TYPES.items():
            if edge_def["temporal"]:
                assert "from_date" in edge_def["attributes"]
                assert "to_date" in edge_def["attributes"]
