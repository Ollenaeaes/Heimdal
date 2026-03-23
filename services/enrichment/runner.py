"""Enrichment service runner — continuous loop that enriches vessel profiles.

Each cycle queries vessel_profiles for vessels that need enrichment (tracked via
Redis hash ``heimdal:enriched`` mapping MMSI → ISO timestamp). The enrichment
pipeline runs in order:

  1. GFW SAR (satellite radar detections — cheap, ~12 calls)
  2. GFW Events (behavioral events: AIS gaps, encounters, loitering, port visits)
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

# Redis key for tracking tier-change triggered enrichment timestamps per MMSI
TRIGGER_KEY = "heimdal:enrichment_triggered"

# Tiers that trigger immediate enrichment on transition
TRIGGER_TIERS = {"yellow", "red", "blacklisted"}

# Default debounce window for tier-change triggered enrichment (hours)
DEFAULT_DEBOUNCE_HOURS = 1

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


async def get_vessels_needing_enrichment(
    session: Any,
    redis_client: Any,
    *,
    green_hours: float = 6,
    yellow_hours: float = 2,
    red_hours: float = 1,
    blacklisted_hours: float = 0.5,
) -> list[int]:
    """Get MMSIs needing enrichment, prioritized by risk tier.

    Each risk tier has its own enrichment interval:
      - blacklisted: every ``blacklisted_hours`` (default 0.5h)
      - red: every ``red_hours`` (default 1h)
      - yellow: every ``yellow_hours`` (default 2h)
      - green: every ``green_hours`` (default 6h)

    Returns vessels sorted by priority: blacklisted first, then red, yellow, green.

    Args:
        session: An async SQLAlchemy session.
        redis_client: An async Redis client.
        green_hours: Hours between enrichments for green vessels.
        yellow_hours: Hours between enrichments for yellow vessels.
        red_hours: Hours between enrichments for red vessels.
        blacklisted_hours: Hours between enrichments for blacklisted vessels.

    Returns:
        List of MMSIs needing enrichment, ordered by risk tier priority.
    """
    from sqlalchemy import text

    result = await session.execute(
        text("SELECT mmsi, risk_tier FROM vessel_profiles ORDER BY mmsi")
    )
    vessels = [(row[0], row[1] or "green") for row in result.fetchall()]

    # Tier-specific intervals in seconds
    intervals = {
        "blacklisted": blacklisted_hours * 3600,
        "red": red_hours * 3600,
        "yellow": yellow_hours * 3600,
        "green": green_hours * 3600,
    }

    # Priority ordering
    tier_priority = {"blacklisted": 0, "red": 1, "yellow": 2, "green": 3}

    now = datetime.now(timezone.utc).timestamp()
    needing: list[tuple[int, str]] = []

    for mmsi, tier in vessels:
        interval = intervals.get(tier, intervals["green"])
        last_enriched = await redis_client.hget(ENRICHED_KEY, str(mmsi))
        if last_enriched is None:
            needing.append((mmsi, tier))
        else:
            try:
                ts = float(last_enriched)
                if ts < now - interval:
                    needing.append((mmsi, tier))
            except (ValueError, TypeError):
                needing.append((mmsi, tier))

    # Sort by tier priority
    needing.sort(key=lambda x: tier_priority.get(x[1], 99))
    return [mmsi for mmsi, _tier in needing]


async def mark_enriched(redis_client: Any, mmsis: list[int]) -> None:
    """Record enrichment timestamps for the given MMSIs in Redis.

    Args:
        redis_client: An async Redis client (or None to skip).
        mmsis: List of MMSIs that were just enriched.
    """
    if redis_client is None:
        return
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
        redis_client: An async Redis client (or None to skip).
        mmsis: List of enriched MMSIs.
        gfw_events_count: Total GFW events fetched in this cycle.
        sar_detections_count: Total SAR detections fetched in this cycle.
    """
    if redis_client is None:
        logger.info(
            "Enrichment complete (no Redis): %d vessels, %d events, %d SAR detections",
            len(mmsis),
            gfw_events_count,
            sar_detections_count,
        )
        return
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


async def update_enrichment_status(
    session: Any,
    mmsi: int,
    *,
    gfw_events_found: bool = False,
    sar_detections_found: bool = False,
    sanctions_checked: bool = False,
    ownership_found: bool = False,
    classification_found: bool = False,
    insurance_found: bool = False,
    tier_at_enrichment: str = "green",
) -> None:
    """Update the enrichment_status JSONB for a vessel after enrichment.

    Writes a structured status object containing last_enriched timestamp,
    enrichment_sources list, data_coverage booleans, and the tier at time
    of enrichment.

    Args:
        session: An async SQLAlchemy session.
        mmsi: Vessel MMSI.
        gfw_events_found: Whether GFW behavioral events were found.
        sar_detections_found: Whether SAR detections were found.
        sanctions_checked: Whether sanctions screening was performed.
        ownership_found: Whether ownership data is available.
        classification_found: Whether classification data is available.
        insurance_found: Whether insurance data is available.
        tier_at_enrichment: The vessel's risk tier at time of enrichment.
    """
    from sqlalchemy import text

    status = {
        "last_enriched": datetime.now(timezone.utc).isoformat(),
        "enrichment_sources": [],
        "data_coverage": {
            "gfw_events": gfw_events_found,
            "sar_detections": sar_detections_found,
            "sanctions": sanctions_checked,
            "ownership": ownership_found,
            "classification": classification_found,
            "insurance": insurance_found,
            "port_state_control": False,  # not yet implemented
        },
        "tier_at_enrichment": tier_at_enrichment,
    }

    # Build sources list based on what was found
    if gfw_events_found:
        status["enrichment_sources"].append("gfw_events")
    if sar_detections_found:
        status["enrichment_sources"].append("gfw_sar")
    if ownership_found:
        status["enrichment_sources"].append("gfw_identity")
    if sanctions_checked:
        status["enrichment_sources"].append("opensanctions")

    await session.execute(
        text(
            "UPDATE vessel_profiles SET enrichment_status = :status, "
            "enriched_at = NOW() WHERE mmsi = :mmsi"
        ),
        {"mmsi": mmsi, "status": json.dumps(status)},
    )


async def _log_enrichment_coverage(session: Any) -> None:
    """Log enrichment data coverage statistics for yellow and red tier vessels.

    Queries the database for coverage percentages of ownership, classification,
    and insurance data across risk tiers.

    Args:
        session: An async SQLAlchemy session.
    """
    from sqlalchemy import text

    result = await session.execute(text("""
        SELECT risk_tier,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE enrichment_status->'data_coverage'->>'ownership' = 'true') as has_ownership,
            COUNT(*) FILTER (WHERE enrichment_status->'data_coverage'->>'classification' = 'true') as has_classification,
            COUNT(*) FILTER (WHERE enrichment_status->'data_coverage'->>'insurance' = 'true') as has_insurance
        FROM vessel_profiles
        WHERE risk_tier IN ('yellow', 'red')
        GROUP BY risk_tier
    """))
    for row in result.fetchall():
        tier, total, has_own, has_class, has_ins = row
        logger.info(
            "Enrichment coverage for %s tier: %d total, %.0f%% ownership, %.0f%% classification, %.0f%% insurance",
            tier,
            total,
            (has_own / total * 100) if total > 0 else 0,
            (has_class / total * 100) if total > 0 else 0,
            (has_ins / total * 100) if total > 0 else 0,
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
      1. GFW SAR (cheap — ~12 API calls for all AOIs)
      2. GFW Events (expensive — 1 call per vessel)
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
        from events_fetcher import fetch_and_store_events
        _events_fn = fetch_and_store_events
    if _sar_fn is None:
        from sar_fetcher import fetch_and_store_sar_detections
        _sar_fn = fetch_and_store_sar_detections
    if _vessel_fn is None:
        from vessel_fetcher import fetch_and_update_vessel_profile
        _vessel_fn = fetch_and_update_vessel_profile

    gfw_events_count = 0
    sar_detections_count = 0

    # Steps 1-3: GFW (events, SAR, vessel identity) — skip if disabled
    from shared.config import settings as _settings
    gfw_enabled = _settings.gfw.enabled

    if not gfw_enabled:
        logger.info("GFW enrichment disabled, skipping steps 1-3")
    else:
        from gfw_client import GFWQuotaExceeded

        gfw_quota_hit = False

        # Step 1: GFW SAR (runs first — only ~12 API calls vs 43k+ for events)
        if aois and not gfw_quota_hit:
            try:
                count = await _sar_fn(gfw_client, session, aois)
                sar_detections_count = count
                await session.commit()
                logger.info("GFW SAR: fetched %d detections", count)
            except GFWQuotaExceeded as e:
                logger.warning("GFW quota exceeded, skipping remaining GFW steps: %s", e)
                gfw_quota_hit = True
            except Exception:
                logger.exception("GFW SAR pipeline failed for batch")
                await session.rollback()

        # Step 2: GFW Events (only for yellow+ risk vessels — STS transfers, encounters, etc.)
        if not gfw_quota_hit:
            from sqlalchemy import text as _text_ev

            ev_result = await session.execute(
                _text_ev("""
                    SELECT mmsi FROM vessel_profiles
                    WHERE mmsi = ANY(:mmsis)
                      AND risk_tier IN ('yellow', 'red', 'blacklisted')
                """),
                {"mmsis": mmsis},
            )
            elevated_mmsis = [row[0] for row in ev_result.fetchall()]

            if elevated_mmsis:
                logger.info(
                    "GFW Events: fetching for %d/%d yellow+ vessels",
                    len(elevated_mmsis), len(mmsis),
                )
                try:
                    count = await _events_fn(gfw_client, session, elevated_mmsis, redis_client=redis_client)
                    gfw_events_count = count
                    await session.commit()
                    logger.info("GFW Events: fetched %d events for %d vessels", count, len(elevated_mmsis))
                except GFWQuotaExceeded as e:
                    logger.warning("GFW quota exceeded, skipping remaining GFW steps: %s", e)
                    gfw_quota_hit = True
                except Exception:
                    logger.exception("GFW Events pipeline failed for batch")
                    await session.rollback()
            else:
                logger.info("GFW Events: no yellow+ vessels, skipping")

        # Step 3: GFW Vessel Identity (only for vessels with stale data)
        if not gfw_quota_hit:
            from datetime import timedelta
            from sqlalchemy import text as _text

            stale_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
            result = await session.execute(
                _text("""
                    SELECT mmsi FROM vessel_profiles
                    WHERE mmsi = ANY(:mmsis)
                      AND (enriched_at IS NULL OR enriched_at < :cutoff)
                """),
                {"mmsis": mmsis, "cutoff": stale_cutoff},
            )
            stale_mmsis = [row[0] for row in result.fetchall()]

            if stale_mmsis:
                logger.info(
                    "GFW Vessel Identity: %d/%d vessels have stale data (>14 days), fetching",
                    len(stale_mmsis), len(mmsis),
                )
                for mmsi in stale_mmsis:
                    try:
                        await _vessel_fn(
                            gfw_client, session, mmsi, redis_client=redis_client
                        )
                    except GFWQuotaExceeded as e:
                        logger.warning("GFW quota exceeded at vessel identity step: %s", e)
                        break
                    except Exception:
                        logger.warning("GFW Vessel Identity failed for MMSI %d", mmsi, exc_info=True)
            else:
                logger.info("GFW Vessel Identity: all %d vessels have fresh data, skipping", len(mmsis))

    # Track vessels that failed critical enrichment — don't mark as enriched
    failed_mmsis: set[int] = set()

    # Step 4: OpenSanctions
    if sanctions_index is not None:
        from sanctions_matcher import match_vessel
        from shared.db.repositories import get_vessel_profile_by_mmsi, update_vessel_sanctions

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
                        await update_vessel_sanctions(
                            session, mmsi, json.dumps(result)
                        )
            except Exception:
                logger.warning("Sanctions check failed for MMSI %d", mmsi, exc_info=True)
                failed_mmsis.add(mmsi)
    else:
        # Sanctions index not loaded — this is a system config issue, not per-vessel.
        # Log loudly so operators fix it, but don't block enrichment for all vessels.
        logger.error(
            "Sanctions index not loaded — %d vessels NOT screened against sanctions. "
            "Check OPENSANCTIONS_DATA_PATH and run download-opensanctions.sh",
            len(mmsis),
        )

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
                        from gisis_mars import merge_gisis_data

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
                    from gisis_mars import merge_mars_data

                    logger.debug("MARS data merged for MMSI %d", mmsi)
            except Exception:
                logger.debug("MARS lookup failed for MMSI %d (non-blocking)", mmsi)

    # Step 7: Update enrichment_status JSONB for each vessel
    from shared.db.repositories import get_vessel_profile_by_mmsi as _get_profile_status

    for mmsi in mmsis:
        if mmsi in failed_mmsis:
            continue
        try:
            profile = await _get_profile_status(session, mmsi)
            tier = (profile or {}).get("risk_tier") or "green"

            await update_enrichment_status(
                session,
                mmsi,
                gfw_events_found=gfw_events_count > 0,
                sar_detections_found=sar_detections_count > 0,
                sanctions_checked=sanctions_index is not None,
                ownership_found=bool((profile or {}).get("ownership_data")),
                classification_found=bool((profile or {}).get("classification_data")),
                insurance_found=bool((profile or {}).get("insurance_data")),
                tier_at_enrichment=tier,
            )
        except Exception:
            logger.warning(
                "Failed to update enrichment_status for MMSI %d", mmsi, exc_info=True
            )

    return {
        "gfw_events_count": gfw_events_count,
        "sar_detections_count": sar_detections_count,
        "failed_mmsis": failed_mmsis,
    }


async def should_trigger_enrichment(
    redis_client: Any,
    mmsi: int,
    new_tier: str,
    debounce_hours: float = DEFAULT_DEBOUNCE_HOURS,
) -> bool:
    """Check if a tier-change should trigger immediate enrichment.

    Returns True if the new tier is in TRIGGER_TIERS and the vessel has not
    been triggered within the debounce window.

    Args:
        redis_client: An async Redis client.
        mmsi: Vessel MMSI.
        new_tier: The tier the vessel transitioned to.
        debounce_hours: Hours to wait before allowing another triggered enrichment.

    Returns:
        True if enrichment should be triggered.
    """
    if new_tier not in TRIGGER_TIERS:
        return False

    last_triggered = await redis_client.hget(TRIGGER_KEY, str(mmsi))
    if last_triggered:
        try:
            ts = float(last_triggered)
        except (ValueError, TypeError):
            return True
        cutoff = datetime.now(timezone.utc).timestamp() - (debounce_hours * 3600)
        if ts > cutoff:
            return False  # debounce: too recent

    return True


async def mark_triggered(redis_client: Any, mmsi: int) -> None:
    """Record that tier-change enrichment was triggered for this MMSI.

    Args:
        redis_client: An async Redis client.
        mmsi: Vessel MMSI.
    """
    now = str(datetime.now(timezone.utc).timestamp())
    await redis_client.hset(TRIGGER_KEY, str(mmsi), now)


async def enrich_single_vessel(
    mmsi: int,
    *,
    gfw_client: Any,
    session: Any,
    redis_client: Any,
    sanctions_index: Any = None,
    gisis_client: Any = None,
    mars_client: Any = None,
    aois: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Enrich a single vessel immediately (triggered by tier change).

    Runs the full enrichment pipeline for the given MMSI. On success, marks
    the vessel as enriched and records the trigger timestamp.

    Args:
        mmsi: Vessel MMSI to enrich.
        gfw_client: An initialized GFWClient instance.
        session: An async SQLAlchemy session.
        redis_client: An async Redis client.
        sanctions_index: Loaded SanctionsIndex (or None).
        gisis_client: GISISClient instance (or None).
        mars_client: MARSClient instance (or None).
        aois: List of AOI dicts for SAR fetching.

    Returns:
        Dict with enrichment result from enrich_batch.
    """
    result = await enrich_batch(
        [mmsi],
        gfw_client=gfw_client,
        session=session,
        redis_client=redis_client,
        sanctions_index=sanctions_index,
        gisis_client=gisis_client,
        mars_client=mars_client,
        aois=aois,
    )
    failed = result.get("failed_mmsis", set())
    if mmsi not in failed:
        await mark_enriched(redis_client, [mmsi])
        await mark_triggered(redis_client, mmsi)
        await publish_enrichment_complete(
            redis_client,
            [mmsi],
            result["gfw_events_count"],
            result["sar_detections_count"],
        )
    return result


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
    # Load adaptive frequency config from settings
    freq = settings.enrichment.frequency
    green_hours = freq.green_hours
    yellow_hours = freq.yellow_hours
    red_hours = freq.red_hours
    blacklisted_hours = freq.blacklisted_hours

    # Get vessels needing enrichment, prioritized by risk tier
    unenriched = await get_vessels_needing_enrichment(
        session,
        redis_client,
        green_hours=green_hours,
        yellow_hours=yellow_hours,
        red_hours=red_hours,
        blacklisted_hours=blacklisted_hours,
    )
    logger.info("Found %d vessels needing enrichment (adaptive frequency)", len(unenriched))

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
            # Only mark vessels as enriched if critical steps succeeded
            failed = result.get("failed_mmsis", set())
            succeeded = [m for m in batch if m not in failed]
            all_enriched.extend(succeeded)
            if failed:
                logger.warning(
                    "%d vessels had critical enrichment failures, will retry: %s",
                    len(failed),
                    list(failed)[:10],
                )
            # Commit after each batch so data is visible immediately
            await session.commit()
        except Exception:
            logger.exception("Batch %d failed", i // batch_size + 1)
            try:
                await session.rollback()
            except Exception:
                pass

    # Mark all enriched vessels
    if all_enriched:
        await mark_enriched(redis_client, all_enriched)
        await publish_enrichment_complete(
            redis_client, all_enriched, total_events, total_sar
        )
        # Log enrichment coverage statistics
        try:
            await _log_enrichment_coverage(session)
        except Exception:
            logger.warning("Failed to log enrichment coverage statistics", exc_info=True)

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
            # Reset GFW client stats before each cycle
            if hasattr(gfw_client, "reset_stats"):
                gfw_client.reset_stats()

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
            elapsed_ms = elapsed * 1000

            # Build cycle summary with API call stats
            summary_extra: dict[str, Any] = {
                "total_duration_ms": round(elapsed_ms, 1),
            }
            if hasattr(gfw_client, "get_stats"):
                api_stats = gfw_client.get_stats()
                summary_extra.update(api_stats)

            logger.info(
                "Enrichment cycle complete in %.1fs: %d vessels, %d events, %d SAR"
                " | API calls: %d, avg %.0fms, retries: %d"
                " | quota: %d/%d daily, %d/%d monthly",
                elapsed,
                result["total_vessels"],
                result["gfw_events_count"],
                result["sar_detections_count"],
                summary_extra.get("api_calls_made", 0),
                summary_extra.get("avg_call_duration_ms", 0),
                summary_extra.get("rate_limit_retries", 0),
                summary_extra.get("daily_calls", 0),
                summary_extra.get("daily_limit", 0),
                summary_extra.get("monthly_calls", 0),
                summary_extra.get("monthly_limit", 0),
                extra=summary_extra,
            )
        except Exception:
            logger.exception("Enrichment cycle failed")

        logger.info("Sleeping %ds until next cycle", interval_seconds)
        await asyncio.sleep(interval_seconds)
