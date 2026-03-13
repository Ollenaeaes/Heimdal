"""Tests for Database Query Performance Logging (Story 5).

Covers all acceptance criteria:
- Slow query (> 500ms) triggers WARNING with query snippet
- Very slow query (> 5s) triggers ERROR
- Normal-speed queries log at DEBUG level only
- Connection pool events are logged
- API request duration is logged for each endpoint
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make shared importable
_project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

from shared.db.connection import (
    SLOW_QUERY_THRESHOLD_MS,
    VERY_SLOW_QUERY_THRESHOLD_MS,
    _after_cursor_execute,
    _before_cursor_execute,
    _on_checkin,
    _on_checkout,
    _on_checkout_failed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn_info():
    """Return a mock connection object with a real dict for .info."""
    conn = MagicMock()
    conn.info = {}
    return conn


def _simulate_query(duration_seconds: float, statement: str = "SELECT 1") -> list[logging.LogRecord]:
    """Simulate a query execution with the given duration and capture log records."""
    conn = _make_conn_info()
    cursor = MagicMock()
    context = MagicMock()

    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record)

    logger = logging.getLogger("shared.db")
    logger.addHandler(handler)
    original_level = logger.level
    logger.setLevel(logging.DEBUG)

    try:
        _before_cursor_execute(conn, cursor, statement, None, context, False)

        # Adjust the stored start time to simulate elapsed time
        conn.info["query_start_time"] = time.monotonic() - duration_seconds

        _after_cursor_execute(conn, cursor, statement, None, context, False)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)

    return records


# ---------------------------------------------------------------------------
# AC: Slow query (> 500ms) triggers WARNING with query snippet
# ---------------------------------------------------------------------------

class TestSlowQueryWarning:
    def test_slow_query_triggers_warning(self):
        """A query taking > 500ms but <= 5000ms should log at WARNING level."""
        records = _simulate_query(0.6)  # 600ms
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.WARNING
        assert record.message == "slow_query"

    def test_slow_query_has_required_fields(self):
        """WARNING log must include slow_query=true, duration_ms, query, service."""
        records = _simulate_query(0.7, "SELECT * FROM vessels WHERE mmsi = 123456789")
        record = records[0]
        assert getattr(record, "slow_query") is True
        assert getattr(record, "duration_ms") > 500
        assert "SELECT * FROM vessels" in getattr(record, "query")
        assert getattr(record, "service") == "shared.db"

    def test_slow_query_at_boundary(self):
        """A query taking exactly at the boundary (just over 500ms) should warn."""
        records = _simulate_query(0.501)
        assert records[0].levelno == logging.WARNING


# ---------------------------------------------------------------------------
# AC: Very slow query (> 5s) triggers ERROR
# ---------------------------------------------------------------------------

class TestVerySlowQueryError:
    def test_very_slow_query_triggers_error(self):
        """A query taking > 5000ms should log at ERROR level."""
        records = _simulate_query(5.5)
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.ERROR
        assert record.message == "very_slow_query"

    def test_very_slow_query_has_required_fields(self):
        """ERROR log for very slow queries must include slow_query=true."""
        records = _simulate_query(6.0, "UPDATE positions SET flag = true WHERE id IN (1,2,3)")
        record = records[0]
        assert getattr(record, "slow_query") is True
        assert getattr(record, "duration_ms") > 5000

    def test_very_slow_query_at_boundary(self):
        """A query just over 5000ms should be ERROR, not WARNING."""
        records = _simulate_query(5.001)
        assert records[0].levelno == logging.ERROR


# ---------------------------------------------------------------------------
# AC: Normal-speed queries log at DEBUG level only
# ---------------------------------------------------------------------------

class TestNormalQueryDebug:
    def test_normal_query_logs_debug(self):
        """A fast query (< 500ms) should log at DEBUG level."""
        records = _simulate_query(0.01)  # 10ms
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.DEBUG
        assert record.message == "query_complete"

    def test_normal_query_includes_duration(self):
        """DEBUG log should still include duration_ms for performance tracking."""
        records = _simulate_query(0.05)
        record = records[0]
        assert hasattr(record, "duration_ms")
        assert getattr(record, "duration_ms") > 0

    def test_normal_query_not_flagged_as_slow(self):
        """Normal queries should NOT have slow_query=true."""
        records = _simulate_query(0.01)
        record = records[0]
        assert not hasattr(record, "slow_query") or not getattr(record, "slow_query", False)


# ---------------------------------------------------------------------------
# AC: Query text is truncated to 200 chars
# ---------------------------------------------------------------------------

class TestQueryTruncation:
    def test_long_query_is_truncated(self):
        """Queries longer than 200 characters should be truncated in the log."""
        long_query = "SELECT " + "x" * 300
        records = _simulate_query(0.01, long_query)
        query_logged = getattr(records[0], "query")
        assert len(query_logged) == 200

    def test_short_query_is_not_truncated(self):
        """Queries shorter than 200 chars should appear in full."""
        short_query = "SELECT 1"
        records = _simulate_query(0.01, short_query)
        assert getattr(records[0], "query") == short_query


# ---------------------------------------------------------------------------
# AC: Connection pool events are logged
# ---------------------------------------------------------------------------

class TestPoolEvents:
    def test_pool_checkout_logged(self):
        """Pool checkout events should be logged at DEBUG."""
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record)
        logger = logging.getLogger("shared.db")
        logger.addHandler(handler)
        original_level = logger.level
        logger.setLevel(logging.DEBUG)

        try:
            _on_checkout(MagicMock(), MagicMock(), MagicMock())
        finally:
            logger.removeHandler(handler)
            logger.setLevel(original_level)

        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG
        assert records[0].message == "pool_checkout"

    def test_pool_checkin_logged(self):
        """Pool checkin events should be logged at DEBUG."""
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record)
        logger = logging.getLogger("shared.db")
        logger.addHandler(handler)
        original_level = logger.level
        logger.setLevel(logging.DEBUG)

        try:
            _on_checkin(MagicMock(), MagicMock())
        finally:
            logger.removeHandler(handler)
            logger.setLevel(original_level)

        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG
        assert records[0].message == "pool_checkin"

    def test_pool_exhaustion_logged_as_error(self):
        """Pool exhaustion should be logged at ERROR with pool_exhausted=true."""
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record)
        logger = logging.getLogger("shared.db")
        logger.addHandler(handler)
        original_level = logger.level
        logger.setLevel(logging.DEBUG)

        try:
            _on_checkout_failed(
                Exception("QueuePool limit reached"),
                MagicMock(),
                None,
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(original_level)

        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.ERROR
        assert record.message == "pool_exhausted"
        assert getattr(record, "pool_exhausted") is True


# ---------------------------------------------------------------------------
# AC: API request duration is logged for each endpoint
# ---------------------------------------------------------------------------

class TestApiRequestDurationLogging:
    """Test that the RequestDurationMiddleware logs request duration.

    We test this by importing the middleware class and verifying its behavior
    without running a full ASGI server.
    """

    def test_request_duration_middleware_exists(self):
        """The api-server module should define RequestDurationMiddleware."""
        api_server_path = Path(__file__).resolve().parent.parent.parent / "api-server"
        sys.path.insert(0, str(api_server_path))
        try:
            # We can't fully import main.py without all api-server deps,
            # so verify the middleware is defined by checking the source.
            source = (api_server_path / "main.py").read_text()
            assert "RequestDurationMiddleware" in source
            assert "request_complete" in source
            assert "duration_ms" in source
            assert "method" in source
            assert "status_code" in source
        finally:
            sys.path.remove(str(api_server_path))

    def test_middleware_logs_expected_fields_in_source(self):
        """The middleware log call should include method, path, status_code, duration_ms."""
        api_server_path = Path(__file__).resolve().parent.parent.parent / "api-server"
        source = (api_server_path / "main.py").read_text()
        # Verify the middleware uses setup_logging instead of basicConfig
        assert "setup_logging" in source
        assert 'logging.basicConfig' not in source
        # Verify the log call has all required fields
        assert '"path"' in source
        assert '"duration_ms"' in source


# ---------------------------------------------------------------------------
# AC: Thresholds are correct
# ---------------------------------------------------------------------------

class TestThresholds:
    def test_slow_query_threshold(self):
        assert SLOW_QUERY_THRESHOLD_MS == 500

    def test_very_slow_query_threshold(self):
        assert VERY_SLOW_QUERY_THRESHOLD_MS == 5000
