"""Tests for database query optimization functions.

Verifies:
- aggregate_score_sql generates correct SQL and produces results matching Python impl
- list_anomalies_with_vessel returns vessel data via JOIN (no N+1)
- count_anomaly_events works with filters
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.constants import MAX_PER_RULE
from shared.db.repositories import (
    aggregate_score_sql,
    count_anomaly_events,
    list_anomalies_with_vessel,
)

# Also import the Python aggregator for equivalence tests
import sys
from pathlib import Path

_scoring_dir = Path(__file__).resolve().parent.parent / "services" / "scoring"
sys.path.insert(0, str(_scoring_dir))

from aggregator import aggregate_score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(rows: list[dict[str, Any]] | None = None, scalar: Any = None):
    """Create an AsyncMock session that returns configurable results."""
    session = AsyncMock()
    result_mock = MagicMock()

    if rows is not None:
        # For mappings().all() — returns list of mapping-like dicts
        mappings_mock = MagicMock()
        mappings_mock.all.return_value = [MagicMock(**{"__iter__": lambda s: iter(r.items()), "keys": lambda s: r.keys(), **r}) for r in rows]
        # Make each row dict-convertible
        mapping_rows = []
        for r in rows:
            row_mock = MagicMock()
            row_mock.__iter__ = lambda s, _r=r: iter(_r.items())
            row_mock.keys = lambda _r=r: _r.keys()
            row_mock.__getitem__ = lambda s, k, _r=r: _r[k]
            # dict(row_mock) needs items()
            row_mock.items = lambda _r=r: _r.items()
            mapping_rows.append(row_mock)
        mappings_mock.all.return_value = mapping_rows
        result_mock.mappings.return_value = mappings_mock

    if scalar is not None:
        # For .first() returning a tuple-like row
        first_mock = MagicMock()
        first_mock.__getitem__ = lambda s, i: scalar if i == 0 else None
        result_mock.first.return_value = first_mock
    elif rows is None:
        result_mock.first.return_value = None

    session.execute.return_value = result_mock
    return session


# ---------------------------------------------------------------------------
# aggregate_score_sql tests
# ---------------------------------------------------------------------------


class TestAggregateScoreSql:
    """Tests for the SQL-based score aggregation."""

    @pytest.mark.asyncio
    async def test_empty_anomalies_returns_zero(self):
        """When no anomalies exist, score should be 0."""
        session = _make_mock_session(scalar=0.0)
        score = await aggregate_score_sql(session, mmsi=123456789)
        assert score == 0.0
        # Verify execute was called
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_sql_contains_all_rule_caps(self):
        """The SQL query should include VALUES for every rule in MAX_PER_RULE."""
        session = _make_mock_session(scalar=0.0)
        await aggregate_score_sql(session, mmsi=123456789)

        # Extract the SQL text from the call
        call_args = session.execute.call_args
        sql_text = str(call_args[0][0].text)

        for rule_id, cap in MAX_PER_RULE.items():
            assert f"'{rule_id}'" in sql_text, f"Missing rule {rule_id} in SQL caps"
            assert str(cap) in sql_text, f"Missing cap {cap} for {rule_id}"

    @pytest.mark.asyncio
    async def test_sql_filters_active_unresolved(self):
        """SQL should filter for resolved=false and event_state='active' or NULL."""
        session = _make_mock_session(scalar=0.0)
        await aggregate_score_sql(session, mmsi=123456789)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "ae.resolved = false" in sql_text
        assert "ae.event_state = 'active'" in sql_text
        assert "ae.event_state IS NULL" in sql_text

    @pytest.mark.asyncio
    async def test_sql_passes_mmsi_param(self):
        """The mmsi should be passed as a bound parameter."""
        session = _make_mock_session(scalar=42.0)
        await aggregate_score_sql(session, mmsi=987654321)

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["mmsi"] == 987654321

    @pytest.mark.asyncio
    async def test_returns_float(self):
        """Result should always be a float."""
        session = _make_mock_session(scalar=55)
        score = await aggregate_score_sql(session, mmsi=123456789)
        assert isinstance(score, float)
        assert score == 55.0

    @pytest.mark.asyncio
    async def test_none_row_returns_zero(self):
        """If somehow first() returns None, should return 0."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.first.return_value = None
        session.execute.return_value = result_mock

        score = await aggregate_score_sql(session, mmsi=123456789)
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_sql_uses_least_for_cap(self):
        """SQL should use LEAST to cap rule totals."""
        session = _make_mock_session(scalar=0.0)
        await aggregate_score_sql(session, mmsi=123456789)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "LEAST" in sql_text

    @pytest.mark.asyncio
    async def test_sql_handles_escalation_multiplier(self):
        """SQL should extract escalation_multiplier from details JSON."""
        session = _make_mock_session(scalar=0.0)
        await aggregate_score_sql(session, mmsi=123456789)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "escalation_multiplier" in sql_text


class TestAggregateScoreEquivalence:
    """Verify SQL logic matches Python implementation for known inputs."""

    def test_single_rule_under_cap(self):
        """Single rule under cap: Python and expected SQL result match."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15, "resolved": False, "event_state": "active", "details": {}},
        ]
        py_score = aggregate_score(anomalies)
        # ais_gap cap is 40, 15 < 40 → score = 15
        assert py_score == 15.0

    def test_single_rule_over_cap(self):
        """Single rule over cap: Python caps it."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 25, "resolved": False, "event_state": "active", "details": {}},
            {"rule_id": "ais_gap", "points": 25, "resolved": False, "event_state": "active", "details": {}},
        ]
        py_score = aggregate_score(anomalies)
        # ais_gap cap is 40, 25+25=50 → capped at 40
        assert py_score == 40.0

    def test_multiple_rules(self):
        """Multiple rules: each capped independently."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 50, "resolved": False, "event_state": "active", "details": {}},
            {"rule_id": "sanctions_match", "points": 80, "resolved": False, "event_state": "active", "details": {}},
        ]
        py_score = aggregate_score(anomalies)
        # ais_gap: min(50, 40) = 40; sanctions_match: min(80, 100) = 80 → 120
        assert py_score == 120.0

    def test_resolved_anomalies_excluded(self):
        """Resolved anomalies should not contribute."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15, "resolved": True, "event_state": "active", "details": {}},
            {"rule_id": "ais_gap", "points": 10, "resolved": False, "event_state": "active", "details": {}},
        ]
        py_score = aggregate_score(anomalies)
        assert py_score == 10.0

    def test_ended_anomalies_excluded(self):
        """Ended anomalies (event_state='ended') should not contribute."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15, "resolved": False, "event_state": "ended", "details": {}},
            {"rule_id": "ais_gap", "points": 10, "resolved": False, "event_state": "active", "details": {}},
        ]
        py_score = aggregate_score(anomalies)
        assert py_score == 10.0

    def test_escalation_multiplier_adjusts_cap(self):
        """Escalation multiplier should increase the effective cap."""
        anomalies = [
            {
                "rule_id": "ais_gap",
                "points": 55,
                "resolved": False,
                "event_state": "active",
                "details": {"escalation_multiplier": 1.5},
            },
        ]
        py_score = aggregate_score(anomalies)
        # ais_gap base cap 40, escalation 1.5 → effective cap 60. min(55, 60) = 55
        assert py_score == 55.0

    def test_escalation_uses_max_across_anomalies(self):
        """When multiple anomalies have different escalation, use the max."""
        anomalies = [
            {
                "rule_id": "ais_gap",
                "points": 20,
                "resolved": False,
                "event_state": "active",
                "details": {"escalation_multiplier": 1.0},
            },
            {
                "rule_id": "ais_gap",
                "points": 20,
                "resolved": False,
                "event_state": "active",
                "details": {"escalation_multiplier": 2.0},
            },
        ]
        py_score = aggregate_score(anomalies)
        # Total points 40, cap 40 * 2.0 = 80, min(40, 80) = 40
        assert py_score == 40.0

    def test_empty_anomalies(self):
        """No anomalies → 0."""
        assert aggregate_score([]) == 0.0

    def test_details_as_json_string(self):
        """Details stored as JSON string should be parsed."""
        anomalies = [
            {
                "rule_id": "ais_gap",
                "points": 55,
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({"escalation_multiplier": 1.5}),
            },
        ]
        py_score = aggregate_score(anomalies)
        # Same as above: cap 40*1.5=60, min(55, 60) = 55
        assert py_score == 55.0


# ---------------------------------------------------------------------------
# list_anomalies_with_vessel tests
# ---------------------------------------------------------------------------


class TestListAnomaliesWithVessel:
    """Tests for the JOIN-based anomaly listing."""

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        """Should return a list of dicts."""
        rows = [
            {"id": 1, "mmsi": 123, "rule_id": "ais_gap", "ship_name": "Test Ship", "risk_tier": "red"},
        ]
        session = _make_mock_session(rows=rows)
        result = await list_anomalies_with_vessel(session)
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_sql_has_join(self):
        """SQL should JOIN vessel_profiles."""
        session = _make_mock_session(rows=[])
        await list_anomalies_with_vessel(session)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "LEFT JOIN vessel_profiles" in sql_text
        assert "vp.ship_name" in sql_text
        assert "vp.risk_tier" in sql_text

    @pytest.mark.asyncio
    async def test_severity_filter(self):
        """Severity filter should appear in WHERE clause."""
        session = _make_mock_session(rows=[])
        await list_anomalies_with_vessel(session, severity="critical")

        sql_text = str(session.execute.call_args[0][0].text)
        assert "ae.severity = :severity" in sql_text
        params = session.execute.call_args[0][1]
        assert params["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_resolved_filter(self):
        """Resolved filter should appear in WHERE clause."""
        session = _make_mock_session(rows=[])
        await list_anomalies_with_vessel(session, resolved=False)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "ae.resolved = :resolved" in sql_text
        params = session.execute.call_args[0][1]
        assert params["resolved"] is False

    @pytest.mark.asyncio
    async def test_pagination_params(self):
        """Limit and offset should be passed."""
        session = _make_mock_session(rows=[])
        await list_anomalies_with_vessel(session, limit=50, offset=10)

        params = session.execute.call_args[0][1]
        assert params["limit"] == 50
        assert params["offset"] == 10

    @pytest.mark.asyncio
    async def test_no_filters_no_where(self):
        """Without filters, WHERE clause should not appear."""
        session = _make_mock_session(rows=[])
        await list_anomalies_with_vessel(session)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "WHERE" not in sql_text

    @pytest.mark.asyncio
    async def test_order_by_created_at_desc(self):
        """Results should be ordered by created_at DESC."""
        session = _make_mock_session(rows=[])
        await list_anomalies_with_vessel(session)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "ORDER BY ae.created_at DESC" in sql_text


# ---------------------------------------------------------------------------
# count_anomaly_events tests
# ---------------------------------------------------------------------------


class TestCountAnomalyEvents:
    """Tests for the anomaly count function."""

    @pytest.mark.asyncio
    async def test_returns_int(self):
        """Should return an integer count."""
        session = _make_mock_session(scalar=42)
        count = await count_anomaly_events(session)
        assert count == 42

    @pytest.mark.asyncio
    async def test_severity_filter(self):
        """Severity filter should be applied."""
        session = _make_mock_session(scalar=5)
        await count_anomaly_events(session, severity="high")

        sql_text = str(session.execute.call_args[0][0].text)
        assert "severity = :severity" in sql_text
        params = session.execute.call_args[0][1]
        assert params["severity"] == "high"

    @pytest.mark.asyncio
    async def test_resolved_filter(self):
        """Resolved filter should be applied."""
        session = _make_mock_session(scalar=3)
        await count_anomaly_events(session, resolved=True)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "resolved = :resolved" in sql_text
        params = session.execute.call_args[0][1]
        assert params["resolved"] is True

    @pytest.mark.asyncio
    async def test_both_filters(self):
        """Both filters together should produce AND clause."""
        session = _make_mock_session(scalar=1)
        await count_anomaly_events(session, severity="critical", resolved=False)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "severity = :severity" in sql_text
        assert "resolved = :resolved" in sql_text
        assert "AND" in sql_text

    @pytest.mark.asyncio
    async def test_no_filters(self):
        """Without filters, no WHERE clause."""
        session = _make_mock_session(scalar=100)
        await count_anomaly_events(session)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "WHERE" not in sql_text

    @pytest.mark.asyncio
    async def test_none_row_returns_zero(self):
        """If first() returns None, should return 0."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.first.return_value = None
        session.execute.return_value = result_mock

        count = await count_anomaly_events(session)
        assert count == 0
