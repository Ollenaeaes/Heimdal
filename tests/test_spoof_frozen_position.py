"""Tests for services/scoring/rules/spoof_frozen_position.py."""

from datetime import datetime, timedelta, timezone

import pytest

from services.scoring.rules.spoof_frozen_position import SpoofFrozenPositionRule


@pytest.fixture
def rule():
    return SpoofFrozenPositionRule()


_BASE_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _pos(lat, lon, ts_offset_hours=0, sog=10.0, cog=180.0, nav_status=None):
    """Create a position dict."""
    ts = _BASE_TS + timedelta(hours=ts_offset_hours)
    pos = {
        "lat": lat,
        "lon": lon,
        "timestamp": ts.isoformat(),
        "sog": sog,
        "cog": cog,
    }
    if nav_status is not None:
        pos["nav_status"] = nav_status
    return pos


class TestSpoofFrozenPositionRule:
    """Test the spoof_frozen_position rule."""

    def test_rule_id(self, rule):
        assert rule.rule_id == "spoof_frozen_position"

    def test_rule_category(self, rule):
        assert rule.rule_category == "realtime"

    @pytest.mark.asyncio
    async def test_less_than_two_positions_returns_none(self, rule):
        result = await rule.evaluate(211000000, {}, [_pos(50, 0)], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_normal_movement_does_not_fire(self, rule):
        """Positions with different lat/lon/sog should not fire."""
        positions = [
            _pos(50.0, 0.0, 0, sog=10.0, cog=180.0),
            _pos(50.1, 0.1, 1, sog=11.0, cog=185.0),
            _pos(50.2, 0.2, 2, sog=12.0, cog=190.0),
            _pos(50.3, 0.3, 3, sog=10.5, cog=175.0),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_frozen_position_fires_high(self, rule):
        """Identical position for > 2 hours → high severity, 40 points."""
        positions = [
            _pos(50.0, 0.0, 0, sog=5.0, cog=180.0),
            _pos(50.0, 0.0, 0.5, sog=5.0, cog=180.0),
            _pos(50.0, 0.0, 1.0, sog=5.0, cog=180.0),
            _pos(50.0, 0.0, 1.5, sog=5.0, cog=180.0),
            _pos(50.0, 0.0, 2.0, sog=5.0, cog=180.0),
            _pos(50.0, 0.0, 2.5, sog=5.0, cog=180.0),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.details["reason"] == "frozen_position"

    @pytest.mark.asyncio
    async def test_frozen_position_at_anchor_does_not_fire(self, rule):
        """Identical position while at anchor is normal — should not fire."""
        positions = [
            _pos(50.0, 0.0, 0, sog=0.0, cog=0.0, nav_status="At anchor"),
            _pos(50.0, 0.0, 1.0, sog=0.0, cog=0.0, nav_status="At anchor"),
            _pos(50.0, 0.0, 2.0, sog=0.0, cog=0.0, nav_status="At anchor"),
            _pos(50.0, 0.0, 3.0, sog=0.0, cog=0.0, nav_status="At anchor"),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_frozen_position_moored_does_not_fire(self, rule):
        """Identical position while moored is normal."""
        positions = [
            _pos(50.0, 0.0, 0, sog=0.0, cog=0.0, nav_status="Moored"),
            _pos(50.0, 0.0, 1.0, sog=0.0, cog=0.0, nav_status="Moored"),
            _pos(50.0, 0.0, 2.0, sog=0.0, cog=0.0, nav_status="Moored"),
            _pos(50.0, 0.0, 3.0, sog=0.0, cog=0.0, nav_status="Moored"),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_frozen_position_less_than_2_hours_does_not_fire(self, rule):
        """Frozen position for < 2 hours should not fire."""
        positions = [
            _pos(50.0, 0.0, 0, sog=5.0, cog=180.0),
            _pos(50.0, 0.0, 0.5, sog=5.0, cog=180.0),
            _pos(50.0, 0.0, 1.0, sog=5.0, cog=180.0),
            _pos(50.0, 0.0, 1.5, sog=5.0, cog=180.0),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_box_pattern_fires_high(self, rule):
        """Positions oscillating between 2 pairs for > 1 hour."""
        positions = [
            _pos(50.0, 0.0, 0, sog=5.0),
            _pos(50.002, 0.002, 0.2, sog=5.0),  # 2nd point (within tolerance of pair2)
            _pos(50.0, 0.0, 0.4, sog=5.0),     # back to pair1
            _pos(50.002, 0.002, 0.6, sog=5.0),  # pair2 again
            _pos(50.0, 0.0, 0.8, sog=5.0),     # pair1 again
            _pos(50.002, 0.002, 1.0, sog=5.0),  # pair2 again
            _pos(50.0, 0.0, 1.2, sog=5.0),     # pair1 again
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.details["reason"] == "box_pattern"

    @pytest.mark.asyncio
    async def test_box_pattern_less_than_1_hour_does_not_fire(self, rule):
        """Box pattern spanning < 1 hour should not fire."""
        positions = [
            _pos(50.0, 0.0, 0, sog=5.0),
            _pos(50.002, 0.002, 0.1, sog=5.0),
            _pos(50.0, 0.0, 0.2, sog=5.0),
            _pos(50.002, 0.002, 0.3, sog=5.0),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_within_tolerance_is_considered_identical(self, rule):
        """Positions within 0.001 deg and 0.1 kn tolerance are 'identical'."""
        positions = [
            _pos(50.0, 0.0, 0, sog=5.0, cog=180.0),
            _pos(50.0005, 0.0005, 0.5, sog=5.03, cog=180.03),
            _pos(50.0003, 0.0003, 1.0, sog=4.97, cog=179.97),
            _pos(50.0004, 0.0004, 1.5, sog=5.02, cog=180.01),
            _pos(50.0002, 0.0002, 2.0, sog=4.98, cog=179.98),
            _pos(50.0001, 0.0001, 2.5, sog=5.01, cog=180.01),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.details["reason"] == "frozen_position"
