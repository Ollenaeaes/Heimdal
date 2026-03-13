"""Tests for the scoring engine: rule discovery, evaluation, persistence.

All database and Redis interactions are mocked — no running services needed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
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

from rules.base import ScoringRule


# ---------------------------------------------------------------------------
# Dummy rules for testing discovery and evaluation
# ---------------------------------------------------------------------------


class DummyRealtimeRule(ScoringRule):
    """A real-time rule that always fires."""

    @property
    def rule_id(self) -> str:
        return "dummy_realtime"

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
            details={"reason": "test firing"},
            source="realtime",
        )


class DummyGfwRule(ScoringRule):
    """A GFW-sourced rule that always fires."""

    @property
    def rule_id(self) -> str:
        return "dummy_gfw"

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
            points=100.0,
            details={"reason": "gfw test firing"},
            source="gfw",
        )


class DummyNonFiringRule(ScoringRule):
    """A real-time rule that never fires."""

    @property
    def rule_id(self) -> str:
        return "dummy_silent"

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
            fired=False,
            rule_id=self.rule_id,
        )


class DummyNoneReturningRule(ScoringRule):
    """A rule that returns None (chose not to evaluate)."""

    @property
    def rule_id(self) -> str:
        return "dummy_none"

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
        return None


# ---------------------------------------------------------------------------
# Test: Rule discovery
# ---------------------------------------------------------------------------


class TestRuleDiscovery:
    """Verify that the engine discovers rule classes from the rules/ package."""

    def test_discover_rules_finds_concrete_subclasses(self):
        """Plant dummy rule modules into the rules package and verify
        that ``discover_rules`` picks them up."""
        from engine import discover_rules

        # Create a fake module with a concrete rule
        fake_mod = types.ModuleType("rules.fake_test_rule")
        fake_mod.DummyRealtimeRule = DummyRealtimeRule  # type: ignore[attr-defined]

        # Patch pkgutil.walk_packages to return our fake module
        fake_iter = [
            (None, "rules.fake_test_rule", False),
        ]

        with (
            patch("engine.pkgutil.walk_packages", return_value=iter(fake_iter)),
            patch("engine.importlib.import_module", return_value=fake_mod),
        ):
            rules = discover_rules()

        assert len(rules) >= 1
        rule_ids = [r.rule_id for r in rules]
        assert "dummy_realtime" in rule_ids

    def test_discover_rules_ignores_abstract_base(self):
        """The abstract ScoringRule itself should not be instantiated."""
        from engine import discover_rules

        fake_mod = types.ModuleType("rules.base_only")
        fake_mod.ScoringRule = ScoringRule  # type: ignore[attr-defined]

        fake_iter = [(None, "rules.base_only", False)]

        with (
            patch("engine.pkgutil.walk_packages", return_value=iter(fake_iter)),
            patch("engine.importlib.import_module", return_value=fake_mod),
        ):
            rules = discover_rules()

        rule_ids = [r.rule_id for r in rules]
        # ScoringRule is abstract — it must NOT appear
        assert all(rid != "ScoringRule" for rid in rule_ids)

    def test_discover_rules_finds_multiple_categories(self):
        """Discovery should find both gfw_sourced and realtime rules."""
        from engine import discover_rules

        fake_mod = types.ModuleType("rules.multi")
        fake_mod.DummyRealtimeRule = DummyRealtimeRule  # type: ignore[attr-defined]
        fake_mod.DummyGfwRule = DummyGfwRule  # type: ignore[attr-defined]

        fake_iter = [(None, "rules.multi", False)]

        with (
            patch("engine.pkgutil.walk_packages", return_value=iter(fake_iter)),
            patch("engine.importlib.import_module", return_value=fake_mod),
        ):
            rules = discover_rules()

        categories = {r.rule_category for r in rules}
        assert "realtime" in categories
        assert "gfw_sourced" in categories


# ---------------------------------------------------------------------------
# Test: Engine evaluation
# ---------------------------------------------------------------------------


class TestEngineEvaluation:
    """Verify that the engine evaluates the right rules for each channel."""

    @pytest.fixture
    def mock_session(self):
        """Return a mock async session and patch get_session to return it."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    def _make_engine(self, rules: list[ScoringRule]):
        from engine import ScoringEngine

        return ScoringEngine(rules=rules)

    @pytest.mark.asyncio
    async def test_evaluate_realtime_calls_only_realtime_rules(self, mock_session):
        """Only realtime-category rules should run for position events."""
        rt_rule = DummyRealtimeRule()
        gfw_rule = DummyGfwRule()
        engine = self._make_engine([rt_rule, gfw_rule])

        mock_factory = MagicMock(return_value=mock_session)

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value={"mmsi": 123456789}),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1) as mock_create,
        ):
            results = await engine.evaluate_realtime(123456789)

        # Only the realtime rule should fire
        fired_ids = [r.rule_id for r in results if r.fired]
        assert "dummy_realtime" in fired_ids
        assert "dummy_gfw" not in fired_ids

        # Anomaly should be created for the fired rule
        mock_create.assert_called_once()
        call_data = mock_create.call_args[0][1]
        assert call_data["rule_id"] == "dummy_realtime"
        assert call_data["severity"] == "high"
        assert call_data["points"] == 40.0

    @pytest.mark.asyncio
    async def test_evaluate_gfw_calls_only_gfw_rules(self, mock_session):
        """Only gfw_sourced-category rules should run for enrichment events."""
        rt_rule = DummyRealtimeRule()
        gfw_rule = DummyGfwRule()
        engine = self._make_engine([rt_rule, gfw_rule])

        mock_factory = MagicMock(return_value=mock_session)

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value={"mmsi": 123456789}),
            patch("engine.list_gfw_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1) as mock_create,
        ):
            results = await engine.evaluate_gfw(123456789)

        fired_ids = [r.rule_id for r in results if r.fired]
        assert "dummy_gfw" in fired_ids
        assert "dummy_realtime" not in fired_ids

        mock_create.assert_called_once()
        call_data = mock_create.call_args[0][1]
        assert call_data["rule_id"] == "dummy_gfw"
        assert call_data["severity"] == "critical"
        assert call_data["points"] == 100.0

    @pytest.mark.asyncio
    async def test_evaluate_all_rules_for_mmsi(self, mock_session):
        """Engine evaluates every rule in its category for a given MMSI."""
        rules = [DummyRealtimeRule(), DummyNonFiringRule(), DummyNoneReturningRule()]
        engine = self._make_engine(rules)

        mock_factory = MagicMock(return_value=mock_session)

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value={"mmsi": 123456789}),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1),
        ):
            results = await engine.evaluate_realtime(123456789)

        # DummyRealtimeRule returns fired=True result
        # DummyNonFiringRule returns fired=False result
        # DummyNoneReturningRule returns None (excluded from results)
        assert len(results) == 2
        ids = [r.rule_id for r in results]
        assert "dummy_realtime" in ids
        assert "dummy_silent" in ids


# ---------------------------------------------------------------------------
# Test: Anomaly persistence
# ---------------------------------------------------------------------------


class TestAnomalyPersistence:
    """Verify that fired rules create anomaly_event rows and non-fired don't."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_fired_rule_creates_anomaly_event(self, mock_session):
        """A fired rule must result in a create_anomaly_event call."""
        from engine import ScoringEngine

        engine = ScoringEngine(rules=[DummyRealtimeRule()])
        mock_factory = MagicMock(return_value=mock_session)

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value={"mmsi": 234567890}),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=42) as mock_create,
        ):
            await engine.evaluate_realtime(234567890)

        mock_create.assert_called_once()
        data = mock_create.call_args[0][1]
        assert data["mmsi"] == 234567890
        assert data["rule_id"] == "dummy_realtime"
        assert data["severity"] == "high"
        assert data["points"] == 40.0
        # details must be JSON-serialised for the JSONB column
        parsed_details = json.loads(data["details"])
        assert parsed_details["reason"] == "test firing"

    @pytest.mark.asyncio
    async def test_non_fired_rule_creates_no_anomaly(self, mock_session):
        """A rule that returns fired=False must NOT create an anomaly row."""
        from engine import ScoringEngine

        engine = ScoringEngine(rules=[DummyNonFiringRule()])
        mock_factory = MagicMock(return_value=mock_session)

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=None),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=0) as mock_create,
        ):
            await engine.evaluate_realtime(345678901)

        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_returning_rule_creates_no_anomaly(self, mock_session):
        """A rule that returns None must NOT create an anomaly row."""
        from engine import ScoringEngine

        engine = ScoringEngine(rules=[DummyNoneReturningRule()])
        mock_factory = MagicMock(return_value=mock_session)

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value=None),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=0) as mock_create,
        ):
            await engine.evaluate_realtime(456789012)

        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_anomaly_details_serialised_as_json_string(self, mock_session):
        """The details field sent to create_anomaly_event must be a JSON
        string, not a raw dict, because the SQL uses :details bound to JSONB."""
        from engine import ScoringEngine

        engine = ScoringEngine(rules=[DummyRealtimeRule()])
        mock_factory = MagicMock(return_value=mock_session)

        with (
            patch("engine.get_session", return_value=mock_factory),
            patch("engine.get_vessel_profile_by_mmsi", new_callable=AsyncMock, return_value={"mmsi": 567890123}),
            patch("engine.get_vessel_track", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_active_anomalies_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.list_anomaly_events_by_mmsi", new_callable=AsyncMock, return_value=[]),
            patch("engine.count_ended_events", new_callable=AsyncMock, return_value=0),
            patch("engine.create_anomaly_event", new_callable=AsyncMock, return_value=1) as mock_create,
        ):
            await engine.evaluate_realtime(567890123)

        data = mock_create.call_args[0][1]
        assert isinstance(data["details"], str)
        json.loads(data["details"])  # must not raise


# ---------------------------------------------------------------------------
# Test: Redis channel subscription (main.py)
# ---------------------------------------------------------------------------


class TestRedisSubscription:
    """Verify that main.py subscribes to both expected channels."""

    def _reload_main(self):
        """Load the scoring main module by file path to avoid module name collisions."""
        import importlib.util

        main_path = Path(__file__).resolve().parent.parent / "main.py"
        module_name = "scoring_main"
        spec = importlib.util.spec_from_file_location(module_name, main_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod

    @pytest.mark.asyncio
    async def test_subscribes_to_both_channels(self):
        """The main function must subscribe to positions and enrichment_complete."""
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()

        # Make listen() return an empty async iterator so main exits quickly
        async def empty_listen():
            return
            yield  # make it an async generator

        mock_pubsub.listen = empty_listen
        mock_pubsub.unsubscribe = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
        mock_redis.close = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.rules = []
        mock_engine.realtime_rules = []
        mock_engine.gfw_rules = []

        main_mod = self._reload_main()

        with (
            patch.object(main_mod.aioredis, "from_url", return_value=mock_redis),
            patch.object(main_mod, "ScoringEngine", return_value=mock_engine),
        ):
            await main_mod.main()

        mock_pubsub.subscribe.assert_called_once_with(
            "heimdal:positions", "heimdal:enrichment_complete"
        )

    @pytest.mark.asyncio
    async def test_positions_channel_triggers_realtime_eval(self):
        """Messages on heimdal:positions should trigger evaluate_realtime."""
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()

        messages = [
            {"type": "subscribe", "channel": "heimdal:positions", "data": 1},
            {
                "type": "message",
                "channel": "heimdal:positions",
                "data": json.dumps({"mmsis": [123456789], "timestamp": "2026-01-01T00:00:00Z", "count": 1}),
            },
        ]

        async def mock_listen():
            for msg in messages:
                yield msg

        mock_pubsub.listen = mock_listen

        mock_redis = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
        mock_redis.close = AsyncMock()

        mock_engine = AsyncMock()
        mock_engine.rules = []
        mock_engine.realtime_rules = []
        mock_engine.gfw_rules = []
        mock_engine.evaluate_realtime = AsyncMock(return_value=[])
        mock_engine.evaluate_gfw = AsyncMock(return_value=[])

        main_mod = self._reload_main()

        with (
            patch.object(main_mod.aioredis, "from_url", return_value=mock_redis),
            patch.object(main_mod, "ScoringEngine", return_value=mock_engine),
        ):
            await main_mod.main()

        mock_engine.evaluate_realtime.assert_called_once_with(123456789)
        mock_engine.evaluate_gfw.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrichment_channel_triggers_gfw_eval(self):
        """Messages on heimdal:enrichment_complete should trigger evaluate_gfw."""
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()

        messages = [
            {"type": "subscribe", "channel": "heimdal:enrichment_complete", "data": 1},
            {
                "type": "message",
                "channel": "heimdal:enrichment_complete",
                "data": json.dumps({"mmsis": [987654321], "gfw_events_count": 3, "sar_detections_count": 0}),
            },
        ]

        async def mock_listen():
            for msg in messages:
                yield msg

        mock_pubsub.listen = mock_listen

        mock_redis = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
        mock_redis.close = AsyncMock()

        mock_engine = AsyncMock()
        mock_engine.rules = []
        mock_engine.realtime_rules = []
        mock_engine.gfw_rules = []
        mock_engine.evaluate_realtime = AsyncMock(return_value=[])
        mock_engine.evaluate_gfw = AsyncMock(return_value=[])

        main_mod = self._reload_main()

        with (
            patch.object(main_mod.aioredis, "from_url", return_value=mock_redis),
            patch.object(main_mod, "ScoringEngine", return_value=mock_engine),
        ):
            await main_mod.main()

        mock_engine.evaluate_gfw.assert_called_once_with(987654321)
        # Post-enrichment also triggers realtime re-evaluation
        mock_engine.evaluate_realtime.assert_called_once_with(987654321)


# ---------------------------------------------------------------------------
# Test: ScoringRule abstract contract
# ---------------------------------------------------------------------------


class TestScoringRuleBase:
    """Verify the abstract base class enforces the expected interface."""

    def test_cannot_instantiate_abstract_base(self):
        """ScoringRule itself cannot be instantiated."""
        with pytest.raises(TypeError):
            ScoringRule()  # type: ignore[abstract]

    def test_concrete_subclass_has_required_properties(self):
        rule = DummyRealtimeRule()
        assert rule.rule_id == "dummy_realtime"
        assert rule.rule_category == "realtime"

    def test_gfw_rule_category(self):
        rule = DummyGfwRule()
        assert rule.rule_category == "gfw_sourced"

    @pytest.mark.asyncio
    async def test_evaluate_returns_rule_result(self):
        rule = DummyRealtimeRule()
        result = await rule.evaluate(123456789, None, [], [], [])
        assert isinstance(result, RuleResult)
        assert result.fired is True
        assert result.source == "realtime"


# ---------------------------------------------------------------------------
# Test: RuleResult source field
# ---------------------------------------------------------------------------


class TestRuleResultSource:
    """Verify the source field was added to RuleResult."""

    def test_source_field_exists(self):
        result = RuleResult(
            fired=True,
            rule_id="test",
            severity="high",
            points=10.0,
            source="gfw",
        )
        assert result.source == "gfw"

    def test_source_defaults_to_none(self):
        result = RuleResult(fired=False, rule_id="test")
        assert result.source is None
