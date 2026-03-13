"""Fetch vessel identity data from the GFW Vessel API.

Queries the Vessel API by MMSI or IMO, caches responses in Redis,
and updates vessel_profiles with ownership data.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

sys.path.insert(0, "/app")

from shared.config import settings

logger = logging.getLogger("enrichment.vessel_fetcher")

# Vessel API endpoints
VESSEL_SEARCH_ENDPOINT = "/v3/vessels/search"

# GFW vessel dataset
VESSEL_DATASET = "public-global-vessel-identity:latest"

# Redis cache key prefix
CACHE_KEY_PREFIX = "heimdal:gfw_vessel:"


def _cache_key(identifier: str, id_type: str = "mmsi") -> str:
    """Build a Redis cache key for vessel identity data."""
    return f"{CACHE_KEY_PREFIX}{id_type}:{identifier}"


def parse_vessel_identity(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse a GFW vessel record into ownership/identity fields.

    Maps GFW Vessel API fields to our vessel_profiles columns.
    Returns a dict suitable for upsert_vessel_profile.
    """
    # GFW returns vessel data with nested structures
    # The selfReportedInfo and registryInfo contain identity data
    self_reported = {}
    registry_info = {}

    if isinstance(raw.get("selfReportedInfo"), list) and raw["selfReportedInfo"]:
        self_reported = raw["selfReportedInfo"][0]
    elif isinstance(raw.get("selfReportedInfo"), dict):
        self_reported = raw["selfReportedInfo"]

    if isinstance(raw.get("registryInfo"), list) and raw["registryInfo"]:
        registry_info = raw["registryInfo"][0]
    elif isinstance(raw.get("registryInfo"), dict):
        registry_info = raw["registryInfo"]

    # Combined info (also check top-level fields)
    combined = raw.get("combinedSourcesInfo", [])
    combined_info = combined[0] if isinstance(combined, list) and combined else {}

    # Extract MMSI from ssvid (Ship Security and Vulnerability Identification)
    ssvid = self_reported.get("ssvid") or raw.get("ssvid")
    mmsi = None
    if ssvid:
        try:
            mmsi = int(ssvid)
        except (ValueError, TypeError):
            pass

    # Extract IMO
    imo = registry_info.get("imoNumber") or raw.get("imo")
    if imo:
        try:
            imo = int(str(imo).replace("IMO", "").strip())
        except (ValueError, TypeError):
            imo = None

    # Prefer registry info, fall back to self-reported, then combined
    ship_name = (
        registry_info.get("shipname")
        or self_reported.get("shipname")
        or combined_info.get("shipname")
        or raw.get("shipname")
    )

    flag = (
        registry_info.get("flag")
        or self_reported.get("flag")
        or combined_info.get("flag")
        or raw.get("flag")
    )

    ship_type_text = (
        registry_info.get("shiptypeText")
        or self_reported.get("shiptypeText")
        or combined_info.get("shiptypeText")
        or raw.get("shiptypeText")
    )

    # Numeric fields
    gross_tonnage = _safe_int(
        registry_info.get("grossTonnage")
        or combined_info.get("grossTonnage")
        or raw.get("grossTonnage")
    )

    dwt = _safe_int(
        registry_info.get("deadweight")
        or combined_info.get("deadweight")
        or raw.get("deadweight")
    )

    build_year = _safe_int(
        registry_info.get("builtYear")
        or combined_info.get("builtYear")
        or raw.get("builtYear")
    )

    length = _safe_float(
        registry_info.get("lengthOverallLOA")
        or self_reported.get("length")
        or combined_info.get("lengthOverallLOA")
        or raw.get("length")
    )

    width = _safe_float(
        registry_info.get("beam")
        or self_reported.get("width")
        or combined_info.get("beam")
        or raw.get("beam")
        or raw.get("width")
    )

    # Ownership fields
    registered_owner = (
        registry_info.get("owner")
        or combined_info.get("owner")
        or raw.get("owner")
    )

    operator = (
        registry_info.get("operator")
        or combined_info.get("operator")
        or raw.get("operator")
    )

    call_sign = (
        registry_info.get("callsign")
        or self_reported.get("callsign")
        or combined_info.get("callsign")
        or raw.get("callsign")
    )

    result = {
        "mmsi": mmsi,
        "imo": imo,
        "ship_name": ship_name,
        "ship_type_text": ship_type_text,
        "flag_country": flag,
        "call_sign": call_sign,
        "length": length,
        "width": width,
        "gross_tonnage": gross_tonnage,
        "dwt": dwt,
        "build_year": build_year,
        "registered_owner": registered_owner,
        "operator": operator,
    }

    # Remove None values to let COALESCE in the upsert preserve existing data
    return {k: v for k, v in result.items() if v is not None}


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def _get_cached(redis_client: Any, key: str) -> dict[str, Any] | None:
    """Get cached vessel data from Redis."""
    if redis_client is None:
        return None
    try:
        cached = await redis_client.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.debug("Redis cache miss or error for key %s", key)
    return None


async def _set_cached(
    redis_client: Any,
    key: str,
    data: dict[str, Any],
    ttl_hours: int | None = None,
) -> None:
    """Cache vessel data in Redis with TTL."""
    if redis_client is None:
        return
    ttl = (ttl_hours or settings.gfw.vessel_cache_ttl_hours) * 3600
    try:
        await redis_client.set(key, json.dumps(data), ex=ttl)
    except Exception:
        logger.debug("Failed to cache vessel data for key %s", key)


async def resolve_gfw_vessel_id(
    client: Any,
    mmsi: int,
    *,
    redis_client: Any = None,
) -> str | None:
    """Resolve an MMSI to a GFW internal vessel ID.

    The GFW Events API requires their internal vessel IDs (UUIDs),
    not raw MMSIs.  This function searches the GFW Vessel API by MMSI
    and returns the ``id`` field from ``combinedSourcesInfo``.

    Results are cached in Redis under ``heimdal:gfw_vessel_id:<mmsi>``.

    Returns:
        The GFW vessel ID string, or None if not found.
    """
    cache_key = f"heimdal:gfw_vessel_id:{mmsi}"

    # Check cache
    if redis_client is not None:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception:
            pass

    # Search GFW
    try:
        data = await client.get(
            VESSEL_SEARCH_ENDPOINT,
            params={
                "query": str(mmsi),
                "datasets[0]": VESSEL_DATASET,
                "limit": 1,
            },
        )
    except Exception:
        logger.debug("Failed to resolve GFW vessel ID for MMSI %d", mmsi)
        return None

    entries = data.get("entries", [])
    if not entries:
        return None

    # Extract GFW vessel ID from combinedSourcesInfo
    combined = entries[0].get("combinedSourcesInfo", [])
    vessel_id = None
    if combined and isinstance(combined, list):
        vessel_id = combined[0].get("vesselId")

    # Fallback: try the top-level id field
    if not vessel_id:
        vessel_id = entries[0].get("id")

    if vessel_id and redis_client is not None:
        try:
            ttl = settings.gfw.vessel_cache_ttl_hours * 3600
            await redis_client.set(cache_key, vessel_id, ex=ttl)
        except Exception:
            pass

    return vessel_id


async def fetch_vessel_by_mmsi(
    client: Any,
    mmsi: int,
    *,
    redis_client: Any = None,
    cache_ttl_hours: int | None = None,
) -> dict[str, Any] | None:
    """Fetch vessel identity data by MMSI.

    Checks Redis cache first, then queries the GFW Vessel API.

    Args:
        client: An initialized GFWClient instance.
        mmsi: The vessel MMSI to search for.
        redis_client: Optional redis.asyncio client for caching.
        cache_ttl_hours: Override for settings.gfw.vessel_cache_ttl_hours.

    Returns:
        Parsed vessel identity dict, or None if not found.
    """
    cache_key = _cache_key(str(mmsi), "mmsi")

    # Check cache
    cached = await _get_cached(redis_client, cache_key)
    if cached is not None:
        logger.debug("Cache hit for MMSI %d", mmsi)
        return cached

    # Query GFW API
    logger.debug("Querying GFW Vessel API for MMSI %d", mmsi)
    try:
        data = await client.get(
            VESSEL_SEARCH_ENDPOINT,
            params={
                "query": str(mmsi),
                "datasets[0]": VESSEL_DATASET,
                "limit": 1,
            },
        )
    except Exception:
        logger.exception("Error fetching vessel data for MMSI %d", mmsi)
        return None

    # Extract the best match
    entries = data.get("entries", [])
    if not entries:
        logger.info("No vessel identity found for MMSI %d", mmsi)
        return None

    parsed = parse_vessel_identity(entries[0])
    # Ensure MMSI is set
    if "mmsi" not in parsed:
        parsed["mmsi"] = mmsi

    # Cache the result
    await _set_cached(redis_client, cache_key, parsed, cache_ttl_hours)

    return parsed


async def fetch_vessel_by_imo(
    client: Any,
    imo: int,
    *,
    redis_client: Any = None,
    cache_ttl_hours: int | None = None,
) -> dict[str, Any] | None:
    """Fetch vessel identity data by IMO number.

    Checks Redis cache first, then queries the GFW Vessel API.

    Args:
        client: An initialized GFWClient instance.
        imo: The vessel IMO number to search for.
        redis_client: Optional redis.asyncio client for caching.
        cache_ttl_hours: Override for settings.gfw.vessel_cache_ttl_hours.

    Returns:
        Parsed vessel identity dict, or None if not found.
    """
    cache_key = _cache_key(str(imo), "imo")

    # Check cache
    cached = await _get_cached(redis_client, cache_key)
    if cached is not None:
        logger.debug("Cache hit for IMO %d", imo)
        return cached

    # Query GFW API
    logger.debug("Querying GFW Vessel API for IMO %d", imo)
    try:
        data = await client.get(
            VESSEL_SEARCH_ENDPOINT,
            params={
                "query": str(imo),
                "datasets[0]": VESSEL_DATASET,
                "limit": 1,
            },
        )
    except Exception:
        logger.exception("Error fetching vessel data for IMO %d", imo)
        return None

    entries = data.get("entries", [])
    if not entries:
        logger.info("No vessel identity found for IMO %d", imo)
        return None

    parsed = parse_vessel_identity(entries[0])

    # Cache the result
    await _set_cached(redis_client, cache_key, parsed, cache_ttl_hours)

    return parsed


async def fetch_and_update_vessel_profile(
    client: Any,
    session: Any,
    mmsi: int,
    *,
    imo: int | None = None,
    redis_client: Any = None,
    cache_ttl_hours: int | None = None,
    _upsert_fn: Any = None,
) -> dict[str, Any] | None:
    """Fetch vessel identity and update the vessel_profiles table.

    Tries MMSI first, then IMO if provided and MMSI returns no results.

    Args:
        client: An initialized GFWClient instance.
        session: An async SQLAlchemy session.
        mmsi: The vessel MMSI.
        imo: Optional IMO number for fallback search.
        redis_client: Optional redis.asyncio client for caching.
        cache_ttl_hours: Override for settings.gfw.vessel_cache_ttl_hours.
        _upsert_fn: Override for the upsert function (for testing).

    Returns:
        The parsed vessel identity dict, or None if not found.
    """
    if _upsert_fn is None:
        from shared.db.repositories import upsert_vessel_profile
        _upsert_fn = upsert_vessel_profile

    # Try by MMSI first
    identity = await fetch_vessel_by_mmsi(
        client, mmsi, redis_client=redis_client, cache_ttl_hours=cache_ttl_hours
    )

    # Fallback to IMO if no result
    if identity is None and imo:
        identity = await fetch_vessel_by_imo(
            client, imo, redis_client=redis_client, cache_ttl_hours=cache_ttl_hours
        )
        if identity is not None:
            # Ensure MMSI is set for the upsert
            identity["mmsi"] = mmsi

    if identity is None:
        return None

    # Build the upsert data — fill missing fields with None for COALESCE
    profile_data = {
        "mmsi": mmsi,
        "imo": identity.get("imo"),
        "ship_name": identity.get("ship_name"),
        "ship_type": None,
        "ship_type_text": identity.get("ship_type_text"),
        "flag_country": identity.get("flag_country"),
        "call_sign": identity.get("call_sign"),
        "length": identity.get("length"),
        "width": identity.get("width"),
        "draught": None,
        "destination": None,
        "eta": None,
        "last_position_time": None,
        "last_lat": None,
        "last_lon": None,
        "risk_score": None,
        "risk_tier": None,
        "sanctions_status": None,
        "pi_tier": None,
        "pi_details": None,
        "owner": identity.get("registered_owner"),
        "operator": identity.get("operator"),
        "insurer": None,
        "class_society": None,
        "build_year": identity.get("build_year"),
        "dwt": identity.get("dwt"),
        "gross_tonnage": identity.get("gross_tonnage"),
        "group_owner": None,
        "registered_owner": identity.get("registered_owner"),
        "technical_manager": None,
    }

    await _upsert_fn(session, profile_data)
    logger.info("Updated vessel profile for MMSI %d with GFW identity data", mmsi)

    return identity
