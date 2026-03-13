"""Fetch vessel identity data from the GFW Vessel API.

Queries the Vessel API by MMSI or IMO, caches responses in Redis,
and updates vessel_profiles with ownership data.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
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


# IACS (International Association of Classification Societies) members
IACS_MEMBERS = {"ABS", "BV", "CCS", "CRS", "DNV", "IRS", "KR", "LR", "NK", "PRS", "RINA", "RS"}


def build_classification_data(
    raw_identity: dict[str, Any],
    existing_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Extract classification society data from a GFW vessel identity response.

    Looks for classificationSociety in registryInfo, combinedSourcesInfo,
    and top-level fields. Returns a classification_data JSONB dict or None.

    If the classification society has changed compared to existing_profile,
    a history entry is appended to class_change_history.
    """
    # Extract nested structures
    registry_info = _get_first_entry(raw_identity, "registryInfo")
    combined_info = _get_first_entry(raw_identity, "combinedSourcesInfo")

    # Look for classification society in multiple locations
    society_name = (
        registry_info.get("classificationSociety")
        or combined_info.get("classificationSociety")
        or raw_identity.get("classificationSociety")
    )

    if not society_name:
        return None

    # Determine society code (use uppercase abbreviation if recognizable)
    society_code = _derive_society_code(society_name)
    is_iacs = society_code in IACS_MEMBERS if society_code else False

    now_iso = datetime.now(timezone.utc).isoformat()

    result: dict[str, Any] = {
        "society_name": society_name,
        "society_code": society_code,
        "is_iacs": is_iacs,
        "class_status": "active",
        "last_survey_date": None,
        "class_change_history": [],
        "last_updated": now_iso,
    }

    # Detect classification change and record history
    if existing_profile and existing_profile.get("classification_data"):
        existing_class = existing_profile["classification_data"]
        if isinstance(existing_class, str):
            import json as _json
            try:
                existing_class = _json.loads(existing_class)
            except (ValueError, TypeError):
                existing_class = {}

        old_society = existing_class.get("society_name")
        if old_society and old_society != society_name:
            history = list(existing_class.get("class_change_history", []))
            history.append({
                "date": now_iso,
                "change": "classification_changed",
                "from": old_society,
                "to": society_name,
            })
            result["class_change_history"] = history

    return result


def build_insurance_data(
    raw_identity: dict[str, Any],
    existing_profile: dict[str, Any] | None = None,
    manual_enrichments: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build P&I insurance data from GFW response and/or manual enrichment.

    GFW typically does not provide P&I data directly, so manual enrichment
    is the primary source. Returns an insurance_data JSONB dict or None.
    """
    # IG P&I club members
    ig_members = {
        "american", "britannia", "gard", "japan", "london", "north",
        "shipowners", "skuld", "standard", "steamship", "swedish", "uk",
        "west of england",
    }

    provider = None
    pi_tier = None
    coverage_status = None
    expiry_date = None

    # Check manual enrichments for P&I data (newest first)
    if manual_enrichments:
        for enrichment in manual_enrichments:
            if enrichment.get("pi_tier") or enrichment.get("pi_details"):
                pi_tier = enrichment.get("pi_tier")
                pi_details = enrichment.get("pi_details")
                if pi_details:
                    provider = pi_details
                break

    if not provider and not pi_tier:
        return None

    # Determine IG membership
    is_ig_member = False
    if provider:
        provider_lower = provider.lower()
        is_ig_member = any(ig in provider_lower for ig in ig_members)

    if pi_tier:
        coverage_status = pi_tier
    else:
        coverage_status = "confirmed" if provider else "unknown"

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "provider": provider,
        "is_ig_member": is_ig_member,
        "coverage_status": coverage_status,
        "expiry_date": expiry_date,
        "last_updated": now_iso,
    }


def _get_first_entry(raw: dict[str, Any], key: str) -> dict[str, Any]:
    """Get the first entry from a list-or-dict field in GFW response."""
    value = raw.get(key)
    if isinstance(value, list) and value:
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


def _derive_society_code(society_name: str) -> str | None:
    """Derive a classification society code from its name.

    Maps known full names to their IACS abbreviation, or returns
    the name uppercased if it's already an abbreviation (<=5 chars).
    """
    name_to_code = {
        "american bureau of shipping": "ABS",
        "bureau veritas": "BV",
        "china classification society": "CCS",
        "croatian register of shipping": "CRS",
        "dnv": "DNV",
        "dnv gl": "DNV",
        "det norske veritas": "DNV",
        "indian register of shipping": "IRS",
        "korean register": "KR",
        "korean register of shipping": "KR",
        "lloyd's register": "LR",
        "lloyds register": "LR",
        "nippon kaiji kyokai": "NK",
        "classnk": "NK",
        "polish register of shipping": "PRS",
        "rina": "RINA",
        "registro italiano navale": "RINA",
        "russian maritime register of shipping": "RS",
        "russian register": "RS",
        "russian maritime register": "RS",
    }

    lower = society_name.strip().lower()
    if lower in name_to_code:
        return name_to_code[lower]

    # If it's a short abbreviation, assume it's already a code
    stripped = society_name.strip().upper()
    if len(stripped) <= 5:
        return stripped

    return stripped


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
    _get_profile_fn: Any = None,
    _get_enrichments_fn: Any = None,
    _raw_entry: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fetch vessel identity and update the vessel_profiles table.

    Tries MMSI first, then IMO if provided and MMSI returns no results.
    Also extracts classification and insurance data from the raw GFW
    response and stores them in the new JSONB columns.

    Args:
        client: An initialized GFWClient instance.
        session: An async SQLAlchemy session.
        mmsi: The vessel MMSI.
        imo: Optional IMO number for fallback search.
        redis_client: Optional redis.asyncio client for caching.
        cache_ttl_hours: Override for settings.gfw.vessel_cache_ttl_hours.
        _upsert_fn: Override for the upsert function (for testing).
        _get_profile_fn: Override for get_vessel_profile_by_mmsi (for testing).
        _get_enrichments_fn: Override for get_manual_enrichment_by_mmsi (for testing).
        _raw_entry: Override for the raw GFW API response entry (for testing).

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

    # Fetch existing profile for change detection
    existing_profile = None
    if _get_profile_fn is None:
        from shared.db.repositories import get_vessel_profile_by_mmsi
        _get_profile_fn = get_vessel_profile_by_mmsi
    try:
        existing_profile = await _get_profile_fn(session, mmsi)
    except Exception:
        logger.debug("Could not fetch existing profile for MMSI %d", mmsi)

    # Fetch manual enrichments for insurance fallback
    manual_enrichments = None
    if _get_enrichments_fn is None:
        from shared.db.repositories import get_manual_enrichment_by_mmsi
        _get_enrichments_fn = get_manual_enrichment_by_mmsi
    try:
        manual_enrichments = await _get_enrichments_fn(session, mmsi)
    except Exception:
        logger.debug("Could not fetch manual enrichments for MMSI %d", mmsi)

    # Build the raw GFW entry for classification/insurance extraction
    # We need the original GFW response entry, not parsed identity
    raw_entry = _raw_entry or {}

    # Build classification and insurance data
    classification_data = build_classification_data(raw_entry, existing_profile)
    insurance_data = build_insurance_data(
        raw_entry, existing_profile, manual_enrichments
    )

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
        "classification_data": json.dumps(classification_data) if classification_data else None,
        "insurance_data": json.dumps(insurance_data) if insurance_data else None,
        "enrichment_status": None,
        "enriched_at": None,
    }

    await _upsert_fn(session, profile_data)
    logger.info("Updated vessel profile for MMSI %d with GFW identity data", mmsi)

    return identity
