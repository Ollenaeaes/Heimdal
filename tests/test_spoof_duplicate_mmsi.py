"""Tests for services/scoring/rules/spoof_duplicate_mmsi.py."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from services.scoring.rules.spoof_duplicate_mmsi import SpoofDuplicateMmsiRule


_BASE_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _pos(lat, lon, ts=None):
    """Create a position dict."""
    ts = ts or _BASE_TS
    return {
        "lat": lat,
        "lon": lon,
        "timestamp": ts.isoformat(),
        "sog": 10.0,
    }


class FakeRedis:
    """Minimal Redis mock for testing."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def setex(self, key: str, ttl: int, value: str):
        self._store[key] = value.encode() if isinstance(value, str) else value

    def delete(self, key: str):
        self._store.pop(key, None)


@pytest.fixture
def redis_client():
    return FakeRedis()


@pytest.fixture
def rule(redis_client):
    return SpoofDuplicateMmsiRule(redis_client=redis_client)


class TestSpoofDuplicateMmsiRule:
    """Test the spoof_duplicate_mmsi rule."""

    def test_rule_id(self, rule):
        assert rule.rule_id == "spoof_duplicate_mmsi"

    def test_rule_category(self, rule):
        assert rule.rule_category == "realtime"

    @pytest.mark.asyncio
    async def test_no_positions_returns_none(self, rule):
        result = await rule.evaluate(211000000, {}, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_first_position_does_not_fire(self, rule):
        """First-ever position for MMSI should store but not fire."""
        positions = [_pos(50.0, 0.0)]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_nearby_position_does_not_fire(self, rule, redis_client):
        """Same MMSI from nearby location (< 10nm) should not fire."""
        # Pre-seed Redis with nearby previous position
        redis_client.setex(
            "heimdal:last_pos:211000000",
            600,
            json.dumps({"lat": 50.0, "lon": 0.0, "timestamp": _BASE_TS.isoformat()}),
        )
        # New position 1nm away, 2 minutes later
        positions = [_pos(50.0167, 0.0, _BASE_TS + timedelta(minutes=2))]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_distant_position_within_5min_fires_critical(self, rule, redis_client):
        """Same MMSI from >10nm away within 5 min → critical."""
        # Pre-seed: North Sea position
        redis_client.setex(
            "heimdal:last_pos:211000000",
            600,
            json.dumps({"lat": 50.0, "lon": 0.0, "timestamp": _BASE_TS.isoformat()}),
        )
        # New position: 100nm away, 3 minutes later
        positions = [_pos(51.67, 0.0, _BASE_TS + timedelta(minutes=3))]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.details["reason"] == "duplicate_mmsi"
        assert result.details["distance_nm"] > 10.0

    @pytest.mark.asyncio
    async def test_distant_position_beyond_5min_does_not_fire(self, rule, redis_client):
        """Same MMSI from >10nm away but > 5 min apart → normal transit."""
        redis_client.setex(
            "heimdal:last_pos:211000000",
            600,
            json.dumps({"lat": 50.0, "lon": 0.0, "timestamp": _BASE_TS.isoformat()}),
        )
        # 10 minutes later — beyond 5-minute window
        positions = [_pos(51.67, 0.0, _BASE_TS + timedelta(minutes=10))]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_redis_updated_after_evaluation(self, rule, redis_client):
        """Redis should always be updated with the latest position."""
        positions = [_pos(55.0, 10.0)]
        await rule.evaluate(211000000, {}, positions, [], [])

        stored = json.loads(redis_client.get("heimdal:last_pos:211000000"))
        assert stored["lat"] == 55.0
        assert stored["lon"] == 10.0

    @pytest.mark.asyncio
    async def test_no_redis_returns_none(self):
        """If Redis is unavailable, rule should return None."""
        rule = SpoofDuplicateMmsiRule(redis_client=None)
        # Force _get_redis to return None
        rule._redis = None
        rule._get_redis = lambda: None
        positions = [_pos(50.0, 0.0)]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_corrupted_redis_data_does_not_fire(self, rule, redis_client):
        """Corrupted Redis data should not crash or fire."""
        redis_client.setex("heimdal:last_pos:211000000", 600, "not-json{{{")
        positions = [_pos(50.0, 0.0)]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_missing_lat_lon_returns_none(self, rule):
        """Position with None lat/lon should be handled gracefully."""
        positions = [{"lat": None, "lon": None, "timestamp": _BASE_TS.isoformat()}]
        result = await rule.evaluate(211000000, {}, positions, [], [])
        assert result is None
