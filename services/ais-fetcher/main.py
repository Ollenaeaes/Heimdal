"""AIS fetcher — lean always-on service that writes raw AIS data to JSONL files.

Connects to aisstream.io WebSocket and writes every received message to
gzipped JSONL files on disk.  No database, no Redis, no Pydantic parsing.
This is the lightest possible data collector.

Designed to run on the production server (Oracle free tier) 24/7, even when
the developer's laptop is off.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.config import settings
from shared.logging import setup_logging

from dedup import InMemoryDedup
from file_writer import RawFileWriter
from websocket import AISWebSocket

logger = logging.getLogger("ais-fetcher")


async def main():
    setup_logging("ais-fetcher")

    base_path = os.environ.get("RAW_STORAGE_PATH", settings.raw_storage.base_path)
    raw_writer = RawFileWriter(base_path=base_path)
    await raw_writer.start()

    dedup = InMemoryDedup()

    msg_count = {"total": 0, "written": 0, "deduped": 0}

    async def handle_message(raw: dict):
        msg_count["total"] += 1
        if msg_count["total"] % 10000 == 0:
            logger.info(
                "Messages: total=%d written=%d deduped=%d",
                msg_count["total"],
                msg_count["written"],
                msg_count["deduped"],
            )

        # Lightweight dedup: skip exact duplicates within the same hour
        mmsi = (raw.get("MetaData") or {}).get("MMSI")
        ts = (raw.get("MetaData") or {}).get("time_utc", "")
        if mmsi is not None and dedup.is_duplicate(mmsi, ts):
            msg_count["deduped"] += 1
            return

        try:
            await raw_writer.write_message(raw)
            msg_count["written"] += 1
        except Exception:
            logger.exception("Raw file write failed")

    ws = AISWebSocket(on_message=handle_message)

    try:
        await ws.start()
    except KeyboardInterrupt:
        pass
    finally:
        await ws.stop()
        await raw_writer.stop()


if __name__ == "__main__":
    asyncio.run(main())
