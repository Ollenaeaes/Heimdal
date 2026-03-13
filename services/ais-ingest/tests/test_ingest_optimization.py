"""Tests for Story 4: AIS Ingest Pipeline Optimization.

Verifies orjson parsing performance, Redis pipeline batch dedup,
and correctness of the optimized ingest paths.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import fakeredis.aioredis

# Make the ais-ingest service importable
_ingest_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ingest_dir))
# Make shared importable
sys.path.insert(0, str(_ingest_dir.parent.parent))

from dedup import Deduplicator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def redis_client():
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def dedup(redis_client):
    """Create a Deduplicator with fake Redis."""
    return Deduplicator(redis_client)


# A realistic AIS position report message from aisstream.io
SAMPLE_AIS_MESSAGE = {
    "MessageType": "PositionReport",
    "MetaData": {
        "MMSI": 259000420,
        "time_utc": "2026-03-12 17:47:42.32216511 +0000 UTC",
        "ShipName": "NORDIC EXPLORER",
        "latitude": 68.12345,
        "longitude": 15.98765,
    },
    "Message": {
        "PositionReport": {
            "Latitude": 68.12345,
            "Longitude": 15.98765,
            "Sog": 12.4,
            "Cog": 245.3,
            "TrueHeading": 244,
            "RateOfTurn": 0.0,
            "NavigationalStatus": 0,
        }
    },
}


def _make_ais_messages(count: int) -> list[dict]:
    """Generate a list of realistic AIS messages for benchmarking."""
    messages = []
    for i in range(count):
        msg = {
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 200000000 + i,
                "time_utc": f"2026-03-12 17:47:{i % 60:02d}.{i:06d} +0000 UTC",
                "ShipName": f"VESSEL_{i:04d}",
                "latitude": 60.0 + (i % 1000) * 0.01,
                "longitude": 10.0 + (i % 1000) * 0.01,
            },
            "Message": {
                "PositionReport": {
                    "Latitude": 60.0 + (i % 1000) * 0.01,
                    "Longitude": 10.0 + (i % 1000) * 0.01,
                    "Sog": 5.0 + (i % 20),
                    "Cog": (i * 17) % 360,
                    "TrueHeading": (i * 17) % 360,
                    "RateOfTurn": 0.0,
                    "NavigationalStatus": 0,
                }
            },
        }
        messages.append(msg)
    return messages


# ---------------------------------------------------------------------------
# Test: orjson is available and faster than stdlib json
# ---------------------------------------------------------------------------


class TestOrjsonParsing:
    """Tests for orjson parsing performance and correctness."""

    def test_orjson_is_importable(self):
        """orjson should be installed and importable."""
        import orjson

        assert hasattr(orjson, "loads")
        assert hasattr(orjson, "dumps")

    def test_orjson_parsing_faster_than_json(self):
        """orjson.loads should be measurably faster than json.loads for AIS messages."""
        import orjson

        messages = _make_ais_messages(5000)
        # Pre-serialize to JSON strings
        json_strings = [json.dumps(m) for m in messages]

        # Benchmark stdlib json
        start = time.perf_counter()
        for s in json_strings:
            json.loads(s)
        json_elapsed = time.perf_counter() - start

        # Benchmark orjson
        start = time.perf_counter()
        for s in json_strings:
            orjson.loads(s)
        orjson_elapsed = time.perf_counter() - start

        # orjson should be at least 1.5x faster (typically 3-5x)
        speedup = json_elapsed / orjson_elapsed
        assert speedup > 1.5, (
            f"orjson speedup was only {speedup:.2f}x "
            f"(json: {json_elapsed:.4f}s, orjson: {orjson_elapsed:.4f}s)"
        )

    def test_orjson_dumps_faster_than_json(self):
        """orjson.dumps should be measurably faster than json.dumps for AIS data."""
        import orjson

        messages = _make_ais_messages(5000)

        # Benchmark stdlib json.dumps
        start = time.perf_counter()
        for m in messages:
            json.dumps(m)
        json_elapsed = time.perf_counter() - start

        # Benchmark orjson.dumps
        start = time.perf_counter()
        for m in messages:
            orjson.dumps(m)
        orjson_elapsed = time.perf_counter() - start

        speedup = json_elapsed / orjson_elapsed
        assert speedup > 1.5, (
            f"orjson dumps speedup was only {speedup:.2f}x "
            f"(json: {json_elapsed:.4f}s, orjson: {orjson_elapsed:.4f}s)"
        )

    def test_orjson_handles_ais_messages(self):
        """orjson produces identical results to json for AIS message parsing."""
        import orjson

        json_str = json.dumps(SAMPLE_AIS_MESSAGE)

        stdlib_result = json.loads(json_str)
        orjson_result = orjson.loads(json_str)

        assert stdlib_result == orjson_result

    def test_orjson_handles_ais_message_bytes(self):
        """orjson can parse bytes directly (common for WebSocket data)."""
        import orjson

        json_bytes = json.dumps(SAMPLE_AIS_MESSAGE).encode("utf-8")
        result = orjson.loads(json_bytes)

        assert result["MessageType"] == "PositionReport"
        assert result["MetaData"]["MMSI"] == 259000420

    def test_orjson_dumps_returns_bytes(self):
        """orjson.dumps returns bytes, and .decode() gives valid JSON string."""
        import orjson

        raw = orjson.dumps(SAMPLE_AIS_MESSAGE)
        assert isinstance(raw, bytes)

        decoded = raw.decode("utf-8")
        parsed_back = json.loads(decoded)
        assert parsed_back["MessageType"] == "PositionReport"

    def test_orjson_roundtrip_with_nested_data(self):
        """orjson handles the nested structure of AIS messages correctly."""
        import orjson

        dumped = orjson.dumps(SAMPLE_AIS_MESSAGE)
        loaded = orjson.loads(dumped)

        assert loaded["Message"]["PositionReport"]["Latitude"] == 68.12345
        assert loaded["Message"]["PositionReport"]["Sog"] == 12.4


# ---------------------------------------------------------------------------
# Test: Redis pipeline batch dedup
# ---------------------------------------------------------------------------


class TestBatchDedup:
    """Tests for the batch pipeline dedup method."""

    @pytest.mark.asyncio
    async def test_batch_dedup_empty_list(self, dedup):
        """Empty input returns empty output."""
        result = await dedup.filter_duplicates_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_batch_dedup_all_new(self, dedup):
        """All unique messages should be marked as new (True)."""
        messages = [
            (200000000 + i, datetime(2024, 1, 15, 10, 0, i, tzinfo=timezone.utc))
            for i in range(10)
        ]
        results = await dedup.filter_duplicates_batch(messages)
        assert all(r is True for r in results)
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_batch_dedup_with_duplicates(self, dedup):
        """Pre-existing keys should be detected as duplicates."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        mmsi = 259000420

        # First, insert one via the single-message method
        is_dup = await dedup.is_duplicate(mmsi, ts)
        assert is_dup is False

        # Now batch-check: same (mmsi, ts) + a new one
        messages = [
            (mmsi, ts),  # should be duplicate
            (211234567, ts),  # should be new
        ]
        results = await dedup.filter_duplicates_batch(messages)
        assert results[0] is False  # duplicate
        assert results[1] is True  # new

    @pytest.mark.asyncio
    async def test_batch_dedup_duplicates_within_batch(self, dedup):
        """Duplicate entries within the same batch: first wins, rest are dupes."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        mmsi = 259000420

        messages = [
            (mmsi, ts),
            (mmsi, ts),  # same as first
            (mmsi, ts),  # same as first
        ]
        results = await dedup.filter_duplicates_batch(messages)
        assert results[0] is True  # first is new
        assert results[1] is False  # duplicate within batch
        assert results[2] is False  # duplicate within batch

    @pytest.mark.asyncio
    async def test_batch_dedup_large_batch(self, dedup):
        """1000 unique messages processed in a single batch."""
        messages = [
            (200000000 + i, datetime(2024, 1, 15, 10, i // 60, i % 60, tzinfo=timezone.utc))
            for i in range(1000)
        ]
        results = await dedup.filter_duplicates_batch(messages)
        assert len(results) == 1000
        assert all(r is True for r in results)

    @pytest.mark.asyncio
    async def test_batch_dedup_microseconds_stripped(self, dedup):
        """Timestamps differing only in microseconds should collide."""
        ts1 = datetime(2024, 1, 15, 10, 30, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 10, 30, 0, 500000, tzinfo=timezone.utc)

        messages = [(259000420, ts1), (259000420, ts2)]
        results = await dedup.filter_duplicates_batch(messages)
        assert results[0] is True  # first is new
        assert results[1] is False  # same second, duplicate

    @pytest.mark.asyncio
    async def test_batch_dedup_keys_have_ttl(self, dedup, redis_client):
        """Keys set by batch dedup should have TTL."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        await dedup.filter_duplicates_batch([(259000420, ts)])

        key = "heimdal:dedup:259000420:2024-01-15T10:30:00+00:00"
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= 10

    @pytest.mark.asyncio
    async def test_batch_dedup_consistent_with_single(self, dedup):
        """Batch dedup and single is_duplicate should use the same key format."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # Use batch to set keys
        await dedup.filter_duplicates_batch([(259000420, ts)])

        # Single check should see the key as duplicate
        is_dup = await dedup.is_duplicate(259000420, ts)
        assert is_dup is True


# ---------------------------------------------------------------------------
# Test: writer uses orjson for Redis publish
# ---------------------------------------------------------------------------


class TestWriterOrjson:
    """Tests that the writer module uses orjson for JSON serialization."""

    def test_writer_imports_orjson_based_dumps(self):
        """writer.py should define a _json_dumps that uses orjson when available."""
        from writer import _json_dumps

        result = _json_dumps({"mmsi": 259000420, "lat": 68.0})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["mmsi"] == 259000420

    def test_writer_json_dumps_handles_isoformat(self):
        """_json_dumps should handle standard Python types used in position events."""
        from writer import _json_dumps

        data = {
            "mmsi": 259000420,
            "lat": 68.12345,
            "lon": 15.98765,
            "sog": 12.4,
            "cog": 245.3,
            "heading": 244,
            "nav_status": 0,
            "timestamp": "2026-03-12T17:47:42+00:00",
            "risk_tier": "green",
            "risk_score": 0,
        }
        result = _json_dumps(data)
        parsed = json.loads(result)
        assert parsed["lat"] == 68.12345
        assert parsed["risk_tier"] == "green"


# ---------------------------------------------------------------------------
# Test: websocket uses orjson for parsing
# ---------------------------------------------------------------------------


class TestWebSocketOrjson:
    """Tests that websocket.py uses orjson for JSON parsing."""

    def test_websocket_imports_orjson_based_funcs(self):
        """websocket.py should define _json_loads and _json_dumps using orjson."""
        from websocket import _json_loads, _json_dumps

        msg_str = json.dumps(SAMPLE_AIS_MESSAGE)
        parsed = _json_loads(msg_str)
        assert parsed["MessageType"] == "PositionReport"

        dumped = _json_dumps({"APIKey": "test", "BoundingBoxes": [[[-180, -90], [180, 90]]]})
        assert isinstance(dumped, str)
        re_parsed = json.loads(dumped)
        assert re_parsed["APIKey"] == "test"
