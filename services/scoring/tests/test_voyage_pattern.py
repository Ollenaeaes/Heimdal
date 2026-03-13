"""Tests for the voyage_pattern scoring rule.

Verifies detection of canonical shadow fleet voyage patterns:
Russian port → STS hotspot → India/China/Turkey destination.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

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

_NOW = datetime.now(timezone.utc)


def _make_gfw_port_visit(
    port_name: str,
    days_ago: int = 5,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a GFW PORT_VISIT event dict."""
    event: dict[str, Any] = {
        "gfw_event_id": f"pv-{port_name.lower()}",
        "event_type": "PORT_VISIT",
        "mmsi": 123456789,
        "start_time": _NOW - timedelta(days=days_ago),
        "end_time": _NOW - timedelta(days=days_ago) + timedelta(hours=12),
        "lat": 59.0,
        "lon": 28.0,
        "details": {},
        "port_name": port_name,
    }
    event.update(kwargs)
    return event


def _make_position(
    lat: float = 35.8,
    lon: float = 14.3,
    sog: float = 2.0,
    draught: float | None = None,
    hours_ago: float = 0.5,
) -> dict[str, Any]:
    """Build a vessel position dict."""
    pos: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "timestamp": (_NOW - timedelta(hours=hours_ago)).isoformat(),
    }
    if draught is not None:
        pos["draught"] = draught
    return pos


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVoyagePatternRule:
    """Tests for VoyagePatternRule."""

    @pytest.fixture
    def rule(self):
        from rules.voyage_pattern import VoyagePatternRule
        return VoyagePatternRule()

    def test_rule_id(self, rule):
        assert rule.rule_id == "voyage_pattern"

    def test_rule_category(self, rule):
        assert rule.rule_category == "gfw_sourced"

    # --- russian_port_to_sts -----------------------------------------------

    @pytest.mark.asyncio
    async def test_russian_port_to_sts_fires_high(self, rule):
        """Vessel with PORT_VISIT to Novorossiysk + position in STS zone -> high."""
        gfw_events = [_make_gfw_port_visit("Novorossiysk", days_ago=10)]
        positions = [_make_position(lat=35.8, lon=14.3, sog=2.0)]
        profile: dict[str, Any] = {"destination": ""}

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value="Malta OPL",
        ):
            result = await rule.evaluate(
                123456789, profile, positions, [], gfw_events,
            )

        assert result is not None
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 15.0
        assert result.details["reason"] == "russian_port_to_sts"
        assert result.details["sts_zone"] == "Malta OPL"

    # --- sts_to_destination ------------------------------------------------

    @pytest.mark.asyncio
    async def test_sts_to_destination_fires_moderate(self, rule):
        """Vessel in STS zone + destination SIKKA -> moderate."""
        gfw_events: list[dict[str, Any]] = []  # no Russian port visits
        positions = [_make_position(lat=35.8, lon=14.3, sog=2.0)]
        profile: dict[str, Any] = {"destination": "SIKKA"}

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value="Kalamata OPL",
        ):
            result = await rule.evaluate(
                123456789, profile, positions, [], gfw_events,
            )

        assert result is not None
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 8.0
        assert result.details["reason"] == "sts_to_destination"
        assert result.details["destination"] == "SIKKA"

    # --- full_evasion_route ------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_evasion_route_fires_critical(self, rule):
        """Primorsk → STS zone → destination JAMNAGAR -> critical."""
        gfw_events = [_make_gfw_port_visit("Primorsk", days_ago=15)]
        positions = [_make_position(lat=35.8, lon=14.3, sog=2.0)]
        profile: dict[str, Any] = {"destination": "JAMNAGAR"}

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value="Laconian Gulf",
        ):
            result = await rule.evaluate(
                123456789, profile, positions, [], gfw_events,
            )

        assert result is not None
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 25.0
        assert result.details["reason"] == "full_evasion_route"
        assert result.details["sts_zone"] == "Laconian Gulf"
        assert result.details["destination"] == "JAMNAGAR"

    # --- high-speed transit should NOT fire --------------------------------

    @pytest.mark.asyncio
    async def test_transit_through_sts_at_high_speed_not_flagged(self, rule):
        """Vessel transiting STS zone at 12 knots -> NOT flagged."""
        gfw_events = [_make_gfw_port_visit("Novorossiysk", days_ago=10)]
        positions = [_make_position(lat=35.8, lon=14.3, sog=12.0)]
        profile: dict[str, Any] = {"destination": "SIKKA"}

        # The STS check should never be called because speed > 8 kn
        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value="Malta OPL",
        ) as mock_sts:
            result = await rule.evaluate(
                123456789, profile, positions, [], gfw_events,
            )

        assert result is not None
        assert result.fired is False
        mock_sts.assert_not_called()

    # --- legitimate trade should NOT fire ----------------------------------

    @pytest.mark.asyncio
    async def test_legitimate_trade_not_flagged(self, rule):
        """Rotterdam → Piraeus, no Russian ports -> NOT flagged."""
        gfw_events = [_make_gfw_port_visit("Rotterdam", days_ago=5)]
        positions = [_make_position(lat=37.9, lon=23.6, sog=11.0)]
        profile: dict[str, Any] = {"destination": "PIRAEUS"}

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await rule.evaluate(
                123456789, profile, positions, [], gfw_events,
            )

        assert result is not None
        assert result.fired is False

    # --- suspicious_ballast ------------------------------------------------

    @pytest.mark.asyncio
    async def test_ballast_vessel_near_sts_fires_moderate(self, rule):
        """Vessel with low draught (4.5m) near STS hotspot -> moderate."""
        gfw_events: list[dict[str, Any]] = []
        positions = [_make_position(lat=36.0, lon=22.5, sog=3.0, draught=4.5)]
        profile: dict[str, Any] = {"destination": ""}  # no destination match

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value="Laconian Gulf",
        ):
            result = await rule.evaluate(
                123456789, profile, positions, [], gfw_events,
            )

        assert result is not None
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 8.0
        assert result.details["reason"] == "suspicious_ballast"
        assert result.details["draught"] == 4.5
        assert result.details["sts_zone"] == "Laconian Gulf"

    # --- edge cases --------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_positions_does_not_fire(self, rule):
        """No recent positions -> does not fire."""
        gfw_events = [_make_gfw_port_visit("Novorossiysk", days_ago=5)]
        result = await rule.evaluate(123456789, None, [], [], gfw_events)
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_profile_does_not_crash(self, rule):
        """None profile -> handles gracefully."""
        positions = [_make_position(lat=35.8, lon=14.3, sog=2.0)]

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await rule.evaluate(
                123456789, None, positions, [], [],
            )

        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_gfw_events_does_not_fire(self, rule):
        """No GFW events + not in STS -> does not fire."""
        positions = [_make_position(lat=51.9, lon=4.5, sog=10.0)]

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await rule.evaluate(
                123456789, {"destination": "ROTTERDAM"}, positions, [], [],
            )

        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_russian_port_visit_older_than_30_days_not_counted(self, rule):
        """Russian port visit 45 days ago should not count."""
        gfw_events = [_make_gfw_port_visit("Primorsk", days_ago=45)]
        positions = [_make_position(lat=35.8, lon=14.3, sog=2.0)]

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value="Malta OPL",
        ):
            result = await rule.evaluate(
                123456789, {"destination": "SIKKA"}, positions, [], gfw_events,
            )

        # Without recent Russian port, it's sts_to_destination (moderate), not full chain
        assert result is not None
        assert result.fired is True
        assert result.details["reason"] == "sts_to_destination"
        assert result.severity == "moderate"

    @pytest.mark.asyncio
    async def test_ballast_with_normal_draught_not_flagged(self, rule):
        """Vessel in STS zone but draught >= 6m -> not flagged as ballast."""
        gfw_events: list[dict[str, Any]] = []
        positions = [_make_position(lat=36.0, lon=22.5, sog=3.0, draught=8.5)]
        profile: dict[str, Any] = {"destination": ""}

        with patch(
            "rules.voyage_pattern._check_position_sts_zone",
            new_callable=AsyncMock,
            return_value="Laconian Gulf",
        ):
            result = await rule.evaluate(
                123456789, profile, positions, [], gfw_events,
            )

        # In STS zone but no Russian port, no dest match, draught is normal -> not fired
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_empty_everything_does_not_fire(self, rule):
        """All inputs empty -> does not fire."""
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is not None
        assert result.fired is False
