"""Tests for services/scoring/rules/spoof_impossible_speed.py."""

from datetime import datetime, timedelta, timezone

import pytest

from services.scoring.rules.spoof_impossible_speed import (
    SpoofImpossibleSpeedRule,
    _get_speed_threshold,
    _SPEED_TANKER,
    _SPEED_CONTAINER,
    _SPEED_GENERAL_CARGO,
    _SPEED_TUG,
    _SPEED_DEFAULT,
    _THRESHOLD_FACTOR,
)


@pytest.fixture
def rule():
    return SpoofImpossibleSpeedRule()


def _pos(lat, lon, ts):
    """Create a position dict."""
    return {
        "lat": lat,
        "lon": lon,
        "timestamp": ts.isoformat() if isinstance(ts, datetime) else ts,
        "sog": 10.0,
    }


_BASE_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestSpeedThreshold:
    """Test ship-type-specific speed threshold computation."""

    def test_tanker_threshold(self):
        threshold = _get_speed_threshold(80, None)
        assert threshold == _SPEED_TANKER * _THRESHOLD_FACTOR  # 27.0

    def test_tanker_type_89(self):
        threshold = _get_speed_threshold(89, None)
        assert threshold == _SPEED_TANKER * _THRESHOLD_FACTOR

    def test_cargo_threshold(self):
        threshold = _get_speed_threshold(70, None)
        assert threshold == _SPEED_GENERAL_CARGO * _THRESHOLD_FACTOR  # 24.0

    def test_container_by_text(self):
        threshold = _get_speed_threshold(70, "Container Ship")
        assert threshold == _SPEED_CONTAINER * _THRESHOLD_FACTOR  # 37.5

    def test_tug_by_text(self):
        threshold = _get_speed_threshold(None, "Tug")
        assert threshold == _SPEED_TUG * _THRESHOLD_FACTOR  # 21.0

    def test_bulk_carrier_by_text(self):
        threshold = _get_speed_threshold(70, "Bulk Carrier")
        assert threshold == 16.0 * _THRESHOLD_FACTOR  # 24.0

    def test_default_threshold(self):
        threshold = _get_speed_threshold(None, None)
        assert threshold == _SPEED_DEFAULT * _THRESHOLD_FACTOR  # 45.0

    def test_text_takes_precedence_over_type(self):
        """Text-based classification should override numeric ship_type."""
        # ship_type 80 = tanker, but text says tug
        threshold = _get_speed_threshold(80, "Tug")
        assert threshold == _SPEED_TUG * _THRESHOLD_FACTOR


class TestSpoofImpossibleSpeedRule:
    """Test the spoof_impossible_speed rule."""

    def test_rule_id(self, rule):
        assert rule.rule_id == "spoof_impossible_speed"

    def test_rule_category(self, rule):
        assert rule.rule_category == "realtime"

    @pytest.mark.asyncio
    async def test_less_than_two_positions_returns_none(self, rule):
        result = await rule.evaluate(211000000, {}, [_pos(0, 0, _BASE_TS)], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_normal_speed_does_not_fire(self, rule):
        """Two positions 10nm apart in 1 hour = 10 knots (well below any threshold)."""
        # ~10nm apart (rough approximation)
        positions = [
            _pos(50.0, 0.0, _BASE_TS),
            _pos(50.1667, 0.0, _BASE_TS + timedelta(hours=1)),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_impossible_speed_fires_high(self, rule):
        """Single impossible speed event → high severity, 40 points."""
        # ~500nm apart in 1 hour = ~500 knots (way over 45kn threshold)
        positions = [
            _pos(50.0, 0.0, _BASE_TS),
            _pos(58.0, 0.0, _BASE_TS + timedelta(hours=1)),  # ~480nm
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_repeated_impossible_speed_fires_critical(self, rule):
        """2+ impossible speed events → critical severity, 100 points."""
        positions = [
            _pos(50.0, 0.0, _BASE_TS),
            _pos(58.0, 0.0, _BASE_TS + timedelta(hours=1)),
            _pos(50.0, 0.0, _BASE_TS + timedelta(hours=2)),
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.details["violation_count"] >= 2

    @pytest.mark.asyncio
    async def test_tanker_lower_threshold(self, rule):
        """Tanker (ship_type=80) has lower threshold (27kn)."""
        # Position 30nm apart in 1 hour = 30 knots (above tanker 27kn, below default 45kn)
        positions = [
            _pos(50.0, 0.0, _BASE_TS),
            _pos(50.5, 0.0, _BASE_TS + timedelta(hours=1)),  # ~30nm
        ]
        profile = {"ship_type": 80}
        result = await rule.evaluate(211000000, profile, positions, [], [])
        assert result is not None
        assert result.fired is True

    @pytest.mark.asyncio
    async def test_zero_time_delta_skipped(self, rule):
        """Zero time delta between positions should be skipped."""
        positions = [
            _pos(50.0, 0.0, _BASE_TS),
            _pos(58.0, 0.0, _BASE_TS),  # same timestamp
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_missing_lat_lon_skipped(self, rule):
        """Positions with None lat/lon should be skipped."""
        positions = [
            {"lat": None, "lon": 0.0, "timestamp": _BASE_TS.isoformat()},
            {"lat": 58.0, "lon": 0.0, "timestamp": (_BASE_TS + timedelta(hours=1)).isoformat()},
        ]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_profile_uses_default_threshold(self, rule):
        """No profile → default threshold (45kn)."""
        # 50kn = above default threshold
        positions = [
            _pos(50.0, 0.0, _BASE_TS),
            _pos(50.85, 0.0, _BASE_TS + timedelta(hours=1)),  # ~51nm
        ]
        result = await rule.evaluate(211000000, None, positions, [], [])
        assert result is not None
        assert result.fired is True
