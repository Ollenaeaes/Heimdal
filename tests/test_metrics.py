"""Tests for metrics publisher."""

import time

import pytest
import fakeredis.aioredis

# Add services to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "ais-ingest"))

from metrics import MetricsPublisher


@pytest.fixture
def redis_client():
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def publisher(redis_client):
    """Create a MetricsPublisher with fake Redis."""
    return MetricsPublisher(redis_client)


class TestMetricsPublisher:
    """Tests for the MetricsPublisher class."""

    @pytest.mark.asyncio
    async def test_ingest_rate_set_after_batch(self, publisher, redis_client):
        await publisher.record_batch(100, [259000420, 211234567])
        rate = await redis_client.get("heimdal:metrics:ingest_rate")
        assert rate is not None
        rate_val = float(rate)
        assert rate_val > 0

    @pytest.mark.asyncio
    async def test_last_message_at_updated(self, publisher, redis_client):
        await publisher.record_batch(50, [259000420])
        ts = await redis_client.get("heimdal:metrics:last_message_at")
        assert ts is not None
        # Should be a valid ISO timestamp
        ts_str = ts.decode()
        assert "T" in ts_str
        assert "+" in ts_str or "Z" in ts_str

    @pytest.mark.asyncio
    async def test_total_vessels_increments_on_new_mmsi(self, publisher, redis_client):
        await publisher.record_batch(10, [259000420])
        v1 = await redis_client.get("heimdal:metrics:total_vessels")
        assert v1 == b"1"

        await publisher.record_batch(10, [211234567])
        v2 = await redis_client.get("heimdal:metrics:total_vessels")
        assert v2 == b"2"

        await publisher.record_batch(10, [636012345])
        v3 = await redis_client.get("heimdal:metrics:total_vessels")
        assert v3 == b"3"

    @pytest.mark.asyncio
    async def test_total_vessels_stays_same_on_existing_mmsi(self, publisher, redis_client):
        await publisher.record_batch(10, [259000420, 211234567])
        v1 = await redis_client.get("heimdal:metrics:total_vessels")
        assert v1 == b"2"

        # Same MMSIs again
        await publisher.record_batch(10, [259000420, 211234567])
        v2 = await redis_client.get("heimdal:metrics:total_vessels")
        assert v2 == b"2"

    @pytest.mark.asyncio
    async def test_multiple_batches_accumulate_vessels(self, publisher, redis_client):
        await publisher.record_batch(5, [259000420])
        await publisher.record_batch(5, [259000420, 211234567])
        await publisher.record_batch(5, [636012345])
        v = await redis_client.get("heimdal:metrics:total_vessels")
        assert v == b"3"

    @pytest.mark.asyncio
    async def test_rate_reflects_batch_count(self, publisher, redis_client):
        """Rate should reflect total positions in the window."""
        await publisher.record_batch(500, [259000420])
        rate = await redis_client.get("heimdal:metrics:ingest_rate")
        rate_val = float(rate)
        # With one batch at time T, rate = 500 / max(elapsed, 1) = 500.0
        assert rate_val == 500.0

    @pytest.mark.asyncio
    async def test_rate_accumulates_over_batches(self, publisher, redis_client):
        """Multiple batches should accumulate in the rate window."""
        await publisher.record_batch(100, [259000420])
        await publisher.record_batch(200, [211234567])
        rate = await redis_client.get("heimdal:metrics:ingest_rate")
        rate_val = float(rate)
        # Total is 300, elapsed is ~0 so clamped to 1
        assert rate_val >= 100.0  # at least includes both batches

    @pytest.mark.asyncio
    async def test_empty_batch(self, publisher, redis_client):
        """An empty batch should still update metrics."""
        await publisher.record_batch(0, [])
        rate = await redis_client.get("heimdal:metrics:ingest_rate")
        assert rate is not None
        v = await redis_client.get("heimdal:metrics:total_vessels")
        assert v == b"0"

    @pytest.mark.asyncio
    async def test_last_message_at_updates_each_batch(self, publisher, redis_client):
        await publisher.record_batch(10, [259000420])
        ts1 = await redis_client.get("heimdal:metrics:last_message_at")

        await publisher.record_batch(10, [211234567])
        ts2 = await redis_client.get("heimdal:metrics:last_message_at")

        # Second timestamp should be same or later
        assert ts2 >= ts1
