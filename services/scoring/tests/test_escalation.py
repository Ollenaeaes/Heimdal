"""Tests for Story 4: Repeat Event Escalation.

Verifies that repeat occurrences of the same anomaly type score higher,
that escalation multipliers are stored in details, that the decay window
is respected, and that MAX_PER_RULE caps adjust with escalation.

All database and Redis interactions are mocked -- no running services needed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make the scoring service importable
_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
# Make shared importable
sys.path.insert(0, str(_scoring_dir.parent.parent))

from shared.models.anomaly import RuleResult

from aggregator import aggregate_score
from rules.base import ScoringRule


# ---------------------------------------------------------------------------
# Dummy rule for escalation tests
# ---------------------------------------------------------------------------


class DummySpeedRule(ScoringRule):
    """A speed_anomaly rule that fires with 15 points."""

    @property
    def rule_id(self) -> str:
        return "speed_anomaly"

    @property
    def rule_category(self) -> str:
        return "realtime"

    async def evaluate(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        existing_anomalies: Sequence[dict[str, Any]],
        gfw_events: Sequence[dict[str, Any]],
    ) -> Optional[RuleResult]:
        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="moderate",
            points=15.0,
            details={"reason": "speed anomaly detected"},
            source="realtime",
        )


# ---------------------------------------------------------------------------
# Tests: Escalation in _create_anomaly
# ---------------------------------------------------------------------------


class TestEscalationMultiplier:
    """Verify that _create_anomaly applies escalation based on ended event count."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_first_occurrence_no_escalation(self, mock_session):
        """First speed_anomaly event = 15 points (1.0x multiplier)."""
        from engine import ScoringEngine

        result = RuleResult(
            fired=True,
            rule_id="speed_anomaly",
            severity="moderate",
            points=15.0,
            details={"reason": "speed anomaly"},
            source="realtime",
        )

        with (
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1) as mock_create,
        ):
            await ScoringEngine._create_anomaly(mock_session, 123456789, result)

        data = mock_create.call_args[0][1]
        assert data["points"] == 15.0
        # No escalation info in details for first occurrence
        details = json.loads(data["details"])
        assert "occurrence_number" not in details
        assert "escalation_multiplier" not in details

    @pytest.mark.asyncio
    async def test_second_occurrence_15x_escalation(self, mock_session):
        """Second speed_anomaly event = 22.5 points (1.5x multiplier)."""
        from engine import ScoringEngine

        result = RuleResult(
            fired=True,
            rule_id="speed_anomaly",
            severity="moderate",
            points=15.0,
            details={"reason": "speed anomaly"},
            source="realtime",
        )

        with (
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=1),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=2) as mock_create,
        ):
            await ScoringEngine._create_anomaly(mock_session, 234567890, result)

        data = mock_create.call_args[0][1]
        assert data["points"] == 22.5  # 15.0 * 1.5
        details = json.loads(data["details"])
        assert details["occurrence_number"] == 2
        assert details["escalation_multiplier"] == 1.5

    @pytest.mark.asyncio
    async def test_third_occurrence_2x_escalation(self, mock_session):
        """Third speed_anomaly event = 30 points (2.0x multiplier)."""
        from engine import ScoringEngine

        result = RuleResult(
            fired=True,
            rule_id="speed_anomaly",
            severity="moderate",
            points=15.0,
            details={"reason": "speed anomaly"},
            source="realtime",
        )

        with (
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=2),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=3) as mock_create,
        ):
            await ScoringEngine._create_anomaly(mock_session, 345678901, result)

        data = mock_create.call_args[0][1]
        assert data["points"] == 30.0  # 15.0 * 2.0
        details = json.loads(data["details"])
        assert details["occurrence_number"] == 3
        assert details["escalation_multiplier"] == 2.0

    @pytest.mark.asyncio
    async def test_fourth_occurrence_still_2x_cap(self, mock_session):
        """Fourth+ occurrence still gets 2.0x (max multiplier)."""
        from engine import ScoringEngine

        result = RuleResult(
            fired=True,
            rule_id="speed_anomaly",
            severity="moderate",
            points=15.0,
            details={"reason": "speed anomaly"},
            source="realtime",
        )

        with (
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=5),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=4) as mock_create,
        ):
            await ScoringEngine._create_anomaly(mock_session, 456789012, result)

        data = mock_create.call_args[0][1]
        assert data["points"] == 30.0  # 15.0 * 2.0 (capped at 3rd+ multiplier)
        details = json.loads(data["details"])
        assert details["occurrence_number"] == 6
        assert details["escalation_multiplier"] == 2.0

    @pytest.mark.asyncio
    async def test_escalation_multiplier_stored_in_details(self, mock_session):
        """Escalation multiplier should be stored in the anomaly details."""
        from engine import ScoringEngine

        result = RuleResult(
            fired=True,
            rule_id="speed_anomaly",
            severity="moderate",
            points=15.0,
            details={"reason": "repeat speed anomaly"},
            source="realtime",
        )

        with (
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=1),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=5) as mock_create,
        ):
            await ScoringEngine._create_anomaly(mock_session, 567890123, result)

        data = mock_create.call_args[0][1]
        details = json.loads(data["details"])
        assert "escalation_multiplier" in details
        assert details["escalation_multiplier"] == 1.5
        assert details["occurrence_number"] == 2
        # Original details should be preserved
        assert details["reason"] == "repeat speed anomaly"


# ---------------------------------------------------------------------------
# Tests: count_ended_events repository function
# ---------------------------------------------------------------------------


class TestCountEndedEvents:
    """Verify count_ended_events repository function."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_returns_correct_count(self, mock_session):
        """Should return the count from the DB query."""
        from shared.db.repositories import count_ended_events

        mock_result = MagicMock()
        mock_result.first.return_value = (3,)
        mock_session.execute.return_value = mock_result

        count = await count_ended_events(mock_session, 123456789, "speed_anomaly")

        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_rows(self, mock_session):
        """Should return 0 when no ended events are found."""
        from shared.db.repositories import count_ended_events

        mock_result = MagicMock()
        mock_result.first.return_value = (0,)
        mock_session.execute.return_value = mock_result

        count = await count_ended_events(mock_session, 234567890, "ais_gap")

        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_result_is_none(self, mock_session):
        """Should return 0 when query returns no row."""
        from shared.db.repositories import count_ended_events

        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        count = await count_ended_events(mock_session, 345678901, "ais_gap")

        assert count == 0

    @pytest.mark.asyncio
    async def test_sql_filters_by_ended_state_and_decay(self, mock_session):
        """SQL should filter by mmsi, rule_id, event_state='ended', and decay window."""
        from shared.db.repositories import count_ended_events

        mock_result = MagicMock()
        mock_result.first.return_value = (0,)
        mock_session.execute.return_value = mock_result

        await count_ended_events(mock_session, 456789012, "speed_anomaly", decay_days=30)

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        params = call_args[0][1]

        assert "event_state = 'ended'" in sql_text
        assert "event_end >= NOW()" in sql_text
        assert params["mmsi"] == 456789012
        assert params["rule_id"] == "speed_anomaly"
        assert params["decay_days"] == 30

    @pytest.mark.asyncio
    async def test_custom_decay_days(self, mock_session):
        """Should pass custom decay_days to the query."""
        from shared.db.repositories import count_ended_events

        mock_result = MagicMock()
        mock_result.first.return_value = (0,)
        mock_session.execute.return_value = mock_result

        await count_ended_events(mock_session, 567890123, "ais_gap", decay_days=7)

        params = mock_session.execute.call_args[0][1]
        assert params["decay_days"] == 7


# ---------------------------------------------------------------------------
# Tests: Aggregate score with escalation cap adjustment
# ---------------------------------------------------------------------------


class TestAggregateScoreEscalation:
    """Verify that MAX_PER_RULE cap adjusts with escalation multiplier."""

    def test_cap_adjusts_with_escalation_multiplier(self):
        """MAX_PER_RULE cap should be multiplied by escalation multiplier."""
        # speed_anomaly MAX_PER_RULE = 15
        # With 2.0x escalation, cap should be 30
        anomalies = [
            {
                "rule_id": "speed_anomaly",
                "points": 30.0,  # escalated from 15 * 2.0
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({"escalation_multiplier": 2.0, "occurrence_number": 3}),
            },
        ]
        score = aggregate_score(anomalies)
        # cap = 15 * 2.0 = 30, points = 30, min(30, 30) = 30
        assert score == 30.0

    def test_cap_without_escalation_still_works(self):
        """Without escalation multiplier, original cap applies."""
        anomalies = [
            {
                "rule_id": "speed_anomaly",
                "points": 15.0,
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({"reason": "first occurrence"}),
            },
        ]
        score = aggregate_score(anomalies)
        assert score == 15.0

    def test_escalated_points_capped_at_adjusted_cap(self):
        """Even with escalation, points exceeding the adjusted cap should be capped."""
        # speed_anomaly MAX_PER_RULE = 15, with 1.5x escalation, cap = 22.5
        anomalies = [
            {
                "rule_id": "speed_anomaly",
                "points": 22.5,  # 15 * 1.5
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({"escalation_multiplier": 1.5, "occurrence_number": 2}),
            },
            {
                "rule_id": "speed_anomaly",
                "points": 22.5,  # another escalated anomaly
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({"escalation_multiplier": 1.5, "occurrence_number": 2}),
            },
        ]
        score = aggregate_score(anomalies)
        # raw total = 45, adjusted cap = 15 * 1.5 = 22.5
        assert score == 22.5

    def test_aggregate_correctly_sums_escalated_with_cap(self):
        """Multiple rules with different escalation levels sum correctly."""
        anomalies = [
            {
                "rule_id": "speed_anomaly",
                "points": 30.0,  # 15 * 2.0
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({"escalation_multiplier": 2.0}),
            },
            {
                "rule_id": "ais_gap",
                "points": 40.0,
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({}),  # no escalation
            },
        ]
        score = aggregate_score(anomalies)
        # speed_anomaly: min(30, 15*2.0) = 30
        # ais_gap: min(40, 40*1.0) = 40
        assert score == 70.0

    def test_details_as_dict_works(self):
        """Details passed as dict (not JSON string) should work for escalation."""
        anomalies = [
            {
                "rule_id": "speed_anomaly",
                "points": 22.5,
                "resolved": False,
                "event_state": "active",
                "details": {"escalation_multiplier": 1.5},
            },
        ]
        score = aggregate_score(anomalies)
        # cap = 15 * 1.5 = 22.5, points = 22.5
        assert score == 22.5

    def test_highest_escalation_multiplier_used_for_cap(self):
        """When multiple anomalies for same rule have different multipliers,
        the highest should be used for the cap."""
        anomalies = [
            {
                "rule_id": "speed_anomaly",
                "points": 15.0,
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({}),  # 1.0x
            },
            {
                "rule_id": "speed_anomaly",
                "points": 22.5,  # 1.5x
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({"escalation_multiplier": 1.5}),
            },
        ]
        score = aggregate_score(anomalies)
        # raw total = 37.5, cap = 15 * 1.5 = 22.5
        assert score == 22.5
