"""Tests for the BatchWriter class."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "ais-ingest"))

from writer import BatchWriter


def _make_position_report(**overrides):
    """Create a mock PositionReport with sensible defaults."""
    defaults = {
        "timestamp": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "mmsi": 259000420,
        "longitude": 15.456,
        "latitude": 68.123,
        "sog": 12.3,
        "cog": 180.5,
        "heading": 179,
        "nav_status": 0,
        "rot": 5.0,
    }
    defaults.update(overrides)
    report = MagicMock()
    for k, v in defaults.items():
        setattr(report, k, v)
    return report


class _FakeAcquireCtx:
    """Mimics asyncpg pool.acquire() as an async context manager."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        return False


def _make_mock_pool():
    """Create a mock asyncpg pool with a context-manager acquire."""
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value = _FakeAcquireCtx(conn)
    pool.close = AsyncMock()
    return pool, conn


def _make_mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def redis_client():
    return _make_mock_redis()


@pytest.fixture
def writer(redis_client):
    """Create a BatchWriter with mocked pool (no periodic flush)."""
    w = BatchWriter(
        dsn="postgresql://test:test@localhost:5432/test",
        redis_client=redis_client,
        batch_size=5,
        flush_interval=100.0,  # long interval so periodic flush doesn't fire
    )
    pool, conn = _make_mock_pool()
    w._pool = pool
    w._conn = conn  # stash for assertions
    return w


class TestBatchWriter:
    """Tests for the BatchWriter class."""

    @pytest.mark.asyncio
    async def test_positions_accumulate_before_batch_size(self, writer):
        """Positions should buffer without flushing before batch_size."""
        report = _make_position_report()
        # Add fewer than batch_size positions
        for _ in range(4):
            await writer.add_position(report)
        assert len(writer._position_buffer) == 4

    @pytest.mark.asyncio
    async def test_flush_triggers_at_batch_size(self, writer, redis_client):
        """Buffer should flush when it reaches batch_size."""
        report = _make_position_report()
        for _ in range(5):  # batch_size = 5
            await writer.add_position(report)
        # Buffer should be empty after flush
        assert len(writer._position_buffer) == 0
        # conn.executemany should have been called
        conn = writer._conn
        conn.executemany.assert_called_once()
        # Redis publish should have been called
        redis_client.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_flush_interval_triggers_flush(self):
        """Periodic flush should fire after flush_interval."""
        redis_client = _make_mock_redis()
        w = BatchWriter(
            dsn="postgresql://test:test@localhost:5432/test",
            redis_client=redis_client,
            batch_size=1000,  # high batch_size so only timer triggers
            flush_interval=0.1,  # 100ms
        )
        pool, conn = _make_mock_pool()
        w._pool = pool

        # Add a position (won't reach batch_size)
        report = _make_position_report()
        await w.add_position(report)
        assert len(w._position_buffer) == 1

        # Start periodic flush
        w._flush_task = asyncio.create_task(w._periodic_flush())

        # Wait for the flush interval to fire
        await asyncio.sleep(0.3)

        # Cancel the task
        w._flush_task.cancel()
        try:
            await w._flush_task
        except asyncio.CancelledError:
            pass

        # Buffer should be empty and DB should have been called
        assert len(w._position_buffer) == 0
        conn.executemany.assert_called()

    @pytest.mark.asyncio
    async def test_redis_event_published_after_flush(self, writer, redis_client):
        """Redis publish event should contain correct MMSIs and count."""
        r1 = _make_position_report(mmsi=259000420)
        r2 = _make_position_report(mmsi=211234567)
        r3 = _make_position_report(mmsi=259000420)  # duplicate MMSI

        await writer.add_position(r1)
        await writer.add_position(r2)
        await writer.add_position(r3)

        # Manually flush
        await writer._flush()

        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args
        assert call_args[0][0] == "heimdal:positions"
        event = json.loads(call_args[0][1])
        assert event["count"] == 3
        assert set(event["mmsis"]) == {259000420, 211234567}
        assert "timestamp" in event

    @pytest.mark.asyncio
    async def test_vessel_updates_queued_and_flushed(self, writer):
        """Vessel profile updates should be queued and flushed to DB."""
        await writer.add_vessel_update(259000420, {
            "ship_name": "NORDIC EXPLORER",
            "ship_type": 70,
        })
        assert 259000420 in writer._vessel_updates

        # Add a position to trigger flush via batch or manual
        await writer._flush()

        conn = writer._conn
        # execute should be called for the vessel upsert
        conn.execute.assert_called()
        # Vessel updates should be cleared
        assert len(writer._vessel_updates) == 0

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self, writer):
        """After flush, both position buffer and vessel updates should be empty."""
        report = _make_position_report()
        await writer.add_position(report)
        await writer.add_vessel_update(211234567, {"ship_name": "AURORA"})

        await writer._flush()

        assert len(writer._position_buffer) == 0
        assert len(writer._vessel_updates) == 0

    @pytest.mark.asyncio
    async def test_empty_flush_is_noop(self, writer, redis_client):
        """Flushing an empty buffer should not call DB or Redis."""
        await writer._flush()

        conn = writer._conn
        conn.executemany.assert_not_called()
        conn.execute.assert_not_called()
        redis_client.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_flushes_remaining(self, redis_client):
        """stop() should flush remaining positions before closing pool."""
        w = BatchWriter(
            dsn="postgresql://test:test@localhost:5432/test",
            redis_client=redis_client,
            batch_size=1000,
            flush_interval=100.0,
        )
        pool, conn = _make_mock_pool()
        w._pool = pool

        report = _make_position_report()
        await w.add_position(report)
        assert len(w._position_buffer) == 1

        await w.stop()

        # Buffer should be flushed
        assert len(w._position_buffer) == 0
        conn.executemany.assert_called_once()
        pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_position_tuple_format(self, writer):
        """Verify the tuple stored in the buffer has the correct shape."""
        report = _make_position_report(
            timestamp=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            mmsi=636012345,
            longitude=-10.5,
            latitude=42.3,
            sog=8.0,
            cog=90.0,
            heading=88,
            nav_status=5,
            rot=-2.0,
        )
        await writer.add_position(report)
        assert len(writer._position_buffer) == 1
        t = writer._position_buffer[0]
        assert t[0] == datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert t[1] == 636012345
        assert t[2] == -10.5   # longitude (x)
        assert t[3] == 42.3    # latitude (y)
        assert t[4] == 8.0     # sog
        assert t[5] == 90.0    # cog
        assert t[6] == 88      # heading
        assert t[7] == 5       # nav_status
        assert t[8] == -2.0    # rot
        assert t[9] is None    # draught
