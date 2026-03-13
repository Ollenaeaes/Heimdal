"""Tests for score aggregation, tier calculation, dedup logic, and engine integration.

All database and Redis interactions are mocked — no running services needed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Make the scoring service importable
from pathlib import Path

_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
# Make shared importable
sys.path.insert(0, str(_scoring_dir.parent.parent))

from shared.models.anomaly import RuleResult

from aggregator import (
    aggregate_score,
    calculate_tier,
    find_suppressed_anomalies,
    publish_anomaly,
    publish_risk_change,
)
from rules.base import ScoringRule


# ---------------------------------------------------------------------------
# Dummy rules for integration tests
# ---------------------------------------------------------------------------


class DummyRealtimeRule(ScoringRule):
    """A real-time rule that always fires."""

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
            points=15.0,
            details={"reason": "ais gap detected"},
            source="realtime",
        )


class DummyGfwRule(ScoringRule):
    """A GFW rule that always fires — gfw_ais_disabling."""

    @property
    def rule_id(self) -> str:
        return "gfw_ais_disabling"

    @property
    def rule_category(self) -> str:
        return "gfw_sourced"

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
            points=50.0,
            details={"reason": "gfw ais disabling detected"},
            source="gfw",
        )


# ---------------------------------------------------------------------------
# Test: Score aggregation
# ---------------------------------------------------------------------------


class TestAggregateScore:
    """Verify score aggregation with per-rule caps."""

    def test_sums_multiple_anomaly_points(self):
        """Score correctly sums points from multiple unresolved anomalies."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
            {"rule_id": "sts_proximity", "points": 15.0, "resolved": False},
            {"rule_id": "destination_spoof", "points": 15.0, "resolved": False},
        ]
        score = aggregate_score(anomalies)
        assert score == 45.0

    def test_per_rule_cap_prevents_runaway_scores(self):
        """10 AIS gap events should not give 10x points — capped by MAX_PER_RULE."""
        # MAX_PER_RULE["ais_gap"] = 30
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False}
            for _ in range(10)
        ]
        score = aggregate_score(anomalies)
        # 10 * 15 = 150, but cap is 30
        assert score == 30.0

    def test_resolved_anomalies_excluded(self):
        """Resolved anomalies should not contribute to the score."""
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": True},
            {"rule_id": "sts_proximity", "points": 15.0, "resolved": False},
        ]
        score = aggregate_score(anomalies)
        assert score == 15.0

    def test_empty_anomalies_return_zero(self):
        """No anomalies means score is 0."""
        assert aggregate_score([]) == 0.0

    def test_multiple_rules_each_capped_independently(self):
        """Each rule's total is capped independently."""
        # MAX_PER_RULE["ais_gap"] = 30, MAX_PER_RULE["sts_proximity"] = 25
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
            {"rule_id": "sts_proximity", "points": 15.0, "resolved": False},
            {"rule_id": "sts_proximity", "points": 15.0, "resolved": False},
        ]
        score = aggregate_score(anomalies)
        # ais_gap: 3*15=45, capped at 30
        # sts_proximity: 2*15=30, capped at 25
        assert score == 55.0

    def test_cap_at_exact_max(self):
        """If total equals the cap, it should pass through unchanged."""
        # MAX_PER_RULE["ais_gap"] = 30
        anomalies = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
        ]
        score = aggregate_score(anomalies)
        assert score == 30.0

    def test_single_anomaly_below_cap(self):
        """A single anomaly below the cap should pass through unchanged."""
        anomalies = [
            {"rule_id": "sanctions_match", "points": 40.0, "resolved": False},
        ]
        score = aggregate_score(anomalies)
        assert score == 40.0


# ---------------------------------------------------------------------------
# Test: Tier calculation
# ---------------------------------------------------------------------------


class TestCalculateTier:
    """Verify tier thresholds: 0-29=green, 30-99=yellow, 100+=red."""

    def test_green_below_30(self):
        assert calculate_tier(0.0) == "green"
        assert calculate_tier(15.0) == "green"
        assert calculate_tier(29.0) == "green"
        assert calculate_tier(29.9) == "green"

    def test_yellow_30_to_99(self):
        assert calculate_tier(30.0) == "yellow"
        assert calculate_tier(50.0) == "yellow"
        assert calculate_tier(99.0) == "yellow"
        assert calculate_tier(99.9) == "yellow"

    def test_red_100_and_above(self):
        assert calculate_tier(100.0) == "red"
        assert calculate_tier(150.0) == "red"
        assert calculate_tier(500.0) == "red"

    def test_exact_boundaries(self):
        """Exact boundary values must map to the correct tier."""
        assert calculate_tier(0.0) == "green"
        assert calculate_tier(30.0) == "yellow"
        assert calculate_tier(100.0) == "red"


# ---------------------------------------------------------------------------
# Test: Dedup logic
# ---------------------------------------------------------------------------


class TestDedupLogic:
    """Verify GFW anomalies suppress corresponding real-time anomalies."""

    def _make_anomaly(
        self,
        rule_id: str,
        created_at: datetime,
        resolved: bool = False,
        anomaly_id: int = 1,
    ) -> dict[str, Any]:
        return {
            "id": anomaly_id,
            "rule_id": rule_id,
            "resolved": resolved,
            "created_at": created_at,
            "points": 15.0,
        }

    def test_gfw_ais_disabling_suppresses_ais_gap(self):
        """gfw_ais_disabling should suppress real-time ais_gap within time window."""
        now = datetime.now(timezone.utc)
        existing = [
            self._make_anomaly("ais_gap", now - timedelta(hours=2)),
        ]
        suppressed = find_suppressed_anomalies("gfw_ais_disabling", now, existing)
        assert len(suppressed) == 1
        assert suppressed[0]["rule_id"] == "ais_gap"

    def test_gfw_encounter_suppresses_sts_proximity(self):
        """gfw_encounter should suppress real-time sts_proximity."""
        now = datetime.now(timezone.utc)
        existing = [
            self._make_anomaly("sts_proximity", now - timedelta(hours=1)),
        ]
        suppressed = find_suppressed_anomalies("gfw_encounter", now, existing)
        assert len(suppressed) == 1
        assert suppressed[0]["rule_id"] == "sts_proximity"

    def test_gfw_loitering_suppresses_sts_proximity(self):
        """gfw_loitering should suppress real-time sts_proximity."""
        now = datetime.now(timezone.utc)
        existing = [
            self._make_anomaly("sts_proximity", now + timedelta(hours=3)),
        ]
        suppressed = find_suppressed_anomalies("gfw_loitering", now, existing)
        assert len(suppressed) == 1

    def test_gfw_port_visit_has_no_dedup_partner(self):
        """gfw_port_visit should not suppress anything."""
        now = datetime.now(timezone.utc)
        existing = [
            self._make_anomaly("ais_gap", now),
            self._make_anomaly("sts_proximity", now, anomaly_id=2),
        ]
        suppressed = find_suppressed_anomalies("gfw_port_visit", now, existing)
        assert len(suppressed) == 0

    def test_outside_dedup_window_not_suppressed(self):
        """Anomaly outside the +-6h window should NOT be suppressed."""
        now = datetime.now(timezone.utc)
        existing = [
            self._make_anomaly("ais_gap", now - timedelta(hours=7)),
        ]
        suppressed = find_suppressed_anomalies("gfw_ais_disabling", now, existing)
        assert len(suppressed) == 0

    def test_already_resolved_not_suppressed(self):
        """Already-resolved anomalies should NOT be suppressed again."""
        now = datetime.now(timezone.utc)
        existing = [
            self._make_anomaly("ais_gap", now - timedelta(hours=1), resolved=True),
        ]
        suppressed = find_suppressed_anomalies("gfw_ais_disabling", now, existing)
        assert len(suppressed) == 0

    def test_different_rule_not_suppressed(self):
        """Anomalies for a non-dedup-partner rule should NOT be suppressed."""
        now = datetime.now(timezone.utc)
        existing = [
            self._make_anomaly("destination_spoof", now),
        ]
        suppressed = find_suppressed_anomalies("gfw_ais_disabling", now, existing)
        assert len(suppressed) == 0

    def test_after_dedup_only_gfw_contributes(self):
        """After dedup, only the GFW anomaly contributes to score."""
        now = datetime.now(timezone.utc)
        anomalies = [
            {
                "id": 1,
                "rule_id": "ais_gap",
                "points": 15.0,
                "resolved": False,
                "created_at": now - timedelta(hours=1),
            },
            {
                "id": 2,
                "rule_id": "gfw_ais_disabling",
                "points": 50.0,
                "resolved": False,
                "created_at": now,
            },
        ]

        # Before dedup, both contribute
        score_before = aggregate_score(anomalies)
        assert score_before == 65.0  # 15 + 50

        # Run dedup — mark the real-time anomaly as resolved
        suppressed = find_suppressed_anomalies(
            "gfw_ais_disabling", now, anomalies
        )
        assert len(suppressed) == 1
        for s in suppressed:
            s["resolved"] = True

        # After dedup, only GFW contributes
        score_after = aggregate_score(anomalies)
        assert score_after == 50.0


# ---------------------------------------------------------------------------
# Test: Redis publishing
# ---------------------------------------------------------------------------


class TestRedisPublishing:
    """Verify Redis publish payloads for tier changes and anomalies."""

    @pytest.mark.asyncio
    async def test_publish_risk_change_payload(self):
        """Tier change publishes correct payload to heimdal:risk_changes."""
        mock_redis = AsyncMock()
        await publish_risk_change(
            mock_redis,
            mmsi=123456789,
            old_tier="green",
            new_tier="yellow",
            score=45.0,
            trigger_rule="ais_gap",
        )

        mock_redis.publish.assert_called_once()
        channel, raw_payload = mock_redis.publish.call_args[0]
        assert channel == "heimdal:risk_changes"
        payload = json.loads(raw_payload)
        assert payload["mmsi"] == 123456789
        assert payload["old_tier"] == "green"
        assert payload["new_tier"] == "yellow"
        assert payload["score"] == 45.0
        assert payload["trigger_rule"] == "ais_gap"
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_publish_anomaly_payload(self):
        """New anomaly publishes correct payload to heimdal:anomalies."""
        mock_redis = AsyncMock()
        await publish_anomaly(
            mock_redis,
            mmsi=987654321,
            rule_id="gfw_ais_disabling",
            severity="critical",
            points=50.0,
            details={"reason": "ais disabling detected"},
        )

        mock_redis.publish.assert_called_once()
        channel, raw_payload = mock_redis.publish.call_args[0]
        assert channel == "heimdal:anomalies"
        payload = json.loads(raw_payload)
        assert payload["mmsi"] == 987654321
        assert payload["rule_id"] == "gfw_ais_disabling"
        assert payload["severity"] == "critical"
        assert payload["points"] == 50.0
        assert payload["details"]["reason"] == "ais disabling detected"
        assert "timestamp" in payload


# ---------------------------------------------------------------------------
# Test: Engine integration — tier change triggers Redis publish
# ---------------------------------------------------------------------------


class TestEngineTierChangePublish:
    """Verify the engine publishes tier changes and respects no-publish when tier stays same."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    def _make_engine(self, rules, redis_client=None):
        from engine import ScoringEngine

        return ScoringEngine(rules=rules, redis_client=redis_client)

    @pytest.mark.asyncio
    async def test_tier_change_triggers_redis_publish(self, mock_session):
        """When tier changes (green -> yellow), Redis publish should fire."""
        mock_redis = AsyncMock()
        engine = self._make_engine([DummyRealtimeRule()], redis_client=mock_redis)
        mock_factory = MagicMock(return_value=mock_session)

        # Profile starts at green with score 0
        profile = {"mmsi": 123456789, "risk_tier": "green", "risk_score": 0.0}

        # After evaluation, list_anomaly_events returns enough to push to yellow
        anomalies_after = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
            {"rule_id": "destination_spoof", "points": 40.0, "resolved": False},
        ]

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=profile),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, side_effect=[
                [],  # first call: existing anomalies for rule evaluation
                anomalies_after,  # second call: after persist, for score calc
            ]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1),
        ):
            await engine.evaluate_realtime(123456789)

        # Check that Redis publish was called for risk change
        publish_calls = mock_redis.publish.call_args_list
        channels = [c[0][0] for c in publish_calls]
        assert "heimdal:risk_changes" in channels

        # Find the risk_changes call and verify payload
        for c in publish_calls:
            if c[0][0] == "heimdal:risk_changes":
                payload = json.loads(c[0][1])
                assert payload["mmsi"] == 123456789
                assert payload["old_tier"] == "green"
                assert payload["new_tier"] == "yellow"
                assert payload["trigger_rule"] == "ais_gap"

    @pytest.mark.asyncio
    async def test_no_redis_publish_when_tier_stays_same(self, mock_session):
        """When tier doesn't change, no risk_changes publish should fire."""
        mock_redis = AsyncMock()
        engine = self._make_engine([DummyRealtimeRule()], redis_client=mock_redis)
        mock_factory = MagicMock(return_value=mock_session)

        # Profile already at yellow
        profile = {"mmsi": 123456789, "risk_tier": "yellow", "risk_score": 30.0}

        # Anomalies still in yellow range
        anomalies_after = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
            {"rule_id": "destination_spoof", "points": 40.0, "resolved": False},
        ]

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=profile),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, side_effect=[
                [],
                anomalies_after,
            ]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1),
        ):
            await engine.evaluate_realtime(123456789)

        # Check that no risk_changes publish fired
        publish_calls = mock_redis.publish.call_args_list
        risk_change_calls = [c for c in publish_calls if c[0][0] == "heimdal:risk_changes"]
        assert len(risk_change_calls) == 0

    @pytest.mark.asyncio
    async def test_anomaly_publish_on_new_anomaly(self, mock_session):
        """New anomaly should publish to heimdal:anomalies."""
        mock_redis = AsyncMock()
        engine = self._make_engine([DummyRealtimeRule()], redis_client=mock_redis)
        mock_factory = MagicMock(return_value=mock_session)

        profile = {"mmsi": 123456789, "risk_tier": "green", "risk_score": 0.0}
        anomalies_after = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
        ]

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=profile),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, side_effect=[
                [],
                anomalies_after,
            ]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1),
        ):
            await engine.evaluate_realtime(123456789)

        # Check anomaly publish
        publish_calls = mock_redis.publish.call_args_list
        anomaly_calls = [c for c in publish_calls if c[0][0] == "heimdal:anomalies"]
        assert len(anomaly_calls) == 1
        payload = json.loads(anomaly_calls[0][0][1])
        assert payload["mmsi"] == 123456789
        assert payload["rule_id"] == "ais_gap"
        assert payload["severity"] == "high"
        assert payload["points"] == 15.0


# ---------------------------------------------------------------------------
# Test: Engine integration — GFW dedup in evaluate_gfw
# ---------------------------------------------------------------------------


class TestEngineGfwDedup:
    """Verify that evaluate_gfw runs dedup and resolves real-time anomalies."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_gfw_eval_suppresses_realtime_anomaly(self, mock_session):
        """When gfw_ais_disabling fires and an ais_gap anomaly exists within
        the dedup window, the ais_gap should be resolved."""
        from engine import ScoringEngine

        now = datetime.now(timezone.utc)
        mock_redis = AsyncMock()
        engine = ScoringEngine(rules=[DummyGfwRule()], redis_client=mock_redis)
        mock_factory = MagicMock(return_value=mock_session)

        profile = {"mmsi": 123456789, "risk_tier": "green", "risk_score": 0.0}
        existing_anomalies = [
            {
                "id": 42,
                "rule_id": "ais_gap",
                "points": 15.0,
                "resolved": False,
                "created_at": now - timedelta(hours=2),
            },
        ]
        # After dedup + new gfw anomaly persisted
        anomalies_after = [
            {"rule_id": "gfw_ais_disabling", "points": 50.0, "resolved": False},
            {"rule_id": "ais_gap", "points": 15.0, "resolved": True},
        ]

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=profile),
            patch("engine.list_gfw_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, side_effect=[
                existing_anomalies,
                anomalies_after,
            ]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=2),
        ):
            results = await engine.evaluate_gfw(123456789)

        # The engine should have called execute to resolve anomaly id=42
        resolve_calls = [
            c for c in mock_session.execute.call_args_list
            if hasattr(c[0][0], "text") and "resolved = true" in c[0][0].text
        ]
        assert len(resolve_calls) == 1

    @pytest.mark.asyncio
    async def test_no_redis_client_does_not_crash(self, mock_session):
        """Engine with no redis_client should still work — just skip publishing."""
        from engine import ScoringEngine

        engine = ScoringEngine(rules=[DummyRealtimeRule()], redis_client=None)
        mock_factory = MagicMock(return_value=mock_session)

        profile = {"mmsi": 123456789, "risk_tier": "green", "risk_score": 0.0}
        anomalies_after = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
        ]

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=profile),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, side_effect=[
                [],
                anomalies_after,
            ]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1),
        ):
            results = await engine.evaluate_realtime(123456789)

        assert len(results) == 1
        assert results[0].fired is True


# ---------------------------------------------------------------------------
# Test: DB update for risk_score/risk_tier
# ---------------------------------------------------------------------------


class TestEngineDbUpdate:
    """Verify the engine updates vessel_profiles with new score and tier."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_vessel_profile_updated_with_new_score(self, mock_session):
        """After evaluation, vessel_profiles should be updated with new score and tier."""
        from engine import ScoringEngine

        engine = ScoringEngine(rules=[DummyRealtimeRule()], redis_client=AsyncMock())
        mock_factory = MagicMock(return_value=mock_session)

        profile = {"mmsi": 123456789, "risk_tier": "green", "risk_score": 0.0}
        anomalies_after = [
            {"rule_id": "ais_gap", "points": 15.0, "resolved": False},
        ]

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=profile),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, side_effect=[
                [],
                anomalies_after,
            ]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1),
        ):
            await engine.evaluate_realtime(123456789)

        # Check that session.execute was called with UPDATE vessel_profiles
        update_calls = [
            c for c in mock_session.execute.call_args_list
            if hasattr(c[0][0], "text") and "UPDATE vessel_profiles" in c[0][0].text
        ]
        assert len(update_calls) == 1
        # Verify the params passed
        params = update_calls[0][0][1]
        assert params["mmsi"] == 123456789
        assert params["score"] == 15.0
        assert params["tier"] == "green"  # 15 < 30 = green
