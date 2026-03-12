"""Tests for the 5 GFW-sourced scoring rules.

All database interactions are mocked — no running services needed.
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


def _make_gfw_event(
    event_type: str,
    lat: float = 35.8,
    lon: float = 14.3,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a minimal GFW event dict."""
    event: dict[str, Any] = {
        "gfw_event_id": "test-event-001",
        "event_type": event_type,
        "mmsi": 123456789,
        "start_time": datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
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
    created_at: datetime | None = None,
    resolved: bool = False,
    points: float = 15.0,
    anomaly_id: int = 1,
) -> dict[str, Any]:
    """Build a minimal anomaly event dict."""
    return {
        "id": anomaly_id,
        "rule_id": rule_id,
        "resolved": resolved,
        "created_at": created_at or datetime.now(timezone.utc),
        "points": points,
    }


# ---------------------------------------------------------------------------
# Zone query mock helpers
# ---------------------------------------------------------------------------


def _zone_query_returns(zone_name: str | None):
    """Create a mock execute side effect for zone queries.

    Returns the zone_name for any ST_DWithin query, None otherwise.
    """

    async def _execute(query, params=None):
        mock_result = MagicMock()
        if zone_name is not None:
            mock_result.first.return_value = (zone_name,)
        else:
            mock_result.first.return_value = None
        return mock_result

    return _execute


def _zone_query_sts_then_terminal(sts_name: str | None, terminal_name: str | None):
    """Mock that returns different results for STS vs terminal queries.

    First call returns sts_name, second call returns terminal_name.
    """
    call_count = 0

    async def _execute(query, params=None):
        nonlocal call_count
        mock_result = MagicMock()
        if call_count == 0:
            call_count += 1
            mock_result.first.return_value = (sts_name,) if sts_name else None
        else:
            mock_result.first.return_value = (terminal_name,) if terminal_name else None
        return mock_result

    return _execute


# ===================================================================
# Story 3: GFW AIS Disabling
# ===================================================================


class TestGfwAisDisabling:
    """Tests for the gfw_ais_disabling rule."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_ais_disabling import GfwAisDisablingRule
        return GfwAisDisablingRule()

    def test_rule_id(self, rule):
        assert rule.rule_id == "gfw_ais_disabling"

    def test_rule_category(self, rule):
        assert rule.rule_category == "gfw_sourced"

    @pytest.mark.asyncio
    async def test_no_ais_disabling_events(self, rule):
        """No AIS_DISABLING events -> does not fire."""
        events = [_make_gfw_event("LOITERING")]
        result = await rule.evaluate(123456789, None, [], [], events)
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_ais_disabling_in_sts_zone_fires_critical(self, rule):
        """AIS_DISABLING in STS zone -> critical, 100 points."""
        events = [_make_gfw_event("AIS_DISABLING", lat=35.8, lon=14.3)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns("Malta OPL"))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_ais_disabling.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.source == "gfw"
        assert result.details["zone"] == "Malta OPL"

    @pytest.mark.asyncio
    async def test_ais_disabling_near_russian_terminal_fires_critical(self, rule):
        """AIS_DISABLING near a Russian terminal -> critical, 100 points."""
        events = [_make_gfw_event("AIS_DISABLING", lat=59.68, lon=28.4)]

        mock_session = AsyncMock()
        # First call (STS check) returns None, second (terminal check) returns zone
        mock_session.execute = AsyncMock(
            side_effect=_zone_query_sts_then_terminal(None, "Ust-Luga")
        )
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_ais_disabling.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.details["zone"] == "Ust-Luga"

    @pytest.mark.asyncio
    async def test_ais_disabling_elsewhere_fires_high(self, rule):
        """AIS_DISABLING outside any known zone -> high, 40 points."""
        events = [_make_gfw_event("AIS_DISABLING", lat=10.0, lon=20.0)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=_zone_query_sts_then_terminal(None, None)
        )
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_ais_disabling.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.source == "gfw"

    @pytest.mark.asyncio
    async def test_empty_gfw_events(self, rule):
        """No GFW events at all -> does not fire."""
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is not None
        assert result.fired is False


# ===================================================================
# Story 4: GFW Encounter
# ===================================================================


class TestGfwEncounter:
    """Tests for the gfw_encounter rule."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_encounter import GfwEncounterRule
        return GfwEncounterRule()

    def test_rule_id(self, rule):
        assert rule.rule_id == "gfw_encounter"

    def test_rule_category(self, rule):
        assert rule.rule_category == "gfw_sourced"

    @pytest.mark.asyncio
    async def test_no_encounter_events(self, rule):
        """No ENCOUNTER events -> does not fire."""
        events = [_make_gfw_event("LOITERING")]
        result = await rule.evaluate(123456789, None, [], [], events)
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_encounter_in_sts_zone_fires_critical(self, rule):
        """ENCOUNTER in STS zone -> critical, 100 points."""
        events = [_make_gfw_event(
            "ENCOUNTER",
            lat=35.8,
            lon=14.3,
            encounter_mmsi=987654321,
        )]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns("Malta OPL"))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.source == "gfw"
        assert result.details["zone"] == "Malta OPL"
        assert result.details["encounter_mmsi"] == 987654321

    @pytest.mark.asyncio
    async def test_encounter_with_sanctioned_partner_fires_critical(self, rule):
        """ENCOUNTER with sanctioned partner (via event details) -> critical."""
        events = [_make_gfw_event(
            "ENCOUNTER",
            lat=10.0,
            lon=20.0,
            encounter_mmsi=987654321,
            details={"partner_sanctioned": True},
        )]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.details["partner_sanctioned"] is True

    @pytest.mark.asyncio
    async def test_encounter_elsewhere_non_sanctioned_fires_high(self, rule):
        """ENCOUNTER outside STS, non-sanctioned partner -> high, 40 points."""
        events = [_make_gfw_event(
            "ENCOUNTER",
            lat=10.0,
            lon=20.0,
            encounter_mmsi=987654321,
        )]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_encounter.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.source == "gfw"

    @pytest.mark.asyncio
    async def test_empty_gfw_events(self, rule):
        """No events at all -> does not fire."""
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result.fired is False


# ===================================================================
# Story 5: GFW Loitering
# ===================================================================


class TestGfwLoitering:
    """Tests for the gfw_loitering rule."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_loitering import GfwLoiteringRule
        return GfwLoiteringRule()

    def test_rule_id(self, rule):
        assert rule.rule_id == "gfw_loitering"

    def test_rule_category(self, rule):
        assert rule.rule_category == "gfw_sourced"

    @pytest.mark.asyncio
    async def test_no_loitering_events(self, rule):
        """No LOITERING events -> does not fire."""
        events = [_make_gfw_event("ENCOUNTER")]
        result = await rule.evaluate(123456789, None, [], [], events)
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_loitering_in_sts_zone_fires_high(self, rule):
        """LOITERING in STS zone -> high, 40 points."""
        events = [_make_gfw_event("LOITERING", lat=35.8, lon=14.3)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns("Malta OPL"))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_loitering.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.source == "gfw"
        assert result.details["zone"] == "Malta OPL"

    @pytest.mark.asyncio
    async def test_loitering_open_ocean_fires_moderate(self, rule):
        """LOITERING outside any zone -> moderate, 15 points."""
        events = [_make_gfw_event("LOITERING", lat=10.0, lon=20.0)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_zone_query_returns(None))
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_loitering.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0
        assert result.source == "gfw"

    @pytest.mark.asyncio
    async def test_empty_gfw_events(self, rule):
        """No events -> does not fire."""
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result.fired is False


# ===================================================================
# Story 6: GFW Port Visit
# ===================================================================


class TestGfwPortVisit:
    """Tests for the gfw_port_visit rule."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_port_visit import GfwPortVisitRule
        return GfwPortVisitRule()

    def test_rule_id(self, rule):
        assert rule.rule_id == "gfw_port_visit"

    def test_rule_category(self, rule):
        assert rule.rule_category == "gfw_sourced"

    @pytest.mark.asyncio
    async def test_no_port_visit_events(self, rule):
        """No PORT_VISIT events -> does not fire."""
        events = [_make_gfw_event("LOITERING")]
        result = await rule.evaluate(123456789, None, [], [], events)
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_port_visit_ust_luga_fires_high(self, rule):
        """PORT_VISIT at Ust-Luga -> high, 40 points."""
        events = [_make_gfw_event(
            "PORT_VISIT",
            lat=59.68,
            lon=28.4,
            port_name="Ust-Luga",
        )]

        result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.source == "gfw"
        assert result.details["port_name"] == "Ust-Luga"

    @pytest.mark.asyncio
    async def test_port_visit_novorossiysk_fires_high(self, rule):
        """PORT_VISIT at Novorossiysk -> high, 40 points."""
        events = [_make_gfw_event(
            "PORT_VISIT",
            lat=44.66,
            lon=37.81,
            port_name="Novorossiysk",
        )]

        result = await rule.evaluate(123456789, None, [], [], events)

        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_port_visit_primorsk_fires_high(self, rule):
        """PORT_VISIT at Primorsk -> high, 40 points."""
        events = [_make_gfw_event(
            "PORT_VISIT",
            port_name="Primorsk",
        )]

        result = await rule.evaluate(123456789, None, [], [], events)
        assert result.fired is True
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_port_visit_non_russian_port_does_not_fire(self, rule):
        """PORT_VISIT at Rotterdam -> does not fire."""
        events = [_make_gfw_event(
            "PORT_VISIT",
            lat=51.9,
            lon=4.5,
            port_name="Rotterdam",
        )]

        result = await rule.evaluate(123456789, None, [], [], events)
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_port_visit_case_insensitive(self, rule):
        """PORT_VISIT at 'ust-luga' (lowercase) -> should fire."""
        events = [_make_gfw_event(
            "PORT_VISIT",
            port_name="ust-luga",
        )]

        result = await rule.evaluate(123456789, None, [], [], events)
        assert result.fired is True
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_port_visit_murmansk_fires(self, rule):
        """PORT_VISIT at Murmansk -> fires."""
        events = [_make_gfw_event("PORT_VISIT", port_name="Murmansk")]
        result = await rule.evaluate(123456789, None, [], [], events)
        assert result.fired is True

    @pytest.mark.asyncio
    async def test_empty_gfw_events(self, rule):
        """No events -> does not fire."""
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_multiple_port_visits_first_russian_fires(self, rule):
        """Multiple PORT_VISITs, one Russian -> fires for the Russian one."""
        events = [
            _make_gfw_event("PORT_VISIT", port_name="Rotterdam"),
            _make_gfw_event("PORT_VISIT", port_name="Kozmino"),
        ]
        result = await rule.evaluate(123456789, None, [], [], events)
        assert result.fired is True
        assert result.details["port_name"] == "Kozmino"


# ===================================================================
# Story 7: GFW Dark SAR
# ===================================================================


class TestGfwDarkSar:
    """Tests for the gfw_dark_sar rule."""

    @pytest.fixture
    def rule(self):
        from rules.gfw_dark_sar import GfwDarkSarRule
        return GfwDarkSarRule()

    def test_rule_id(self, rule):
        assert rule.rule_id == "gfw_dark_sar"

    def test_rule_category(self, rule):
        assert rule.rule_category == "gfw_sourced"

    @pytest.mark.asyncio
    async def test_no_dark_sar_detections(self, rule):
        """No dark SAR detections -> does not fire."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_dark_sar.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], [])

        assert result.fired is False

    @pytest.mark.asyncio
    async def test_dark_sar_with_ais_gap_within_48h_fires(self, rule):
        """Dark SAR detection + AIS gap within 48h -> fires high, 40 points."""
        now = datetime.now(timezone.utc)
        det_time = now - timedelta(hours=6)

        # Mock SAR detection query
        sar_detections = [
            {
                "id": 1,
                "detection_time": det_time,
                "lat": 35.8,
                "lon": 14.3,
                "is_dark": True,
                "matched_mmsi": 123456789,
                "confidence": 0.95,
            }
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = sar_detections
        mock_session.execute = AsyncMock(return_value=mock_result)
        factory = _mock_session_factory(mock_session)

        # Existing ais_gap anomaly within 48h
        existing_anomalies = [
            _make_anomaly("ais_gap", created_at=now - timedelta(hours=4)),
        ]

        with patch("rules.gfw_dark_sar.get_session", return_value=factory):
            result = await rule.evaluate(
                123456789, None, [], existing_anomalies, []
            )

        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.source == "gfw"
        assert result.details["event_type"] == "DARK_SAR"

    @pytest.mark.asyncio
    async def test_dark_sar_without_ais_gap_does_not_fire(self, rule):
        """Dark SAR detection but no AIS gap -> does not fire."""
        now = datetime.now(timezone.utc)

        sar_detections = [
            {
                "id": 1,
                "detection_time": now - timedelta(hours=6),
                "lat": 35.8,
                "lon": 14.3,
                "is_dark": True,
                "matched_mmsi": 123456789,
                "confidence": 0.95,
            }
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = sar_detections
        mock_session.execute = AsyncMock(return_value=mock_result)
        factory = _mock_session_factory(mock_session)

        with patch("rules.gfw_dark_sar.get_session", return_value=factory):
            result = await rule.evaluate(123456789, None, [], [], [])

        assert result.fired is False

    @pytest.mark.asyncio
    async def test_dark_sar_with_ais_gap_outside_48h_does_not_fire(self, rule):
        """Dark SAR + AIS gap outside 48h window -> does not fire."""
        now = datetime.now(timezone.utc)
        det_time = now - timedelta(hours=72)  # 72h ago

        sar_detections = [
            {
                "id": 1,
                "detection_time": det_time,
                "lat": 35.8,
                "lon": 14.3,
                "is_dark": True,
                "matched_mmsi": 123456789,
                "confidence": 0.95,
            }
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = sar_detections
        mock_session.execute = AsyncMock(return_value=mock_result)
        factory = _mock_session_factory(mock_session)

        # AIS gap created NOW, detection 72h ago -> outside 48h window
        existing_anomalies = [
            _make_anomaly("ais_gap", created_at=now),
        ]

        with patch("rules.gfw_dark_sar.get_session", return_value=factory):
            result = await rule.evaluate(
                123456789, None, [], existing_anomalies, []
            )

        assert result.fired is False

    @pytest.mark.asyncio
    async def test_dark_sar_with_resolved_ais_gap_does_not_fire(self, rule):
        """Dark SAR + resolved AIS gap -> does not fire."""
        now = datetime.now(timezone.utc)

        sar_detections = [
            {
                "id": 1,
                "detection_time": now - timedelta(hours=6),
                "lat": 35.8,
                "lon": 14.3,
                "is_dark": True,
                "matched_mmsi": 123456789,
                "confidence": 0.95,
            }
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = sar_detections
        mock_session.execute = AsyncMock(return_value=mock_result)
        factory = _mock_session_factory(mock_session)

        # AIS gap exists but resolved
        existing_anomalies = [
            _make_anomaly("ais_gap", created_at=now - timedelta(hours=4), resolved=True),
        ]

        with patch("rules.gfw_dark_sar.get_session", return_value=factory):
            result = await rule.evaluate(
                123456789, None, [], existing_anomalies, []
            )

        assert result.fired is False

    @pytest.mark.asyncio
    async def test_dark_sar_at_exactly_48h_boundary(self, rule):
        """Dark SAR detection exactly 48h from AIS gap -> should fire."""
        now = datetime.now(timezone.utc)
        det_time = now - timedelta(hours=48)

        sar_detections = [
            {
                "id": 1,
                "detection_time": det_time,
                "lat": 35.8,
                "lon": 14.3,
                "is_dark": True,
                "matched_mmsi": 123456789,
                "confidence": 0.95,
            }
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = sar_detections
        mock_session.execute = AsyncMock(return_value=mock_result)
        factory = _mock_session_factory(mock_session)

        existing_anomalies = [
            _make_anomaly("ais_gap", created_at=now),
        ]

        with patch("rules.gfw_dark_sar.get_session", return_value=factory):
            result = await rule.evaluate(
                123456789, None, [], existing_anomalies, []
            )

        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0


# ===================================================================
# Zone helpers unit tests
# ===================================================================


class TestZoneHelpers:
    """Tests for zone_helpers utility functions."""

    def test_is_russian_terminal_port_ust_luga(self):
        from rules.zone_helpers import is_russian_terminal_port
        assert is_russian_terminal_port("Ust-Luga") is True

    def test_is_russian_terminal_port_case_insensitive(self):
        from rules.zone_helpers import is_russian_terminal_port
        assert is_russian_terminal_port("novorossiysk") is True

    def test_is_russian_terminal_port_substring_match(self):
        from rules.zone_helpers import is_russian_terminal_port
        assert is_russian_terminal_port("Port of Murmansk") is True

    def test_is_russian_terminal_port_non_russian(self):
        from rules.zone_helpers import is_russian_terminal_port
        assert is_russian_terminal_port("Rotterdam") is False

    def test_is_russian_terminal_port_none(self):
        from rules.zone_helpers import is_russian_terminal_port
        assert is_russian_terminal_port(None) is False

    def test_is_russian_terminal_port_empty(self):
        from rules.zone_helpers import is_russian_terminal_port
        assert is_russian_terminal_port("") is False

    @pytest.mark.asyncio
    async def test_is_in_sts_zone_found(self):
        from rules.zone_helpers import is_in_sts_zone

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = ("Malta OPL",)
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await is_in_sts_zone(mock_session, 35.8, 14.3)
        assert result == "Malta OPL"

    @pytest.mark.asyncio
    async def test_is_in_sts_zone_not_found(self):
        from rules.zone_helpers import is_in_sts_zone

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await is_in_sts_zone(mock_session, 10.0, 20.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_is_near_russian_terminal_found(self):
        from rules.zone_helpers import is_near_russian_terminal

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = ("Ust-Luga",)
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await is_near_russian_terminal(mock_session, 59.68, 28.4)
        assert result == "Ust-Luga"

    @pytest.mark.asyncio
    async def test_is_near_russian_terminal_not_found(self):
        from rules.zone_helpers import is_near_russian_terminal

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await is_near_russian_terminal(mock_session, 10.0, 20.0)
        assert result is None
