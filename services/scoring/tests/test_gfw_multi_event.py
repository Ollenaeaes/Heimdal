"""Tests for GFW multi-event handling (Story 5 of spec 17).

Validates that evaluate_all() returns one result per distinct GFW event,
applies temporal deduplication (24h window), filters already-seen events,
and that the default evaluate_all() on the base class wraps evaluate().
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make the scoring service importable
_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
# Make shared importable
sys.path.insert(0, str(_scoring_dir.parent.parent))

from shared.models.anomaly import RuleResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session_factory(session: AsyncMock) -> MagicMock:
    """Create a mock session factory that returns an async context manager."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = ctx
    return factory


def _zone_query_returns(zone_name: str | None):
    """Mock execute that returns zone_name for any query."""

    async def _execute(query, params=None):
        mock_result = MagicMock()
        if zone_name is not None:
            mock_result.first.return_value = (zone_name,)
        else:
            mock_result.first.return_value = None
        return mock_result

    return _execute


def _zone_query_sts_then_terminal(sts_name: str | None, terminal_name: str | None):
    """Mock that returns different results for STS vs terminal queries."""
    call_count = 0

    async def _execute(query, params=None):
        nonlocal call_count
        mock_result = MagicMock()
        if call_count % 2 == 0:
            call_count += 1
            mock_result.first.return_value = (sts_name,) if sts_name else None
        else:
            call_count += 1
            mock_result.first.return_value = (terminal_name,) if terminal_name else None
        return mock_result

    return _execute


def _make_gfw_event(
    event_type: str,
    gfw_event_id: str = "test-event-001",
    start_time: datetime | None = None,
    lat: float = 35.8,
    lon: float = 14.3,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a minimal GFW event dict."""
    event: dict[str, Any] = {
        "gfw_event_id": gfw_event_id,
        "event_type": event_type,
        "mmsi": 123456789,
        "start_time": start_time or datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
        "end_time": datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc),
        "lat": lat,
        "lon": lon,
        "details": {},
        "encounter_mmsi": None,
        "port_name": None,
    }
    event.update(kwargs)
    return event


def _make_anomaly(
    rule_id: str,
    gfw_event_id: str | None = None,
    created_at: datetime | None = None,
    resolved: bool = False,
    points: float = 15.0,
    anomaly_id: int = 1,
) -> dict[str, Any]:
    """Build a minimal anomaly event dict."""
    details: dict[str, Any] = {}
    if gfw_event_id:
        details["gfw_event_id"] = gfw_event_id
    return {
        "id": anomaly_id,
        "rule_id": rule_id,
        "resolved": resolved,
        "created_at": created_at or datetime.now(timezone.utc),
        "points": points,
        "details": details,
    }


# ===================================================================
# Test: 3 distinct encounter events -> 3 anomaly results
# ===================================================================


class TestMultiEncounterEvents:
    """Multiple ENCOUNTER events produce multiple results."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_encounter import GfwEncounterRule
        return GfwEncounterRule()

    @pytest.mark.asyncio
    async def test_three_encounter_events_produce_three_results(self, rule):
        """3 ENCOUNTER events with distinct times/IDs -> 3 results."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-001",
                start_time=base_time,
                encounter_mmsi=111111111,
            ),
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-002",
                start_time=base_time + timedelta(hours=48),
                encounter_mmsi=222222222,
            ),
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-003",
                start_time=base_time + timedelta(hours=96),
                encounter_mmsi=333333333,
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 3
        event_ids = {r.details["gfw_event_id"] for r in results}
        assert event_ids == {"enc-001", "enc-002", "enc-003"}
        assert all(r.fired is True for r in results)

    @pytest.mark.asyncio
    async def test_evaluate_returns_first_of_multi(self, rule):
        """evaluate() returns the first result from evaluate_all()."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-001",
                start_time=base_time,
                encounter_mmsi=111111111,
            ),
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-002",
                start_time=base_time + timedelta(hours=48),
                encounter_mmsi=222222222,
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.details["gfw_event_id"] == "enc-001"


# ===================================================================
# Test: Temporal dedup — events within 24h are merged
# ===================================================================


class TestTemporalDedup:
    """Events of same type within 24h window produce a single result."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_encounter import GfwEncounterRule
        return GfwEncounterRule()

    @pytest.mark.asyncio
    async def test_two_events_1h_apart_produce_one_result(self, rule):
        """2 ENCOUNTER events 1 hour apart -> 1 result (temporal dedup)."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-001",
                start_time=base_time,
                encounter_mmsi=111111111,
            ),
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-002",
                start_time=base_time + timedelta(hours=1),
                encounter_mmsi=222222222,
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 1
        assert results[0].details["gfw_event_id"] == "enc-001"

    @pytest.mark.asyncio
    async def test_two_events_48h_apart_produce_two_results(self, rule):
        """2 ENCOUNTER events 48 hours apart -> 2 results."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-001",
                start_time=base_time,
                encounter_mmsi=111111111,
            ),
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-002",
                start_time=base_time + timedelta(hours=48),
                encounter_mmsi=222222222,
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_dedup_boundary_exactly_24h(self, rule):
        """2 events exactly 24h apart -> 1 result (at boundary, still deduped)."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-001",
                start_time=base_time,
            ),
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-002",
                start_time=base_time + timedelta(hours=24),
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            results = await rule.evaluate_all(123456789, None, [], [], events)

        # Exactly 24h = not greater than window, so still deduped
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_dedup_boundary_24h_plus_1s(self, rule):
        """2 events 24h+1s apart -> 2 results (just outside dedup window)."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-001",
                start_time=base_time,
            ),
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-002",
                start_time=base_time + timedelta(hours=24, seconds=1),
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 2


# ===================================================================
# Test: GFW event matching existing anomaly gfw_event_id -> no dup
# ===================================================================


class TestExistingAnomalyDedup:
    """Events whose gfw_event_id already appears in an anomaly are skipped."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_encounter import GfwEncounterRule
        return GfwEncounterRule()

    @pytest.mark.asyncio
    async def test_existing_anomaly_filters_matching_event(self, rule):
        """Event with gfw_event_id already in existing anomalies -> no result."""
        events = [
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-already-seen",
                encounter_mmsi=111111111,
            ),
        ]
        existing_anomalies = [
            _make_anomaly("gfw_encounter", gfw_event_id="enc-already-seen"),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            results = await rule.evaluate_all(
                123456789, None, [], existing_anomalies, events,
            )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_mixed_seen_and_new_events(self, rule):
        """One seen + one new event -> only the new event produces a result."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-seen",
                start_time=base_time,
                encounter_mmsi=111111111,
            ),
            _make_gfw_event(
                "ENCOUNTER",
                gfw_event_id="enc-new",
                start_time=base_time + timedelta(hours=48),
                encounter_mmsi=222222222,
            ),
        ]
        existing_anomalies = [
            _make_anomaly("gfw_encounter", gfw_event_id="enc-seen"),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            results = await rule.evaluate_all(
                123456789, None, [], existing_anomalies, events,
            )

        assert len(results) == 1
        assert results[0].details["gfw_event_id"] == "enc-new"


# ===================================================================
# Test: Multi-event across different rule types
# ===================================================================


class TestMultiEventAisDisabling:
    """AIS disabling rule handles multiple events."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_ais_disabling import GfwAisDisablingRule
        return GfwAisDisablingRule()

    @pytest.mark.asyncio
    async def test_multiple_ais_disabling_events(self, rule):
        """3 AIS_DISABLING events, well separated -> 3 results."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "AIS_DISABLING",
                gfw_event_id="dis-001",
                start_time=base_time,
                lat=10.0,
                lon=20.0,
            ),
            _make_gfw_event(
                "AIS_DISABLING",
                gfw_event_id="dis-002",
                start_time=base_time + timedelta(hours=48),
                lat=15.0,
                lon=25.0,
            ),
            _make_gfw_event(
                "AIS_DISABLING",
                gfw_event_id="dis-003",
                start_time=base_time + timedelta(hours=96),
                lat=20.0,
                lon=30.0,
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=_zone_query_sts_then_terminal(None, None)
        )
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_ais_disabling.get_session", return_value=factory):
            results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 3
        assert all(r.fired for r in results)
        assert all(r.details.get("gfw_event_id") for r in results)

    @pytest.mark.asyncio
    async def test_ais_disabling_includes_gfw_event_id(self, rule):
        """Each result includes gfw_event_id in details."""
        events = [
            _make_gfw_event(
                "AIS_DISABLING",
                gfw_event_id="dis-xyz",
                lat=10.0,
                lon=20.0,
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=_zone_query_sts_then_terminal(None, None)
        )
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_ais_disabling.get_session", return_value=factory):
            results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 1
        assert results[0].details["gfw_event_id"] == "dis-xyz"


class TestMultiEventLoitering:
    """Loitering rule handles multiple events."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_loitering import GfwLoiteringRule
        return GfwLoiteringRule()

    @pytest.mark.asyncio
    async def test_multiple_loitering_events(self, rule):
        """2 LOITERING events 48h apart -> 2 results."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "LOITERING",
                gfw_event_id="loi-001",
                start_time=base_time,
            ),
            _make_gfw_event(
                "LOITERING",
                gfw_event_id="loi-002",
                start_time=base_time + timedelta(hours=48),
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_loitering.get_session", return_value=factory):
            results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 2
        assert results[0].details["gfw_event_id"] == "loi-001"
        assert results[1].details["gfw_event_id"] == "loi-002"


class TestMultiEventPortVisit:
    """Port visit rule handles multiple Russian terminal visits."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_port_visit import GfwPortVisitRule
        return GfwPortVisitRule()

    @pytest.mark.asyncio
    async def test_multiple_russian_port_visits(self, rule):
        """2 Russian port visits 48h apart -> 2 results."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "PORT_VISIT",
                gfw_event_id="pv-001",
                start_time=base_time,
                port_name="Ust-Luga",
            ),
            _make_gfw_event(
                "PORT_VISIT",
                gfw_event_id="pv-002",
                start_time=base_time + timedelta(hours=48),
                port_name="Novorossiysk",
            ),
        ]

        results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 2
        assert results[0].details["port_name"] == "Ust-Luga"
        assert results[1].details["port_name"] == "Novorossiysk"

    @pytest.mark.asyncio
    async def test_non_russian_ports_filtered(self, rule):
        """Russian + non-Russian visits -> only Russian fires."""
        base_time = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event(
                "PORT_VISIT",
                gfw_event_id="pv-001",
                start_time=base_time,
                port_name="Rotterdam",
            ),
            _make_gfw_event(
                "PORT_VISIT",
                gfw_event_id="pv-002",
                start_time=base_time + timedelta(hours=48),
                port_name="Kozmino",
            ),
        ]

        results = await rule.evaluate_all(123456789, None, [], [], events)

        assert len(results) == 1
        assert results[0].details["port_name"] == "Kozmino"


# ===================================================================
# Test: Default evaluate_all wraps single evaluate result
# ===================================================================


class TestDefaultEvaluateAll:
    """Base class default evaluate_all() wraps evaluate() result."""

    @pytest.mark.asyncio
    async def test_default_evaluate_all_wraps_fired_result(self):
        """A realtime rule's evaluate_all() wraps its evaluate() result."""
        from rules.ais_gap import AisGapRule
        rule = AisGapRule()

        # We need to mock the rule's evaluate to return a fired result
        fired_result = RuleResult(
            fired=True,
            rule_id="ais_gap",
            severity="high",
            points=40.0,
            details={"reason": "test"},
            source="realtime",
        )

        original_evaluate = rule.evaluate

        async def mock_evaluate(*args, **kwargs):
            return fired_result

        rule.evaluate = mock_evaluate  # type: ignore[assignment]

        results = await rule.evaluate_all(123456789, None, [], [], [])

        assert len(results) == 1
        assert results[0] is fired_result

        rule.evaluate = original_evaluate  # type: ignore[assignment]

    @pytest.mark.asyncio
    async def test_default_evaluate_all_empty_on_not_fired(self):
        """A rule that does not fire -> evaluate_all returns empty list."""
        from rules.ais_gap import AisGapRule
        rule = AisGapRule()

        not_fired = RuleResult(fired=False, rule_id="ais_gap")

        async def mock_evaluate(*args, **kwargs):
            return not_fired

        rule.evaluate = mock_evaluate  # type: ignore[assignment]

        results = await rule.evaluate_all(123456789, None, [], [], [])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_default_evaluate_all_empty_on_none(self):
        """A rule that returns None -> evaluate_all returns empty list."""
        from rules.ais_gap import AisGapRule
        rule = AisGapRule()

        async def mock_evaluate(*args, **kwargs):
            return None

        rule.evaluate = mock_evaluate  # type: ignore[assignment]

        results = await rule.evaluate_all(123456789, None, [], [], [])

        assert len(results) == 0


# ===================================================================
# Test: GFW helpers unit tests
# ===================================================================


class TestGfwHelpers:
    """Unit tests for gfw_helpers module."""

    def test_parse_start_time_datetime(self):
        from rules.gfw_helpers import parse_start_time
        dt = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        event = {"start_time": dt}
        assert parse_start_time(event) == dt

    def test_parse_start_time_naive_datetime(self):
        from rules.gfw_helpers import parse_start_time
        dt = datetime(2026, 1, 15, 12, 0)
        event = {"start_time": dt}
        result = parse_start_time(event)
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_parse_start_time_iso_string(self):
        from rules.gfw_helpers import parse_start_time
        event = {"start_time": "2026-01-15T12:00:00+00:00"}
        result = parse_start_time(event)
        assert result is not None
        assert result.year == 2026

    def test_parse_start_time_none(self):
        from rules.gfw_helpers import parse_start_time
        event = {"start_time": None}
        assert parse_start_time(event) is None

    def test_parse_start_time_missing(self):
        from rules.gfw_helpers import parse_start_time
        event = {}
        assert parse_start_time(event) is None

    def test_dedup_events_empty(self):
        from rules.gfw_helpers import dedup_events
        assert dedup_events([]) == []

    def test_dedup_events_single(self):
        from rules.gfw_helpers import dedup_events
        events = [_make_gfw_event("ENCOUNTER")]
        result = dedup_events(events)
        assert len(result) == 1

    def test_dedup_events_within_window(self):
        from rules.gfw_helpers import dedup_events
        base = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event("ENCOUNTER", start_time=base),
            _make_gfw_event("ENCOUNTER", start_time=base + timedelta(hours=12)),
        ]
        result = dedup_events(events)
        assert len(result) == 1

    def test_dedup_events_outside_window(self):
        from rules.gfw_helpers import dedup_events
        base = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = [
            _make_gfw_event("ENCOUNTER", start_time=base),
            _make_gfw_event("ENCOUNTER", start_time=base + timedelta(hours=25)),
        ]
        result = dedup_events(events)
        assert len(result) == 2

    def test_filter_already_seen_removes_matching(self):
        from rules.gfw_helpers import filter_already_seen
        events = [
            _make_gfw_event("ENCOUNTER", gfw_event_id="enc-001"),
            _make_gfw_event("ENCOUNTER", gfw_event_id="enc-002"),
        ]
        anomalies = [_make_anomaly("gfw_encounter", gfw_event_id="enc-001")]
        result = filter_already_seen(events, anomalies)
        assert len(result) == 1
        assert result[0]["gfw_event_id"] == "enc-002"

    def test_filter_already_seen_empty_anomalies(self):
        from rules.gfw_helpers import filter_already_seen
        events = [_make_gfw_event("ENCOUNTER", gfw_event_id="enc-001")]
        result = filter_already_seen(events, [])
        assert len(result) == 1
