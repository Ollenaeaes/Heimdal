"""Tests for the Infrastructure Speed Anomaly scoring rule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.scoring.rules.infra_speed_anomaly import InfraSpeedAnomalyRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(minutes_ago: float = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return dt.isoformat()


def _position(lat=56.0, lon=19.5, sog=12.0, minutes_ago=0):
    return {
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "timestamp": _ts(minutes_ago),
    }


def _make_speed_history(normal_speed=12.0, count=10, span_minutes=150):
    """Create position history spread over span_minutes at normal_speed."""
    positions = []
    interval = span_minutes / max(count - 1, 1)
    for i in range(count):
        positions.append(_position(sog=normal_speed, minutes_ago=span_minutes - i * interval))
    return positions


_ROUTE = {
    "id": 1,
    "name": "Balticconnector Gas Pipeline",
    "route_type": "gas_pipeline",
    "operator": "Gasgrid Finland / Elering",
    "buffer_nm": 2.0,
    "metadata": {},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInfraSpeedAnomaly:
    @pytest.fixture
    def rule(self):
        return InfraSpeedAnomalyRule()

    # -- Basic non-firing cases --

    @pytest.mark.asyncio
    async def test_insufficient_positions(self, rule):
        """Fewer than 4 positions should return None."""
        result = await rule.evaluate(123456789, {}, [_position(), _position(minutes_ago=30)], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_not_in_corridor(self, rule):
        """Vessel not in any corridor should not fire."""
        positions = _make_speed_history()
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[]):
            result = await rule.evaluate(123456789, {}, positions, [], [])
            assert result.fired is False

    @pytest.mark.asyncio
    async def test_in_port_approach(self, rule):
        """Vessel in port approach should not fire."""
        positions = _make_speed_history()
        # Add slow latest position
        positions.append(_position(sog=3.0, minutes_ago=0))

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=True):
                result = await rule.evaluate(123456789, {}, positions, [], [])
                assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_speed_drop(self, rule):
        """Normal speed should not fire."""
        positions = _make_speed_history(normal_speed=12.0)

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                result = await rule.evaluate(123456789, {}, positions, [], [])
                assert result.fired is False

    # -- Firing cases --

    @pytest.mark.asyncio
    async def test_fires_on_50_percent_drop(self, rule):
        """Speed dropping >50% of 2h average should fire."""
        # Normal speed history at 12 knots
        positions = _make_speed_history(normal_speed=12.0, count=8, span_minutes=130)
        # Latest position at 5 knots (>50% drop from avg 12)
        positions.append(_position(sog=5.0, minutes_ago=0))

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                result = await rule.evaluate(123456789, {}, positions, [], [])
                assert result.fired is True
                assert result.severity == "moderate"
                assert result.points == 15.0
                assert result.details["speed_drop_percent"] > 50

    @pytest.mark.asyncio
    async def test_does_not_fire_on_small_drop(self, rule):
        """Speed dropping <50% should not fire."""
        positions = _make_speed_history(normal_speed=12.0, count=8, span_minutes=130)
        # Latest at 8 knots — only 33% drop
        positions.append(_position(sog=8.0, minutes_ago=0))

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                result = await rule.evaluate(123456789, {}, positions, [], [])
                assert result.fired is False

    @pytest.mark.asyncio
    async def test_insufficient_history_span(self, rule):
        """Positions spanning <2 hours should not fire."""
        # All positions within last 60 minutes
        positions = _make_speed_history(normal_speed=12.0, count=6, span_minutes=60)
        positions.append(_position(sog=3.0, minutes_ago=0))

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                result = await rule.evaluate(123456789, {}, positions, [], [])
                assert result.fired is False

    # -- Details content --

    @pytest.mark.asyncio
    async def test_details_include_speed_info(self, rule):
        positions = _make_speed_history(normal_speed=14.0, count=8, span_minutes=130)
        positions.append(_position(sog=4.0, minutes_ago=0))

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                result = await rule.evaluate(123456789, {}, positions, [], [])
                assert result.fired is True
                assert "current_sog" in result.details
                assert "avg_speed_2h" in result.details
                assert "speed_drop_percent" in result.details
                assert result.details["route_name"] == "Balticconnector Gas Pipeline"

    # -- Edge cases --

    @pytest.mark.asyncio
    async def test_missing_lat_lon(self, rule):
        positions = _make_speed_history()
        positions[-1]["lat"] = None
        positions[-1]["lon"] = None
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_sog_on_latest(self, rule):
        positions = _make_speed_history()
        positions[-1]["sog"] = None
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_average_speed(self, rule):
        """All historical positions at SOG 0 should not fire (no division by zero)."""
        positions = _make_speed_history(normal_speed=0.0, count=8, span_minutes=130)
        positions.append(_position(sog=0.0, minutes_ago=0))

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                result = await rule.evaluate(123456789, {}, positions, [], [])
                assert result.fired is False

    # -- Rule properties --

    def test_rule_id(self, rule):
        assert rule.rule_id == "infra_speed_anomaly"

    def test_rule_category(self, rule):
        assert rule.rule_category == "realtime"
