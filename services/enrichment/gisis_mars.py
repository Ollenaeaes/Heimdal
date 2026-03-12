"""Optional GISIS and MARS lookups for vessel enrichment.

GISIS (IMO Global Integrated Shipping Information System) provides vessel
particulars by IMO number. MARS (ITU Maritime Mobile Access and Retrieval
System) provides call sign and flag by MMSI.

Both services are web interfaces without formal APIs, so these are stub/skeleton
implementations with proper interfaces and error handling. They can be fleshed
out with actual scraping logic later.

Default: disabled. When enabled, they attempt to fetch but gracefully handle
any failure — they must never block the enrichment pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

sys.path.insert(0, "/app")

logger = logging.getLogger("enrichment.gisis_mars")

# Rate limiting: minimum seconds between requests
GISIS_REQUEST_INTERVAL = 5.0
MARS_REQUEST_INTERVAL = 3.0


class GISISClient:
    """Stub client for IMO GISIS vessel particulars lookup.

    Queries gisis.imo.org for vessel data by IMO number.
    This is a skeleton implementation — actual scraping logic TBD.

    Rate limit: 5 seconds between requests.
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def _wait_for_rate_limit(self) -> None:
        """Enforce rate limit of one request per GISIS_REQUEST_INTERVAL seconds."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < GISIS_REQUEST_INTERVAL:
                await asyncio.sleep(GISIS_REQUEST_INTERVAL - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    async def lookup_vessel(self, imo: int) -> dict[str, Any] | None:
        """Look up vessel particulars from GISIS by IMO number.

        Args:
            imo: The vessel IMO number.

        Returns:
            Dict with vessel data (flag, owner, ship_name, call_sign, etc.)
            or None if not found / service unavailable.
        """
        if not self.enabled:
            logger.debug("GISIS lookup disabled, skipping IMO %d", imo)
            return None

        if not imo:
            return None

        try:
            await self._wait_for_rate_limit()

            # Stub: actual implementation would scrape gisis.imo.org
            # For now, log and return None
            logger.info(
                "GISIS lookup for IMO %d — stub implementation, no data returned",
                imo,
            )
            return None
        except Exception:
            logger.warning("GISIS lookup failed for IMO %d", imo, exc_info=True)
            return None


class MARSClient:
    """Stub client for ITU MARS (Maritime Mobile Access and Retrieval System).

    Queries ITU MARS for call sign and flag by MMSI.
    This is a skeleton implementation — actual scraping logic TBD.

    Rate limit: 3 seconds between requests.
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def _wait_for_rate_limit(self) -> None:
        """Enforce rate limit of one request per MARS_REQUEST_INTERVAL seconds."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < MARS_REQUEST_INTERVAL:
                await asyncio.sleep(MARS_REQUEST_INTERVAL - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    async def lookup_vessel(self, mmsi: int) -> dict[str, Any] | None:
        """Look up vessel call sign and flag from MARS by MMSI.

        Args:
            mmsi: The vessel MMSI number.

        Returns:
            Dict with 'call_sign' and 'flag' keys, or None if not
            found / service unavailable.
        """
        if not self.enabled:
            logger.debug("MARS lookup disabled, skipping MMSI %d", mmsi)
            return None

        if not mmsi:
            return None

        try:
            await self._wait_for_rate_limit()

            # Stub: actual implementation would scrape ITU MARS
            # For now, log and return None
            logger.info(
                "MARS lookup for MMSI %d — stub implementation, no data returned",
                mmsi,
            )
            return None
        except Exception:
            logger.warning("MARS lookup failed for MMSI %d", mmsi, exc_info=True)
            return None


def merge_gisis_data(
    profile_data: dict[str, Any],
    gisis_data: dict[str, Any],
) -> dict[str, Any]:
    """Merge GISIS data into a vessel profile, respecting GFW priority.

    GFW data takes priority over GISIS data. GISIS data only fills in
    fields that are currently None/empty in the profile.

    Args:
        profile_data: Existing vessel profile data (may contain GFW data).
        gisis_data: Data from GISIS lookup.

    Returns:
        Updated profile data dict.
    """
    # Fields where GISIS can contribute (GFW takes priority)
    gisis_fields = [
        "flag_country",
        "ship_name",
        "call_sign",
        "registered_owner",
        "operator",
        "gross_tonnage",
        "dwt",
        "build_year",
        "length",
        "width",
    ]

    result = dict(profile_data)
    for field in gisis_fields:
        if not result.get(field) and gisis_data.get(field):
            result[field] = gisis_data[field]

    return result


def merge_mars_data(
    profile_data: dict[str, Any],
    mars_data: dict[str, Any],
) -> dict[str, Any]:
    """Merge MARS data into a vessel profile, respecting GFW priority.

    GFW data takes priority over MARS data. MARS data only fills in
    fields that are currently None/empty in the profile.

    Args:
        profile_data: Existing vessel profile data (may contain GFW data).
        mars_data: Data from MARS lookup.

    Returns:
        Updated profile data dict.
    """
    # MARS provides call_sign and flag
    mars_fields = ["call_sign", "flag_country"]

    result = dict(profile_data)
    for field in mars_fields:
        if not result.get(field) and mars_data.get(field):
            result[field] = mars_data[field]

    return result
