"""Tests for services/scoring/rules/spoof_land_position.py."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.scoring.rules.spoof_land_position import SpoofLandPositionRule


@pytest.fixture
def rule():
    return SpoofLandPositionRule()


def _pos(lat, lon, ts_offset_hours=0):
    """Create a position dict."""
    ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    if ts_offset_hours:
        from datetime import timedelta
        ts = ts + timedelta(hours=ts_offset_hours)
    return {
        "lat": lat,
        "lon": lon,
        "timestamp": ts.isoformat(),
        "sog": 10.0,
        "cog": 180.0,
    }


class TestSpoofLandPositionRule:
    """Test the spoof_land_position rule."""

    def test_rule_id(self, rule):
        assert rule.rule_id == "spoof_land_position"

    def test_rule_category(self, rule):
        assert rule.rule_category == "realtime"

    @pytest.mark.asyncio
    async def test_no_positions_returns_none(self, rule):
        result = await rule.evaluate(211000000, {}, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_no_land_mask_data_returns_none(self, rule):
        """When land_mask table is empty, rule should return None (not fire)."""
        positions = [_pos(52.52, 13.405)]
        with patch.object(rule, "_has_land_mask_data", new_callable=AsyncMock, return_value=False):
            result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_ocean_position_does_not_fire(self, rule):
        """Position in mid-Atlantic should not fire."""
        positions = [_pos(30.0, -40.0)]
        with patch.object(rule, "_has_land_mask_data", new_callable=AsyncMock, return_value=True), \
             patch.object(rule, "_is_on_land", new_callable=AsyncMock, return_value=False):
            result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_single_land_position_fires_moderate(self, rule):
        """Single position on land → moderate severity, 15 points."""
        positions = [_pos(52.52, 13.405)]
        with patch.object(rule, "_has_land_mask_data", new_callable=AsyncMock, return_value=True), \
             patch.object(rule, "_is_on_land", new_callable=AsyncMock, return_value=True):
            result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0
        assert result.details["reason"] == "land_position"

    @pytest.mark.asyncio
    async def test_three_consecutive_land_positions_fires_critical(self, rule):
        """3+ consecutive land positions → critical severity, 100 points."""
        positions = [
            _pos(52.52, 13.405, 0),
            _pos(52.53, 13.41, 0.5),
            _pos(52.54, 13.42, 1.0),
        ]
        with patch.object(rule, "_has_land_mask_data", new_callable=AsyncMock, return_value=True), \
             patch.object(rule, "_is_on_land", new_callable=AsyncMock, return_value=True):
            result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.details["reason"] == "consecutive_land_positions"
        assert result.details["max_consecutive"] >= 3

    @pytest.mark.asyncio
    async def test_mixed_land_ocean_below_threshold(self, rule):
        """Alternating land/ocean positions should not reach 3 consecutive."""
        positions = [
            _pos(52.52, 13.405, 0),
            _pos(30.0, -40.0, 0.5),
            _pos(52.53, 13.41, 1.0),
        ]
        on_land_results = [True, False, True]
        call_count = 0

        async def mock_is_on_land(lat, lon):
            nonlocal call_count
            result = on_land_results[call_count]
            call_count += 1
            return result

        with patch.object(rule, "_has_land_mask_data", new_callable=AsyncMock, return_value=True), \
             patch.object(rule, "_is_on_land", side_effect=mock_is_on_land):
            result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "moderate"  # not critical

    def test_count_max_consecutive(self, rule):
        """Test the consecutive counting helper."""
        all_pos = [_pos(0, 0, i) for i in range(5)]
        land_pos = [all_pos[1], all_pos[2], all_pos[3]]
        assert rule._count_max_consecutive_land(all_pos, land_pos) == 3

    def test_count_max_consecutive_with_gaps(self, rule):
        all_pos = [_pos(0, 0, i) for i in range(5)]
        land_pos = [all_pos[0], all_pos[2], all_pos[3]]
        assert rule._count_max_consecutive_land(all_pos, land_pos) == 2
