"""Raw AIS message writer to gzipped JSONL files.

Appends raw aisstream.io JSON messages to hourly-rotated gzipped JSONL files.
Each line is the exact raw message plus a _received_at timestamp — zero
transformation.  This serves as the durable source of truth for all AIS data,
independent of the database.

Directory layout:
    {base_path}/ais/{YYYY}/{MM}/{DD}/{type}_{YYYY}-{MM}-{DD}T{HH}.jsonl.gz
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    import orjson

    def _json_dumps_bytes(obj: dict) -> bytes:
        return orjson.dumps(obj)

except ImportError:
    import json

    def _json_dumps_bytes(obj: dict) -> bytes:
        return json.dumps(obj, separators=(",", ":")).encode("utf-8")

logger = logging.getLogger("ais-ingest")


class RawFileWriter:
    """Append raw AIS messages to hourly-rotated gzipped JSONL files."""

    def __init__(self, base_path: str = "/data/raw"):
        self.base_path = Path(base_path)
        self._current_hour: str | None = None
        self._handles: dict[str, gzip.GzipFile] = {}
        self._lock = asyncio.Lock()
        self._write_count = 0

    async def start(self):
        """Ensure base directory exists."""
        meta_dir = self.base_path / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        logger.info("RawFileWriter started, base_path=%s", self.base_path)

    async def stop(self):
        """Close all open file handles."""
        async with self._lock:
            for handle in self._handles.values():
                handle.close()
            self._handles.clear()
        logger.info(
            "RawFileWriter stopped, wrote %d messages total", self._write_count
        )

    async def write_message(self, raw: dict):
        """Write a raw AIS message to the appropriate JSONL.gz file.

        Determines message type from MessageType field and routes to
        the correct file.  Adds _received_at timestamp.
        """
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%dT%H")

        msg_type = raw.get("MessageType", "unknown")
        if msg_type == "PositionReport":
            file_type = "positions"
        elif msg_type == "ShipStaticData":
            file_type = "static"
        else:
            file_type = "other"

        # Add received timestamp
        raw_with_ts = dict(raw)
        raw_with_ts["_received_at"] = now.isoformat()

        line = _json_dumps_bytes(raw_with_ts) + b"\n"

        async with self._lock:
            await self._rotate_if_needed(hour_key)
            handle = self._get_or_create_handle(file_type, hour_key, now)
            handle.write(line)
            self._write_count += 1

            # Flush periodically to avoid data loss
            if self._write_count % 1000 == 0:
                handle.flush()

    def _get_or_create_handle(
        self, file_type: str, hour_key: str, now: datetime
    ) -> gzip.GzipFile:
        """Get or create a gzip file handle for the given type and hour."""
        key = f"{file_type}_{hour_key}"
        if key not in self._handles:
            day_dir = (
                self.base_path
                / "ais"
                / now.strftime("%Y")
                / now.strftime("%m")
                / now.strftime("%d")
            )
            day_dir.mkdir(parents=True, exist_ok=True)

            filepath = day_dir / f"{file_type}_{hour_key}.jsonl.gz"
            # Open in append mode so restarts don't overwrite
            self._handles[key] = gzip.open(filepath, "ab", compresslevel=6)
            logger.info("Opened raw file: %s", filepath)

        return self._handles[key]

    async def _rotate_if_needed(self, hour_key: str):
        """Close handles from previous hours when the hour changes."""
        if self._current_hour is not None and hour_key != self._current_hour:
            for k in list(self._handles.keys()):
                if not k.endswith(hour_key):
                    self._handles[k].close()
                    del self._handles[k]
                    logger.info("Rotated and closed file for key: %s", k)
        self._current_hour = hour_key
