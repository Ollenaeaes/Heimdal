"""Tests for GraphBuilder — Static Data Sources (Story 3).

Tests mock PostgreSQL reads and use a real FalkorDB instance on localhost:6380.
Skipped if FalkorDB is not available.
"""

import pytest
from unittest.mock import MagicMock, patch
from falkordb import FalkorDB

from services.graph_builder.builder import GraphBuilder, BuildStats

# ---------------------------------------------------------------------------
# FalkorDB availability check & fixtures
# ---------------------------------------------------------------------------

TEST_GRAPH_NAME = "heimdal_test_builder"


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
    """Provide a clean FalkorDB test graph, deleted after each test."""
    db = FalkorDB(host="localhost", port=6380)
    g = db.select_graph(TEST_GRAPH_NAME)
    yield g
    try:
        g.delete()
    except Exception:
        pass
    db.close()


@pytest.fixture
def mock_pg():
    """Return a mock psycopg2 connection with a context-managed cursor."""
    conn = MagicMock()
    cursor = MagicMock()
    # Support context manager: `with conn.cursor(...) as cur:`
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


def _make_builder(graph, mock_pg_conn):
    """Create a GraphBuilder with the test graph and mock PG connection."""
    builder = GraphBuilder(graph=graph, pg_conn=mock_pg_conn)
    return builder


# ---------------------------------------------------------------------------
# Paris MoU Tests
# ---------------------------------------------------------------------------


@skip_no_falkordb
class TestParisMoU:
    """Test graph building from Paris MoU inspections."""

    def test_inspection_creates_vessel_node(self, graph, mock_pg):
        """Paris MoU inspection creates Vessel node with correct attributes."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        # Mock flag performance
        cursor.fetchall.side_effect = [
            # _load_flag_performance
            [{"iso_code": "PA", "list_status": "white"}],
            # main inspections query
            [{
                "imo": 9876543,
                "ship_name": "Nordic Star",
                "flag_state": "PA",
                "ship_type": "Oil Tanker",
                "gross_tonnage": 85000,
                "inspection_date": "2025-11-15",
                "detained": False,
                "deficiency_count": 3,
                "ism_deficiency": False,
                "ro_at_inspection": "DNV",
                "pi_provider_at_inspection": "The Standard Club",
                "pi_is_ig_member": True,
                "ism_company_imo": "1234567",
                "ism_company_name": "Nordic Maritime AS",
            }],
        ]

        builder.build_from_paris_mou()

        # Verify Vessel node
        result = graph.query(
            "MATCH (v:Vessel {imo: 9876543}) "
            "RETURN v.name, v.ship_type, v.gross_tonnage, v.deficiency_count, v.detained"
        )
        assert len(result.result_set) == 1
        row = result.result_set[0]
        assert row[0] == "Nordic Star"
        assert row[1] == "Oil Tanker"
        assert row[2] == 85000
        assert row[3] == 3
        assert row[4] is False

        # Verify CLASSED_BY edge
        result = graph.query(
            "MATCH (v:Vessel {imo: 9876543})-[e:CLASSED_BY]->(cs:ClassSociety) "
            "RETURN cs.name, e.status, e.from_date"
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "DNV"
        assert result.result_set[0][1] == "active"

        # Verify FLAGGED_AS edge
        result = graph.query(
            "MATCH (v:Vessel {imo: 9876543})-[:FLAGGED_AS]->(f:FlagState) "
            "RETURN f.iso_code, f.paris_mou_list"
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "PA"
        assert result.result_set[0][1] == "white"

        # Verify INSURED_BY edge
        result = graph.query(
            "MATCH (v:Vessel {imo: 9876543})-[:INSURED_BY]->(p:PIClub) "
            "RETURN p.name"
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "The Standard Club"

        # Verify MANAGED_BY edge
        result = graph.query(
            "MATCH (v:Vessel {imo: 9876543})-[:MANAGED_BY]->(c:Company) "
            "RETURN c.name, c.ism_company_number"
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "Nordic Maritime AS"
        assert result.result_set[0][1] == "1234567"

    def test_class_transition_creates_two_edges(self, graph, mock_pg):
        """Two inspections with different RO creates two CLASSED_BY edges;
        old one gets to_date set."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        cursor.fetchall.side_effect = [
            # flag performance
            [{"iso_code": "PA", "list_status": "white"}],
            # inspections — same vessel, two inspections, different RO
            [
                {
                    "imo": 1111111,
                    "ship_name": "Class Changer",
                    "flag_state": "PA",
                    "ship_type": "Bulk",
                    "gross_tonnage": 40000,
                    "inspection_date": "2024-01-15",
                    "detained": False,
                    "deficiency_count": 1,
                    "ism_deficiency": False,
                    "ro_at_inspection": "Lloyd Register",
                    "pi_provider_at_inspection": None,
                    "pi_is_ig_member": None,
                    "ism_company_imo": None,
                    "ism_company_name": None,
                },
                {
                    "imo": 1111111,
                    "ship_name": "Class Changer",
                    "flag_state": "PA",
                    "ship_type": "Bulk",
                    "gross_tonnage": 40000,
                    "inspection_date": "2025-06-20",
                    "detained": False,
                    "deficiency_count": 0,
                    "ism_deficiency": False,
                    "ro_at_inspection": "DNV",
                    "pi_provider_at_inspection": None,
                    "pi_is_ig_member": None,
                    "ism_company_imo": None,
                    "ism_company_name": None,
                },
            ],
        ]

        builder.build_from_paris_mou()

        # Should have two CLASSED_BY edges
        result = graph.query(
            """
            MATCH (v:Vessel {imo: 1111111})-[e:CLASSED_BY]->(cs:ClassSociety)
            RETURN cs.name, e.from_date, e.to_date, e.status
            ORDER BY e.from_date
            """
        )
        assert len(result.result_set) == 2

        # Old edge (Lloyd Register) should have to_date set
        old_edge = result.result_set[0]
        assert old_edge[0] == "Lloyd Register"
        assert old_edge[2] == "2025-06-20"  # to_date

        # New edge (DNV) should have no to_date
        new_edge = result.result_set[1]
        assert new_edge[0] == "DNV"
        assert new_edge[2] is None  # to_date

        # Verify transition was counted
        assert builder.stats.transitions >= 1


# ---------------------------------------------------------------------------
# OpenSanctions Tests
# ---------------------------------------------------------------------------


@skip_no_falkordb
class TestOpenSanctions:
    """Test graph building from OpenSanctions entities and relationships."""

    def test_ownership_chain(self, graph, mock_pg):
        """Company→Person ownership chain creates correct nodes and edges."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        # Pre-create a vessel node (as if Paris MoU already ran)
        graph.query("CREATE (v:Vessel {imo: 2222222, name: 'Shadow Runner'})")

        cursor.fetchall.side_effect = [
            # vessel_links
            [{"entity_id": "os-vessel-1", "imo": 2222222}],
            # entities
            [
                {
                    "entity_id": "os-vessel-1",
                    "schema_type": "Vessel",
                    "name": "Shadow Runner",
                    "properties": {},
                    "topics": ["shadow_fleet"],
                    "target": False,
                },
                {
                    "entity_id": "os-company-1",
                    "schema_type": "Company",
                    "name": "Shadow Maritime Ltd",
                    "properties": {"jurisdiction": ["MH"]},
                    "topics": [],
                    "target": False,
                },
                {
                    "entity_id": "os-person-1",
                    "schema_type": "Person",
                    "name": "Ivan Petrov",
                    "properties": {"nationality": ["RU"], "birthDate": ["1975-03-12"]},
                    "topics": [],
                    "target": False,
                },
            ],
            # relationships
            [
                {
                    "rel_type": "ownership",
                    "source_entity_id": "os-vessel-1",
                    "target_entity_id": "os-company-1",
                    "properties": {"startDate": ["2023-01-01"]},
                },
                {
                    "rel_type": "ownership",
                    "source_entity_id": "os-company-1",
                    "target_entity_id": "os-person-1",
                    "properties": {"startDate": ["2020-06-15"]},
                },
            ],
        ]

        builder.build_from_opensanctions()

        # Verify vessel has opensanctions_id and topics
        result = graph.query(
            "MATCH (v:Vessel {imo: 2222222}) RETURN v.opensanctions_id, v.topics"
        )
        assert result.result_set[0][0] == "os-vessel-1"
        assert "shadow_fleet" in result.result_set[0][1]

        # Verify Company node
        result = graph.query(
            "MATCH (c:Company {opensanctions_id: 'os-company-1'}) RETURN c.name, c.jurisdiction"
        )
        assert result.result_set[0][0] == "Shadow Maritime Ltd"
        assert result.result_set[0][1] == "MH"

        # Verify Person node
        result = graph.query(
            "MATCH (p:Person {opensanctions_id: 'os-person-1'}) RETURN p.name, p.nationality"
        )
        assert result.result_set[0][0] == "Ivan Petrov"
        assert result.result_set[0][1] == "RU"

        # Verify ownership chain: Vessel → Company → Person
        result = graph.query(
            """
            MATCH (v:Vessel {imo: 2222222})-[:OWNED_BY]->(c:Company)-[:OWNED_BY]->(p:Person)
            RETURN c.name, p.name
            """
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "Shadow Maritime Ltd"
        assert result.result_set[0][1] == "Ivan Petrov"

    def test_directorship_edge(self, graph, mock_pg):
        """Directorship relationship creates DIRECTED_BY edge."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        cursor.fetchall.side_effect = [
            # vessel_links (empty — no vessels)
            [],
        ]

        # Since no vessel links, build_from_opensanctions returns early
        # Let's test with vessel links pointing to a company
        cursor.fetchall.side_effect = [
            # vessel_links
            [{"entity_id": "os-vessel-2", "imo": 3333333}],
            # entities
            [
                {
                    "entity_id": "os-vessel-2",
                    "schema_type": "Vessel",
                    "name": "Test Vessel",
                    "properties": {},
                    "topics": [],
                    "target": False,
                },
                {
                    "entity_id": "os-company-2",
                    "schema_type": "Company",
                    "name": "Acme Shipping Co",
                    "properties": {},
                    "topics": [],
                    "target": False,
                },
                {
                    "entity_id": "os-person-2",
                    "schema_type": "Person",
                    "name": "Dmitry Smirnov",
                    "properties": {"nationality": ["RU"]},
                    "topics": [],
                    "target": False,
                },
            ],
            # relationships
            [
                {
                    "rel_type": "directorship",
                    "source_entity_id": "os-company-2",
                    "target_entity_id": "os-person-2",
                    "properties": {},
                },
            ],
        ]

        builder.build_from_opensanctions()

        result = graph.query(
            "MATCH (c:Company)-[:DIRECTED_BY]->(p:Person) RETURN c.name, p.name"
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "Acme Shipping Co"
        assert result.result_set[0][1] == "Dmitry Smirnov"


# ---------------------------------------------------------------------------
# IACS Tests
# ---------------------------------------------------------------------------


@skip_no_falkordb
class TestIACS:
    """Test graph building from IACS vessels-in-class data."""

    def test_withdrawn_sets_to_date(self, graph, mock_pg):
        """IACS withdrawn status sets CLASSED_BY to_date."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        # Pre-create vessel with active CLASSED_BY edge
        graph.query(
            """
            CREATE (v:Vessel {imo: 4444444, name: 'Withdrawn Ship'})
            CREATE (cs:ClassSociety {name: 'Bureau Veritas', iacs_member: true})
            CREATE (v)-[:CLASSED_BY {from_date: '2020-01-01', status: 'active'}]->(cs)
            """
        )

        cursor.fetchall.return_value = [{
            "imo": 4444444,
            "ship_name": "Withdrawn Ship",
            "class_society": "Bureau Veritas",
            "status": "Withdrawn",
            "date_of_latest_status": "2025-12-01",
        }]

        builder.build_from_iacs()

        result = graph.query(
            """
            MATCH (v:Vessel {imo: 4444444})-[e:CLASSED_BY]->(cs:ClassSociety)
            RETURN e.status, e.to_date
            """
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "withdrawn"
        assert result.result_set[0][1] == "2025-12-01"

    def test_active_status_creates_edge(self, graph, mock_pg):
        """IACS Delivered status creates active CLASSED_BY edge."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        cursor.fetchall.return_value = [{
            "imo": 5555555,
            "ship_name": "Active Ship",
            "class_society": "DNV",
            "status": "Delivered",
            "date_of_latest_status": "2024-03-15",
        }]

        builder.build_from_iacs()

        result = graph.query(
            """
            MATCH (v:Vessel {imo: 5555555})-[e:CLASSED_BY]->(cs:ClassSociety {name: 'DNV'})
            RETURN e.status, e.from_date, e.to_date, cs.iacs_member
            """
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "active"
        assert result.result_set[0][3] is True

    def test_suspended_status(self, graph, mock_pg):
        """IACS Suspended status sets CLASSED_BY status to suspended."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        cursor.fetchall.return_value = [{
            "imo": 6666666,
            "ship_name": "Suspended Ship",
            "class_society": "Lloyd Register",
            "status": "Suspended",
            "date_of_latest_status": "2025-08-10",
        }]

        builder.build_from_iacs()

        result = graph.query(
            """
            MATCH (v:Vessel {imo: 6666666})-[e:CLASSED_BY]->(cs:ClassSociety)
            RETURN e.status
            """
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "suspended"


# ---------------------------------------------------------------------------
# Integration / Cross-source Tests
# ---------------------------------------------------------------------------


@skip_no_falkordb
class TestCrossSource:
    """Test that data from all three sources merges correctly."""

    def test_vessel_from_all_sources(self, graph, mock_pg):
        """Vessel present in Paris MoU + OpenSanctions + IACS has merged data."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        imo = 7777777

        # --- Paris MoU ---
        cursor.fetchall.side_effect = [
            [{"iso_code": "GA", "list_status": "black"}],
            [{
                "imo": imo,
                "ship_name": "Dark Voyager",
                "flag_state": "GA",
                "ship_type": "Oil Tanker",
                "gross_tonnage": 150000,
                "inspection_date": "2025-09-01",
                "detained": True,
                "deficiency_count": 8,
                "ism_deficiency": True,
                "ro_at_inspection": "Indian Register",
                "pi_provider_at_inspection": None,
                "pi_is_ig_member": None,
                "ism_company_imo": None,
                "ism_company_name": None,
            }],
        ]
        builder.build_from_paris_mou()

        # --- OpenSanctions ---
        cursor.fetchall.side_effect = [
            [{"entity_id": "os-dark-1", "imo": imo}],
            [
                {
                    "entity_id": "os-dark-1",
                    "schema_type": "Vessel",
                    "name": "DARK VOYAGER",
                    "properties": {},
                    "topics": ["sanction", "shadow_fleet"],
                    "target": True,
                },
                {
                    "entity_id": "os-dark-owner",
                    "schema_type": "Company",
                    "name": "Dark Pool Holdings Ltd",
                    "properties": {"jurisdiction": ["SC"]},
                    "topics": [],
                    "target": False,
                },
            ],
            [
                {
                    "rel_type": "ownership",
                    "source_entity_id": "os-dark-1",
                    "target_entity_id": "os-dark-owner",
                    "properties": {},
                },
            ],
        ]
        builder.build_from_opensanctions()

        # --- IACS ---
        cursor.fetchall.side_effect = None
        cursor.fetchall.return_value = [{
            "imo": imo,
            "ship_name": "DARK VOYAGER",
            "class_society": "Indian Register",
            "status": "Suspended",
            "date_of_latest_status": "2025-10-15",
        }]
        builder.build_from_iacs()

        # Verify merged vessel
        result = graph.query(
            """
            MATCH (v:Vessel {imo: $imo})
            RETURN v.name, v.ship_type, v.gross_tonnage, v.detained,
                   v.topics, v.classification, v.opensanctions_id
            """,
            {"imo": imo},
        )
        assert len(result.result_set) == 1
        row = result.result_set[0]
        # Name from Paris MoU (first source)
        assert row[0] == "Dark Voyager"
        assert row[1] == "Oil Tanker"
        assert row[2] == 150000
        assert row[3] is True  # detained
        assert "sanction" in row[4]  # topics from OpenSanctions
        assert row[5] == "blacklisted"  # classification from sanctions
        assert row[6] == "os-dark-1"  # opensanctions_id

        # Flag: black-listed Gabon
        result = graph.query(
            "MATCH (v:Vessel {imo: $imo})-[:FLAGGED_AS]->(f:FlagState) RETURN f.iso_code, f.paris_mou_list",
            {"imo": imo},
        )
        assert result.result_set[0] == ["GA", "black"]

        # CLASSED_BY: Indian Register, now suspended from IACS
        result = graph.query(
            """
            MATCH (v:Vessel {imo: $imo})-[e:CLASSED_BY]->(cs:ClassSociety)
            RETURN cs.name, e.status
            """,
            {"imo": imo},
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "Indian Register"
        assert result.result_set[0][1] == "suspended"

        # OWNED_BY: ownership edge to company
        result = graph.query(
            "MATCH (v:Vessel {imo: $imo})-[:OWNED_BY]->(c:Company) RETURN c.name",
            {"imo": imo},
        )
        assert len(result.result_set) == 1
        assert result.result_set[0][0] == "Dark Pool Holdings Ltd"


# ---------------------------------------------------------------------------
# Idempotency Test
# ---------------------------------------------------------------------------


@skip_no_falkordb
class TestIdempotency:
    """Test that the graph builder produces the same result when run twice."""

    def test_idempotent_build(self, graph, mock_pg):
        """Running the builder twice produces the same graph."""
        conn, cursor = mock_pg
        builder = _make_builder(graph, conn)

        def setup_mocks():
            cursor.fetchall.side_effect = [
                # Paris MoU: flag performance
                [{"iso_code": "NO", "list_status": "white"}],
                # Paris MoU: inspections
                [{
                    "imo": 8888888,
                    "ship_name": "Idempotent Vessel",
                    "flag_state": "NO",
                    "ship_type": "Cargo",
                    "gross_tonnage": 30000,
                    "inspection_date": "2025-05-01",
                    "detained": False,
                    "deficiency_count": 0,
                    "ism_deficiency": False,
                    "ro_at_inspection": "DNV",
                    "pi_provider_at_inspection": None,
                    "pi_is_ig_member": None,
                    "ism_company_imo": None,
                    "ism_company_name": None,
                }],
                # OpenSanctions: vessel links (empty)
                [],
                # IACS
                [{
                    "imo": 8888888,
                    "ship_name": "Idempotent Vessel",
                    "class_society": "DNV",
                    "status": "Delivered",
                    "date_of_latest_status": "2020-01-01",
                }],
            ]

        # First run
        setup_mocks()
        builder.build_all()

        # Count nodes and edges after first run
        vessels_1 = graph.query("MATCH (v:Vessel) RETURN count(v)").result_set[0][0]
        edges_1 = graph.query("MATCH ()-[e]->() RETURN count(e)").result_set[0][0]

        # Second run
        builder2 = _make_builder(graph, conn)
        setup_mocks()
        builder2.build_all()

        # Count after second run — should be identical
        vessels_2 = graph.query("MATCH (v:Vessel) RETURN count(v)").result_set[0][0]
        edges_2 = graph.query("MATCH ()-[e]->() RETURN count(e)").result_set[0][0]

        assert vessels_1 == vessels_2, f"Vessel count changed: {vessels_1} -> {vessels_2}"
        assert edges_1 == edges_2, f"Edge count changed: {edges_1} -> {edges_2}"


# ---------------------------------------------------------------------------
# BuildStats Tests
# ---------------------------------------------------------------------------


class TestBuildStats:
    """Test the stats tracking helper."""

    def test_initial_stats(self):
        stats = BuildStats()
        assert stats.nodes["Vessel"] == 0
        assert stats.edges["CLASSED_BY"] == 0
        assert stats.transitions == 0

    def test_log_summary(self):
        """log_summary doesn't raise."""
        stats = BuildStats()
        stats.nodes["Vessel"] = 5
        stats.transitions = 2
        stats.elapsed = 1.5
        stats.log_summary()  # Should not raise
