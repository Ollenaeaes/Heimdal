"""Tests for the Cable Alignment Transit scoring rule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.scoring.rules.cable_alignment import CableAlignmentRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(minutes_ago: float = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return dt.isoformat()


def _position(lat=56.0, lon=19.5, sog=10.0, cog=45.0, minutes_ago=0):
    return {
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "cog": cog,
        "timestamp": _ts(minutes_ago),
    }


_ROUTE = {
    "id": 1,
    "name": "C-Lion1 Submarine Telecom Cable",
    "route_type": "telecom_cable",
    "operator": "Cinia Oy",
    "buffer_nm": 1.5,
    "metadata": {},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCableAlignment:
    @pytest.fixture
    def rule(self):
        return CableAlignmentRule()

    # -- Basic non-firing cases --

    @pytest.mark.asyncio
    async def test_no_positions(self, rule):
        result = await rule.evaluate(123456789, {}, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_cog(self, rule):
        positions = [{"lat": 56.0, "lon": 19.5, "sog": 10.0, "cog": None, "timestamp": _ts()}]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_not_in_corridor(self, rule):
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[]):
            with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock):
                result = await rule.evaluate(
                    123456789, {}, [_position()], [], []
                )
                assert result.fired is False

    # -- Alignment detection --

    @pytest.mark.asyncio
    async def test_first_alignment_records_state(self, rule):
        """First aligned position should set Redis state but not fire."""
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=None):
                    with patch.object(rule, "_set_redis_state", new_callable=AsyncMock) as mock_set:
                        result = await rule.evaluate(
                            123456789, {}, [_position(cog=50.0)], [], []  # 5 deg off
                        )
                        assert result.fired is False
                        mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_fires_high_after_15_minutes(self, rule):
        """15-60 minutes of alignment should fire with severity 'high'."""
        first_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        redis_state = {
            "route_id": 1,
            "first_parallel_time": first_time,
            "consecutive_count": 5,
        }

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    with patch.object(rule, "_set_redis_state", new_callable=AsyncMock):
                        result = await rule.evaluate(
                            123456789, {}, [_position(cog=50.0)], [], []
                        )
                        assert result.fired is True
                        assert result.severity == "high"
                        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_fires_critical_after_60_minutes(self, rule):
        """Over 60 minutes of alignment should fire with severity 'critical'."""
        first_time = (datetime.now(timezone.utc) - timedelta(minutes=75)).isoformat()
        redis_state = {
            "route_id": 1,
            "first_parallel_time": first_time,
            "consecutive_count": 15,
        }

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    with patch.object(rule, "_set_redis_state", new_callable=AsyncMock):
                        result = await rule.evaluate(
                            123456789, {}, [_position(cog=50.0)], [], []
                        )
                        assert result.fired is True
                        assert result.severity == "critical"
                        assert result.points == 100.0

    @pytest.mark.asyncio
    async def test_not_enough_duration(self, rule):
        """Under 15 minutes should not fire."""
        first_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        redis_state = {
            "route_id": 1,
            "first_parallel_time": first_time,
            "consecutive_count": 3,
        }

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    with patch.object(rule, "_set_redis_state", new_callable=AsyncMock):
                        result = await rule.evaluate(
                            123456789, {}, [_position(cog=50.0)], [], []
                        )
                        assert result.fired is False

    # -- Reset when angle diverges --

    @pytest.mark.asyncio
    async def test_reset_when_angle_exceeds_30(self, rule):
        """COG > 30 degrees from bearing should clear state."""
        redis_state = {
            "route_id": 1,
            "first_parallel_time": _ts(20),
            "consecutive_count": 5,
        }

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock) as mock_clear:
                        result = await rule.evaluate(
                            123456789, {}, [_position(cog=120.0)], [], []  # 75 deg off
                        )
                        assert result.fired is False
                        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_hysteresis_between_20_and_30(self, rule):
        """Angle between 20-30 degrees should maintain state (no fire, no reset)."""
        redis_state = {
            "route_id": 1,
            "first_parallel_time": _ts(20),
            "consecutive_count": 5,
        }

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    result = await rule.evaluate(
                        123456789, {}, [_position(cog=70.0)], [], []  # 25 deg off
                    )
                    assert result.fired is False

    # -- No cable bearing available --

    @pytest.mark.asyncio
    async def test_no_cable_bearing(self, rule):
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=None):
                result = await rule.evaluate(
                    123456789, {}, [_position()], [], []
                )
                assert result.fired is False

    # -- check_event_ended --

    @pytest.mark.asyncio
    async def test_event_ended_when_diverged(self, rule):
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock):
                    ended = await rule.check_event_ended(
                        123456789, {}, [_position(cog=120.0)], {}
                    )
                    assert ended is True

    @pytest.mark.asyncio
    async def test_event_ended_when_left_corridor(self, rule):
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[]):
            with patch.object(rule, "_clear_redis_state", new_callable=AsyncMock):
                ended = await rule.check_event_ended(
                    123456789, {}, [_position()], {}
                )
                assert ended is True

    @pytest.mark.asyncio
    async def test_event_not_ended_still_aligned(self, rule):
        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                ended = await rule.check_event_ended(
                    123456789, {}, [_position(cog=50.0)], {}
                )
                assert ended is False

    # -- Details content --

    @pytest.mark.asyncio
    async def test_details_include_alignment_info(self, rule):
        first_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        redis_state = {
            "route_id": 1,
            "first_parallel_time": first_time,
            "consecutive_count": 5,
        }

        with patch.object(rule, "_check_corridor", new_callable=AsyncMock, return_value=[_ROUTE]):
            with patch.object(rule, "_get_cable_bearing", new_callable=AsyncMock, return_value=45.0):
                with patch.object(rule, "_get_redis_state", new_callable=AsyncMock, return_value=redis_state):
                    with patch.object(rule, "_set_redis_state", new_callable=AsyncMock):
                        result = await rule.evaluate(
                            123456789, {}, [_position(cog=50.0)], [], []
                        )
                        assert result.fired is True
                        assert "angle_difference" in result.details
                        assert "cable_bearing" in result.details
                        assert "consecutive_count" in result.details
                        assert result.details["route_name"] == "C-Lion1 Submarine Telecom Cable"

    # -- Rule properties --

    def test_rule_id(self, rule):
        assert rule.rule_id == "cable_alignment"

    def test_rule_category(self, rule):
        assert rule.rule_category == "realtime"
