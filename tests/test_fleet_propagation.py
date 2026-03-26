"""Tests for graph-based fleet risk propagation (Story 7).

Tests use a real FalkorDB instance and verify A10/B4 signal generation.
"""

import pytest
from falkordb import FalkorDB

TEST_GRAPH_NAME = "heimdal_test_fleet"


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


@skip_no_falkordb
class TestA10ISMCompanyFleetRisk:
    """A10: ISM company manages a blacklisted/red vessel → sibling gets A10."""

    def test_a10_fires_for_sibling_of_blacklisted(self, graph):
        """Vessel B under same ISM company as blacklisted Vessel A gets A10."""
        graph.query("""
            CREATE (va:Vessel {imo: 9000001, name: 'Vessel A', classification: 'blacklisted'})
            CREATE (vb:Vessel {imo: 9000002, name: 'Vessel B', classification: 'green'})
            CREATE (c:Company {name: 'Shadow Shipping ISM'})
            CREATE (va)-[:MANAGED_BY]->(c)
            CREATE (vb)-[:MANAGED_BY]->(c)
        """)

        from services.graph_builder.fleet_propagation import evaluate_a10
        signals = evaluate_a10(graph, 9000002)

        assert len(signals) == 1
        assert signals[0].signal_id == "A10"
        assert signals[0].weight == 2
        assert signals[0].details["risky_siblings"][0]["imo"] == 9000001
        assert signals[0].details["risky_siblings"][0]["classification"] == "blacklisted"

    def test_a10_fires_for_sibling_of_red(self, graph):
        """Vessel B under same ISM company as red Vessel A gets A10."""
        graph.query("""
            CREATE (va:Vessel {imo: 9100001, name: 'Red Ship', classification: 'red'})
            CREATE (vb:Vessel {imo: 9100002, name: 'Clean Ship', classification: 'green'})
            CREATE (c:Company {name: 'Red Fleet ISM'})
            CREATE (va)-[:MANAGED_BY]->(c)
            CREATE (vb)-[:MANAGED_BY]->(c)
        """)

        from services.graph_builder.fleet_propagation import evaluate_a10
        signals = evaluate_a10(graph, 9100002)
        assert len(signals) == 1
        assert signals[0].signal_id == "A10"

    def test_a10_does_not_fire_for_different_company(self, graph):
        """Vessel D owned by different company does NOT get A10."""
        graph.query("""
            CREATE (va:Vessel {imo: 9200001, name: 'Bad Ship', classification: 'blacklisted'})
            CREATE (vd:Vessel {imo: 9200002, name: 'Unrelated Ship', classification: 'green'})
            CREATE (c1:Company {name: 'Bad ISM Co'})
            CREATE (c2:Company {name: 'Good ISM Co'})
            CREATE (va)-[:MANAGED_BY]->(c1)
            CREATE (vd)-[:MANAGED_BY]->(c2)
        """)

        from services.graph_builder.fleet_propagation import evaluate_a10
        signals = evaluate_a10(graph, 9200002)
        assert signals == []


@skip_no_falkordb
class TestB4OwnerFleetRisk:
    """B4: Owner's other vessel is blacklisted/red → sibling gets B4."""

    def test_b4_fires_for_owned_sibling(self, graph):
        """Vessel C owned by same Company as blacklisted Vessel A gets B4."""
        graph.query("""
            CREATE (va:Vessel {imo: 9300001, name: 'Sanctioned Vessel', classification: 'blacklisted'})
            CREATE (vc:Vessel {imo: 9300002, name: 'Fleet Mate', classification: 'green'})
            CREATE (c:Company {name: 'Dark Pool Holdings', opensanctions_id: 'os-123'})
            CREATE (va)-[:OWNED_BY]->(c)
            CREATE (vc)-[:OWNED_BY]->(c)
        """)

        from services.graph_builder.fleet_propagation import evaluate_b4
        signals = evaluate_b4(graph, 9300002)

        assert len(signals) == 1
        assert signals[0].signal_id == "B4"
        assert signals[0].weight == 3
        assert signals[0].details["risky_siblings"][0]["imo"] == 9300001

    def test_b4_does_not_fire_for_different_owner(self, graph):
        """Vessel with different owner does NOT get B4."""
        graph.query("""
            CREATE (va:Vessel {imo: 9400001, name: 'Bad Vessel', classification: 'blacklisted'})
            CREATE (vd:Vessel {imo: 9400002, name: 'Innocent Vessel', classification: 'green'})
            CREATE (c1:Company {name: 'Bad Owner', opensanctions_id: 'os-bad'})
            CREATE (c2:Company {name: 'Good Owner', opensanctions_id: 'os-good'})
            CREATE (va)-[:OWNED_BY]->(c1)
            CREATE (vd)-[:OWNED_BY]->(c2)
        """)

        from services.graph_builder.fleet_propagation import evaluate_b4
        signals = evaluate_b4(graph, 9400002)
        assert signals == []


@skip_no_falkordb
class TestNoCascade:
    """Propagation does not cascade — B4 on Vessel B does NOT propagate further."""

    def test_no_cascade(self, graph):
        """A vessel flagged via propagation does not itself trigger propagation."""
        # Vessel A (blacklisted) → Company → Vessel B (will get B4)
        # Vessel B → Company2 → Vessel C (should NOT get B4 from Vessel B)
        graph.query("""
            CREATE (va:Vessel {imo: 9500001, name: 'Source', classification: 'blacklisted'})
            CREATE (vb:Vessel {imo: 9500002, name: 'Middle', classification: 'green'})
            CREATE (vc:Vessel {imo: 9500003, name: 'End', classification: 'green'})
            CREATE (c1:Company {name: 'Owner A', opensanctions_id: 'os-a'})
            CREATE (c2:Company {name: 'Owner B', opensanctions_id: 'os-b'})
            CREATE (va)-[:OWNED_BY]->(c1)
            CREATE (vb)-[:OWNED_BY]->(c1)
            CREATE (vb)-[:OWNED_BY]->(c2)
            CREATE (vc)-[:OWNED_BY]->(c2)
        """)

        from services.graph_builder.fleet_propagation import evaluate_b4

        # Vessel B should get B4 (shares owner with blacklisted Vessel A)
        signals_b = evaluate_b4(graph, 9500002)
        assert len(signals_b) == 1

        # Vessel C shares Owner B with Vessel B, but Vessel B is only "green"
        # (its classification hasn't been updated to reflect the B4 signal yet)
        # So Vessel C should NOT get B4
        signals_c = evaluate_b4(graph, 9500003)
        assert signals_c == []

    def test_removing_blacklist_removes_propagation(self, graph):
        """When vessel's blacklisted status is removed, siblings lose A10/B4 on next run."""
        graph.query("""
            CREATE (va:Vessel {imo: 9600001, name: 'Was Bad', classification: 'green'})
            CREATE (vb:Vessel {imo: 9600002, name: 'Sibling', classification: 'green'})
            CREATE (c:Company {name: 'Fleet Co'})
            CREATE (va)-[:MANAGED_BY]->(c)
            CREATE (vb)-[:MANAGED_BY]->(c)
        """)

        from services.graph_builder.fleet_propagation import evaluate_a10
        signals = evaluate_a10(graph, 9600002)
        # VA is now "green", so no propagation
        assert signals == []


@skip_no_falkordb
class TestPropagateFleetRisk:
    """Test the combined propagate_fleet_risk function."""

    def test_both_signals_fire(self, graph):
        """Vessel gets both A10 and B4 when applicable."""
        graph.query("""
            CREATE (va:Vessel {imo: 9700001, name: 'Bad Ship', classification: 'blacklisted'})
            CREATE (vb:Vessel {imo: 9700002, name: 'Both Risks', classification: 'green'})
            CREATE (c1:Company {name: 'Shared Manager'})
            CREATE (c2:Company {name: 'Shared Owner', opensanctions_id: 'os-shared'})
            CREATE (va)-[:MANAGED_BY]->(c1)
            CREATE (vb)-[:MANAGED_BY]->(c1)
            CREATE (va)-[:OWNED_BY]->(c2)
            CREATE (vb)-[:OWNED_BY]->(c2)
        """)

        from services.graph_builder.fleet_propagation import propagate_fleet_risk
        signals = propagate_fleet_risk(graph, 9700002)

        signal_ids = {s.signal_id for s in signals}
        assert "A10" in signal_ids
        assert "B4" in signal_ids
