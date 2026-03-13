"""Tests for structured JSON logging (shared.logging).

Covers all acceptance criteria for Story 1: Structured JSON Logging.
"""

from __future__ import annotations

import json
import logging
import os
from unittest import mock

import pytest

from shared.logging import JsonFormatter, setup_logging


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_log_output(logger_name: str = "test.logger", message: str = "hello world",
                        extra: dict | None = None, service: str = "scoring") -> str:
    """Set up JSON logging, emit one record, and return the formatted string."""
    formatter = JsonFormatter(service)
    record = logging.LogRecord(
        name=logger_name,
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    return formatter.format(record)


# ---------------------------------------------------------------------------
# AC: Log output is valid JSON with required fields
# ---------------------------------------------------------------------------

class TestJsonOutput:
    def test_output_is_valid_json(self):
        line = _capture_log_output()
        parsed = json.loads(line)  # raises on invalid JSON
        assert isinstance(parsed, dict)

    def test_required_fields_present(self):
        line = _capture_log_output(service="scoring", logger_name="scoring.engine",
                                    message="Engine started")
        doc = json.loads(line)
        assert "timestamp" in doc
        assert doc["level"] == "INFO"
        assert doc["service"] == "scoring"
        assert doc["logger"] == "scoring.engine"
        assert doc["message"] == "Engine started"

    def test_timestamp_is_iso8601(self):
        doc = json.loads(_capture_log_output())
        # ISO 8601 with timezone — should contain 'T' and '+' or end with 'Z'
        ts = doc["timestamp"]
        assert "T" in ts
        # datetime.fromisoformat should parse it without error
        from datetime import datetime
        datetime.fromisoformat(ts)

    def test_single_line_output(self):
        """Each log record must be a single line for docker compose logs."""
        line = _capture_log_output(message="multi\nline\nmessage")
        # json.dumps escapes newlines inside strings, so the outer string
        # should be one line.
        assert "\n" not in line


# ---------------------------------------------------------------------------
# AC: Extra context fields appear at top level
# ---------------------------------------------------------------------------

class TestExtraContext:
    def test_extra_fields_at_top_level(self):
        line = _capture_log_output(extra={"mmsi": 123456789, "rule_id": "dark-voyage"})
        doc = json.loads(line)
        assert doc["mmsi"] == 123456789
        assert doc["rule_id"] == "dark-voyage"

    def test_extra_fields_not_in_message(self):
        """Context should be separate keys, not embedded in the message string."""
        line = _capture_log_output(message="Vessel scored", extra={"mmsi": 123456789})
        doc = json.loads(line)
        assert doc["message"] == "Vessel scored"
        assert doc["mmsi"] == 123456789


# ---------------------------------------------------------------------------
# AC: LOG_FORMAT=text produces human-readable output
# ---------------------------------------------------------------------------

class TestTextFormat:
    def test_text_format_is_human_readable(self):
        """When LOG_FORMAT=text, output should NOT be JSON."""
        with mock.patch.dict(os.environ, {"LOG_FORMAT": "text", "LOG_LEVEL": "DEBUG"}):
            # Reset root logger
            root = logging.getLogger()
            root.handlers.clear()
            setup_logging("scoring")

            handler = root.handlers[0]
            record = logging.LogRecord(
                name="scoring.engine", level=logging.INFO,
                pathname="test.py", lineno=1,
                msg="Engine started", args=(), exc_info=None,
            )
            output = handler.format(record)

        # Should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(output)

        # Should contain the message in human-readable form
        assert "Engine started" in output
        assert "scoring.engine" in output

    def test_json_is_default_format(self):
        """With no LOG_FORMAT set, output should be JSON."""
        env = os.environ.copy()
        env.pop("LOG_FORMAT", None)
        with mock.patch.dict(os.environ, env, clear=True):
            root = logging.getLogger()
            root.handlers.clear()
            setup_logging("scoring")

            handler = root.handlers[0]
            assert isinstance(handler.formatter, JsonFormatter)


# ---------------------------------------------------------------------------
# AC: Existing log calls work without modification (backward compatible)
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_percent_style_formatting(self):
        """logger.info("got %d items", 5) should still work."""
        formatter = JsonFormatter("scoring")
        record = logging.LogRecord(
            name="scoring", level=logging.INFO,
            pathname="test.py", lineno=1,
            msg="got %d items", args=(5,), exc_info=None,
        )
        doc = json.loads(formatter.format(record))
        assert doc["message"] == "got 5 items"

    def test_simple_string_message(self):
        formatter = JsonFormatter("scoring")
        record = logging.LogRecord(
            name="scoring", level=logging.WARNING,
            pathname="test.py", lineno=1,
            msg="something happened", args=(), exc_info=None,
        )
        doc = json.loads(formatter.format(record))
        assert doc["message"] == "something happened"
        assert doc["level"] == "WARNING"

    def test_setup_logging_configures_root(self):
        """setup_logging should work and subsequent getLogger calls should use it."""
        with mock.patch.dict(os.environ, {"LOG_FORMAT": "json", "LOG_LEVEL": "DEBUG"}):
            root = logging.getLogger()
            root.handlers.clear()
            setup_logging("scoring")

            assert len(root.handlers) == 1
            assert isinstance(root.handlers[0].formatter, JsonFormatter)
            assert root.level == logging.DEBUG


# ---------------------------------------------------------------------------
# AC: Exception logging includes traceback in JSON exc_info field
# ---------------------------------------------------------------------------

class TestExceptionLogging:
    def test_exception_traceback_in_json(self):
        formatter = JsonFormatter("scoring")

        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="scoring", level=logging.ERROR,
            pathname="test.py", lineno=1,
            msg="Something failed", args=(), exc_info=exc_info,
        )
        doc = json.loads(formatter.format(record))
        assert "exc_info" in doc
        assert "ValueError: test error" in doc["exc_info"]
        assert "Traceback" in doc["exc_info"]

    def test_no_exc_info_when_no_exception(self):
        doc = json.loads(_capture_log_output())
        assert "exc_info" not in doc


# ---------------------------------------------------------------------------
# AC: LOG_LEVEL env var controls threshold
# ---------------------------------------------------------------------------

class TestLogLevel:
    def test_log_level_from_env(self):
        with mock.patch.dict(os.environ, {"LOG_LEVEL": "WARNING", "LOG_FORMAT": "json"}):
            root = logging.getLogger()
            root.handlers.clear()
            setup_logging("scoring")
            assert root.level == logging.WARNING

    def test_default_log_level_is_info(self):
        env = os.environ.copy()
        env.pop("LOG_LEVEL", None)
        with mock.patch.dict(os.environ, env, clear=True):
            root = logging.getLogger()
            root.handlers.clear()
            setup_logging("scoring")
            assert root.level == logging.INFO
