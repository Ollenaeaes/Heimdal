"""Tests for Redis-based AIS message deduplication."""

from datetime import datetime, timezone

import pytest
import fakeredis.aioredis

# Add services to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "ais-ingest"))

from dedup import Deduplicator


@pytest.fixture
def redis_client():
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def dedup(redis_client):
    """Create a Deduplicator with fake Redis."""
    return Deduplicator(redis_client)


class TestDeduplicator:
    """Tests for the Deduplicator class."""

    @pytest.mark.asyncio
    async def test_first_message_is_not_duplicate(self, dedup):
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = await dedup.is_duplicate(259000420, ts)
        assert result is False

    @pytest.mark.asyncio
    async def test_second_same_message_is_duplicate(self, dedup):
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        first = await dedup.is_duplicate(259000420, ts)
        assert first is False
        second = await dedup.is_duplicate(259000420, ts)
        assert second is True

    @pytest.mark.asyncio
    async def test_same_mmsi_different_timestamp_not_duplicate(self, dedup):
        ts1 = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc)
        r1 = await dedup.is_duplicate(259000420, ts1)
        r2 = await dedup.is_duplicate(259000420, ts2)
        assert r1 is False
        assert r2 is False

    @pytest.mark.asyncio
    async def test_different_mmsi_same_timestamp_not_duplicate(self, dedup):
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        r1 = await dedup.is_duplicate(259000420, ts)
        r2 = await dedup.is_duplicate(211234567, ts)
        assert r1 is False
        assert r2 is False

    @pytest.mark.asyncio
    async def test_microseconds_are_stripped(self, dedup):
        """Timestamps that differ only in microseconds should be treated as duplicates."""
        ts1 = datetime(2024, 1, 15, 10, 30, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 10, 30, 0, 500000, tzinfo=timezone.utc)
        r1 = await dedup.is_duplicate(259000420, ts1)
        r2 = await dedup.is_duplicate(259000420, ts2)
        assert r1 is False
        assert r2 is True

    @pytest.mark.asyncio
    async def test_key_format(self, dedup, redis_client):
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        await dedup.is_duplicate(259000420, ts)
        key = "heimdal:dedup:259000420:2024-01-15T10:30:00+00:00"
        val = await redis_client.get(key)
        assert val is not None
        assert val == b"1"

    @pytest.mark.asyncio
    async def test_key_has_ttl(self, dedup, redis_client):
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        await dedup.is_duplicate(259000420, ts)
        key = "heimdal:dedup:259000420:2024-01-15T10:30:00+00:00"
        ttl = await redis_client.ttl(key)
        assert ttl > 0
        assert ttl <= 10

    @pytest.mark.asyncio
    async def test_after_ttl_expiry_key_can_be_reused(self, redis_client):
        """After TTL expires, the same key should be usable again."""
        dedup = Deduplicator(redis_client)
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        r1 = await dedup.is_duplicate(259000420, ts)
        assert r1 is False

        # Manually delete the key to simulate TTL expiry
        # (fakeredis time advancement is version-dependent, so we simulate)
        key = "heimdal:dedup:259000420:2024-01-15T10:30:00+00:00"
        await redis_client.delete(key)

        r2 = await dedup.is_duplicate(259000420, ts)
        assert r2 is False

    @pytest.mark.asyncio
    async def test_many_unique_messages(self, dedup):
        """Process many unique messages, none should be duplicates."""
        base_mmsi = 200000000
        base_ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(50):
            ts = base_ts.replace(second=i % 60)
            mmsi = base_mmsi + i
            result = await dedup.is_duplicate(mmsi, ts)
            assert result is False
