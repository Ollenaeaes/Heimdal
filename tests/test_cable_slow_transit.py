"""Tests for the Cable Corridor Slow Transit scoring rule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.scoring.rules.cable_slow_transit import CableSlowTransitRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(minutes_ago: float = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return dt.isoformat()


def _position(lat=56.0, lon=19.5, sog=3.0, minutes_ago=0, cog=90.0):
    return {
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "cog": cog,
        "timestamp": _ts(minutes_ago),
    }


_ROUTE = {
    "id": 1,
    "name": "NordBalt HVDC Cable",
    "route_type": "power_cable",
    "operator": "Svenska Kraftnät",
    "buffer_nm": 1.0,
    "metadata": {},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCableSlowTransit:
    @pytest.fixture
    def rule(self):
        return CableSlowTransitRule()

    # -- Basic non-firing cases --

    @pytest.mark.asyncio
    async def test_no_positions(self, rule):
        result = await rule.evaluate(123456789, {}, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_cable_laying_vessel_excluded(self, rule):
        """Ship type 33 (cable layer) should never fire."""
        profile = {"ship_type": 33}
        positions = [_position(sog=2.0)]
        result = await rule.evaluate(123456789, profile, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_not_in_corridor(self, rule):
        """Vessel not in any infrastructure corridor."""
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[]):
            with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock):
                result = await rule.evaluate(
                    123456789, {"ship_type": 70}, [_position()], [], []
                )
                assert result.fired is False

    @pytest.mark.asyncio
    async def test_in_port_approach_excluded(self, rule):
        """Vessel in port approach should not fire."""
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=True):
                with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock):
                    result = await rule.evaluate(
                        123456789, {"ship_type": 70}, [_position(sog=3.0)], [], []
                    )
                    assert result.fired is False

    @pytest.mark.asyncio
    async def test_speed_above_threshold(self, rule):
        """Vessel at normal speed should not fire."""
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock):
                    result = await rule.evaluate(
                        123456789, {"ship_type": 70}, [_position(sog=10.0)], [], []
                    )
                    assert result.fired is False

    # -- Entry detection (first time in corridor) --

    @pytest.mark.asyncio
    async def test_first_entry_records_state(self, rule):
        """First slow-speed detection should set Redis state but not fire."""
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=None):
                    with patch.object(rule, "_set_redis_state", new_callable=AsyncMock) as mock_set:
                        result = await rule.evaluate(
                            123456789, {"ship_type": 70}, [_position(sog=3.0)], [], []
                        )
                        assert result.fired is False
                        mock_set.assert_called_once()
                        call_state = mock_set.call_args[0][1]
                        assert call_state["route_id"] == 1

    # -- Duration-based firing --

    @pytest.mark.asyncio
    async def test_fires_high_after_30_minutes(self, rule):
        """30-60 minutes at slow speed should fire with severity 'high'."""
        entry_time = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
        redis_state = {"route_id": 1, "entry_time": entry_time, "entry_lat": 56.0, "entry_lon": 19.5}

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    result = await rule.evaluate(
                        123456789, {"ship_type": 70}, [_position(sog=3.0)], [], []
                    )
                    assert result.fired is True
                    assert result.severity == "high"
                    assert result.points == 40.0
                    assert result.details["route_name"] == "NordBalt HVDC Cable"

    @pytest.mark.asyncio
    async def test_fires_critical_after_60_minutes(self, rule):
        """Over 60 minutes should fire with severity 'critical'."""
        entry_time = (datetime.now(timezone.utc) - timedelta(minutes=75)).isoformat()
        redis_state = {"route_id": 1, "entry_time": entry_time, "entry_lat": 56.0, "entry_lon": 19.5}

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    result = await rule.evaluate(
                        123456789, {"ship_type": 70}, [_position(sog=3.0)], [], []
                    )
                    assert result.fired is True
                    assert result.severity == "critical"
                    assert result.points == 100.0

    @pytest.mark.asyncio
    async def test_not_enough_duration(self, rule):
        """Under 30 minutes should not fire."""
        entry_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        redis_state = {"route_id": 1, "entry_time": entry_time, "entry_lat": 56.0, "entry_lon": 19.5}

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    result = await rule.evaluate(
                        123456789, {"ship_type": 70}, [_position(sog=3.0)], [], []
                    )
                    assert result.fired is False

    # -- Shadow fleet escalation --

    @pytest.mark.asyncio
    async def test_shadow_fleet_escalation(self, rule):
        """Existing sanctions_match should add 40 points."""
        entry_time = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
        redis_state = {"route_id": 1, "entry_time": entry_time, "entry_lat": 56.0, "entry_lon": 19.5}
        existing = [{"rule_id": "sanctions_match", "resolved": False}]

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    result = await rule.evaluate(
                        123456789, {"ship_type": 70}, [_position(sog=3.0)], existing, []
                    )
                    assert result.fired is True
                    assert result.points == 80.0  # 40 base + 40 escalation
                    assert result.details["shadow_fleet_escalation"] is True

    @pytest.mark.asyncio
    async def test_shadow_fleet_no_escalation_resolved(self, rule):
        """Resolved sanctions_match should not trigger escalation."""
        entry_time = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
        redis_state = {"route_id": 1, "entry_time": entry_time, "entry_lat": 56.0, "entry_lon": 19.5}
        existing = [{"rule_id": "sanctions_match", "resolved": True}]

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    result = await rule.evaluate(
                        123456789, {"ship_type": 70}, [_position(sog=3.0)], existing, []
                    )
                    assert result.points == 40.0  # no escalation

    @pytest.mark.asyncio
    async def test_shadow_fleet_escalation_flag_hopping(self, rule):
        """flag_hopping should also trigger escalation."""
        entry_time = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
        redis_state = {"route_id": 1, "entry_time": entry_time, "entry_lat": 56.0, "entry_lon": 19.5}
        existing = [{"rule_id": "flag_hopping", "resolved": False}]

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_check_port_approach", new_callable=AsyncMock, return_value=False):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    result = await rule.evaluate(
                        123456789, {"ship_type": 70}, [_position(sog=3.0)], existing, []
                    )
                    assert result.points == 80.0

    # -- Missing data edge cases --

    @pytest.mark.asyncio
    async def test_missing_lat_lon(self, rule):
        positions = [{"sog": 3.0, "timestamp": _ts(), "lat": None, "lon": None}]
        result = await rule.evaluate(123456789, {"ship_type": 70}, positions, [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_sog(self, rule):
        positions = [{"lat": 56.0, "lon": 19.5, "sog": None, "timestamp": _ts()}]
        result = await rule.evaluate(123456789, {"ship_type": 70}, positions, [], [])
        assert result is None

    # -- check_event_ended --

    @pytest.mark.asyncio
    async def test_event_ended_when_left_corridor(self, rule):
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[]):
            with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock):
                ended = await rule.check_event_ended(
                    123456789, {}, [_position(sog=3.0)], {}
                )
                assert ended is True

    @pytest.mark.asyncio
    async def test_event_ended_when_sped_up(self, rule):
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock):
                ended = await rule.check_event_ended(
                    123456789, {}, [_position(sog=10.0)], {}
                )
                assert ended is True

    @pytest.mark.asyncio
    async def test_event_not_ended_still_slow_in_corridor(self, rule):
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            ended = await rule.check_event_ended(
                123456789, {}, [_position(sog=3.0)], {}
            )
            assert ended is False

    # -- Rule properties --

    def test_rule_id(self, rule):
        assert rule.rule_id == "cable_slow_transit"

    def test_rule_category(self, rule):
        assert rule.rule_category == "realtime"
