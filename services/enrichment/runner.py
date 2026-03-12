"""Enrichment service runner — continuous loop that enriches vessel profiles.

Each cycle queries vessel_profiles for vessels that need enrichment (tracked via
Redis hash ``heimdal:enriched`` mapping MMSI → ISO timestamp). The enrichment
pipeline runs in order:

  1. GFW Events (behavioral events: AIS gaps, encounters, loitering, port visits)
  2. GFW SAR (satellite radar detections)
  3. GFW Vessel Identity (ownership, flag, dimensions)
  4. OpenSanctions (sanctions screening)
  5. GISIS (optional — IMO vessel particulars)
  6. MARS (optional — ITU call sign / flag)

After enrichment, the runner records the enrichment timestamp in Redis and
publishes an ``enrichment_complete`` event for downstream consumers (scoring).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, "/app")

from shared.config import settings

logger = logging.getLogger("enrichment.runner")

# Redis key for tracking enrichment timestamps per MMSI
ENRICHED_KEY = "heimdal:enriched"

# Redis channel for enrichment completion events
ENRICHMENT_CHANNEL = "heimdal:enrichment_complete"

# Default enrichment interval in seconds (6 hours)
DEFAULT_INTERVAL_SECONDS = 6 * 3600

# Default batch size for processing vessels
DEFAULT_BATCH_SIZE = 50


async def get_all_mmsis(session: Any) -> list[int]:
    """Query all MMSIs from vessel_profiles table.

    Args:
        session: An async SQLAlchemy session.

    Returns:
        List of MMSI integers.
    """
    from sqlalchemy import text

    result = await session.execute(text("SELECT mmsi FROM vessel_profiles"))
    return [row[0] for row in result.fetchall()]


async def get_unenriched_mmsis(
    redis_client: Any,
    all_mmsis: list[int],
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> list[int]:
    """Filter MMSIs to those needing enrichment.

    A vessel needs enrichment if it has never been enriched or was last
    enriched more than ``interval_seconds`` ago.

    Args:
        redis_client: An async Redis client.
        all_mmsis: All known vessel MMSIs.
        interval_seconds: Minimum seconds between enrichments.

    Returns:
        List of MMSIs that need enrichment.
    """
    if not all_mmsis:
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - interval_seconds
    unenriched = []

    for mmsi in all_mmsis:
        last_enriched = await redis_client.hget(ENRICHED_KEY, str(mmsi))
        if last_enriched is None:
            unenriched.append(mmsi)
        else:
            try:
                ts = float(last_enriched)
                if ts < cutoff:
                    unenriched.append(mmsi)
            except (ValueError, TypeError):
                unenriched.append(mmsi)

    return unenriched


async def mark_enriched(redis_client: Any, mmsis: list[int]) -> None:
    """Record enrichment timestamps for the given MMSIs in Redis.

    Args:
        redis_client: An async Redis client.
        mmsis: List of MMSIs that were just enriched.
    """
    now = str(datetime.now(timezone.utc).timestamp())
    for mmsi in mmsis:
        await redis_client.hset(ENRICHED_KEY, str(mmsi), now)


async def publish_enrichment_complete(
    redis_client: Any,
    mmsis: list[int],
    gfw_events_count: int,
    sar_detections_count: int,
) -> None:
    """Publish enrichment_complete event to Redis.

    Args:
        redis_client: An async Redis client.
        mmsis: List of enriched MMSIs.
        gfw_events_count: Total GFW events fetched in this cycle.
        sar_detections_count: Total SAR detections fetched in this cycle.
    """
    payload = json.dumps({
        "mmsis": mmsis,
        "gfw_events_count": gfw_events_count,
        "sar_detections_count": sar_detections_count,
    })
    await redis_client.publish(ENRICHMENT_CHANNEL, payload)
    logger.info(
        "Published enrichment_complete: %d vessels, %d events, %d SAR detections",
        len(mmsis),
        gfw_events_count,
        sar_detections_count,
    )


async def enrich_batch(
    mmsis: list[int],
    *,
    gfw_client: Any,
    session: Any,
    redis_client: Any,
    sanctions_index: Any = None,
    gisis_client: Any = None,
    mars_client: Any = None,
    aois: list[dict[str, Any]] | None = None,
    _events_fn: Any = None,
    _sar_fn: Any = None,
    _vessel_fn: Any = None,
) -> dict[str, int]:
    """Run the enrichment pipeline for a batch of vessels.

    Pipeline order:
      1. GFW Events
      2. GFW SAR
      3. GFW Vessel Identity
      4. OpenSanctions
      5. GISIS (optional)
      6. MARS (optional)

    Individual vessel failures don't stop the batch.

    Args:
        mmsis: List of MMSIs to enrich.
        gfw_client: An initialized GFWClient instance.
        session: An async SQLAlchemy session.
        redis_client: An async Redis client.
        sanctions_index: Loaded SanctionsIndex (or None to skip).
        gisis_client: GISISClient instance (or None to skip).
        mars_client: MARSClient instance (or None to skip).
        aois: List of AOI dicts for SAR fetching.
        _events_fn: Override for fetch_and_store_events (for testing).
        _sar_fn: Override for fetch_and_store_sar_detections (for testing).
        _vessel_fn: Override for fetch_and_update_vessel_profile (for testing).

    Returns:
        Dict with 'gfw_events_count' and 'sar_detections_count'.
    """
    if _events_fn is None:
        from services.enrichment.events_fetcher import fetch_and_store_events
        _events_fn = fetch_and_store_events
    if _sar_fn is None:
        from services.enrichment.sar_fetcher import fetch_and_store_sar_detections
        _sar_fn = fetch_and_store_sar_detections
    if _vessel_fn is None:
        from services.enrichment.vessel_fetcher import fetch_and_update_vessel_profile
        _vessel_fn = fetch_and_update_vessel_profile

    gfw_events_count = 0
    sar_detections_count = 0

    # Step 1: GFW Events
    try:
        count = await _events_fn(gfw_client, session, mmsis)
        gfw_events_count = count
        logger.info("GFW Events: fetched %d events for %d vessels", count, len(mmsis))
    except Exception:
        logger.exception("GFW Events pipeline failed for batch")

    # Step 2: GFW SAR
    if aois:
        try:
            count = await _sar_fn(gfw_client, session, aois)
            sar_detections_count = count
            logger.info("GFW SAR: fetched %d detections", count)
        except Exception:
            logger.exception("GFW SAR pipeline failed for batch")

    # Step 3: GFW Vessel Identity
    for mmsi in mmsis:
        try:
            await _vessel_fn(
                gfw_client, session, mmsi, redis_client=redis_client
            )
        except Exception:
            logger.warning("GFW Vessel Identity failed for MMSI %d", mmsi, exc_info=True)

    # Step 4: OpenSanctions
    if sanctions_index is not None:
        from services.enrichment.sanctions_matcher import match_vessel
        from shared.db.repositories import get_vessel_profile_by_mmsi, upsert_vessel_profile

        for mmsi in mmsis:
            try:
                profile = await get_vessel_profile_by_mmsi(session, mmsi)
                if profile:
                    result = match_vessel(
                        sanctions_index,
                        imo=profile.get("imo"),
                        mmsi=mmsi,
                        name=profile.get("ship_name"),
                    )
                    if result.get("matches"):
                        await upsert_vessel_profile(session, {
                            **{k: None for k in [
                                "imo", "ship_name", "ship_type", "ship_type_text",
                                "flag_country", "call_sign", "length", "width",
                                "draught", "destination", "eta", "last_position_time",
                                "last_lat", "last_lon", "risk_score", "risk_tier",
                                "pi_tier", "pi_details", "owner", "operator",
                                "insurer", "class_society", "build_year", "dwt",
                                "gross_tonnage", "group_owner", "registered_owner",
                                "technical_manager",
                            ]},
                            "mmsi": mmsi,
                            "sanctions_status": json.dumps(result),
                        })
            except Exception:
                logger.warning("Sanctions check failed for MMSI %d", mmsi, exc_info=True)

    # Step 5: GISIS (optional — failures don't block)
    if gisis_client is not None:
        from shared.db.repositories import get_vessel_profile_by_mmsi as _get_profile

        for mmsi in mmsis:
            try:
                profile = await _get_profile(session, mmsi)
                imo = profile.get("imo") if profile else None
                if imo:
                    gisis_data = await gisis_client.lookup_vessel(imo)
                    if gisis_data:
                        from services.enrichment.gisis_mars import merge_gisis_data

                        merge_gisis_data(profile or {}, gisis_data)
                        logger.debug("GISIS data merged for MMSI %d", mmsi)
            except Exception:
                logger.debug("GISIS lookup failed for MMSI %d (non-blocking)", mmsi)

    # Step 6: MARS (optional — failures don't block)
    if mars_client is not None:
        for mmsi in mmsis:
            try:
                mars_data = await mars_client.lookup_vessel(mmsi)
                if mars_data:
                    from services.enrichment.gisis_mars import merge_mars_data

                    logger.debug("MARS data merged for MMSI %d", mmsi)
            except Exception:
                logger.debug("MARS lookup failed for MMSI %d (non-blocking)", mmsi)

    return {
        "gfw_events_count": gfw_events_count,
        "sar_detections_count": sar_detections_count,
    }


async def run_cycle(
    *,
    gfw_client: Any,
    session: Any,
    redis_client: Any,
    sanctions_index: Any = None,
    gisis_client: Any = None,
    mars_client: Any = None,
    aois: list[dict[str, Any]] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    _events_fn: Any = None,
    _sar_fn: Any = None,
    _vessel_fn: Any = None,
) -> dict[str, Any]:
    """Run one enrichment cycle.

    Queries for unenriched vessels, processes them in batches, updates
    enrichment timestamps, and publishes completion event.

    Returns:
        Dict with 'total_vessels', 'gfw_events_count', 'sar_detections_count'.
    """
    # Get all MMSIs from the database
    all_mmsis = await get_all_mmsis(session)
    logger.info("Found %d total vessel profiles", len(all_mmsis))

    # Filter to those needing enrichment
    unenriched = await get_unenriched_mmsis(redis_client, all_mmsis, interval_seconds)
    logger.info("Found %d vessels needing enrichment", len(unenriched))

    if not unenriched:
        return {"total_vessels": 0, "gfw_events_count": 0, "sar_detections_count": 0}

    total_events = 0
    total_sar = 0
    all_enriched: list[int] = []

    # Process in batches
    for i in range(0, len(unenriched), batch_size):
        batch = unenriched[i : i + batch_size]
        logger.info(
            "Processing batch %d/%d (%d vessels)",
            i // batch_size + 1,
            (len(unenriched) + batch_size - 1) // batch_size,
            len(batch),
        )

        try:
            result = await enrich_batch(
                batch,
                gfw_client=gfw_client,
                session=session,
                redis_client=redis_client,
                sanctions_index=sanctions_index,
                gisis_client=gisis_client,
                mars_client=mars_client,
                aois=aois,
                _events_fn=_events_fn,
                _sar_fn=_sar_fn,
                _vessel_fn=_vessel_fn,
            )
            total_events += result["gfw_events_count"]
            total_sar += result["sar_detections_count"]
            all_enriched.extend(batch)
        except Exception:
            logger.exception("Batch %d failed", i // batch_size + 1)

    # Mark all enriched vessels
    if all_enriched:
        await mark_enriched(redis_client, all_enriched)
        await publish_enrichment_complete(
            redis_client, all_enriched, total_events, total_sar
        )

    return {
        "total_vessels": len(all_enriched),
        "gfw_events_count": total_events,
        "sar_detections_count": total_sar,
    }


async def run_loop(
    *,
    gfw_client: Any,
    session_factory: Any,
    redis_client: Any,
    sanctions_index: Any = None,
    gisis_client: Any = None,
    mars_client: Any = None,
    aois: list[dict[str, Any]] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Run the enrichment loop continuously.

    Each cycle runs run_cycle(), then sleeps for ``interval_seconds``.
    The loop runs forever until cancelled.

    Args:
        gfw_client: An initialized GFWClient instance.
        session_factory: An async_sessionmaker to create DB sessions.
        redis_client: An async Redis client.
        sanctions_index: Loaded SanctionsIndex (or None).
        gisis_client: GISISClient instance (or None).
        mars_client: MARSClient instance (or None).
        aois: List of AOI dicts for SAR fetching.
        batch_size: Number of vessels per batch.
        interval_seconds: Seconds to sleep between cycles.
    """
    logger.info(
        "Starting enrichment loop: interval=%ds, batch_size=%d",
        interval_seconds,
        batch_size,
    )

    while True:
        cycle_start = time.monotonic()

        try:
            async with session_factory() as session:
                result = await run_cycle(
                    gfw_client=gfw_client,
                    session=session,
                    redis_client=redis_client,
                    sanctions_index=sanctions_index,
                    gisis_client=gisis_client,
                    mars_client=mars_client,
                    aois=aois,
                    batch_size=batch_size,
                    interval_seconds=interval_seconds,
                )
                await session.commit()

            elapsed = time.monotonic() - cycle_start
            logger.info(
                "Enrichment cycle complete in %.1fs: %d vessels, %d events, %d SAR",
                elapsed,
                result["total_vessels"],
                result["gfw_events_count"],
                result["sar_detections_count"],
            )
        except Exception:
            logger.exception("Enrichment cycle failed")

        logger.info("Sleeping %ds until next cycle", interval_seconds)
        await asyncio.sleep(interval_seconds)
