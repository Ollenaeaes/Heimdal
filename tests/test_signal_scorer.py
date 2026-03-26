"""Tests for the signal-based scoring engine (Story 6).

Tests the SignalScorer evaluator and compute_score calculator with
mocked PostgreSQL connections. Focus is on signal evaluation logic,
classification thresholds, and override rules.
"""

from __future__ import annotations

import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from services.graph_builder.signal_scorer import (
    Signal,
    SignalScorer,
    IACS_MEMBERS,
    _is_iacs_member,
    _is_tanker,
)
from services.graph_builder.score_calculator import compute_score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_inspection(
    imo: int = 9999999,
    ship_name: str = "TEST VESSEL",
    flag_state: str = "NO",
    ship_type: int = 80,
    gross_tonnage: float = 60000,
    inspection_date: date | None = None,
    detained: bool = False,
    deficiency_count: int = 0,
    ism_deficiency: int = 0,
    ro_at_inspection: str = "DNV",
    pi_provider_at_inspection: str | None = None,
    pi_is_ig_member: bool | None = None,
    ism_company_imo: int | None = None,
    ism_company_name: str | None = None,
) -> dict:
    """Create a mock PSC inspection row."""
    if inspection_date is None:
        inspection_date = date.today() - timedelta(days=30)
    return {
        "imo": imo,
        "ship_name": ship_name,
        "flag_state": flag_state,
        "ship_type": ship_type,
        "gross_tonnage": gross_tonnage,
        "inspection_date": inspection_date,
        "detained": detained,
        "deficiency_count": deficiency_count,
        "ism_deficiency": ism_deficiency,
        "ro_at_inspection": ro_at_inspection,
        "pi_provider_at_inspection": pi_provider_at_inspection,
        "pi_is_ig_member": pi_is_ig_member,
        "ism_company_imo": ism_company_imo,
        "ism_company_name": ism_company_name,
    }


class MockCursor:
    """Mock psycopg2 cursor that returns predefined results for queries."""

    def __init__(self, results: dict[str, list] | None = None):
        # Map from query substring to list of result rows
        self._results = results or {}
        self._current_results: list = []
        self._idx = 0

    def execute(self, query: str, params=None):
        self._current_results = []
        for key, rows in self._results.items():
            if key.lower() in query.lower():
                self._current_results = list(rows)
                break
        self._idx = 0

    def fetchone(self):
        if self._current_results:
            return self._current_results[0]
        return None

    def fetchall(self):
        return self._current_results

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockConnection:
    """Mock psycopg2 connection."""

    def __init__(self, results: dict[str, list] | None = None):
        self._results = results or {}

    def cursor(self, cursor_factory=None):
        return MockCursor(self._results)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# compute_score tests
# ---------------------------------------------------------------------------

class TestComputeScore:
    """Tests for the score_calculator.compute_score function."""

    def test_no_signals_scores_zero_green(self):
        """Vessel with no signals scores 0 → green."""
        score, classification = compute_score([])
        assert score == 0
        assert classification == "green"

    def test_a1_only_scores_3_green(self):
        """Vessel with A1(3) only scores 3 → green."""
        signals = [Signal(signal_id="A1", weight=3)]
        score, classification = compute_score(signals)
        assert score == 3
        assert classification == "green"

    def test_a1_plus_b5_scores_4_yellow(self):
        """Vessel with A1(3) + B5(1) scores 4 → yellow."""
        signals = [
            Signal(signal_id="A1", weight=3),
            Signal(signal_id="B5", weight=1),
        ]
        score, classification = compute_score(signals)
        assert score == 4
        assert classification == "yellow"

    def test_a1_plus_c1_scores_6_red(self):
        """Vessel with A1(3) + C1(3) scores 6 → red."""
        signals = [
            Signal(signal_id="A1", weight=3),
            Signal(signal_id="C1", weight=3),
        ]
        score, classification = compute_score(signals)
        assert score == 6
        assert classification == "red"

    def test_b1_alone_override_yellow(self):
        """Vessel with B1(4) alone → yellow (override)."""
        signals = [Signal(signal_id="B1", weight=4)]
        score, classification = compute_score(signals)
        assert score == 4
        assert classification == "yellow"

    def test_d3_plus_a7_override_red(self):
        """Vessel with D3(4) + A7(3) → red (override)."""
        signals = [
            Signal(signal_id="D3", weight=4),
            Signal(signal_id="A7", weight=3),
        ]
        score, classification = compute_score(signals)
        assert score == 7
        assert classification == "red"

    def test_d4_plus_a6_override_red(self):
        """D4 + A6 also triggers the (D3|D4) + (A7|A6) override → red."""
        signals = [
            Signal(signal_id="D4", weight=4),
            Signal(signal_id="A6", weight=2),
        ]
        score, classification = compute_score(signals)
        assert score == 6
        assert classification == "red"

    def test_d6_alone_override_red(self):
        """Vessel with D6(4) → red (override)."""
        signals = [Signal(signal_id="D6", weight=4)]
        score, classification = compute_score(signals)
        # Score is 4, which would normally be yellow
        assert score == 4
        assert classification == "red"

    def test_sanctioned_vessel_blacklisted(self):
        """Sanctioned vessel → blacklisted regardless of score."""
        signals = [Signal(signal_id="A4", weight=1)]
        score, classification = compute_score(signals, is_sanctioned=True)
        assert score == 1
        assert classification == "blacklisted"

    def test_sanctioned_vessel_no_signals_blacklisted(self):
        """Sanctioned vessel with no other signals → blacklisted."""
        score, classification = compute_score([], is_sanctioned=True)
        assert score == 0
        assert classification == "blacklisted"

    def test_c3_plus_a1_override_yellow(self):
        """C3 + A1 → minimum yellow."""
        signals = [
            Signal(signal_id="C3", weight=4),
            Signal(signal_id="A1", weight=3),
        ]
        score, classification = compute_score(signals)
        # Score is 7 → already red, override doesn't downgrade
        assert score == 7
        assert classification == "red"

    def test_c3_plus_a1_low_weight_override(self):
        """C3 + A1 override ensures at least yellow when score is low."""
        # Create signals with artificially low weights to test override
        signals = [
            Signal(signal_id="C3", weight=1),
            Signal(signal_id="A1", weight=1),
        ]
        score, classification = compute_score(signals)
        # Score is 2 → green normally, but C3+A1 override → yellow
        assert score == 2
        assert classification == "yellow"

    def test_a10_override_yellow(self):
        """A10 → minimum yellow."""
        signals = [Signal(signal_id="A10", weight=2)]
        score, classification = compute_score(signals)
        assert classification == "yellow"

    def test_b4_override_yellow(self):
        """B4 → minimum yellow."""
        signals = [Signal(signal_id="B4", weight=3)]
        score, classification = compute_score(signals)
        assert classification == "yellow"

    def test_threshold_boundary_3_green(self):
        """Score exactly 3 → green."""
        signals = [Signal(signal_id="A7", weight=3)]
        score, classification = compute_score(signals)
        assert score == 3
        assert classification == "green"

    def test_threshold_boundary_5_yellow(self):
        """Score exactly 5 → yellow."""
        signals = [
            Signal(signal_id="A7", weight=3),
            Signal(signal_id="A3", weight=2),
        ]
        score, classification = compute_score(signals)
        assert score == 5
        assert classification == "yellow"

    def test_threshold_boundary_9_red(self):
        """Score >= 9 → still red (strong multi-source pattern)."""
        signals = [
            Signal(signal_id="A1", weight=3),
            Signal(signal_id="A2", weight=4),
            Signal(signal_id="C1", weight=3),
        ]
        score, classification = compute_score(signals)
        assert score == 10
        assert classification == "red"


# ---------------------------------------------------------------------------
# SignalScorer evaluator tests
# ---------------------------------------------------------------------------

class TestSignalScorerA1:
    """Signal A1: Large tanker with >= 3 PSC deficiencies."""

    def test_a1_fires_for_large_tanker_with_deficiencies(self):
        """A1 fires for tanker GT >= 50000 with >= 3 deficiencies."""
        inspections = [_make_inspection(
            ship_type=80, gross_tonnage=55000, deficiency_count=4,
        )]
        conn = MockConnection({"psc_inspections": inspections})
        scorer = SignalScorer(pg_conn=conn)
        signals = scorer._evaluate_a_signals(9999999)
        a1_signals = [s for s in signals if s.signal_id == "A1"]
        assert len(a1_signals) == 1
        assert a1_signals[0].weight == 3

    def test_a1_does_not_fire_for_small_tanker(self):
        """A1 does NOT fire for tanker GT < 50000."""
        inspections = [_make_inspection(
            ship_type=80, gross_tonnage=40000, deficiency_count=5,
        )]
        conn = MockConnection({"psc_inspections": inspections})
        scorer = SignalScorer(pg_conn=conn)
        signals = scorer._evaluate_a_signals(9999999)
        a1_signals = [s for s in signals if s.signal_id == "A1"]
        assert len(a1_signals) == 0

    def test_a1_does_not_fire_for_non_tanker(self):
        """A1 does NOT fire for non-tanker vessels."""
        inspections = [_make_inspection(
            ship_type=70, gross_tonnage=60000, deficiency_count=5,
        )]
        conn = MockConnection({"psc_inspections": inspections})
        scorer = SignalScorer(pg_conn=conn)
        signals = scorer._evaluate_a_signals(9999999)
        a1_signals = [s for s in signals if s.signal_id == "A1"]
        assert len(a1_signals) == 0

    def test_a1_does_not_fire_with_few_deficiencies(self):
        """A1 does NOT fire with < 3 deficiencies."""
        inspections = [_make_inspection(
            ship_type=80, gross_tonnage=55000, deficiency_count=2,
        )]
        conn = MockConnection({"psc_inspections": inspections})
        scorer = SignalScorer(pg_conn=conn)
        signals = scorer._evaluate_a_signals(9999999)
        a1_signals = [s for s in signals if s.signal_id == "A1"]
        assert len(a1_signals) == 0


class TestSignalScorerA8:
    """Signal A8: >= 2 inspections with different RO (class switch)."""

    def test_a8_fires_with_ro_change(self):
        """A8 fires when inspections show RO transition."""
        inspections = [
            _make_inspection(
                inspection_date=date.today() - timedelta(days=10),
                ro_at_inspection="Bureau Veritas",
            ),
            _make_inspection(
                inspection_date=date.today() - timedelta(days=400),
                ro_at_inspection="DNV",
            ),
        ]
        conn = MockConnection({"psc_inspections": inspections})
        scorer = SignalScorer(pg_conn=conn)
        signals = scorer._evaluate_a_signals(9999999)
        a8_signals = [s for s in signals if s.signal_id == "A8"]
        assert len(a8_signals) == 1
        assert a8_signals[0].weight == 3

    def test_a8_does_not_fire_with_same_ro(self):
        """A8 does NOT fire when all inspections have the same RO."""
        inspections = [
            _make_inspection(
                inspection_date=date.today() - timedelta(days=10),
                ro_at_inspection="DNV",
            ),
            _make_inspection(
                inspection_date=date.today() - timedelta(days=400),
                ro_at_inspection="DNV",
            ),
        ]
        conn = MockConnection({"psc_inspections": inspections})
        scorer = SignalScorer(pg_conn=conn)
        signals = scorer._evaluate_a_signals(9999999)
        a8_signals = [s for s in signals if s.signal_id == "A8"]
        assert len(a8_signals) == 0

    def test_a8_requires_at_least_2_inspections(self):
        """A8 does NOT fire with a single inspection."""
        inspections = [_make_inspection(ro_at_inspection="DNV")]
        conn = MockConnection({"psc_inspections": inspections})
        scorer = SignalScorer(pg_conn=conn)
        signals = scorer._evaluate_a_signals(9999999)
        a8_signals = [s for s in signals if s.signal_id == "A8"]
        assert len(a8_signals) == 0


class TestSignalScorerC5:
    """Signal C5: Paris MoU historical RO was IACS but current status not active."""

    def test_c5_fires_when_historical_iacs_but_not_active(self):
        """C5 fires when historical RO was IACS member but current status is withdrawn."""
        iacs_data = {
            "imo": 9999999,
            "class_society": "Unknown Society",
            "status": "Withdrawn",
            "date_of_latest_status": date.today() - timedelta(days=60),
        }
        historical_ros = [{"ro_at_inspection": "DNV"}]

        # Build a connection that returns the right data for each query
        class C5MockCursor(MockCursor):
            def __init__(self):
                super().__init__()
                self._call_count = 0

            def execute(self, query, params=None):
                self._call_count += 1
                if "iacs_vessels_current" in query:
                    self._current_results = [iacs_data]
                elif "ro_at_inspection" in query:
                    self._current_results = historical_ros
                elif "psc_flag_performance" in query:
                    self._current_results = []
                elif "psc_inspections" in query:
                    self._current_results = []
                else:
                    self._current_results = []

        class C5MockConnection:
            def cursor(self, cursor_factory=None):
                return C5MockCursor()
            def close(self):
                pass

        scorer = SignalScorer(pg_conn=C5MockConnection())
        signals = scorer._evaluate_c_signals(9999999)
        c5_signals = [s for s in signals if s.signal_id == "C5"]
        assert len(c5_signals) == 1
        assert c5_signals[0].weight == 3

    def test_c5_does_not_fire_when_active(self):
        """C5 does NOT fire when current status is active."""
        iacs_data = {
            "imo": 9999999,
            "class_society": "DNV",
            "status": "Active",
            "date_of_latest_status": date.today() - timedelta(days=60),
        }

        class ActiveMockCursor(MockCursor):
            def execute(self, query, params=None):
                if "iacs_vessels_current" in query:
                    self._current_results = [iacs_data]
                else:
                    self._current_results = []

        class ActiveMockConnection:
            def cursor(self, cursor_factory=None):
                return ActiveMockCursor()
            def close(self):
                pass

        scorer = SignalScorer(pg_conn=ActiveMockConnection())
        signals = scorer._evaluate_c_signals(9999999)
        c5_signals = [s for s in signals if s.signal_id == "C5"]
        assert len(c5_signals) == 0


class TestSignalScorerHelpers:
    """Tests for helper functions."""

    def test_is_iacs_member_positive(self):
        assert _is_iacs_member("DNV") is True
        assert _is_iacs_member("Lloyd's Register") is True
        assert _is_iacs_member("Bureau Veritas") is True

    def test_is_iacs_member_case_insensitive(self):
        assert _is_iacs_member("dnv") is True
        assert _is_iacs_member("LLOYD'S REGISTER") is True

    def test_is_iacs_member_negative(self):
        assert _is_iacs_member("Unknown Society") is False
        assert _is_iacs_member(None) is False
        assert _is_iacs_member("") is False

    def test_is_tanker(self):
        assert _is_tanker(80) is True
        assert _is_tanker(85) is True
        assert _is_tanker(89) is True
        assert _is_tanker(70) is False
        assert _is_tanker(None) is False


class TestSignalScorerNoSignals:
    """Test vessel with no data produces no signals."""

    def test_no_inspections_no_a_signals(self):
        """No inspections → no A signals."""
        conn = MockConnection({"psc_inspections": []})
        scorer = SignalScorer(pg_conn=conn)
        signals = scorer._evaluate_a_signals(9999999)
        assert len(signals) == 0


class TestSignalScorerIntegration:
    """Integration-style tests using evaluate_vessel with mocked DB."""

    def test_evaluate_vessel_returns_all_signal_types(self):
        """evaluate_vessel combines A, B, C, and D signals."""
        # Build a comprehensive mock that handles multiple query types
        class IntegMockCursor(MockCursor):
            def execute(self, query, params=None):
                q = query.lower()
                if "psc_inspections" in q and "order by" in q:
                    self._current_results = [
                        _make_inspection(
                            ship_type=80, gross_tonnage=55000,
                            deficiency_count=4, ro_at_inspection="DNV",
                        ),
                    ]
                elif "psc_inspections" in q:
                    self._current_results = []
                elif "psc_flag_performance" in q:
                    self._current_results = [{"list_status": "white"}]
                elif "os_vessel_links" in q:
                    self._current_results = []
                elif "iacs_vessels_current" in q:
                    self._current_results = [{
                        "imo": 9999999,
                        "class_society": "DNV",
                        "status": "Active",
                        "date_of_latest_status": date.today() - timedelta(days=400),
                    }]
                elif "vessel_signals" in q:
                    self._current_results = [{
                        "signal_id": "D1",
                        "weight": 3,
                        "details": {"zone": "GoF"},
                        "source_data": "geographic_inference",
                    }]
                elif "os_entities" in q:
                    self._current_results = []
                elif "os_relationships" in q:
                    self._current_results = []
                else:
                    self._current_results = []

        class IntegMockConnection:
            def cursor(self, cursor_factory=None):
                return IntegMockCursor()
            def close(self):
                pass

        scorer = SignalScorer(pg_conn=IntegMockConnection())
        signals = scorer.evaluate_vessel(9999999)

        signal_ids = {s.signal_id for s in signals}
        # Should have A1 (large tanker deficiencies) and D1 (from vessel_signals)
        assert "A1" in signal_ids
        assert "D1" in signal_ids

    def test_evaluate_vessel_empty_data(self):
        """Vessel with no data at all produces C1 (no IACS class) only."""
        class EmptyMockCursor(MockCursor):
            def execute(self, query, params=None):
                self._current_results = []

        class EmptyMockConnection:
            def cursor(self, cursor_factory=None):
                return EmptyMockCursor()
            def close(self):
                pass

        scorer = SignalScorer(pg_conn=EmptyMockConnection())
        signals = scorer.evaluate_vessel(9999999)

        signal_ids = {s.signal_id for s in signals}
        # No inspections → no A signals
        # No OS data → no B signals
        # No IACS record → C1 fires
        # No vessel_signals → no D signals
        assert signal_ids == {"C1"}

    def test_sanctioned_check(self):
        """is_sanctioned returns True when vessel has target=True entity."""
        class SanctionMockCursor(MockCursor):
            def execute(self, query, params=None):
                if "os_vessel_links" in query.lower() and "target" in query.lower():
                    self._current_results = [{"target": True}]
                else:
                    self._current_results = []

        class SanctionMockConnection:
            def cursor(self, cursor_factory=None):
                return SanctionMockCursor()
            def close(self):
                pass

        scorer = SignalScorer(pg_conn=SanctionMockConnection())
        assert scorer.is_sanctioned(9999999) is True

    def test_not_sanctioned_check(self):
        """is_sanctioned returns False when no target=True entity."""
        class NotSanctionMockCursor(MockCursor):
            def execute(self, query, params=None):
                self._current_results = []

        class NotSanctionMockConnection:
            def cursor(self, cursor_factory=None):
                return NotSanctionMockCursor()
            def close(self):
                pass

        scorer = SignalScorer(pg_conn=NotSanctionMockConnection())
        assert scorer.is_sanctioned(9999999) is False


class TestFullScoringPipeline:
    """End-to-end tests combining SignalScorer + compute_score."""

    def test_clean_vessel_green(self):
        """Clean vessel with only C1 (no IACS class) → green."""
        signals = [Signal(signal_id="C1", weight=3)]
        score, classification = compute_score(signals)
        assert score == 3
        assert classification == "green"

    def test_risky_vessel_red(self):
        """Vessel with multiple signals → red."""
        signals = [
            Signal(signal_id="A1", weight=3),
            Signal(signal_id="A2", weight=4),
            Signal(signal_id="B3", weight=2),
        ]
        score, classification = compute_score(signals)
        assert score == 9
        assert classification == "red"

    def test_sanctioned_with_signals_blacklisted(self):
        """Sanctioned vessel with additional signals → blacklisted."""
        signals = [
            Signal(signal_id="A1", weight=3),
            Signal(signal_id="C1", weight=3),
        ]
        score, classification = compute_score(signals, is_sanctioned=True)
        assert score == 6
        assert classification == "blacklisted"

    def test_d6_override_with_low_score(self):
        """D6 alone (score 4) would be yellow, but override makes it red."""
        signals = [Signal(signal_id="D6", weight=4)]
        score, classification = compute_score(signals)
        assert score == 4
        assert classification == "red"
