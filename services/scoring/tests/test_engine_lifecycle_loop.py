"""Tests for Story 6: Engine Event Lifecycle Loop.

Verifies that the engine checks and ends active anomalies whose conditions
have ceased, and that aggregate_score only includes active anomalies.

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
# Dummy rules
# ---------------------------------------------------------------------------


class DummySpeedAnomalyRule(ScoringRule):
    """A realtime rule that fires. Ends when vessel speed > 5 knots."""

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
            details={"reason": "vessel speed anomaly detected"},
            source="realtime",
        )

    async def check_event_ended(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        active_anomaly: dict[str, Any],
    ) -> bool:
        # End the event if the latest position shows speed > 5
        if recent_positions:
            latest = recent_positions[-1]
            return float(latest.get("sog", 0)) > 5.0
        return False


class DummyAisGapRule(ScoringRule):
    """A realtime rule for AIS gap. Ends when position is received."""

    @property
    def rule_id(self) -> str:
        return "ais_gap"

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
            severity="high",
            points=40.0,
            details={"reason": "ais gap detected"},
            source="realtime",
        )

    async def check_event_ended(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        active_anomaly: dict[str, Any],
    ) -> bool:
        # End the event if we have a recent position
        if recent_positions:
            return True
        return False


class DummyNeverEndsRule(ScoringRule):
    """A rule that never ends its events (default behavior)."""

    @property
    def rule_id(self) -> str:
        return "sanctions_match"

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
            severity="critical",
            points=100.0,
            details={"reason": "sanctions match"},
            source="realtime",
        )
    # Uses default check_event_ended which returns False


class DummyErrorRule(ScoringRule):
    """A rule whose check_event_ended raises an exception."""

    @property
    def rule_id(self) -> str:
        return "error_rule"

    @property
    def rule_category(self) -> str:
        return "realtime"

    async def evaluate(self, *args, **kwargs) -> Optional[RuleResult]:
        return None

    async def check_event_ended(self, *args, **kwargs) -> bool:
        raise RuntimeError("check failed")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEngineLifecycleCheck:
    """Engine evaluate_realtime calls lifecycle check for all active anomalies."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_evaluate_realtime_calls_lifecycle_check(self, mock_session):
        """Engine should call _check_and_end_active_events during evaluate_realtime."""
        from engine import ScoringEngine

        rule = DummySpeedAnomalyRule()
        engine = ScoringEngine(rules=[rule])
        mock_factory = MagicMock(return_value=mock_session)

        profile = {"mmsi": 123456789, "risk_tier": "green", "risk_score": 0.0}
        active_anomalies = [
            {
                "id": 10,
                "mmsi": 123456789,
                "rule_id": "speed_anomaly",
                "severity": "moderate",
                "points": 15.0,
                "event_state": "active",
            },
        ]

        # Recent positions: vessel is now going fast (speed > 5), so event should end
        recent_positions = [
            {"timestamp": datetime.now(timezone.utc), "sog": 12.0, "lat": 36.0, "lon": 22.0},
        ]

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=profile),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=recent_positions),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=active_anomalies),
            patch("engine.end_anomaly_event", new_callable=AsyncMock) as mock_end,
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1),
        ):
            await engine.evaluate_realtime(123456789)

        # end_anomaly_event should have been called for the active anomaly
        mock_end.assert_called_once_with(mock_session, 10)

    @pytest.mark.asyncio
    async def test_speed_anomaly_ended_when_vessel_speeds_up(self, mock_session):
        """Active speed_anomaly should be ended when vessel speeds up past threshold."""
        from engine import ScoringEngine

        rule = DummySpeedAnomalyRule()
        engine = ScoringEngine(rules=[rule])

        profile = {"mmsi": 234567890, "risk_tier": "yellow", "risk_score": 15.0}
        active_anomalies = [
            {
                "id": 5,
                "mmsi": 234567890,
                "rule_id": "speed_anomaly",
                "severity": "moderate",
                "points": 15.0,
                "event_state": "active",
            },
        ]
        # Vessel now at 10 knots -> should end the speed anomaly
        recent_positions = [
            {"timestamp": datetime.now(timezone.utc), "sog": 10.0, "lat": 36.0, "lon": 22.0},
        ]

        with (
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=active_anomalies),
            patch("engine.end_anomaly_event", new_callable=AsyncMock) as mock_end,
        ):
            ended_ids = await engine._check_and_end_active_events(
                mock_session, 234567890, profile, recent_positions
            )

        mock_end.assert_called_once_with(mock_session, 5)
        assert 5 in ended_ids

    @pytest.mark.asyncio
    async def test_ais_gap_ended_when_position_received(self, mock_session):
        """Active ais_gap should be ended when a new position is received."""
        from engine import ScoringEngine

        rule = DummyAisGapRule()
        engine = ScoringEngine(rules=[rule])

        profile = {"mmsi": 345678901, "risk_tier": "yellow", "risk_score": 40.0}
        active_anomalies = [
            {
                "id": 7,
                "mmsi": 345678901,
                "rule_id": "ais_gap",
                "severity": "high",
                "points": 40.0,
                "event_state": "active",
            },
        ]
        recent_positions = [
            {"timestamp": datetime.now(timezone.utc), "sog": 8.0, "lat": 37.0, "lon": 23.0},
        ]

        with patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=active_anomalies):
            ended_ids = await engine._check_and_end_active_events(
                mock_session, 345678901, profile, recent_positions
            )

        assert 7 in ended_ids

    @pytest.mark.asyncio
    async def test_ended_anomalies_call_end_anomaly_event(self, mock_session):
        """Ended anomalies should trigger end_anomaly_event with correct ID."""
        from engine import ScoringEngine

        rule = DummySpeedAnomalyRule()
        engine = ScoringEngine(rules=[rule])

        active_anomalies = [
            {
                "id": 42,
                "mmsi": 456789012,
                "rule_id": "speed_anomaly",
                "severity": "moderate",
                "points": 15.0,
                "event_state": "active",
            },
        ]
        recent_positions = [{"timestamp": datetime.now(timezone.utc), "sog": 8.0}]

        with (
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=active_anomalies),
            patch("engine.end_anomaly_event", new_callable=AsyncMock) as mock_end,
        ):
            ended_ids = await engine._check_and_end_active_events(
                mock_session, 456789012, {}, recent_positions
            )

        mock_end.assert_called_once_with(mock_session, 42)
        assert ended_ids == [42]

    @pytest.mark.asyncio
    async def test_rule_not_found_skips_anomaly(self, mock_session):
        """Anomalies for unknown rules should be skipped (not ended)."""
        from engine import ScoringEngine

        # Engine only has speed_anomaly rule
        engine = ScoringEngine(rules=[DummySpeedAnomalyRule()])

        active_anomalies = [
            {
                "id": 99,
                "mmsi": 567890123,
                "rule_id": "unknown_rule",
                "severity": "low",
                "points": 5.0,
                "event_state": "active",
            },
        ]
        recent_positions = [{"timestamp": datetime.now(timezone.utc), "sog": 10.0}]

        with (
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=active_anomalies),
            patch("engine.end_anomaly_event", new_callable=AsyncMock) as mock_end,
        ):
            ended_ids = await engine._check_and_end_active_events(
                mock_session, 567890123, {}, recent_positions
            )

        mock_end.assert_not_called()
        assert ended_ids == []

    @pytest.mark.asyncio
    async def test_check_event_ended_exception_is_caught(self, mock_session):
        """If check_event_ended raises, the error should be caught and anomaly skipped."""
        from engine import ScoringEngine

        engine = ScoringEngine(rules=[DummyErrorRule()])

        active_anomalies = [
            {
                "id": 88,
                "mmsi": 678901234,
                "rule_id": "error_rule",
                "severity": "low",
                "points": 5.0,
                "event_state": "active",
            },
        ]

        with (
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=active_anomalies),
            patch("engine.end_anomaly_event", new_callable=AsyncMock) as mock_end,
        ):
            ended_ids = await engine._check_and_end_active_events(
                mock_session, 678901234, {}, []
            )

        mock_end.assert_not_called()
        assert ended_ids == []

    @pytest.mark.asyncio
    async def test_never_ends_rule_keeps_anomaly_active(self, mock_session):
        """Rules with default check_event_ended (returns False) should not end."""
        from engine import ScoringEngine

        engine = ScoringEngine(rules=[DummyNeverEndsRule()])

        active_anomalies = [
            {
                "id": 77,
                "mmsi": 789012345,
                "rule_id": "sanctions_match",
                "severity": "critical",
                "points": 100.0,
                "event_state": "active",
            },
        ]

        with (
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=active_anomalies),
            patch("engine.end_anomaly_event", new_callable=AsyncMock) as mock_end,
        ):
            ended_ids = await engine._check_and_end_active_events(
                mock_session, 789012345, {}, [{"sog": 10.0}]
            )

        mock_end.assert_not_called()
        assert ended_ids == []


class TestAggregateScoreActiveOnly:
    """Aggregate score only includes active anomalies (not ended ones)."""

    def test_active_anomalies_contribute_to_score(self):
        """Anomalies with event_state='active' should contribute."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False, "event_state": "active"},
            {"rule_id": "speed_anomaly", "points": 10.0, "resolved": False, "event_state": "active"},
        ]
        score = aggregate_score(anomalies)
        assert score == 25.0

    def test_ended_anomalies_excluded_from_score(self):
        """Anomalies with event_state='ended' should not contribute."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False, "event_state": "active"},
            {"rule_id": "speed_anomaly", "points": 10.0, "resolved": False, "event_state": "ended"},
        ]
        score = aggregate_score(anomalies)
        assert score == 15.0

    def test_superseded_anomalies_excluded_from_score(self):
        """Anomalies with event_state='superseded' should not contribute."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False, "event_state": "active"},
            {"rule_id": "speed_anomaly", "points": 10.0, "resolved": False, "event_state": "superseded"},
        ]
        score = aggregate_score(anomalies)
        assert score == 15.0

    def test_null_event_state_treated_as_active(self):
        """Backward compat: anomalies without event_state should be treated as active."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
            {"rule_id": "speed_anomaly", "points": 10.0, "resolved": False, "event_state": None},
        ]
        score = aggregate_score(anomalies)
        assert score == 25.0

    def test_resolved_still_excluded(self):
        """Resolved anomalies remain excluded even if event_state is active."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": True, "event_state": "active"},
            {"rule_id": "speed_anomaly", "points": 10.0, "resolved": False, "event_state": "active"},
        ]
        score = aggregate_score(anomalies)
        assert score == 10.0

    def test_mix_of_active_ended_and_no_state(self):
        """Score should only sum active + null-state anomalies."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False, "event_state": "active"},
            {"rule_id": "speed_anomaly", "points": 10.0, "resolved": False, "event_state": "ended"},
            {"rule_id": "sanctions_match", "points": 40.0, "resolved": False},  # no event_state
            {"rule_id": "identity_mismatch", "points": 25.0, "resolved": True, "event_state": "active"},
        ]
        score = aggregate_score(anomalies)
        assert score == 55.0  # 15 (ais_gap) + 40 (sanctions_match)
