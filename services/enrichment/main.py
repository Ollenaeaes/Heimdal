"""Enrichment service entry point.

Creates the GFW client, Redis client, optional GISIS/MARS clients,
loads the sanctions index, and starts the enrichment loop.
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("enrichment.main")


async def main() -> None:
    """Initialize all clients and start the enrichment loop."""
    import redis.asyncio as aioredis

    from services.enrichment.gfw_client import GFWClient
    from services.enrichment.gisis_mars import GISISClient, MARSClient
    from services.enrichment.runner import DEFAULT_BATCH_SIZE, DEFAULT_INTERVAL_SECONDS, run_loop
    from services.enrichment.sanctions_matcher import SanctionsIndex
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

    # GFW client
    async with GFWClient() as gfw_client:
        await run_loop(
            gfw_client=gfw_client,
            session_factory=session_factory,
            redis_client=redis_client,
            sanctions_index=sanctions_index,
            gisis_client=gisis_client,
            mars_client=mars_client,
            aois=[],  # TODO: load AOIs from config
            batch_size=batch_size,
            interval_seconds=interval,
        )


if __name__ == "__main__":
    asyncio.run(main())
