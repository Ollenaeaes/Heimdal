"""Tests for API Call Duration Tracking (Story 2: logging-observability).

Covers all acceptance criteria:
- GFW API call logs include duration_ms and status_code
- Slow API call (> 5s) triggers WARNING log with slow_api_call=true
- Very slow API call (> 30s) triggers ERROR log
- Enrichment cycle summary includes correct total_duration and call_count
- Retry attempts are logged with attempt number and reason
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make project root importable
_project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "services" / "enrichment"))

import httpx

from services.enrichment.gfw_client import GFWClient, GFWAPIError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class LogCapture(logging.Handler):
    """Captures log records for inspection in tests."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord):
        self.records.append(record)

    def clear(self):
        self.records.clear()

    def find(self, **kwargs) -> list[logging.LogRecord]:
        """Find records matching all given attribute filters."""
        result = []
        for r in self.records:
            match = True
            for k, v in kwargs.items():
                # Check both record attributes and extra dict
                record_val = getattr(r, k, None)
                if record_val is None:
                    match = False
                    break
                if record_val != v:
                    match = False
                    break
            if match:
                result.append(r)
        return result


def _make_response(status_code: int = 200, json_data: dict | None = None,
                   headers: dict | None = None) -> httpx.Response:
    """Create a mock httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data or {},
        headers=headers or {},
        request=httpx.Request("GET", "https://test.example.com/test"),
    )
    return resp


@pytest.fixture
def log_capture():
    """Install a log capture handler on the gfw_client logger."""
    logger = logging.getLogger("enrichment.gfw_client")
    capture = LogCapture()
    capture.setLevel(logging.DEBUG)
    logger.addHandler(capture)
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    yield capture
    logger.removeHandler(capture)
    logger.setLevel(original_level)


@pytest.fixture
def runner_log_capture():
    """Install a log capture handler on the runner logger."""
    logger = logging.getLogger("enrichment.runner")
    capture = LogCapture()
    capture.setLevel(logging.DEBUG)
    logger.addHandler(capture)
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    yield capture
    logger.removeHandler(capture)
    logger.setLevel(original_level)


@pytest.fixture
def gfw_client():
    """Create a GFWClient with mocked HTTP transport."""
    client = GFWClient.__new__(GFWClient)
    client._api_token = "test-token"
    client._base_url = "https://test.example.com"
    client._rate_limit = 100
    client._semaphore = asyncio.Semaphore(100)
    client._request_interval = 0.01
    client._last_request_time = 0.0
    client._rate_lock = asyncio.Lock()
    client._http = AsyncMock(spec=httpx.AsyncClient)
    client._call_count = 0
    client._total_call_duration_ms = 0.0
    client._retry_count = 0
    return client


# ---------------------------------------------------------------------------
# AC: GFW API call logs include duration_ms and status_code
# ---------------------------------------------------------------------------

class TestApiCallLogging:
    @pytest.mark.asyncio
    async def test_api_call_logs_include_duration_and_status(self, gfw_client, log_capture):
        """GIVEN a GFW API call WHEN it completes THEN log includes duration_ms, url, status_code, method."""
        response = _make_response(200, {"data": "ok"})
        gfw_client._http.request = AsyncMock(return_value=response)

        await gfw_client._request("GET", "/v3/events")

        # Find the debug-level log for the completed call
        matching = [r for r in log_capture.records
                    if hasattr(r, "duration_ms") and hasattr(r, "status_code")]
        assert len(matching) >= 1, "Expected at least one log record with duration_ms and status_code"

        record = matching[0]
        assert record.duration_ms >= 0
        assert record.status_code == 200
        assert record.url == "/v3/events"
        assert record.method == "GET"

    @pytest.mark.asyncio
    async def test_call_count_incremented(self, gfw_client, log_capture):
        """Each API call should increment the call counter."""
        response = _make_response(200, {"data": "ok"})
        gfw_client._http.request = AsyncMock(return_value=response)

        assert gfw_client._call_count == 0
        await gfw_client._request("GET", "/v3/events")
        assert gfw_client._call_count == 1
        await gfw_client._request("POST", "/v3/vessels")
        assert gfw_client._call_count == 2

    @pytest.mark.asyncio
    async def test_total_duration_accumulated(self, gfw_client, log_capture):
        """Total call duration should accumulate across calls."""
        response = _make_response(200, {"data": "ok"})
        gfw_client._http.request = AsyncMock(return_value=response)

        await gfw_client._request("GET", "/v3/events")
        await gfw_client._request("GET", "/v3/events")

        assert gfw_client._total_call_duration_ms > 0


# ---------------------------------------------------------------------------
# AC: Slow API call (> 5s) triggers WARNING log with slow_api_call=true
# ---------------------------------------------------------------------------

class TestSlowCallWarning:
    @pytest.mark.asyncio
    async def test_slow_call_triggers_warning(self, gfw_client, log_capture):
        """GIVEN a GFW API call takes > 5 seconds WHEN it completes THEN WARNING with slow_api_call=true."""
        response = _make_response(200, {"data": "ok"})

        async def slow_request(*args, **kwargs):
            # Simulate slow call by manipulating time
            return response

        gfw_client._http.request = AsyncMock(side_effect=slow_request)

        # Monkey-patch time.monotonic to simulate a 6-second call
        real_monotonic = time.monotonic
        call_count = [0]

        def fake_monotonic():
            call_count[0] += 1
            base = real_monotonic()
            # First call is the start, second call is the end
            # We need to return values that differ by 6 seconds
            if call_count[0] % 2 == 0:
                return base + 6.0  # end time: 6 seconds later
            return base

        with patch("services.enrichment.gfw_client.time") as mock_time:
            mock_time.monotonic = fake_monotonic

            await gfw_client._request("GET", "/v3/events")

        warning_records = [r for r in log_capture.records
                          if r.levelno == logging.WARNING
                          and hasattr(r, "slow_api_call")]
        assert len(warning_records) >= 1, "Expected WARNING log with slow_api_call=true"
        assert warning_records[0].slow_api_call is True
        assert warning_records[0].duration_ms > 5000


# ---------------------------------------------------------------------------
# AC: Very slow API call (> 30s) triggers ERROR log
# ---------------------------------------------------------------------------

class TestVerySlowCallError:
    @pytest.mark.asyncio
    async def test_very_slow_call_triggers_error(self, gfw_client, log_capture):
        """GIVEN a GFW API call takes > 30 seconds WHEN it completes THEN ERROR log."""
        response = _make_response(200, {"data": "ok"})
        gfw_client._http.request = AsyncMock(return_value=response)

        real_monotonic = time.monotonic
        call_count = [0]

        def fake_monotonic():
            call_count[0] += 1
            base = real_monotonic()
            if call_count[0] % 2 == 0:
                return base + 31.0  # 31 seconds later
            return base

        with patch("services.enrichment.gfw_client.time") as mock_time:
            mock_time.monotonic = fake_monotonic

            await gfw_client._request("GET", "/v3/events")

        error_records = [r for r in log_capture.records
                         if r.levelno == logging.ERROR]
        assert len(error_records) >= 1, "Expected ERROR log for >30s call"
        assert error_records[0].duration_ms > 30000


# ---------------------------------------------------------------------------
# AC: Enrichment cycle summary includes correct total_duration and call_count
# ---------------------------------------------------------------------------

class TestCycleSummary:
    @pytest.mark.asyncio
    async def test_cycle_summary_includes_api_stats(self, runner_log_capture):
        """GIVEN the enrichment cycle runs WHEN it completes THEN summary log includes api stats."""
        from services.enrichment.runner import run_loop

        # Create a mock GFW client with stats
        mock_gfw_client = MagicMock()
        mock_gfw_client.reset_stats = MagicMock()
        mock_gfw_client.get_stats = MagicMock(return_value={
            "api_calls_made": 15,
            "total_call_duration_ms": 4500.0,
            "avg_call_duration_ms": 300.0,
            "rate_limit_retries": 2,
        })

        # Mock session factory
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        # Create an async context manager for session_factory
        class MockSessionCtx:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, *args):
                pass

        mock_session_factory = MagicMock(return_value=MockSessionCtx())

        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)

        # Patch run_cycle to return a result without doing real work
        cycle_result = {
            "total_vessels": 5,
            "gfw_events_count": 12,
            "sar_detections_count": 3,
        }

        loop_iterations = [0]

        async def patched_run_cycle(**kwargs):
            return cycle_result

        async def patched_sleep(seconds):
            loop_iterations[0] += 1
            if loop_iterations[0] >= 1:
                raise asyncio.CancelledError("Stop after one iteration")

        with patch("services.enrichment.runner.run_cycle", side_effect=patched_run_cycle), \
             patch("services.enrichment.runner.asyncio.sleep", side_effect=patched_sleep):
            try:
                await run_loop(
                    gfw_client=mock_gfw_client,
                    session_factory=mock_session_factory,
                    redis_client=mock_redis,
                    interval_seconds=10,
                )
            except asyncio.CancelledError:
                pass

        # Verify reset_stats was called before the cycle
        mock_gfw_client.reset_stats.assert_called_once()

        # Verify get_stats was called after the cycle
        mock_gfw_client.get_stats.assert_called_once()

        # Find the summary log
        summary_records = [r for r in runner_log_capture.records
                          if "Enrichment cycle complete" in r.getMessage()
                          and hasattr(r, "total_duration_ms")]
        assert len(summary_records) >= 1, "Expected cycle summary log with total_duration_ms"

        record = summary_records[0]
        assert record.total_duration_ms > 0
        assert record.api_calls_made == 15
        assert record.avg_call_duration_ms == 300.0
        assert record.rate_limit_retries == 2


# ---------------------------------------------------------------------------
# AC: Retry attempts are logged with attempt number and reason
# ---------------------------------------------------------------------------

class TestRetryLogging:
    @pytest.mark.asyncio
    async def test_retry_logged_with_attempt_and_reason(self, gfw_client, log_capture):
        """GIVEN the GFW client makes a retry WHEN the retry completes THEN log includes retry_attempt and retry_reason."""
        # First call returns 429 (retryable), second call returns 200
        response_429 = _make_response(429, {"error": "rate limited"})
        response_200 = _make_response(200, {"data": "ok"})
        gfw_client._http.request = AsyncMock(side_effect=[response_429, response_200])

        # Patch sleep to avoid waiting
        with patch("services.enrichment.gfw_client.asyncio.sleep", new_callable=AsyncMock):
            await gfw_client._request("GET", "/v3/events")

        # Find retry warning log
        retry_records = [r for r in log_capture.records
                         if hasattr(r, "retry_attempt") and hasattr(r, "retry_reason")]
        assert len(retry_records) >= 1, "Expected retry log with retry_attempt and retry_reason"

        record = retry_records[0]
        assert record.retry_attempt == 1
        assert "429" in record.retry_reason
        assert hasattr(record, "duration_ms")

    @pytest.mark.asyncio
    async def test_retry_count_tracked_in_stats(self, gfw_client, log_capture):
        """Retry attempts should be counted in client stats."""
        response_429 = _make_response(429, {"error": "rate limited"})
        response_200 = _make_response(200, {"data": "ok"})
        gfw_client._http.request = AsyncMock(side_effect=[response_429, response_200])

        with patch("services.enrichment.gfw_client.asyncio.sleep", new_callable=AsyncMock):
            await gfw_client._request("GET", "/v3/events")

        stats = gfw_client.get_stats()
        assert stats["rate_limit_retries"] == 1
        assert stats["api_calls_made"] == 2  # 429 attempt + 200 success

    @pytest.mark.asyncio
    async def test_connection_error_retry_logged(self, gfw_client, log_capture):
        """Connection errors should also log retry_attempt and retry_reason."""
        response_200 = _make_response(200, {"data": "ok"})
        gfw_client._http.request = AsyncMock(
            side_effect=[httpx.ConnectError("Connection refused"), response_200]
        )

        with patch("services.enrichment.gfw_client.asyncio.sleep", new_callable=AsyncMock):
            await gfw_client._request("GET", "/v3/events")

        retry_records = [r for r in log_capture.records
                         if hasattr(r, "retry_attempt")]
        assert len(retry_records) >= 1
        record = retry_records[0]
        assert record.retry_attempt == 1
        assert "ConnectError" in record.retry_reason


# ---------------------------------------------------------------------------
# Stats reset and get_stats
# ---------------------------------------------------------------------------

class TestStatsManagement:
    def test_reset_stats_clears_counters(self, gfw_client):
        """reset_stats should zero all counters."""
        gfw_client._call_count = 10
        gfw_client._total_call_duration_ms = 5000.0
        gfw_client._retry_count = 3

        gfw_client.reset_stats()

        assert gfw_client._call_count == 0
        assert gfw_client._total_call_duration_ms == 0.0
        assert gfw_client._retry_count == 0

    def test_get_stats_returns_correct_averages(self, gfw_client):
        """get_stats should compute correct averages."""
        gfw_client._call_count = 4
        gfw_client._total_call_duration_ms = 2000.0
        gfw_client._retry_count = 1

        stats = gfw_client.get_stats()
        assert stats["api_calls_made"] == 4
        assert stats["total_call_duration_ms"] == 2000.0
        assert stats["avg_call_duration_ms"] == 500.0
        assert stats["rate_limit_retries"] == 1

    def test_get_stats_zero_calls(self, gfw_client):
        """get_stats with zero calls should return zero averages."""
        stats = gfw_client.get_stats()
        assert stats["api_calls_made"] == 0
        assert stats["avg_call_duration_ms"] == 0.0

    def test_stats_initialized_on_construction(self):
        """Stats should be initialized to zero on new client."""
        with patch("services.enrichment.gfw_client.settings") as mock_settings:
            mock_settings.gfw_api_token = "test"
            mock_settings.gfw.base_url = "https://test.example.com"
            mock_settings.gfw.rate_limit_per_second = 10
            client = GFWClient(api_token="test", base_url="https://test.example.com")
        assert client._call_count == 0
        assert client._total_call_duration_ms == 0.0
        assert client._retry_count == 0
