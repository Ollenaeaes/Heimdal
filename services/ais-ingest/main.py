"""AIS ingest service entry point.

Connects to aisstream.io WebSocket, parses messages, deduplicates,
and writes positions/vessel profiles to the database in batches.
"""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

from shared.config import settings
from shared.models.ais_message import PositionReport, ShipStaticData

# These imports work inside the Docker container where the service code
# lives at /app/ and sys.path includes /app/.  For the same reason,
# we import without the services.ais_ingest prefix.
from parser import parse_message, parse_vessel_extras
from dedup import Deduplicator
from metrics import MetricsPublisher
from writer import BatchWriter
from websocket import AISWebSocket

logger = logging.getLogger("ais-ingest")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Initialize Redis
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    # Initialize components
    dedup = Deduplicator(redis)
    metrics = MetricsPublisher(redis)

    # Convert SQLAlchemy URL to asyncpg DSN
    dsn = settings.database_url.get_secret_value().replace("+asyncpg", "")
    writer = BatchWriter(
        dsn=dsn,
        redis_client=redis,
        batch_size=settings.ingest.batch_size,
        flush_interval=settings.ingest.flush_interval,
        metrics=metrics,
    )
    await writer.start()

    msg_count = {"total": 0, "parsed": 0, "written": 0}

    async def handle_message(raw: dict):
        msg_count["total"] += 1
        if msg_count["total"] % 1000 == 0:
            logger.info(
                "Messages: total=%d parsed=%d written=%d",
                msg_count["total"], msg_count["parsed"], msg_count["written"],
            )

        result = parse_message(raw)
        if result is None:
            return
        msg_count["parsed"] += 1

        if isinstance(result, ShipStaticData):
            extras = parse_vessel_extras(raw)
            extras["mmsi"] = result.mmsi
            if result.imo:
                extras["imo"] = result.imo
            if result.ship_name:
                extras["ship_name"] = result.ship_name
            if result.ship_type is not None:
                extras["ship_type"] = result.ship_type
            await writer.add_vessel_update(result.mmsi, extras)
            msg_count["written"] += 1

        elif isinstance(result, PositionReport):
            if await dedup.is_duplicate(result.mmsi, result.timestamp):
                return
            await writer.add_position(result)
            msg_count["written"] += 1

    ws = AISWebSocket(on_message=handle_message)

    try:
        await ws.start()
    except KeyboardInterrupt:
        pass
    finally:
        await ws.stop()
        await writer.stop()
        await redis.close()


if __name__ == "__main__":
    asyncio.run(main())
