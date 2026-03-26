"""ADS-B API poller for adsb.lol.

Polls geographic regions at configurable intervals, returning
raw aircraft dicts from the adsb.lol v2 API.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger("adsb-ingest.poller")

BASE_URL = "https://api.adsb.lol"


@dataclass
class PollRegion:
    """A geographic region to poll."""
    name: str
    lat: float
    lon: float
    radius_nm: int  # nautical miles


# Regions of interest — covers Baltic, Norwegian Coast, North Sea
# Using overlapping circles to approximate bounding boxes from the spec
REGIONS: list[PollRegion] = [
    # Baltic Sea (53-60N, 12-30E) — 2 circles
    PollRegion("Baltic West", 57.0, 18.0, 200),
    PollRegion("Baltic East", 57.5, 25.0, 200),
    # Norwegian Coast (57-71N, 0-16E) — 2 circles
    PollRegion("Norway South", 62.0, 5.0, 250),
    PollRegion("Norway North", 68.0, 14.0, 200),
    # North Sea (53-62N, -4W-8E)
    PollRegion("North Sea", 57.5, 2.0, 250),
]

# Stagger interval between region polls (seconds)
STAGGER_INTERVAL = 2.0
# Full cycle interval (seconds) — time between starting poll cycles
POLL_CYCLE_INTERVAL = 10.0
# Backoff settings
MAX_BACKOFF = 120.0
INITIAL_BACKOFF = 5.0


class AdsbPoller:
    """Polls adsb.lol API for aircraft data across configured regions."""

    def __init__(self, regions: list[PollRegion] | None = None):
        self.regions = regions or REGIONS
        self._session: aiohttp.ClientSession | None = None
        self._backoff = 0.0
        self._running = False

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Accept": "application/json"},
        )
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None

    async def poll_region(self, region: PollRegion) -> list[dict]:
        """Poll a single region, returning aircraft dicts."""
        url = f"{BASE_URL}/v2/point/{region.lat}/{region.lon}/{region.radius_nm}"
        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    aircraft = data.get("ac", [])
                    self._backoff = 0.0  # reset on success
                    logger.debug(
                        "Polled %s: %d aircraft", region.name, len(aircraft)
                    )
                    return aircraft
                elif resp.status == 429:
                    self._backoff = min(
                        max(self._backoff * 2, INITIAL_BACKOFF), MAX_BACKOFF
                    )
                    logger.warning(
                        "Rate limited polling %s, backing off %.0fs",
                        region.name, self._backoff,
                    )
                    return []
                else:
                    logger.warning(
                        "Poll %s returned %d", region.name, resp.status
                    )
                    return []
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self._backoff = min(
                max(self._backoff * 2, INITIAL_BACKOFF), MAX_BACKOFF
            )
            logger.error("Poll %s failed: %s", region.name, e)
            return []

    async def poll_all(self) -> dict[str, dict]:
        """Poll all regions, deduplicate by ICAO hex, return merged dict.

        Returns dict keyed by lowercase ICAO hex -> aircraft dict.
        """
        if self._backoff > 0:
            logger.info("Backing off for %.0fs", self._backoff)
            await asyncio.sleep(self._backoff)

        all_aircraft: dict[str, dict] = {}
        for region in self.regions:
            aircraft = await self.poll_region(region)
            for ac in aircraft:
                hex_code = ac.get("hex", "").lower()
                if hex_code:
                    # Keep the most recent observation (lowest `seen` value)
                    existing = all_aircraft.get(hex_code)
                    if existing is None or ac.get("seen", 999) < existing.get("seen", 999):
                        all_aircraft[hex_code] = ac
            # Stagger between regions
            await asyncio.sleep(STAGGER_INTERVAL)

        return all_aircraft

    async def poll_military(self) -> list[dict]:
        """Poll the global military aircraft endpoint."""
        url = f"{BASE_URL}/v2/mil"
        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    aircraft = data.get("ac", [])
                    logger.debug("Polled /v2/mil: %d aircraft", len(aircraft))
                    return aircraft
                else:
                    logger.warning("Poll /v2/mil returned %d", resp.status)
                    return []
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("Poll /v2/mil failed: %s", e)
            return []
