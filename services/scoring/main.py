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
from shared.logging import setup_logging

from debouncer import ScoringDebouncer
from engine import ScoringEngine

logger = logging.getLogger("scoring")

POSITIONS_CHANNEL = "heimdal:positions"
ENRICHMENT_CHANNEL = "heimdal:enrichment_complete"


async def main() -> None:
    setup_logging("scoring")

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()

    engine = ScoringEngine()
    logger.info(
        "Scoring engine started with %d rules (%d realtime, %d gfw)",
        len(engine.rules),
        len(engine.realtime_rules),
        len(engine.gfw_rules),
    )

    debounce_cfg = settings.scoring.debounce
    debouncer = ScoringDebouncer(
        engine,
        default_seconds=debounce_cfg.default_seconds,
        red_tier_seconds=debounce_cfg.red_tier_seconds,
        max_concurrent=debounce_cfg.max_concurrent,
    )
    logger.info(
        "Scoring debouncer initialised (default=%ss, red=%ss, max_concurrent=%d)",
        debounce_cfg.default_seconds,
        debounce_cfg.red_tier_seconds,
        debounce_cfg.max_concurrent,
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
            # Position channel sends single mmsi, enrichment sends mmsis list
            if not mmsis and "mmsi" in payload:
                mmsis = [payload["mmsi"]]
            if not mmsis:
                continue

            logger.info("Received %d MMSIs on %s", len(mmsis), channel)

            if channel == POSITIONS_CHANNEL:
                for mmsi in mmsis:
                    try:
                        await debouncer.on_position(mmsi)
                    except Exception:
                        logger.exception(
                            "Debounced position handling failed for MMSI %d", mmsi
                        )

            elif channel == ENRICHMENT_CHANNEL:
                for mmsi in mmsis:
                    logger.info("Scoring MMSI %d (enrichment)", mmsi)
                    try:
                        gfw_results = await engine.evaluate_gfw(mmsi)
                        fired = [r for r in gfw_results if r.fired]
                        logger.info("GFW eval for %d: %d rules fired", mmsi, len(fired))
                    except Exception:
                        logger.exception(
                            "GFW evaluation failed for MMSI %d", mmsi
                        )
                    try:
                        rt_results = await engine.evaluate_realtime(mmsi)
                        fired = [r for r in rt_results if r.fired]
                        logger.info("Realtime eval for %d: %d rules fired", mmsi, len(fired))
                    except Exception:
                        logger.exception(
                            "Realtime evaluation (post-enrichment) failed for MMSI %d", mmsi
                        )

    except asyncio.CancelledError:
        pass
    finally:
        debouncer.shutdown()
        await pubsub.unsubscribe()
        await redis.close()
        logger.info("Scoring service stopped")


if __name__ == "__main__":
    asyncio.run(main())
