"""Structured JSON logging for Heimdal services.

Provides a custom JSON formatter and a ``setup_logging()`` function that
configures the root logger.  Every log line becomes a single JSON object
with guaranteed fields: ``timestamp``, ``level``, ``service``, ``logger``,
``message``.  Extra keyword arguments passed via ``logging.info("msg",
extra={...})`` are promoted to top-level keys.

Set ``LOG_FORMAT=text`` (env var) to fall back to human-readable output
for local development.  ``LOG_LEVEL`` controls the threshold (default
``INFO``).
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    # Keys that belong to the standard LogRecord and should NOT be promoted
    # into the JSON output as extra context.
    _RESERVED = frozenset(
        (
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "process",
            "processName",
            "message",
            "taskName",
        )
    )

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        # Ensure record.message is populated
        record.message = record.getMessage()

        doc: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.message,
        }

        # Promote any extra keys that aren't part of the standard LogRecord
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in self._RESERVED:
                continue
            doc[key] = value

        # Exception info
        if record.exc_info and record.exc_info[0] is not None:
            doc["exc_info"] = self._format_exception(record.exc_info)

        if record.stack_info:
            doc["stack_info"] = record.stack_info

        return json.dumps(doc, default=str)

    @staticmethod
    def _format_exception(exc_info: tuple) -> str:
        return "".join(traceback.format_exception(*exc_info))


def setup_logging(service_name: str) -> None:
    """Configure the root logger for *service_name*.

    Reads two environment variables:

    * ``LOG_FORMAT`` – ``"json"`` (default) or ``"text"`` for human-readable
      output during local development.
    * ``LOG_LEVEL`` – any standard Python log level name (default ``"INFO"``).
    """
    log_format = os.environ.get("LOG_FORMAT", "json").lower()
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove any existing handlers (e.g. from basicConfig)
    root.handlers.clear()

    handler = logging.StreamHandler()

    if log_format == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
    else:
        handler.setFormatter(JsonFormatter(service_name))

    root.addHandler(handler)
