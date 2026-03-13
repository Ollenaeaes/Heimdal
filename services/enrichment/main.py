"""Enrichment service entry point.

Creates the GFW client, Redis client, optional GISIS/MARS clients,
loads the sanctions index, and starts the enrichment loop.

Also listens for tier-change events on ``heimdal:risk_changes`` and
triggers immediate enrichment for vessels transitioning to yellow or red.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.config import settings
from shared.logging import setup_logging

setup_logging("enrichment")
logger = logging.getLogger("enrichment.main")


def _load_aois() -> list[dict]:
    """Load AOIs from config.yaml's gfw.aois section.

    Falls back to an empty list if the section is missing.
    """
    yaml_path = Path("/app/config.yaml")
    if not yaml_path.is_file():
        # Try local development path
        yaml_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    if not yaml_path.is_file():
        logger.warning("config.yaml not found — no AOIs loaded")
        return []

    import yaml

    with open(yaml_path) as f:
        data = yaml.safe_load(f) or {}

    aois = data.get("gfw", {}).get("aois", [])
    if not aois:
        logger.warning("No AOIs configured in config.yaml gfw.aois section")
    return aois


async def listen_for_tier_changes(
    *,
    redis_client,
    gfw_client,
    session_factory,
    sanctions_index,
    gisis_client,
    mars_client,
    aois,
) -> None:
    """Listen for tier-change events and trigger immediate enrichment.

    Subscribes to ``heimdal:risk_changes`` and, when a vessel transitions to
    yellow or red, runs the full enrichment pipeline for that MMSI (subject
    to debounce).
    """
    from runner import enrich_single_vessel, should_trigger_enrichment

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("heimdal:risk_changes")
    logger.info("Listening for tier changes on heimdal:risk_changes")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            payload = json.loads(message["data"])
            mmsi = payload.get("mmsi")
            new_tier = payload.get("new_tier")
            old_tier = payload.get("old_tier")

            if not mmsi or not new_tier:
                continue

            should = await should_trigger_enrichment(redis_client, mmsi, new_tier)
            if not should:
                logger.debug(
                    "Skipping tier-change enrichment for MMSI %d (debounce or tier=%s)",
                    mmsi,
                    new_tier,
                )
                continue

            logger.info(
                "Tier change %s->%s for MMSI %d — triggering immediate enrichment",
                old_tier,
                new_tier,
                mmsi,
            )

            async with session_factory() as session:
                await enrich_single_vessel(
                    mmsi,
                    gfw_client=gfw_client,
                    session=session,
                    redis_client=redis_client,
                    sanctions_index=sanctions_index,
                    gisis_client=gisis_client,
                    mars_client=mars_client,
                    aois=aois,
                )
                await session.commit()
        except Exception:
            logger.exception("Error handling tier-change trigger")


async def main() -> None:
    """Initialize all clients and start the enrichment loop + tier-change listener."""
    import redis.asyncio as aioredis

    from gfw_client import GFWClient
    from gisis_mars import GISISClient, MARSClient
    from runner import DEFAULT_BATCH_SIZE, DEFAULT_INTERVAL_SECONDS, run_loop
    from sanctions_matcher import SanctionsIndex
    from shared.db.connection import get_session

    # Configuration
    interval = int(os.environ.get("ENRICHMENT_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS))
    batch_size = int(os.environ.get("ENRICHMENT_BATCH_SIZE", DEFAULT_BATCH_SIZE))
    gisis_enabled = os.environ.get("GISIS_ENABLED", "false").lower() == "true"
    mars_enabled = os.environ.get("MARS_ENABLED", "false").lower() == "true"

    # Redis
    redis_client = aioredis.from_url(settings.redis_url)

    # Sanctions index
    sanctions_index = SanctionsIndex()
    count = sanctions_index.load()
    if count > 0:
        logger.info("Sanctions index loaded with %d vessels", count)
    else:
        logger.warning("No sanctions data loaded — sanctions matching will be skipped")
        sanctions_index = None

    # Optional GISIS/MARS clients
    gisis_client = GISISClient(enabled=gisis_enabled) if gisis_enabled else None
    mars_client = MARSClient(enabled=mars_enabled) if mars_enabled else None

    if gisis_enabled:
        logger.info("GISIS lookups enabled")
    if mars_enabled:
        logger.info("MARS lookups enabled")

    # Session factory
    session_factory = get_session()

    # Load AOIs from config.yaml (gfw.aois section)
    aois = _load_aois()
    logger.info("Loaded %d AOIs for SAR detection queries", len(aois))

    # GFW client
    async with GFWClient() as gfw_client:
        await asyncio.gather(
            run_loop(
                gfw_client=gfw_client,
                session_factory=session_factory,
                redis_client=redis_client,
                sanctions_index=sanctions_index,
                gisis_client=gisis_client,
                mars_client=mars_client,
                aois=aois,
                batch_size=batch_size,
                interval_seconds=interval,
            ),
            listen_for_tier_changes(
                redis_client=redis_client,
                gfw_client=gfw_client,
                session_factory=session_factory,
                sanctions_index=sanctions_index,
                gisis_client=gisis_client,
                mars_client=mars_client,
                aois=aois,
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
