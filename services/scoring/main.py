"""Scoring service entry point.

Subscribes to Redis pub/sub channels and dispatches vessel scoring
to the :class:`ScoringEngine`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

# Allow importing shared from project root (works in Docker at /app/)
sys.path.insert(0, "/app")
# Also support running from the repo root during development
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
# Allow bare imports of sibling modules (rules, engine) when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent))

import redis.asyncio as aioredis

from shared.config import settings

from engine import ScoringEngine

logger = logging.getLogger("scoring")

POSITIONS_CHANNEL = "heimdal:positions"
ENRICHMENT_CHANNEL = "heimdal:enrichment_complete"


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()

    engine = ScoringEngine()
    logger.info(
        "Scoring engine started with %d rules (%d realtime, %d gfw)",
        len(engine.rules),
        len(engine.realtime_rules),
        len(engine.gfw_rules),
    )

    await pubsub.subscribe(POSITIONS_CHANNEL, ENRICHMENT_CHANNEL)
    logger.info(
        "Subscribed to channels: %s, %s", POSITIONS_CHANNEL, ENRICHMENT_CHANNEL
    )

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            channel = message["channel"]
            try:
                payload = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Invalid JSON on %s: %s", channel, message["data"])
                continue

            mmsis = payload.get("mmsis", [])
            if not mmsis:
                continue

            if channel == POSITIONS_CHANNEL:
                for mmsi in mmsis:
                    try:
                        await engine.evaluate_realtime(mmsi)
                    except Exception:
                        logger.exception(
                            "Realtime evaluation failed for MMSI %d", mmsi
                        )

            elif channel == ENRICHMENT_CHANNEL:
                for mmsi in mmsis:
                    try:
                        await engine.evaluate_gfw(mmsi)
                    except Exception:
                        logger.exception(
                            "GFW evaluation failed for MMSI %d", mmsi
                        )

    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe()
        await redis.close()
        logger.info("Scoring service stopped")


if __name__ == "__main__":
    asyncio.run(main())
