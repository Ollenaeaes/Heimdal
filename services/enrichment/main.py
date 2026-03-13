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


async def main() -> None:
    """Initialize all clients and start the enrichment loop."""
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
        await run_loop(
            gfw_client=gfw_client,
            session_factory=session_factory,
            redis_client=redis_client,
            sanctions_index=sanctions_index,
            gisis_client=gisis_client,
            mars_client=mars_client,
            aois=aois,
            batch_size=batch_size,
            interval_seconds=interval,
        )


if __name__ == "__main__":
    asyncio.run(main())
